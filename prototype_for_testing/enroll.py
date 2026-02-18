# enroll.py
import cv2
import numpy as np
import onnxruntime as ort
import os
import time
import tkinter as tk
from tkinter import messagebox, simpledialog

# Suppress harmless ONNX Runtime warnings
ort.set_default_logger_severity(3)

print("--- Project Sentinel: Smart Enrollment ---")

# --- Configuration ---
MODEL_DIR = 'models'
DETECTOR_MODEL_FILE = 'face_detection_yunet_2023mar.onnx'
RECOGNIZER_MODEL_FILE = 'face_recognition_sface_2021dec.onnx'
OUTPUT_GALLERY_FILE = 'user_gallery.npy'

# --- Load Models ---
print("Loading models...")
try:
    face_detector = cv2.FaceDetectorYN.create(
        model=os.path.join(MODEL_DIR, DETECTOR_MODEL_FILE), config="",
        input_size=(320, 320), score_threshold=0.9, nms_threshold=0.3, top_k=5000
    )
    providers = ['OpenVINOExecutionProvider', 'CPUExecutionProvider']
    face_recognizer = ort.InferenceSession(os.path.join(MODEL_DIR, RECOGNIZER_MODEL_FILE), providers=providers)
    print("All models loaded successfully.")
except Exception as e:
    print(f"Error loading models: {e}"); exit()

# --- Get Recognizer Model Input Details ---
recognizer_input_name = face_recognizer.get_inputs()[0].name
recognizer_input_shape = face_recognizer.get_inputs()[0].shape[2:]

# --- NEW: GUI Function to get user info before starting ---
def get_user_info():
    """Creates a GUI window to get user's name and glasses info."""
    root = tk.Tk()
    root.withdraw() # Hide the main tkinter window

    # Display instructions
    messagebox.showinfo(
        "Enrollment Instructions",
        "Welcome to Project Sentinel Enrollment!\n\n"
        "Please follow these instructions for best results:\n\n"
        "1. Sit in a well-lit room, facing the light.\n"
        "2. Remove any hats or obstructions from your face.\n"
        "3. Make sure you are the only person in the camera's view.\n\n"
        "You will be asked to hold several poses."
    )

    # Ask for user's name
    user_name = simpledialog.askstring("User Name", "Please enter your name (e.g., 'alex'):")
    if not user_name: # If user cancels or enters nothing
        return None, False

    # Ask if they wear glasses
    wears_glasses = messagebox.askyesno("Glasses Information", "Do you wear glasses?")
    
    root.destroy()
    return user_name.lower(), wears_glasses

# --- Helper function to generate embedding ---
def generate_embedding(face_roi):
    """Generates a 128-d embedding from a cropped face image."""
    recognizer_input = cv2.resize(face_roi, recognizer_input_shape)
    recognizer_input = cv2.cvtColor(recognizer_input, cv2.COLOR_BGR2RGB)
    recognizer_input = np.transpose(recognizer_input, (2, 0, 1))
    recognizer_input = np.expand_dims(recognizer_input, axis=0).astype('float32')
    embedding = face_recognizer.run(None, {recognizer_input_name: recognizer_input})[0]
    return embedding

def preprocess_frame(frame):
    """Enhance image for better face detection in challenging lighting."""
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    enhanced = cv2.merge([l, a, b])
    enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
    return enhanced

# --- Main Enrollment Logic ---
# --- Main Enrollment Logic ---
def run_enrollment():
    # 1. Get user info from the GUI
    user_name, wears_glasses = get_user_info()
    
    if not user_name:
        print("Enrollment cancelled by user.")
        return

    # 2. Define the dynamic sequence of poses
    base_poses = [
        {"name": "Center", "instruction": "Look directly at the camera"},
        {"name": "Left", "instruction": "Slowly turn your head to the LEFT"},
        {"name": "Right", "instruction": "Slowly turn your head to the RIGHT"},
        {"name": "Up", "instruction": "Slowly tilt your head UP"},
        {"name": "Down", "instruction": "Slowly tilt your head DOWN"},
    ]
    
    poses = []
    if wears_glasses:
        # If they wear glasses, do a full set with and without
        for pose in base_poses:
            poses.append({"name": f"{pose['name']} (With Glasses)", "instruction": f"{pose['instruction']} (with glasses on)"})
        poses.append({"name": "Remove Glasses", "instruction": "Please remove your glasses now"})
        for pose in base_poses:
            poses.append({"name": f"{pose['name']} (No Glasses)", "instruction": f"{pose['instruction']} (with glasses off)"})
    else:
        # Otherwise, just do the base poses
        poses = base_poses

    face_gallery = []
    video_capture = cv2.VideoCapture(0)
    if not video_capture.isOpened():
        print("Error: Could not open webcam."); return

    current_pose_index = 0
    capture_countdown = -1

    # --- NEW: State machine variables for a mobile-style experience ---
    # States can be: "INSTRUCT", "DETECTING", "SUCCESS"
    current_state = "INSTRUCT"
    # Timer for delays (in frames). 90 frames is ~3 seconds at 30fps.
    state_timer = 90

    while True: # Loop will now be broken internally
        ret, frame = video_capture.read()
        if not ret: break

        # Gracefully exit if all poses are done
        if current_pose_index >= len(poses):
            break

        pose = poses[current_pose_index]
        display_frame = frame.copy()
        frame_height, frame_width, _ = display_frame.shape
        
        status_text = ""
        status_color = (255, 255, 255)

        # --- STATE MACHINE LOGIC ---

        if current_state == "INSTRUCT":
            # State 1: Show the instruction and pause for 3 seconds.
            status_text = pose["instruction"]
            status_color = (255, 150, 0) # Orange
            cv2.putText(display_frame, f"GET READY...", (frame_width // 2 - 100, frame_height // 2), cv2.FONT_HERSHEY_SIMPLEX, 1, status_color, 2)
            
            state_timer -= 1
            if state_timer <= 0:
                current_state = "DETECTING" # Move to next state

        elif current_state == "DETECTING":
            # State 2: Actively look for a face and run the countdown.
            status_text = pose["instruction"] # Keep showing the instruction
            status_color = (0, 255, 255) # Yellow

            # Apply lighting correction before detection
            processed_frame = preprocess_frame(display_frame)
            
            face_detector.setInputSize((frame_width, frame_height))
            _, faces = face_detector.detect(processed_frame)
            faces = faces if faces is not None else []

            if len(faces) == 1:
                box = faces[0][0:4].astype(int)
                x, y, w, h = box
                cv2.rectangle(display_frame, (x, y), (x + w, y + h), status_color, 2)
                
                if capture_countdown == -1: capture_countdown = 30 # Start countdown
                capture_countdown -= 1
                status_text = f"Hold still... {capture_countdown // 10}"

                if capture_countdown <= 0:
                    face_roi = frame[y:y+h, x:x+w]
                    if face_roi.size > 0:
                        print(f"Capturing embedding for pose: {pose['name']}...")
                        embedding = generate_embedding(face_roi)
                        face_gallery.append(embedding)
                        
                        current_state = "SUCCESS"
                        state_timer = 60 # Set a 2-second timer for the success message
            else:
                # If face is lost, reset the countdown
                capture_countdown = -1
                status_text = "Please position your face in the camera"
        
        elif current_state == "SUCCESS":
            # State 3: Show a success message, then prepare for the next pose.
            status_text = "Great! Get Ready..."
            status_color = (0, 255, 0) # Green
            
            state_timer -= 1
            if state_timer <= 0:
                current_pose_index += 1
                capture_countdown = -1
                current_state = "INSTRUCT"
                state_timer = 90 # Reset timer for the next 3-second instruction pause

        # Draw UI text ON THE CAMERA WINDOW
        cv2.putText(display_frame, f"Step {current_pose_index + 1}/{len(poses)}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(display_frame, status_text, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
        
        # --- Special instruction for removing glasses (This part remains the same) ---
        if "Remove Glasses" in pose['name'] and current_state == "INSTRUCT" and state_timer == 89: # Show it once
            cv2.putText(display_frame, "Please remove your glasses.", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
            cv2.putText(display_frame, "Press any key to continue...", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.imshow('Project Sentinel - Enrollment', display_frame)
            cv2.waitKey(0)
            state_timer = 0 # Skip the rest of the pause

        cv2.imshow('Project Sentinel - Enrollment', display_frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Enrollment cancelled by user.")
            face_gallery = []
            break

    video_capture.release()
    cv2.destroyAllWindows()

    if len(face_gallery) > 0 and (current_pose_index == len(poses)):
        print("\nEnrollment complete!")
        gallery_array = np.vstack(face_gallery)
        print(f"Created a gallery with {gallery_array.shape[0]} embeddings.")
        
        # 3. Save the gallery with the user's name
        output_filename = f"gallery_{user_name}.npy"
        output_path = os.path.join(MODEL_DIR, output_filename)
        np.save(output_path, gallery_array)
        print(f"Successfully saved user gallery to: {output_path}")
    else:
        print("\nEnrollment did not complete. No data was saved.")

if __name__ == "__main__":
    run_enrollment()