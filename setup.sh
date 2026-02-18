#!/bin/bash
set -e

# Project Sentinel - Unified Setup Script
# Handles dependencies, app compilation, service installation, and configuration.

if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (sudo)" 
   exit 1
fi

PROJECT_LIB="/usr/lib/project-sentinel"
PROJECT_VAR="/var/lib/project-sentinel"
PROJECT_ETC="/etc/project-sentinel"
SERVICE_FILE="packaging/sentinel-backend.service"
CURRENT_DIR=$(pwd)

echo "=========================================="
echo "   Project Sentinel - Setup Wizard"
echo "=========================================="

# 1. Dependency Check
echo "[1] Checking System Dependencies..."
if command -v dnf &> /dev/null; then
    dnf install -y git gcc meson ninja-build vala gtk4-devel \
                   json-glib-devel gstreamer1-devel gstreamer1-plugins-base-devel \
                   python3-devel pam-devel polkit wget
else
    echo "Warning: 'dnf' not found. Please ensure you have the required dependencies manually:"
    echo "vala, gtk4-devel, json-glib-devel, gstreamer1-devel, python3-devel, pam-devel"
fi
echo "Dependencies checked."
echo ""

# 1.5. Model Download
echo "[1.5] Checking AI Models..."
if [ -f "models/download_models.sh" ]; then
    chmod +x models/download_models.sh
    ./models/download_models.sh
else
    echo "⚠️ Warning: 'models/download_models.sh' not found. You may need to download models manually."
    echo "2.7_80x80_MiniFASNetV2.pth  (https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/blob/master/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth)"
    echo "4_0_0_80x80_MiniFASNetV1SE.pth (https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/blob/master/resources/anti_spoof_models/4_0_0_80x80_MiniFASNetV1SE.pth)"
    echo "face_detection_yunet_2023mar.onnx (https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx)"
    echo "face_recognition_sface_2021dec.onnx (https://github.com/opencv/opencv_zoo/blob/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx)"
    echo "MiniFASNetV1SE.onnx (https://github.com/yakhyo/face-anti-spoofing/releases/download/weights/MiniFASNetV1SE.onnx)"
    echo "MiniFASNetV2.onnx (https://github.com/yakhyo/face-anti-spoofing/releases/download/weights/MiniFASNetV2.onnx)"
fi
echo ""

# 2. Installation Mode
echo "Select Installation Mode:"
echo "  1) Full System Install (Recommended for Production)"
echo "     - Installs to /usr/lib/project-sentinel"
echo "     - Sets up systemd service"
echo "     - Config in /etc/project-sentinel"
echo "  2) Development / Temporary Install"
echo "     - Compiles locally in ./build"
echo "     - Sets up local venv"
echo "     - Config remains in local directory"
read -p "Enter choice [1/2]: " -r MODE

if [[ "$MODE" != "1" && "$MODE" != "2" ]]; then
    echo "Invalid choice. Exiting."
    exit 1
fi

# 3. Compile Vala App
echo ""
echo "[2] Compiling Vala Application..."
# Clean builddir if exists
rm -rf builddir

# Run build
meson setup builddir --prefix=/usr
ninja -C builddir

if [[ "$MODE" == "1" ]]; then
    # --- FULL INSTALL ---
    echo ""
    echo "[3] Performing Full System Install..."
    
    # Directories
    mkdir -p "$PROJECT_LIB"
    mkdir -p "$PROJECT_VAR"/{models,blacklist}
    mkdir -p "$PROJECT_ETC"
    chmod 700 "$PROJECT_VAR"
    
    # Copy Compiled Binary
    cp builddir/src/sentinel-ui "$PROJECT_LIB/sentinel-val-app"
    chmod +x "$PROJECT_LIB/sentinel-val-app"
    
    # Copy Python Code
    cp -r src "$PROJECT_LIB/" 2>/dev/null || true
    cp *.py "$PROJECT_LIB/"
    cp requirements.txt "$PROJECT_LIB/"
    
    # Python Venv
    if [ ! -d "$PROJECT_LIB/venv" ]; then
        python3 -m venv "$PROJECT_LIB/venv"
    fi
    "$PROJECT_LIB/venv/bin/pip" install -r "$PROJECT_LIB/requirements.txt" --upgrade
    
    # Config
    if [ ! -f "$PROJECT_ETC/config.ini" ]; then
        cp config.ini "$PROJECT_ETC/" 2>/dev/null || echo "Creating default config..."
        # (Could generate default here but assuming config.ini exists in repo)
    fi
    
    # Service
    echo "Installing Service..."
    cp "$SERVICE_FILE" "/etc/systemd/system/"
    # Adjust service file logic if needed (repo service file points to /usr/lib/project-sentinel)
    systemctl daemon-reload
    systemctl enable sentinel-backend
    systemctl restart sentinel-backend
    
    # Client Script (for PAM)
    cp sentinel_client.py /usr/bin/sentinel_client.py
    chmod +x /usr/bin/sentinel_client.py
    
    echo "✅ Full Installation Complete."
    
elif [[ "$MODE" == "2" ]]; then
    # --- DEV INSTALL ---
    echo ""
    echo "[3] Setting up Development Environment..."
    
    # Local Venv
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    ./venv/bin/pip install -r requirements.txt
    
    # Compile Local (already done in builddir)
    echo "App compiled in 'builddir/src/sentinel-ui'"
    
    echo "✅ Dev Setup Complete."
    echo "To run the backend manually:"
    echo "  sudo ./venv/bin/python3 sentinel_service.py"
    echo "To run the app:"
    echo "  ./builddir/src/sentinel-ui"
fi

# 4. PAM Instructions
echo ""
echo "=========================================="
echo "   PAM Configuration (Manual Step)"
echo "=========================================="
echo "To enable Face Unlock for Lock Screen / GDM, you must edit PAM config."
echo "I will NOT do this automatically to prevent system lockouts."
echo ""
echo "Edit: /etc/pam.d/gdm-password"
echo "Add this line to the TOP of the 'auth' section:"
echo ""
echo "auth sufficient pam_exec.so expose_authtok quiet /usr/bin/sentinel_client.py"
echo ""
echo "=========================================="
echo "Setup Finished!"
