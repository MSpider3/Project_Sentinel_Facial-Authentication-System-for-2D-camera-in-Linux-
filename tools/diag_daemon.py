#!/usr/bin/env python3
"""Quick diagnostic script to trace daemon import failures."""
import sys
import os
import traceback

print("=== Sentinel Daemon Import Diagnostic ===")

tests = [
    ("pam", "import pam"),
    ("socket", "import socket"),
    ("cv2", "import cv2"),
    ("numpy", "import numpy"),
    ("onnxruntime", "import onnxruntime"),
    ("scipy", "import scipy"),
]

for name, stmt in tests:
    try:
        exec(stmt)
        print(f"[OK] {name}")
    except Exception as e:
        print(f"[FAIL] {name}: {e}")

print("\n=== Checking sentinel_service.py top-level config ===")
print(f"Working dir: {os.getcwd()}")
print(f"Python: {sys.executable}")
print(f"Config file: {os.path.exists('/etc/project-sentinel/config.ini')}")
print(f"Models dir: {os.path.exists('/var/lib/project-sentinel/models')}")
print(f"Runtime dir: {os.path.exists('/run/sentinel')}")
