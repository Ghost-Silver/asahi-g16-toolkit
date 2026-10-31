#!/usr/bin/env python3
"""
check_m1n1_env.py - Quick environment and USB interface checker for m1n1 remote control.
Can be run on either the target machine or the controller machine.
"""

import sys
import os
import platform
import subprocess

def check_system():
    os_name = platform.system()
    print(f"[*] Operating System: {os_name} ({platform.machine()})")

    if os_name == "Darwin":
        print("[*] Checking macOS USB topology...")
        try:
            out = subprocess.check_output(["ioreg", "-p", "IOUSB", "-l"], text=True)
            if "m1n1" in out.lower():
                print("    [+] Found m1n1 proxy device in IORegistry!")
            else:
                print("    [-] m1n1 device not currently attached via USB.")
        except Exception as e:
            print(f"    [!] Error checking ioreg: {e}")

    elif os_name == "Linux":
        print("[*] Checking Linux USB devices and TTY ACM ports...")
        try:
            lsusb = subprocess.check_output(["lsusb"], text=True)
            if "1209:316e" in lsusb:
                print("    [+] Found m1n1 USB device (1209:316e)!")
            else:
                print("    [-] m1n1 USB device (1209:316e) not seen in lsusb.")
        except Exception as e:
            print(f"    [!] Error running lsusb: {e}")

    # Check python dependencies
    print("[*] Checking Python dependencies for proxyclient...")
    for mod in ["construct", "serial", "usb"]:
        try:
            __import__(mod)
            print(f"    [+] {mod}: available")
        except ImportError:
            print(f"    [-] {mod}: NOT installed (run: pip install {mod})")

    print("\n[+] Target Port reminder for MacBook Pro 14\" M3 Pro (Mac15,6):")
    print("    Connect USB-C to the LEFT REAR port (closest to MagSafe / screen)!")

if __name__ == "__main__":
    check_system()
