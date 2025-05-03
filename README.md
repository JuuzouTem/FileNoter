# File Noter

A simple and fast Windows utility to add, view, and manage notes associated with files and folders directly from the right-click context menu.

## Features

*   **Add/Edit Notes:** Add or modify text notes for any file or folder.
*   **View Notes:** Quickly view the note associated with a specific file or folder.
*   **View All Notes:** A dedicated window to browse, search (implicitly by scrolling/viewing), and manage all your saved notes.
    *   See the note content directly in the window.
    *   Delete notes you no longer need.
    *   Right-click an entry to open the file/folder's location in Explorer.
*   **Fast Operation:** Thanks to a background process architecture, note windows open much faster after the initial launch.
*   **Context Menu Integration:** Seamlessly integrates with the Windows Explorer context menu (right-click menu).
*   **Flexible Installation:** Use the easy installer (`.exe`) or set up manually using the Python script.
*   **Data Storage:** Notes are stored locally in a simple database file within your `%APPDATA%\FileNoter` folder.

## Installation and Setup

You have two main ways to install File Noter: the recommended installer or manual setup.

**Important:** Both manual methods require modifying the Windows Registry and need **Administrator privileges**. Please be careful when editing the registry. Back up your registry if you are unsure. The installer handles this automatically.

### Option 1: Using the Installer (Recommended)

1.  **Download:** Go to the [Latest Release](https://github.com/JuuzouTem/FileNoter/releases/latest) page.
2.  Download the `FileNoter_vX.X.X_setup.exe` file.
3.  **Run Installer:** Double-click the downloaded `.exe` file and follow the on-screen instructions. The installer will:
    *   Copy the necessary files to an appropriate location (e.g., `Program Files`).
    *   Automatically configure the required Windows Registry entries for the "Add/Edit Note", "View Note", and "View All Notes" context menu options.
    *   (Optional) Provide an uninstaller.
4.  **Done!** You can now start using File Noter from the right-click menu.

### Option 2: Manual Setup with Executable (`FileNoter.exe`)

Use this if you prefer not to use the installer or want more control over the location.

1.  **Download:** Go to the [Latest Release](https://github.com/JuuzouTem/FileNoter/releases/latest) page. Basically download `FileNoter_Setup.exe`. You will need sample `.reg` files if you download directly, Go to the [FileNoter Github](https://github.com/JuuzouTem/FileNoter/) page. (or create your own based on the examples below). Let's assume you have `add_edit_note.reg`, `view_note.reg`, `add_note_folder.reg`,`view_note_folder.reg` and `view_all_notes.reg`.
2.  **Place Executable:** Move `FileNoter.exe` to a permanent location on your computer where it won't be accidentally moved or deleted (e.g., `C:\Program Files\FileNoter\`).
3.  **Edit Registry Files:**
    *   Open **each** `.reg` file (`add_edit_note.reg`, `view_note.reg`, `add_note_folder.reg`,`view_note_folder.reg` and `view_all_notes.reg`) using a text editor (like Notepad).
    *   Find lines similar to the examples below and replace `"C:\\path\\to\\your\\FileNoter.exe"` with the **full path** to where you placed `FileNoter.exe`.
    *   **Crucially:** Use **double backslashes (`\\`)** in the path within the `.reg` file.

    *   **Example for `add_edit_note.reg` (Applies to Files and Folders):**
        ```reg
        Windows Registry Editor Version 5.00

        [HKEY_CLASSES_ROOT\*\shell\AddEditFileNoter]
        @="Add/Edit Note"

        [HKEY_CLASSES_ROOT\*\shell\AddEditFileNoter\command]
        @="\"C:\\Program Files\\FileNoter\\FileNoter.exe\" --add \"%1\""

        [HKEY_CLASSES_ROOT\Directory\shell\AddEditFileNoter]
        @="Add/Edit Note"

        [HKEY_CLASSES_ROOT\Directory\shell\AddEditFileNoter\command]
        @="\"C:\\Program Files\\FileNoter\\FileNoter.exe\" --add \"%1\""
        ```

    *   **Example for `view_note.reg` (Applies to Files and Folders):**
        ```reg
        Windows Registry Editor Version 5.00

        [HKEY_CLASSES_ROOT\*\shell\ViewFileNoter]
        @="View Note"

        [HKEY_CLASSES_ROOT\*\shell\ViewFileNoter\command]
        @="\"C:\\Program Files\\FileNoter\\FileNoter.exe\" --view \"%1\""

        [HKEY_CLASSES_ROOT\Directory\shell\ViewFileNoter]
        @="View Note"

        [HKEY_CLASSES_ROOT\Directory\shell\ViewFileNoter\command]
        @="\"C:\\Program Files\\FileNoter\\FileNoter.exe\" --view \"%1\""
        ```

    *   **Example for `view_all_notes.reg` (Applies to Folder Background):**
        ```reg
        Windows Registry Editor Version 5.00

        [HKEY_CLASSES_ROOT\Directory\Background\shell\ViewAllFileNoter]
        @="View All Notes"

        [HKEY_CLASSES_ROOT\Directory\Background\shell\ViewAllFileNoter\command]
        @="\"C:\\Program Files\\FileNoter\\FileNoter.exe\" --view-all"
        ```

    *   **Example for `add_note_folder_only.reg` (Applies *only* to Folders, specific text/icon):**
        ```reg
        Windows Registry Editor Version 5.00

        [HKEY_CLASSES_ROOT\Directory\shell\TakeNote]
        @="Not Al"
        "Icon"="imageres.dll,71" ; Optional: Icon

        [HKEY_CLASSES_ROOT\Directory\shell\TakeNote\command]
        @="\"C:\\Program Files\\FileNoter\\FileNoter.exe\" --add \"%1\""
        ```
        *(Note: If you use this, you might want to remove the `[HKEY_CLASSES_ROOT\Directory\shell\AddEditFileNoter]` sections from the first example if you don't want two "Add Note" entries for folders).*

    *   **Example for `view_note_folder_only.reg` (Applies *only* to Folders, specific text/icon):**
        ```reg
        Windows Registry Editor Version 5.00

        [HKEY_CLASSES_ROOT\Directory\shell\ViewNoteSpecific]
        @="Notu Görüntüle"
        "Icon"="shell32.dll,277" ; Optional: Icon

        [HKEY_CLASSES_ROOT\Directory\shell\ViewNoteSpecific\command]
        @="\"C:\\Program Files\\FileNoter\\FileNoter.exe\" --view \"%1\""
        ```
        *(Note: I used `ViewNoteSpecific` for the key name to avoid conflict with the general `ViewNote` key if used simultaneously. Adjust as needed. Similar to the above, you might remove the folder part from the general `view_note.reg` if using this one exclusively for folders).*

    *   Save the changes to all `.reg` files.
4.  **Apply Registry Changes:**
    *   Double-click each edited `.reg` file one by one.
    *   Approve the User Account Control (UAC) prompt (Click **Yes**).
    *   Confirm the Registry Editor warning (Click **Yes**).
    *   Click **OK** on the success message. Repeat for all `.reg` files.

### Option 3: Manual Setup with Python Script (`file_noter_vX.X.X.py`)

Use this if you prefer running directly from the Python script.

1.  **Prerequisites:** Ensure you have Python 3 installed and added to your system's PATH. Using `pythonw.exe` (usually included) is recommended to avoid console windows popping up.
2.  **Download:** Download the `file_noter_vX.X.X.py` script from the source code or Releases. You will also need sample `.reg` files as described in Option 2.
3.  **Place Script:** Move the `.py` script to a permanent location (e.g., `C:\Scripts\FileNoter\`). Rename it to something simple like `filenoter.py` if desired.
4.  **Edit Registry Files:**
    *   Open **each** `.reg` file (`add_edit_note.reg`, `view_note.reg`, `add_note_folder.reg`,`view_note_folder.reg` and `view_all_notes.reg`) using a text editor.
    *   Locate the command lines. Replace the path to the executable with the path to `pythonw.exe` followed by the path to your script.
    *   Use **double backslashes (`\\`)** for all paths.

    *   **Example command line for `add_edit_note.reg`:**
        `@="\"C:\\Python311\\pythonw.exe\" \"C:\\Scripts\\FileNoter\\filenoter.py\" --add \"%1\""`
    *   **Example command line for `view_note.reg`:**
        `@="\"C:\\Python311\\pythonw.exe\" \"C:\\Scripts\\FileNoter\\filenoter.py\" --view \"%1\""`
    *   **Example command line for `view_all_notes.reg`:** (No `%1`)
        `@="\"C:\\Python311\\pythonw.exe\" \"C:\\Scripts\\FileNoter\\filenoter.py\" --view-all"`

    *   Modify these lines within the `.reg` file structures shown in Option 2, replacing the `FileNoter.exe` path with the `pythonw.exe` and script path combination.
    *   Save the changes to all `.reg` files.
5.  **Apply Registry Changes:** Follow step 4 from Option 2 (double-click each `.reg` file and approve prompts).

## Usage

Once installed:

1.  Navigate to any file or folder in Windows Explorer.
2.  **Right-click** on the file or folder.
3.  You should see new options:
    *   **Add/Edit Note:** Opens a window to create or modify the note for the selected item. Saving an empty note will delete the note for that item.
    *   **View Note:** Displays the current note for the selected item in a read-only window.
4.  To see all notes, right-click on the background of a folder (or wherever you configured the `view_all_notes.reg` entry) and select:
    *   **View All Notes:** Opens the dedicated window listing all notes. From here you can view content, delete notes, or right-click an entry to open its file location.

## Uninstallation

*   **Installer Method:** Use the "Add or remove programs" feature in Windows Settings to uninstall File Noter.
*   **Manual Method:**
    1.  Delete the registry keys you added (e.g., `HKEY_CLASSES_ROOT\*\shell\AddEditFileNoter`, `HKEY_CLASSES_ROOT\*\shell\ViewFileNoter`, `HKEY_CLASSES_ROOT\Directory\Background\shell\ViewAllFileNoter`, etc.). You can do this using `regedit.exe` or by creating corresponding "remove" `.reg` files (which start the key path with a hyphen, e.g., `[-HKEY_CLASSES_ROOT\*\shell\AddEditFileNoter]`).
    2.  Delete the `FileNoter.exe` or `.py` script file you placed manually.
    3.  (Optional) Delete the notes database folder: `%APPDATA%\FileNoter`.

Enjoy your enhanced file/folder organization with File Noter!
