#!/bin/bash
# tools/check_daemon.sh — Full diagnostic for sentinel-backend connection failures
# Run as:  sudo bash tools/check_daemon.sh
# Output:  /tmp/sentinel_diag.txt

OUT="/tmp/sentinel_diag.txt"
echo "==== Sentinel Daemon Diagnostics $(date) ====" | tee "$OUT"

section() { echo -e "\n\n### $1 ###" | tee -a "$OUT"; }

# ── 1. Systemd service status ────────────────────────────────────────────────
section "systemctl status"
systemctl status sentinel-backend.service --no-pager 2>&1 | tee -a "$OUT"

# ── 2. Last 100 journal lines ────────────────────────────────────────────────
section "journalctl (last 100 lines)"
journalctl -u sentinel-backend.service -n 100 --no-pager 2>&1 | tee -a "$OUT"

# ── 3. Installed files ───────────────────────────────────────────────────────
section "Installed file tree"
ls -la /usr/lib/project-sentinel/ 2>&1 | tee -a "$OUT"
echo "--- venv/bin ---" | tee -a "$OUT"
ls /usr/lib/project-sentinel/venv/bin/ 2>&1 | tee -a "$OUT"
echo "--- sentinel.sock ---" | tee -a "$OUT"
ls -la /run/sentinel/ 2>&1 | tee -a "$OUT"

# ── 4. Log file ──────────────────────────────────────────────────────────────
section "Sentinel log file (/var/log/sentinel/sentinel.log)"
if [ -f /var/log/sentinel/sentinel.log ]; then
    tail -n 100 /var/log/sentinel/sentinel.log | tee -a "$OUT"
else
    echo "Log file does not exist yet." | tee -a "$OUT"
fi

# ── 5. Try to manually run the daemon and capture crash output ───────────────
section "Manual daemon launch (5s timeout)"
DAEMON="/usr/lib/project-sentinel/venv/bin/sentinel-daemon"
if [ -f "$DAEMON" ]; then
    timeout 5 "$DAEMON" 2>&1 | tee -a "$OUT" || true
else
    echo "sentinel-daemon executable NOT FOUND at $DAEMON" | tee -a "$OUT"
    echo "Available executables in venv/bin:" | tee -a "$OUT"
    ls /usr/lib/project-sentinel/venv/bin/ 2>&1 | tee -a "$OUT"
fi

# ── 6. Python import test ────────────────────────────────────────────────────
section "Python import test"
PYTHON="/usr/lib/project-sentinel/venv/bin/python3"
if [ -f "$PYTHON" ]; then
    cd /usr/lib/project-sentinel
    "$PYTHON" - 2>&1 | tee -a "$OUT" << 'PYEOF'
import sys, os
print(f"Python: {sys.version}")
print(f"CWD: {os.getcwd()}")
tests = [
    "import pam; print('pam OK')",
    "import cv2; print('cv2 OK')",
    "import numpy; print('numpy OK')",
    "import onnxruntime; print('onnxruntime OK')",
    "import scipy; print('scipy OK')",
    "import biometric_processor; print('biometric_processor OK')",
    "import sentinel_service; print('sentinel_service OK')",
]
for t in tests:
    try:
        exec(t)
    except Exception as e:
        print(f"FAIL [{t[:30]}]: {e}")
PYEOF
else
    echo "Python interpreter NOT FOUND at $PYTHON" | tee -a "$OUT"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo -e "\n\n=== DONE. Full output saved to: $OUT ===" | tee -a "$OUT"
echo "Share $OUT to diagnose the issue."
