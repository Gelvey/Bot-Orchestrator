#!/usr/bin/env python3
import signal
import sys
import time

running = True

def handle_term(signum, frame):
    global running
    running = False

signal.signal(signal.SIGTERM, handle_term)
signal.signal(signal.SIGINT, handle_term)

print("ARKBots example started")
sys.stdout.flush()
count = 0
while running and count < 1000:
    print(f"ARKBots heartbeat {count}")
    sys.stdout.flush()
    time.sleep(1)
    count += 1

print("ARKBots example exiting")
