'''
HOARfD 
Headless On-demand Automatic Raspberry pi (Floppy) Dumper (The 'F' is silent)
(dragons hoard treasure → you’re hoarding floppies)

v4.0

Description:
    This program is designed to run unattended on a dedicated headless Raspberry Pi.
    Intended for copying floppy disks from Sony Mavica FD cameras rapidly in the field. 

    Simply run this program as a service as root at startup. It will locate a USB
    Floppy Drive and a USB memory stick. Once a disk is inserted into the drive, it will 
    begin copying the contents to the USB stick. The floppy drive access light will 
    blink once complete. Replace the disk with a new one to perform a new copy.

RasPi Setup:
    1. Flash a vanilla headless Raspberry Pi.
    2. Copy this python script to the home directory (/home/pi/HOARfD.py)
    3. run "sudo nano /etc/systemd/system/HOARfD.service" in terminal.
    4. Paste the following into that file.

        [Unit]
        Description=HOARfD Python Program
        After=network.target

        [Service]
        ExecStart=/usr/bin/python /home/pi/HOARfD.py
        WorkingDirectory=/home/pi
        StandardOutput=inherit
        StandardError=inherit
        Restart=always
        User=root

        [Install]
        WantedBy=multi-user.target

    5. Reboot the Pi with a USB floppy drive plugged in.  
    6. System is now ready to receive a USB memory stick and a Floppy disk.
    
'''
import os
import subprocess
import time
import shutil
import json
import re

# --- Configuration ---
FLOPPY_DEVICE_NAME = "sda"  # This might change, check with `lsblk`
FLOPPY_MOUNT_POINT = "/mnt/floppy"
USB_MOUNT_POINT = "/mnt/usb_stick"
BACKUP_BASE_DIR = "floppy_backups"

def get_next_backup_number(base_dir):
    """
    Scans the backup directory to find the highest existing backup number
    and returns the next number in the sequence (e.g., if BKP_003 exists, returns 4).
    """
    max_num = 0
    if not os.path.exists(base_dir):
        # If the base backup directory doesn't exist, we start with 1
        return 1
        
    # Regex to find folders matching the BKP_XXX pattern
    pattern = re.compile(r"^BKP_(\d{3})")
    
    for item in os.listdir(base_dir):
        item_path = os.path.join(base_dir, item)
        if os.path.isdir(item_path):
            match = pattern.match(item)
            if match:
                # Extract the number from the folder name
                num = int(match.group(1))
                if num > max_num:
                    max_num = num
                    
    # The next backup number is the highest found number plus one
    return max_num + 1

def get_device_size(device_name):
    """Gets the size of a block device in bytes."""
    try:
        # Reads the size from the sysfs filesystem
        with open(f"/sys/class/block/{device_name}/size", "r") as f:
            # The size is given in 512-byte sectors
            return int(f.read().strip()) * 512
    except (IOError, ValueError):
        return 0

def find_usb_stick():
    """Finds a USB stick using the lsblk command, ignoring the floppy drive."""
    try:
        # Use lsblk to get device info in JSON format.
        result = subprocess.run(
            ['lsblk', '--json', '-b', '-o', 'NAME,TRAN,SIZE,TYPE'],
            capture_output=True, text=True, check=True
        )
        devices = json.loads(result.stdout)['blockdevices']

        for device in devices:
            # We are looking for a USB device that is large enough to be a USB stick
            # AND is explicitly not the designated floppy drive.
            if (device.get('tran') == 'usb' and
                    device.get('size', 0) > 100 * 1024 * 1024 and
                    device.get('name') != FLOPPY_DEVICE_NAME):
                
                # Case 1: The device has partitions. Find and return the first partition.
                if 'children' in device and device['children']:
                    for partition in device['children']:
                        if partition.get('type') == 'part':
                            return f"/dev/{partition['name']}"
                # Case 2: The device has no partitions. Return the device itself.
                elif device.get('type') == 'disk':
                        return f"/dev/{device['name']}"

    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
        print(f"Error finding USB stick: {e}")
    return None

def mount_device(device_path, mount_point):
    """Mounts a device to a specified mount point."""
    if not os.path.exists(mount_point):
        os.makedirs(mount_point)
    try:
        # Unmount first to ensure a clean state
        subprocess.run(["umount", mount_point], check=False, stderr=subprocess.DEVNULL)
        # Mount the device
        subprocess.run(["mount", device_path, mount_point], check=True)
        print(f"Successfully mounted {device_path} to {mount_point}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to mount {device_path}: {e}")
        return False

def unmount_device(mount_point):
    """Unmounts a device from a specified mount point."""
    try:
        subprocess.run(["umount", mount_point], check=True)
        print(f"Successfully unmounted {mount_point}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to unmount {mount_point}: {e}")

def is_disk_present():
    """
    Checks for the presence of a floppy disk by attempting to run fdisk.
    This command typically fails if no media is present in the drive.
    Returns True if a disk seems to be present, False otherwise.
    """
    floppy_device_path = f"/dev/{FLOPPY_DEVICE_NAME}"
    if not os.path.exists(floppy_device_path):
        return False
    try:
        # We run fdisk and check its output. If it fails, it means no disk.
        # The output is redirected to DEVNULL to keep the console clean.
        subprocess.run(
            ['fdisk', '-l', floppy_device_path],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return True
    except subprocess.CalledProcessError:
        # fdisk returns a non-zero exit code if it can't read the disk
        return False

def attempt_backup():
    """
    Attempts to mount the floppy, find a USB stick, and perform the backup.
    Returns True on success, False on failure.
    """
    try:
        # We check for partitions on the floppy. If a disk is inserted,
        # a partition like /dev/sda1 should exist.
        floppy_partition = f"/dev/{FLOPPY_DEVICE_NAME}1"
        if not os.path.exists(floppy_partition):
            # If no partition is found, some floppies might be formatted without one.
            # We can try to mount the base device itself.
            floppy_partition = f"/dev/{FLOPPY_DEVICE_NAME}"

        # Check if a USB stick is also present
        usb_stick_partition = find_usb_stick()
        if not usb_stick_partition:
            print("No USB stick detected. Waiting for one to be inserted.")
            return False

        print(f"Found USB stick at {usb_stick_partition}")

        # Mount floppy and USB stick
        if mount_device(floppy_partition, FLOPPY_MOUNT_POINT) and \
           mount_device(usb_stick_partition, USB_MOUNT_POINT):

            # --- MODIFIED SECTION ---
            # Determine the next backup number
            usb_backup_path = os.path.join(USB_MOUNT_POINT, BACKUP_BASE_DIR)
            next_backup_num = get_next_backup_number(usb_backup_path)

            # Create the unique directory name for the backup
            backup_folder_name = f"BKP_{next_backup_num:03d}"
            backup_dir = os.path.join(usb_backup_path, backup_folder_name)
            # --- END MODIFIED SECTION ---
            
            os.makedirs(backup_dir, exist_ok=True)

            print(f"Copying files from {FLOPPY_MOUNT_POINT} to {backup_dir}...")
            try:
                # Copy all files and directories, preserving metadata
                shutil.copytree(FLOPPY_MOUNT_POINT, backup_dir, dirs_exist_ok=True)
                print("File copy complete.")
            except shutil.Error as e:
                print(f"Error during file copy: {e}")

            # Unmount devices
            unmount_device(FLOPPY_MOUNT_POINT)
            unmount_device(USB_MOUNT_POINT)
            return True

    except Exception as e:
        print(f"Could not access floppy. No disk inserted? Error: {e}")
        # Clean up by unmounting if anything was left mounted
        unmount_device(FLOPPY_MOUNT_POINT)
        unmount_device(USB_MOUNT_POINT)

    return False

def main():
    """Main function to run the floppy backup process."""
    print("Starting floppy backup utility...")
    # State variable to track if we've successfully backed up a disk in the current cycle
    disk_copied_this_cycle = False

    while True:
        disk_present = is_disk_present()

        if disk_present:
            # A disk is in the drive.
            if not disk_copied_this_cycle:
                # We haven't copied this disk yet, so let's do it.
                print("New floppy disk detected. Starting backup...")
                success = attempt_backup()
                if success:
                    disk_copied_this_cycle = True
                    print("\nBackup complete. Please remove the floppy disk.\n")
                else:
                    # This might happen if the disk is unreadable, for example.
                    print("Backup attempt failed. Please check the disk and USB stick.")
        else:
            # No disk is in the drive.
            if disk_copied_this_cycle:
                # This means the user has just removed the disk we copied.
                print("Floppy disk removed. Ready for the next one.")
            # Reset the state to be ready for the next disk.
            disk_copied_this_cycle = False

        # Wait for a couple of seconds before checking again to avoid high CPU usage.
        time.sleep(2)

if __name__ == "__main__":
    main()
