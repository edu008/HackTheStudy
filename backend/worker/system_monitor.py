#!/usr/bin/env python3
import time
import psutil

def main():
    while True:
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
        print('[INFO] System Status - CPU: {}%, RAM: {}%, Disk: {}%'.format(cpu, mem, disk))
        time.sleep(60)

if __name__ == "__main__":
    main() 