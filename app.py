import streamlit as st
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
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
        host="127.0.0.1",
        user="root",
        password="2003",
        database="",
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

def get_user_role(email, password):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT role FROM users WHERE email=%s AND password=%s"
            cursor.execute(sql, (email, password))
            result = cursor.fetchone()
            if result:
                return result['role']
            else:
                return None
    finally:
        connection.close()

def add_user(email, password, role):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO users (email, password, role) VALUES (%s, %s, %s)"
            cursor.execute(sql, (email, password, role))
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

def login_page():
    st.title("Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        user_role = get_user_role(username, password)

        if user_role:
            st.success("Logged in successfully!")
            # Set session state variables
            st.session_state.user_email = username
            st.session_state.user_role = user_role
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

        if st.button("Add User", key="add_user"):
            if new_user_email and new_user_password and new_user_role:
                add_user(new_user_email, new_user_password, new_user_role)
                st.success(f"User '{new_user_email}' added successfully with role '{new_user_role}'.")
            else:
                st.error("Please fill out all fields to add a new user.")
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

    # Step 5: Select Roll Number
    roll_number = st.selectbox("Select Roll Number", roll_numbers)

    # Step 6: List Files based on selected Roll Number
    blob_prefix = f"{department}/{directory}/{roll_number}/"
    file_list = list_files(container_client, blob_prefix)

    if not file_list:
        st.write("No files found for the selected roll number.")
        return

    # Step 7: Display Files for Download
    st.write(f"Files for {department}/{directory}/{roll_number}:")
    files_to_download = []
    for file_path in file_list:
        file_name = os.path.basename(file_path)
        st.write(file_name)
        if st.checkbox(f"Select {file_name}", key=file_path):
            file_stream = download_blob_as_bytes(container_client, file_path)
            files_to_download.append((file_name, file_stream))

    # Step 8: Provide Download Options
    if files_to_download:
        if len(files_to_download) == 1:
            file_name, file_stream = files_to_download[0]
            st.download_button(label=f"Download {file_name}", data=file_stream, file_name=file_name)
        else:
            zip_buffer = create_zip(files_to_download)
            st.download_button(label="Download Selected as Zip", data=zip_buffer, file_name="selected_files.zip")

def uploader_page():
    st.title("Uploader Page")

    department_list = load_departments_from_db()
    department = st.selectbox("Select Department", department_list, index=0)

    container_client = blob_service_client.get_container_client(container_name)
    directories = load_directories(container_client, department)

    if directories:
        directory = st.selectbox("Select Directory", directories)
    else:
        st.write("No directories found. Please contact admin to create directories.")

    roll_number = st.text_input("Enter Roll Number")

    file = st.file_uploader("Upload File")
    
    if st.button("Upload"):
        if department and directory and roll_number and file:
            blob_name = f"{department}/{directory}/{roll_number}/{file.name}"
            upload_file(container_client, file, blob_name)
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
        roll_number = st.selectbox("Select Roll Number", roll_numbers)
    else:
        st.write("No roll numbers found.")
        return

    blob_prefix = f"{department}/{directory}/{roll_number}/"
    blobs = list_files(container_client, blob_prefix)

    if blobs:
        selected_files = st.multiselect("Select Files to Move", [os.path.basename(blob) for blob in blobs])

        if selected_files:
            action = st.radio("Action", ["Move to Archive", "Reject File"])

            if action == "Reject File":
                rejection_reason = st.text_input("Reason for Rejection")

            if st.button("Execute"):
                for file_name in selected_files:
                    blob_name = f"{blob_prefix}{file_name}"
                    if action == "Move to Archive":
                        display_timer(3)  # Display a 3-second timer
                        move_blob(blob_service_client.get_container_client(container_name),
                                  blob_service_client.get_container_client(archive_container),
                                  blob_name, f"{blob_prefix}{file_name}")
                        st.success(f"File {file_name} moved to archive successfully.")
                    elif action == "Reject File":
                        if rejection_reason:
                            display_timer(3)  # Display a 3-second timer
                            move_blob(blob_service_client.get_container_client(container_name),
                                      blob_service_client.get_container_client(reject_container),
                                      blob_name, f"{blob_prefix}{file_name}")
                            log_rejection(roll_number, file_name, rejection_reason)
                            st.success(f"File {file_name} rejected successfully.")
                        else:
                            st.warning("Please provide a reason for rejection.")
    else:
        st.write("No files found.")



def main():
    st.sidebar.title("Navigation")

    if 'user_email' not in st.session_state:
        # If user is not logged in, show login page
        if login_page():
            st.experimental_rerun()
        return

    # Determine authenticated user role
    user_role = st.session_state.user_role

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