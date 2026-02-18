# convert_models.py
import torch
import os
from collections import OrderedDict

# Import the model definitions from the file we created
try:
    from FasNetBackbone import MiniFASNetV2, MiniFASNetV1SE
    print("Successfully imported model architectures from FasNetBackbone.py")
except ImportError:
    print("[ERROR] FasNetBackbone.py not found. Please create it in the same directory.")
    exit()

print("--- Project Sentinel: PyTorch to ONNX Model Converter ---")

# --- Configuration ---
MODEL_DIR = 'models'
# Source PyTorch model filenames
PTH_MODEL_V2 = '2.7_80x80_MiniFASNetV2.pth'
PTH_MODEL_V1SE = '4_0_0_80x80_MiniFASNetV1SE.pth'

# Target ONNX model filenames
ONNX_MODEL_V2 = 'MiniFASNetV2.onnx'
ONNX_MODEL_V1SE = 'MiniFASNetV1SE.onnx'

# --- Function to handle model loading and state dict cleaning ---
def load_and_clean_model(model, pth_path):
    """Loads a .pth file and cleans the state dictionary if needed."""
    print(f"Loading weights from {os.path.basename(pth_path)}...")
    
    # Load the state dictionary from the .pth file
    state_dict = torch.load(pth_path, map_location=torch.device('cpu'))
    
    # The deepface source code shows that sometimes the keys have a 'module.' prefix.
    # We must remove this prefix for the model to load the weights correctly.
    first_key = next(iter(state_dict))
    if first_key.startswith('module.'):
        print("  -> 'module.' prefix detected. Cleaning state dictionary...")
        new_state_dict = OrderedDict()
        for key, value in state_dict.items():
            new_key = key[7:]  # Remove 'module.'
            new_state_dict[new_key] = value
        model.load_state_dict(new_state_dict)
    else:
        print("  -> No prefix detected. Loading state dictionary as is.")
        model.load_state_dict(state_dict)
    
    model.eval() # Set the model to evaluation mode
    print("  -> Weights loaded successfully.")
    return model

# --- Main Conversion Process ---

# 1. Convert MiniFASNetV2
try:
    print("\n[Converting MiniFASNetV2]")
    v2_model = MiniFASNetV2(conv6_kernel=(5, 5))
    v2_model_path = os.path.join(MODEL_DIR, PTH_MODEL_V2)
    v2_model = load_and_clean_model(v2_model, v2_model_path)
    
    # Create a dummy input tensor that matches the model's expected input
    dummy_input = torch.randn(1, 3, 80, 80) 
    
    # Define the output path for the ONNX model
    v2_onnx_path = os.path.join(MODEL_DIR, ONNX_MODEL_V2)
    
    print(f"Exporting to ONNX at {v2_onnx_path}...")
    torch.onnx.export(
        v2_model,
        dummy_input,
        v2_onnx_path,
        verbose=False,
        input_names=['input'],
        output_names=['output']
    )
    print(f"[SUCCESS] Converted {PTH_MODEL_V2} to {ONNX_MODEL_V2}")

except Exception as e:
    print(f"[ERROR] Failed to convert MiniFASNetV2: {e}")

# 2. Convert MiniFASNetV1SE
try:
    print("\n[Converting MiniFASNetV1SE]")
    v1se_model = MiniFASNetV1SE(conv6_kernel=(5, 5))
    v1se_model_path = os.path.join(MODEL_DIR, PTH_MODEL_V1SE)
    v1se_model = load_and_clean_model(v1se_model, v1se_model_path)
    
    dummy_input = torch.randn(1, 3, 80, 80)
    
    v1se_onnx_path = os.path.join(MODEL_DIR, ONNX_MODEL_V1SE)
    
    print(f"Exporting to ONNX at {v1se_onnx_path}...")
    torch.onnx.export(
        v1se_model,
        dummy_input,
        v1se_onnx_path,
        verbose=False,
        input_names=['input'],
        output_names=['output']
    )
    print(f"[SUCCESS] Converted {PTH_MODEL_V1SE} to {ONNX_MODEL_V1SE}")

except Exception as e:
    print(f"[ERROR] Failed to convert MiniFASNetV1SE: {e}")

print("\n--- Conversion process finished. ---")