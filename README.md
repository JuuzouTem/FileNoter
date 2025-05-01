# File-Reader

A simple Windows utility to add and view notes associated with files and folders directly from the right-click context menu.

## Features

*   Add text notes to any file or folder.
*   View existing notes associated with files or folders.
*   Integrates seamlessly with the Windows Explorer context menu (right-click menu).
*   Provides options for using a pre-compiled executable or the Python script directly.

## Installation and Setup

Choose one of the following methods based on whether you want to use the pre-compiled executable (`.exe`) or the Python script (`.py`).

**Important:** Both methods require modifying the Windows Registry. This requires **Administrator privileges**. Please be careful when editing the registry. Back up your registry if you are unsure.

### Option 1: Using the Executable (`FileNoter.exe`)

1.  **Download:** Download `FileNoter.exe` and the provided `.reg` files (e.g., `add_note.reg`, `view_note.reg`).
2.  **Place Executable:** Move `FileNoter.exe` to a permanent location on your computer where you won't accidentally delete it (e.g., `C:\Program Files\FileNoter\`).
3.  **Edit Registry Files:**
    *   Open **each** `.reg` file using a text editor (like Notepad).
    *   Find the placeholder text: `"your_folder_location"`
    *   Replace **all occurrences** of `"your_folder_location"` with the **full path** to where you placed `FileNoter.exe`.
    *   **Crucially:** Use **double backslashes (`\\`)** in the path within the `.reg` file.
    *   Example: If you placed the file at `C:\Tools\FileNoter\FileNoter.exe`, the line in the `.reg` file should look something like: `@="\"C:\\Tools\\FileNoter\\FileNoter.exe\" --add \"%1\""` (adjust according to the specific structure of your `.reg` files).
    *   Save the changes to the `.reg` files.
4.  **Apply Registry Changes:**
    *   Double-click on the first edited `.reg` file (e.g., `add_note.reg`).
    *   You will likely see a User Account Control (UAC) prompt asking for Administrator permission. Click **Yes**.
    *   You will see a Registry Editor warning. Click **Yes** to continue.
    *   You should see a confirmation message that the keys and values were successfully added. Click **OK**.
    *   Repeat this step for the other edited `.reg` file (e.g., `view_note.reg`).

### Option 2: Using the Python Script (`file_noter.py`)

1.  **Prerequisites:** Ensure you have Python installed on your system. It's recommended to use `pythonw.exe` (usually included with standard Python installations) to avoid console windows popping up.
2.  **Download:** Download `file_noter.py` and the provided `.reg` files (e.g., `add_note.reg`, `view_note.reg`).
3.  **Place Script:** Move `file_noter.py` to a permanent location on your computer (e.g., `C:\Scripts\FileNoter\`).
4.  **Edit Registry Files:**
    *   Open **each** `.reg` file using a text editor (like Notepad).
    *   Locate the lines defining the commands for adding and viewing notes. They will look similar to the examples below.
    *   **For adding notes (`add_note.reg` or similar):**
        *   Find the line similar to: `@="\"C:\\path\\to\\your\\pythonw.exe\" \"C:\\path\\to\\your\\file_noter.py\" --add \"%1\""`
        *   Replace `"C:\\path\\to\\your\\pythonw.exe"` with the actual full path to your `pythonw.exe`. Remember to use **double backslashes (`\\`)**.
        *   Replace `"C:\\path\\to\\your\\file_noter.py"` with the actual full path to where you placed `file_noter.py`. Remember to use **double backslashes (`\\`)**.
    *   **For viewing notes (`view_note.reg` or similar):**
        *   Find the line similar to: `@="\"C:\\path\\to\\your\\pythonw.exe\" \"C:\\path\\to\\your\\file_noter.py\" --view \"%1\""`
        *   Replace `"C:\\path\\to\\your\\pythonw.exe"` with the actual full path to your `pythonw.exe`. Remember to use **double backslashes (`\\`)**.
        *   Replace `"C:\\path\\to\\your\\file_noter.py"` with the actual full path to where you placed `file_noter.py`. Remember to use **double backslashes (`\\`)**.
    *   Save the changes to the `.reg` files.
5.  **Apply Registry Changes:**
    *   Double-click on the first edited `.reg` file (e.g., `add_note.reg`).
    *   You will likely see a User Account Control (UAC) prompt asking for Administrator permission. Click **Yes**.
    *   You will see a Registry Editor warning. Click **Yes** to continue.
    *   You should see a confirmation message that the keys and values were successfully added. Click **OK**.
    *   Repeat this step for the other edited `.reg` file (e.g., `view_note.reg`).

## Usage

Once you have completed the installation and setup steps:

1.  Navigate to any file or folder in Windows Explorer.
2.  **Right-click** on the file or folder.
3.  You should now see new options in the context menu (e.g., "Add/Edit Note" and "View Note" - the exact text depends on how the `.reg` files were configured).
4.  Select **"Add/Edit Note"** to create a new note or modify an existing one for that item.
5.  Select **"View Note"** to display the note currently associated with that item.

That's it! You can now easily attach notes to your files and folders.

Enjoy your experience with FileNoter!
