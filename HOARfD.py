'''
HOARfD 
Headless On-demand Automatic Raspberry pi (Floppy) Dumper (The 'F' is silent)
(dragons hoard treasure → you’re hoarding floppies)

v4.2

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
        return 1
        
    pattern = re.compile(r"^BKP_(\d{3})")
    
    for item in os.listdir(base_dir):
        item_path = os.path.join(base_dir, item)
        if os.path.isdir(item_path):
            match = pattern.match(item)
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num
                    
    return max_num + 1

def find_devices():
    """
    Identifies the floppy drive and USB stick from connected USB devices based on size.
    Returns a tuple: (floppy_device_name, usb_stick_partition_path)
    e.g., ('sda', '/dev/sdb1')
    """
    floppy_name = None
    usb_stick_path = None
    try:
        result = subprocess.run(
            ['lsblk', '--json', '-b', '-o', 'NAME,TRAN,SIZE,TYPE'],
            capture_output=True, text=True, check=True
        )
        devices = json.loads(result.stdout)['blockdevices']

        for device in devices:
            if device.get('tran') == 'usb':
                device_size = device.get('size', 0)
                
                # Floppy drives are very small (< 5MB)
                if 0 < device_size < 5 * 1024 * 1024:
                    floppy_name = device.get('name')

                # USB sticks are much larger (> 100MB)
                elif device_size > 100 * 1024 * 1024:
                    if 'children' in device and device['children']:
                        for part in device['children']:
                            if part.get('type') == 'part':
                                usb_stick_path = f"/dev/{part['name']}"
                                break # Use the first partition found
                    elif device.get('type') == 'disk':
                        usb_stick_path = f"/dev/{device['name']}"
        
        return (floppy_name, usb_stick_path)

    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
        print(f"Error finding devices: {e}")
    return (None, None)

def mount_device(device_path, mount_point):
    """Mounts a device to a specified mount point."""
    if not os.path.exists(mount_point):
        os.makedirs(mount_point)
    try:
        subprocess.run(["umount", mount_point], check=False, stderr=subprocess.DEVNULL)
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

def is_disk_present(floppy_device_name):
    """
    Checks for the presence of a floppy disk by attempting to run fdisk.
    Returns True if a disk seems to be present, False otherwise.
    """
    if not floppy_device_name:
        return False
        
    floppy_device_path = f"/dev/{floppy_device_name}"
    if not os.path.exists(floppy_device_path):
        return False
    try:
        subprocess.run(
            ['fdisk', '-l', floppy_device_path],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return True
    except subprocess.CalledProcessError:
        return False

def attempt_backup(floppy_device_name, usb_stick_partition):
    """
    Attempts to mount the floppy, find a USB stick, and perform the backup.
    Returns True on success, False on failure.
    """
    try:
        # Floppy drives may or may not have a partition table. Try mounting the partition
        # first (e.g., /dev/sda1), and if that path doesn't exist, fall back to the
        # base device (e.g., /dev/sda).
        floppy_partition_path = f"/dev/{floppy_device_name}1"
        if not os.path.exists(floppy_partition_path):
            floppy_partition_path = f"/dev/{floppy_device_name}"

        print(f"Found floppy at {floppy_partition_path} and USB stick at {usb_stick_partition}")

        # Mount floppy and USB stick
        if mount_device(floppy_partition_path, FLOPPY_MOUNT_POINT) and \
           mount_device(usb_stick_partition, USB_MOUNT_POINT):

            usb_backup_path = os.path.join(USB_MOUNT_POINT, BACKUP_BASE_DIR)
            next_backup_num = get_next_backup_number(usb_backup_path)
            
            backup_folder_name = f"BKP_{next_backup_num:03d}"
            backup_dir = os.path.join(usb_backup_path, backup_folder_name)
            
            os.makedirs(backup_dir, exist_ok=True)

            print(f"Copying files from {FLOPPY_MOUNT_POINT} to {backup_dir}...")
            try:
                shutil.copytree(FLOPPY_MOUNT_POINT, backup_dir, dirs_exist_ok=True)
                print("File copy complete.")
            except shutil.Error as e:
                print(f"Error during file copy: {e}")

            # Unmount devices
            unmount_device(FLOPPY_MOUNT_POINT)
            unmount_device(USB_MOUNT_POINT)
            return True

    except Exception as e:
        print(f"An error occurred during backup: {e}")
        # Clean up by unmounting if anything was left mounted
        unmount_device(FLOPPY_MOUNT_POINT)
        unmount_device(USB_MOUNT_POINT)

    return False

def main():
    """Main function to run the floppy backup process."""
    print("Starting floppy backup utility...")
    disk_copied_this_cycle = False

    while True:
        floppy_drive, usb_stick = find_devices()

        if not floppy_drive or not usb_stick:
            if not floppy_drive: print("Waiting for USB floppy drive...")
            if not usb_stick: print("Waiting for USB flash drive...")
            time.sleep(5)
            continue

        disk_present = is_disk_present(floppy_drive)

        if disk_present:
            if not disk_copied_this_cycle:
                print("New floppy disk detected. Starting backup...")
                success = attempt_backup(floppy_drive, usb_stick)
                if success:
                    disk_copied_this_cycle = True
                    print("\nBackup complete. Please remove the floppy disk.\n")
                else:
                    print("Backup attempt failed. Please check the disk and USB stick.")
        else:
            if disk_copied_this_cycle:
                print("Floppy disk removed. Ready for the next one.")
            disk_copied_this_cycle = False

        time.sleep(2)

if __name__ == "__main__":
    main()
