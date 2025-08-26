# HOARfD
a "Headless On-demand Automatic Raspberry pi (Floppy) Dumper." Use it on a headless Raspberry Pi to copy the contents of a floppy disk to a flash drive automatically.


## About HOARfD

HOARfD was intended for copying floppy disks from Sony Mavica FD cameras rapidly in the field. It has been tested on an original Raspberry Pi 1 running Raspberry Pi OS Lite (32-bit) (Release 2025-05-13).

Simply run this program as a service as root at startup on a Raspberry Pi. It will locate a USB Floppy Drive and a USB memory stick. Once a disk is inserted into the drive, it will begin copying the contents to the USB stick. The floppy drive access light will blink slowly once complete. Replace the disk with a new one to perform a new copy. 

## Features

- Automatic Device Detection by detecting the size of USB storage devices as listed in lsblk
- Automatic Detection: No need to manually start the copy; it waits for you to insert a disk.
- Safe Archiving: Each disk copy is given a unique folder. The disk is never written to or formatted.
- Open Source: The full source code is available for you to inspect and modify!

## System Requirements

Floppy Copy is a Python program. To run it, you'll need:

- A Raspberry Pi with at least two USB ports.
- Python 3.x (comes standard with Raspberry Pi OS and Lite versions)
- USB Floppy Drive I'm using a generic no-name one
- USB Flash Drive or any removable flash media to store your copied/dumped files

## Run Automatically on Startup

Flash a vanilla headless Raspberry Pi.
Copy this python script to the home directory (/home/pi/HOARfD.py).
Run ```sudo nano /etc/systemd/system/HOARfD.service``` in terminal.
Paste the following into that file:

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

Reboot the Pi with a USB floppy drive plugged in.
System is now ready to receive a USB memory stick and a Floppy disk.

