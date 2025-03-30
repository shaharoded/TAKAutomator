"""_summary_
When you are all ready for TAK deployment, 
call this module to create a zipped folder with your TAK files 
"""

import os
import shutil
import zipfile
from tak_automator import TAKAutomator
from Config.agent_config import AgentConfig

def copy_and_compress_files(source_dir, files_to_remove, zip_name):
    tmp_dir=f'/tmp/{zip_name}'
    # Define tmp directory inside the script's running directory
    tmp_dir = os.path.join(os.getcwd(), zip_name)  # Creates a '1600' folder in repo root
    zip_file_path = os.path.join(os.getcwd(), f'{zip_name}.zip')  # Saves '1600.zip' in repo root

    # Ensure tmp_dir exists
    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir)

    # Track if files were copied
    files_copied = 0

    # Copy all files (flattening hierarchy)
    for root, _, files in os.walk(source_dir):
        for file in files:
            if file not in files_to_remove:
                file_path = os.path.join(root, file)
                new_path = os.path.join(tmp_dir, file)  # No hierarchy, all files go into tmp_dir

                # Copy file instead of moving
                shutil.copy2(file_path, new_path)
                files_copied += 1

    if files_copied == 0:
        print("⚠️ No files were found to copy. Check if source_dir exists and contains files.")
        return

    # Step 3: Compress the tmp folder into a ZIP file (saved in repo root)
    with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in os.listdir(tmp_dir):
            file_path = os.path.join(tmp_dir, file)
            zipf.write(file_path, arcname=file)  # Store without folder structure

    print(f"✅ All {files_copied} files copied to {tmp_dir} and compressed as {zip_file_path}")
    
    # Step 4: Delete the `1600/` folder after zipping
    shutil.rmtree(tmp_dir)
    print(f"🗑️ Folder {tmp_dir} deleted after compression.")


def main_menu():
    print("\n--- TAKAutomator Menu ---")
    print("1. Run TAKAutomator (full run)")
    print("2. Run TAKAutomator (test mode - one TAK only)")
    print("3. Zip TAKs folder for deployment")
    print("0. Exit")

    while True:
        choice = input("\nEnter your choice (0–3): ").strip()
        
        if choice == "1":
            print("\n▶ Running TAKAutomator in full mode...")
            automator = TAKAutomator()
            automator.run(test_mode=False)
        elif choice == "2":
            print("\n🧪 Running TAKAutomator in test mode...")
            automator = TAKAutomator()
            automator.run(test_mode=True)
        elif choice == "3":
            source_directory = os.path.join(os.getcwd(), "TAKs")
            zip_name = input("Enter zip name (e.g. '1600'): ").strip()
            files_to_remove = ['STATE_BASAL_BITZUA.xml', 'STATE_BOLUS_BITZUA.xml']  # You can hardcode or dynamically add known invalids here
            copy_and_compress_files(source_directory, files_to_remove, zip_name)
        elif choice == "0":
            print("👋 Exiting.")
            break
        else:
            print("❌ Invalid choice. Please enter 0, 1, 2, or 3.")

if __name__ == "__main__":
    main_menu()