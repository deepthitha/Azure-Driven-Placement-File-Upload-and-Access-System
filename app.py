import streamlit as st
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from azure.core.exceptions import ResourceNotFoundError  # Add this import
import pymysql
import pandas as pd
import time
import os
import zipfile
from io import BytesIO

# Initialize connection to Azure Blob Storage
connect_str = ""
blob_service_client = BlobServiceClient.from_connection_string(connect_str)
container_name = "placements-2024"
archive_container = "archive"
reject_container = "reject"

# Define user roles
USER_ROLE_UPLOADER = "Uploader"
USER_ROLE_ACCESSOR = "Accessor"
USER_ROLE_MANAGER = "Manager"
USER_ROLE_ADMIN = "Admin"

def get_db_connection():
    return pymysql.connect(
        host="",
        user="root",
        password="",
        database="user_credentials",
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def load_departments_from_db():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT name FROM departments"
            cursor.execute(sql)
            departments = [row['name'] for row in cursor.fetchall()]
            return departments
    finally:
        connection.close()

def get_rejected_files(roll_number):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT file_name, reason FROM rejection_logs WHERE roll_number=%s AND resolved=0"
            cursor.execute(sql, (roll_number,))
            rejected_files = cursor.fetchall()
            return rejected_files
    finally:
        connection.close()

def get_user_details(email, password):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT role, name, roll_number FROM users WHERE email=%s AND password=%s"
            cursor.execute(sql, (email, password))
            result = cursor.fetchone()
            if result:
                return result['role'], result['name'], result['roll_number']
            else:
                return None, None, None
    finally:
        connection.close()

def add_user(email, password, role, name, roll_number):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO users (email, password, role, name, roll_number) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(sql, (email, password, role, name, roll_number))
        connection.commit()
    finally:
        connection.close()

def check_file_exists(container_client, blob_name):
    try:
        container_client.get_blob_client(blob_name).get_blob_properties()
        return True
    except:
        return False

def upload_file(container_client, file, blob_name):
    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(file, overwrite=True)

def list_files(container_client, prefix):
    blobs = container_client.list_blobs(name_starts_with=prefix)
    return [blob.name for blob in blobs]

def list_roll_numbers(container_client, path_prefix):
    roll_numbers = set()
    blobs = container_client.list_blobs(name_starts_with=path_prefix)
    for blob in blobs:
        parts = blob.name.split('/')
        if len(parts) > 2:
            roll_numbers.add(parts[2])
    return sorted(list(roll_numbers))

def move_blob(source_client, dest_client, blob_name, new_blob_name):
    source_blob = source_client.get_blob_client(blob_name)
    dest_blob = dest_client.get_blob_client(new_blob_name)
    copy = dest_blob.start_copy_from_url(source_blob.url)

    while True:
        props = dest_blob.get_blob_properties()
        if props.copy.status == 'success':
            source_blob.delete_blob()
            break
        time.sleep(1)

def log_rejection(roll_number, file_name, reason):
    try:
        df = pd.read_excel("rejections_log.xlsx")
    except FileNotFoundError:
        df = pd.DataFrame(columns=["Roll Number", "File Name", "Reason"])
    new_entry = pd.DataFrame([[roll_number, file_name, reason]], columns=["Roll Number", "File Name", "Reason"])
    df = pd.concat([df, new_entry], ignore_index=True)
    df.to_excel("rejections_log.xlsx", index=False)

def download_blob_as_bytes(container_client, blob_name):
    blob_client = container_client.get_blob_client(blob_name)
    stream = BytesIO()
    blob_client.download_blob().readinto(stream)
    stream.seek(0)
    return stream

def create_zip(files):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zip_file:
        for file_name, file_stream in files:
            zip_file.writestr(file_name, file_stream.read())
    zip_buffer.seek(0)
    return zip_buffer

def display_timer(duration):
    timer_placeholder = st.empty()
    for i in range(duration, 0, -1):
        timer_placeholder.write(f"Please wait... {i} seconds remaining")
        time.sleep(1)
    timer_placeholder.empty()

# Initialize session state attributes
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'user_role' not in st.session_state:
    st.session_state.user_role = None
if 'user_name' not in st.session_state:
    st.session_state.user_name = None
if 'roll_number' not in st.session_state:
    st.session_state.roll_number = None
if 'rejected_files' not in st.session_state:
    st.session_state.rejected_files = []

def login_page():
    st.title("LOGIN")

    username = st.text_input("USERNAME")
    password = st.text_input("PASSWORD", type="password")
    
    if st.button("LOGIN"):
        user_role, user_name, roll_number = get_user_details(username, password)

        if user_role:
            st.success("Logged in successfully!")
            st.session_state.user_email = username
            st.session_state.user_role = user_role
            st.session_state.user_name = user_name
            st.session_state.roll_number = roll_number
            return True

        st.error("Incorrect username or password. Please try again.")
    
    return False

def create_directory_placeholder(container_client, directory_path):
    blob_client = container_client.get_blob_client(f"{directory_path}/")
    blob_client.upload_blob(b"", overwrite=True)

def load_directories(container_client, department):
    directories = set()
    blobs = container_client.list_blobs(name_starts_with=department)
    for blob in blobs:
        parts = blob.name.split('/')
        if len(parts) > 1:
            directories.add(parts[1])
    return sorted(list(directories))

def log_rejection(department, directory, roll_number, file_name, reason):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO rejection_logs (department, directory, roll_number, file_name, reason, resolved) VALUES (%s, %s, %s, %s, %s, 0)"
            cursor.execute(sql, (department, directory, roll_number, file_name, reason))
        connection.commit()
    finally:
        connection.close()

def admin_page():
    st.title("Admin Page")
    
    # Create a dropdown menu to switch between different functionalities
    option = st.selectbox("Select an option", ["Create New Directory", "Add New User", "Add Department"])

    if option == "Create New Directory":
        st.header("Create New Directory")
        department_list = load_departments_from_db()
        department = st.selectbox("Select Department", department_list, index=0)

        new_directory = st.text_input("Enter New Directory Name")

        if st.button("Create Directory", key="create_directory"):
            if new_directory:
                # Save the new directory as a placeholder blob
                container_client = blob_service_client.get_container_client(container_name)
                directory_path = f"{department}/{new_directory}"
                create_directory_placeholder(container_client, directory_path)
                st.success(f"New directory '{new_directory}' created successfully under {department} department.")
            else:
                st.error("Please enter a directory name.")

    elif option == "Add New User":
        st.header("Add New User")

        new_user_email = st.text_input("New User Email", key="new_user_email")
        new_user_password = st.text_input("New User Password", type="password", key="new_user_password")
        new_user_role = st.selectbox("Select Role", [USER_ROLE_UPLOADER, USER_ROLE_ACCESSOR, USER_ROLE_MANAGER, USER_ROLE_ADMIN], key="new_user_role")
        new_user_name = st.text_input("New User Name", key="new_user_name")
        new_user_roll_number = st.text_input("New User Roll Number", key="new_user_roll_number")

        if st.button("Add User", key="add_user"):
            if new_user_email and new_user_password and new_user_role and new_user_name and new_user_roll_number:
                add_user(new_user_email, new_user_password, new_user_role, new_user_name, new_user_roll_number)
                st.success(f"User '{new_user_email}' added successfully with role '{new_user_role}'.")
            else:
                st.error("Please fill out all fields to add a new user.")

    elif option == "Add Department":
        st.header("Add Department")
        new_department = st.text_input("Enter New Department Name")
    elif option == "Add Department":
        st.header("Add Department")
        new_department = st.text_input("Enter New Department Name")

        if st.button("Add Department", key="add_department"):
            if new_department:
                connection = get_db_connection()
                try:
                    with connection.cursor() as cursor:
                        sql = "INSERT INTO departments (name) VALUES (%s)"
                        cursor.execute(sql, (new_department,))
                    connection.commit()
                    st.success(f"Department '{new_department}' added successfully.")
                finally:
                    connection.close()
        else:
                st.error("Please enter a department name.")

def file_manager_page():
    st.title("File Manager Page")

    department_list = load_departments_from_db()
    department = st.selectbox("Select Department", department_list)

    container_client = blob_service_client.get_container_client(archive_container)
    directories = load_directories(container_client, department)

    if not directories:
        st.write("No directories found. Please contact admin to create directories.")
        return

    directory = st.selectbox("Select Directory", directories)
    roll_numbers = list_roll_numbers(container_client, f"{department}/{directory}")

    if roll_numbers:
        roll_number = st.selectbox("Select Roll Number", roll_numbers)
    else:
        st.write("No roll numbers found.")
        return

    blob_prefix = f"{department}/{directory}/{roll_number}/"
    blobs = list_files(container_client, blob_prefix)

    if blobs:
        selected_files = st.multiselect("Select Files to Move", blobs)

        if selected_files:
            action = st.radio("Action", ["Move to Archive", "Reject File"])

            if action == "Reject File":
                rejection_reason = st.text_input("Reason for Rejection")

            if st.button("Execute"):
                for blob_name in selected_files:
                    file_name = os.path.basename(blob_name)
                    if action == "Move to Archive":
                        display_timer(3)  # Display a 3-second timer
                        move_blob(blob_service_client.get_container_client(container_name),
                                  blob_service_client.get_container_client(archive_container),
                                  blob_name, f"{department}/{directory}/{roll_number}/{file_name}")
                        st.success(f"File {file_name} moved to archive successfully.")
                    elif action == "Reject File":
                        if rejection_reason:
                            display_timer(3)  # Display a 3-second timer
                            move_blob(blob_service_client.get_container_client(container_name),
                                      blob_service_client.get_container_client(reject_container),
                                      blob_name, f"{department}/{directory}/{roll_number}/{file_name}")
                            log_rejection(roll_number, file_name, rejection_reason)
                            st.success(f"File {file_name} rejected successfully.")
                        else:
                            st.warning("Please provide a reason for rejection.")
    else:
        st.write("No files found.")

def view_and_download_files_page():
    st.title("View and Download Files Page")

    # Step 1: Select Department
    department_list = load_departments_from_db()
    department = st.selectbox("Select Department", department_list)

    # Step 2: Load Directories based on selected Department
    container_client = blob_service_client.get_container_client(archive_container)
    directories = load_directories(container_client, department)

    if not directories:
        st.write("No directories found. Please contact admin to create directories.")
        return

    # Step 3: Select Directory
    directory = st.selectbox("Select Directory", directories)

    # Step 4: Load Roll Numbers based on selected Directory
    roll_numbers = list_roll_numbers(container_client, f"{department}/{directory}")

    if not roll_numbers:
        st.write("No roll numbers found.")
        return

    # Step 5: Select Roll Numbers
    selected_roll_numbers = st.multiselect("Select Roll Number(s)", roll_numbers)

    all_files = []
    roll_number_file_map = {}

    if selected_roll_numbers:
        for roll_number in selected_roll_numbers:
            blob_prefix = f"{department}/{directory}/{roll_number}/"
            file_list = list_files(container_client, blob_prefix)
            if file_list:
                file_names = [os.path.basename(file) for file in file_list]
                roll_number_file_map[roll_number] = file_names
                all_files.extend(file_list)

    if all_files:
        st.write("Files for selected roll number(s):")

        # Add a checkbox for "Select All"
        select_all = st.checkbox("Select All", key="select_all")
        
        files_to_download = []
        individual_checks = {}

        if select_all:
            for file_path in all_files:
                file_name = os.path.basename(file_path)
                individual_checks[file_path] = True
                file_stream = download_blob_as_bytes(container_client, file_path)
                files_to_download.append((file_name, file_stream))
        else:
            for file_path in all_files:
                file_name = os.path.basename(file_path)
                individual_checks[file_path] = st.checkbox(f"Select {file_name}", key=file_path)
                if individual_checks[file_path]:
                    file_stream = download_blob_as_bytes(container_client, file_path)
                    files_to_download.append((file_name, file_stream))
        
        # Check if any individual checkbox is unchecked, then uncheck the "Select All" checkbox
        if all(individual_checks.values()) and not select_all:
            st.experimental_rerun()

        # Step 8: Provide Download Options
        if files_to_download:
            zip_buffer = create_zip(files_to_download)
            st.download_button(label="Download Selected as Zip", data=zip_buffer, file_name="selected_files.zip")

def uploader_page():
    # Check for rejected files
    roll_number = st.session_state.roll_number
    rejected_files = get_rejected_files(roll_number)
    if rejected_files:
        st.session_state.rejected_files = rejected_files
    else:
        st.session_state.rejected_files = []

    st.title("Uploader Page")
        # Check for rejected files
    if "rejected_files" in st.session_state and st.session_state.rejected_files:
        for file in st.session_state.rejected_files:
            st.warning(f"Your file '{file['file_name']}' was rejected. Reason: {file['reason']}. Please re-upload.")

    department_list = load_departments_from_db()
    department = st.selectbox("Select Department", department_list, index=0)

    container_client = blob_service_client.get_container_client(container_name)
    directories = load_directories(container_client, department)

    if directories:
        directory = st.selectbox("Select Directory", directories)
    else:
        st.write("No directories found. Please contact admin to create directories.")

    file = st.file_uploader("Upload File",type={"pdf"})
    
    if st.button("Upload"):
        if department and directory and roll_number and file:
            blob_name = f"{department}/{directory}/{roll_number}/{file.name}"
            upload_file(container_client, file, blob_name)

            # Update the rejection log to set resolved flag to 1
            connection = get_db_connection()
            try:
                with connection.cursor() as cursor:
                    sql = "UPDATE rejection_logs SET resolved = 1 WHERE directory = %s AND roll_number = %s"
                    cursor.execute(sql, (directory, roll_number))
                connection.commit()
            finally:
                connection.close()

            st.success("File uploaded successfully!")
        else:
            st.error("Please fill in all fields before uploading.")

def file_manager_page():
    st.title("File Manager Page")
    department_list = load_departments_from_db()
    department = st.selectbox("Select Department", department_list)

    container_client = blob_service_client.get_container_client(container_name)
    directories = load_directories(container_client, department)

    if not directories:
        st.write("No directories found. Please contact admin to create directories.")
        return

    directory = st.selectbox("Select Directory", directories)
    roll_numbers = list_roll_numbers(container_client, f"{department}/{directory}")

    if roll_numbers:
        selected_roll_numbers = st.multiselect("Select Roll Number(s)", roll_numbers)
    else:
        st.write("No roll numbers found in this directory.")
        return

    all_files = []
    roll_number_file_map = {}

    if selected_roll_numbers:
        st.write(f"Files for selected roll number(s):")
        for roll_number in selected_roll_numbers:
            path_prefix = f"{department}/{directory}/{roll_number}"
            files = list_files(container_client, path_prefix)
            if files:
                file_names = [os.path.basename(file) for file in files]
                roll_number_file_map[roll_number] = file_names
                all_files.extend(file_names)

    if all_files:
        selected_files = st.multiselect("Select Files to Archive/Reject", all_files)
        action = st.selectbox("Select Action", ["Archive", "Reject"])

        if action == "Reject":
            rejection_reason = st.text_area("Enter reason for rejection")
            if st.button("Submit"):
                if rejection_reason:
                    for selected_file in selected_files:
                        for roll_number in selected_roll_numbers:
                            if selected_file in roll_number_file_map[roll_number]:
                                source_blob_name = f"{department}/{directory}/{roll_number}/{selected_file}"
                                new_blob_name = source_blob_name.replace(container_name, reject_container)
                                try:
                                    source_client = blob_service_client.get_container_client(container_name)
                                    dest_client = blob_service_client.get_container_client(reject_container)
                                    move_blob(source_client, dest_client, source_blob_name, new_blob_name)
                                    log_rejection(department, directory, roll_number, selected_file, rejection_reason)
                                except ResourceNotFoundError:
                                    st.error(f"File {selected_file} not found in the source path.")
                    st.success("Selected files rejected and moved successfully.")
                else:
                    st.error("Please provide a reason for rejection.")
        elif action == "Archive":
            if st.button("Archive"):
                for selected_file in selected_files:
                    for roll_number in selected_roll_numbers:
                        if selected_file in roll_number_file_map[roll_number]:
                            source_blob_name = f"{department}/{directory}/{roll_number}/{selected_file}"
                            new_blob_name = source_blob_name.replace(container_name, archive_container)
                            try:
                                source_client = blob_service_client.get_container_client(container_name)
                                dest_client = blob_service_client.get_container_client(archive_container)
                                move_blob(source_client, dest_client, source_blob_name, new_blob_name)
                            except ResourceNotFoundError:
                                st.error(f"File {selected_file} not found in the source path.")
                st.success("Selected files archived successfully.")

def main():
    page = []
    # Determine authenticated user role
    user_role = st.session_state.user_role
    if "user_role" not in st.session_state:
        st.session_state.user_role = None

    if st.session_state.user_role is None:
        if login_page():
            st.experimental_rerun()
    else:
        user_role = st.session_state.user_role
        user_name = st.session_state.user_name
        user_roll = st.session_state.roll_number

        st.sidebar.title(f"Welcome {user_name}! ({user_roll})")
        st.sidebar.write(f"Role: {user_role}")
            

    # Example of using user role for access control
    if user_role == USER_ROLE_UPLOADER:
        # Display only "Upload Files" page
        page = st.sidebar.selectbox("Go to", ["📤 Upload Files"])
    elif user_role == USER_ROLE_ACCESSOR:
        # Display "Upload Files" and "View and Download Files" pages
        page = st.sidebar.selectbox("Go to", ["📤 Upload Files", "📥 View and Download Files"])
    elif user_role == USER_ROLE_MANAGER:
        # Display all pages
        page = st.sidebar.selectbox("Go to", ["📤 Upload Files", "📁 Manage Files", "📥 View and Download Files"])
    elif user_role == USER_ROLE_ADMIN:
        # Display all pages plus admin page
        page = st.sidebar.selectbox("Go to", ["⚙️ Admin"])

    # Render selected page based on user's role and selected option
    if page == "📤 Upload Files":
        uploader_page()
    elif page == "📁 Manage Files":
        file_manager_page()
    elif page == "📥 View and Download Files":
        view_and_download_files_page()
    elif page == "⚙️ Admin":
        admin_page()

    # Logout button
    if st.sidebar.button("Logout"):
        st.session_state.clear()  # Clear all session state variables
        st.experimental_rerun()

if __name__ == "__main__":
    main()