#!/bin/bash

# Script to download necessary AI models for Project Sentinel
# Run from the project root or models directory

# Ensure we are in the models directory
CURRENT_DIR=$(dirname "$0")
cd "$CURRENT_DIR" || exit 1

echo "=========================================="
echo "   Downloading AI Models..."
echo "=========================================="

# Function to download a file if it doesn't exist
download_file() {
    local url="$1"
    local filename="$2"

    if [ -f "$filename" ]; then
        echo "✅ $filename already exists. Skipping."
    else
        echo "⬇️ Downloading $filename..."
        if command -v wget &> /dev/null; then
            wget -q --show-progress -O "$filename" "$url"
        elif command -v curl &> /dev/null; then
            curl -L -o "$filename" "$url"
        else
            echo "❌ Error: Neither 'wget' nor 'curl' found. Please install one to download models."
            exit 1
        fi

        if [ $? -eq 0 ]; then
            echo "✅ Downloaded $filename successfully."
        else
            echo "❌ Failed to download $filename."
            exit 1
        fi
    fi
}

# --- Download Links ---

# 1. MiniFASNetV2 (PyTorch)
download_file "https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/raw/master/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth" "2.7_80x80_MiniFASNetV2.pth"

# 2. MiniFASNetV1SE (PyTorch)
download_file "https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/raw/master/resources/anti_spoof_models/4_0_0_80x80_MiniFASNetV1SE.pth" "4_0_0_80x80_MiniFASNetV1SE.pth"

# 3. YuNet Face Detection (ONNX)
download_file "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" "face_detection_yunet_2023mar.onnx"

# 4. SFace Face Recognition (ONNX)
download_file "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx" "face_recognition_sface_2021dec.onnx"

# 5. MiniFASNetV1SE (ONNX)
download_file "https://github.com/yakhyo/face-anti-spoofing/releases/download/weights/MiniFASNetV1SE.onnx" "MiniFASNetV1SE.onnx"

# 6. MiniFASNetV2 (ONNX)
download_file "https://github.com/yakhyo/face-anti-spoofing/releases/download/weights/MiniFASNetV2.onnx" "MiniFASNetV2.onnx"

echo ""
echo "✅ All models checked/downloaded."
