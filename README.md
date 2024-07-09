# Placement Portal - README

Welcome to the Placement Portal! This web application streamlines the process of managing placement-related files for students, faculty, and administrative staff. The portal allows for the upload, management, and retrieval of placement documents securely using Azure Blob Storage and a MySQL database.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [User Roles](#user-roles)
- [Functions Overview](#functions-overview)
- [Contributing](#contributing)
- [License](#license)

## Features

- **Secure Login**: Users can securely log in using their credentials.
- **Role-based Access Control**: Different functionalities are accessible based on user roles.
- **File Upload**: Users can upload files, with automatic handling of rejected files.
- **File Management**: Admins and Managers can archive or reject files, with reasons logged for rejections.
- **Directory Management**: Admins can create new directories and add new users.
- **File Download**: Users can view and download files in bulk as ZIP files.
- **Departments Management**: Admins can manage departments.

## Installation

### Prerequisites

- Python 3.8 or higher
- Azure Storage Account
- MySQL Database

### Steps

1. **Clone the repository:**
    ```sh
    git clone https://github.com/your-repository/placement-portal.git
    cd placement-portal
    ```

2. **Install dependencies:**
    ```sh
    pip install -r requirements.txt
    ```

3. **Set up Azure Blob Storage:**
    - Create an Azure Storage Account and a container named `placements-2024`.
    - Note the connection string.

4. **Set up MySQL Database:**
    - Create a MySQL database and necessary tables (`users`, `departments`, `rejection_logs`).

5. **Configure environment variables:**
    - Set your Azure Storage connection string and database credentials in a `.env` file or directly in the script.

6. **Run the application:**
    ```sh
    streamlit run app.py
    ```

## Usage

### Login

1. **Navigate to the Login Page:**
    - Enter your username and password to log in.

### Admin Page

- **Create New Directory**: Create new directories for departments.
- **Add New User**: Add new users with specific roles.
- **Add Department**: Add new departments.

### Uploader Page

- **Upload Files**: Select department and directory to upload files. Handle rejected files if any.

### File Manager Page

- **Manage Files**: Move files to archive or reject them with a reason.

### View and Download Files Page

- **View Files**: Select department, directory, and roll numbers to view files.
- **Download Files**: Select files to download as a ZIP archive.

## User Roles

- **Uploader**: Can upload files and handle rejected files.
- **Accessor**: Can view and download files.
- **Manager**: Can upload, view, download, archive, and reject files.
- **Admin**: Full access including user and department management.

## Functions Overview

- **Database Functions**: Connect, retrieve, and manage data from MySQL.
- **Blob Storage Functions**: Upload, list, and move files in Azure Blob Storage.
- **Session Management**: Handle user sessions and state using Streamlit's session state.
- **File Management**: Upload, archive, reject, and download files with proper logging.

## Contributing

Contributions are welcome! 

## License



---

Thank you for using the Placement Portal! For any issues or queries, please contact the development team at 2032012mds@cit.edu.in
