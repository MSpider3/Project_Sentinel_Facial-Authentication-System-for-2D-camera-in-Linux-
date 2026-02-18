# authenticate.py (v2.3 - Fedora Workstation 43 Edition)
# Thin client wrapper using the new SentinelAuthenticator engine

import sys
import os
import argparse
import logging
import time
import cv2
import configparser
import glob
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

# Import new modules
from biometric_processor import SentinelAuthenticator
from camera_stream import CameraStream

# Setup logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("SentinelClient")

# Use X11 (xcb) for Qt
os.environ['QT_QPA_PLATFORM'] = 'xcb'

def review_intrusions():
    """Checks for intrusion screenshots and asks user to review them."""
    blacklist_dir = "models/blacklist"
    if not os.path.exists(blacklist_dir):
        return

    images = glob.glob(os.path.join(blacklist_dir, "intrusion_*.jpg"))
    if not images:
        return

    root = tk.Tk()
    root.withdraw() # Hide main window
    
    if not messagebox.askyesno("Security Alert", f"{len(images)} suspicious login attempts detected while you were away.\nReview them now?"):
        root.destroy()
        return

    review_window = tk.Toplevel(root)
    review_window.title("Intrusion Review")
    
    current_idx = 0
    
    def show_image():
        if current_idx >= len(images):
            review_window.destroy()
            root.destroy()
            return
            
        img_path = images[current_idx]
        try:
            pil_img = Image.open(img_path)
            pil_img = pil_img.resize((400, 300))
            tk_img = ImageTk.PhotoImage(pil_img)
            
            lbl_img.config(image=tk_img)
            lbl_img.image = tk_img
            lbl_info.config(text=f"Image {current_idx+1}/{len(images)}\n{os.path.basename(img_path)}")
        except Exception as e:
            logger.error(f"Error showing image: {e}")
            delete_image() # Skip corrupted

    def keep_blocked():
        nonlocal current_idx
        logger.info(f"Kept blocked: {images[current_idx]}")
        current_idx += 1
        show_image()

    def delete_false_positive():
        nonlocal current_idx
        try:
            os.remove(images[current_idx])
            logger.info(f"Removed false positive: {images[current_idx]}")
        except:
            pass
        current_idx += 1
        show_image()

    lbl_img = tk.Label(review_window)
    lbl_img.pack()
    
    lbl_info = tk.Label(review_window, text="")
    lbl_info.pack()
    
    btn_frame = tk.Frame(review_window)
    btn_frame.pack(pady=10)
    
    tk.Button(btn_frame, text="Keep Blocked (Intruder)", command=keep_blocked, bg="red", fg="white").pack(side=tk.LEFT, padx=10)
    tk.Button(btn_frame, text="Delete (False Positive)", command=delete_false_positive, bg="green", fg="white").pack(side=tk.LEFT, padx=10)
    
    show_image()
    root.wait_window(review_window)

def main(target_user=None):
    # 0. Check for intrusions - REMOVED from startup as per new policy
    # try:
    #     review_intrusions()
    # except Exception as e:
    #     logger.error(f"Failed to run intrusion review: {e}")

    # Load config for camera settings
    config = configparser.ConfigParser()
    config.read('config.ini')
    
    width = config.getint('Camera', 'width', fallback=640)
    height = config.getint('Camera', 'height', fallback=480)
    fps = config.getint('Camera', 'fps', fallback=15)
    
    # Initialize Camera Stream
    logger.info("Starting camera stream...")
    camera = CameraStream(src=0, width=width, height=height, fps=fps).start()
    
    # Initialize Authenticator
    logger.info("Initializing Sentinel Engine...")
    authenticator = SentinelAuthenticator(target_user=target_user)
    if not authenticator.initialize():
        logger.error(f"Initialization failed: {authenticator.message}")
        camera.stop()
        return "FAILURE"
    
    logger.info("Authentication session started.")
    
    final_status = "CANCELLED"
    
    # Main Loop
    try:
        while True:
            frame = camera.read()
            if frame is None:
                continue

            # Process Frame
            state, message, face_box, info = authenticator.process_frame(frame)
            
            # --- Draw UI ---
            display_frame = frame.copy()
            h, w = display_frame.shape[:2]
            
            # Status Bar
            cv2.rectangle(display_frame, (0, 0), (w, 80), (30, 30, 30), -1)
            cv2.putText(display_frame, message[:50], (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
            
            # Face Box
            if face_box:
                x, y, w_box, h_box = face_box
                color = (0, 255, 255) # Yellow (Waiting)
                
                if state == SentinelAuthenticator.STATE_RECOGNIZED:
                    color = (0, 255, 0) # Green
                elif state == SentinelAuthenticator.STATE_FAILURE:
                    color = (0, 0, 255) # Red
                elif state == SentinelAuthenticator.STATE_2FA:
                    color = (255, 165, 0) # Orange
                
                cv2.rectangle(display_frame, (int(x), int(y)), (int(x+w_box), int(y+h_box)), color, 3)
                
                # Confidence
                if 'dist' in info and info['dist'] is not None:
                     dist = info['dist']
                     conf = max(0.0, min(1.0, 1.0 - min(float(dist), 1.0))) * 100
                     cv2.putText(display_frame, f"{conf:.1f}%", (int(x), int(y)+int(h_box)+30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

            # Footer
            cv2.putText(display_frame, "Press 'q' to quit", (20, h-20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

            cv2.imshow("Project Sentinel", display_frame)
            
            # Handle End States
            if state == SentinelAuthenticator.STATE_SUCCESS:
                logger.info(f"SUCCESS! User: {info.get('user')}")
                
                # Check for Golden Zone (Tier 1) to trigger review
                dist = info.get('dist', 1.0)
                # We can access config via authenticator but let's check strictness. 
                # Ideally pass 'active_tier' in info but we can check distance against config.
                # Re-reading config here or accessing authenticator.config
                golden_thresh = authenticator.config.GOLDEN_THRESHOLD
                
                if dist < golden_thresh:
                    logger.info("Golden Zone Match! Checking for intrusions to review...")
                    try:
                        # Stop camera briefly or handle GUI overlap?
                        # Tkinter runs in main thread, so this pauses the loop, which is fine.
                        review_intrusions()
                    except Exception as e:
                        logger.error(f"Review error: {e}")
                
                cv2.waitKey(2000) # Show success for 2s
                final_status = "SUCCESS"
                break
                
            if state == SentinelAuthenticator.STATE_FAILURE:
                logger.info(f"FAILURE: {message}")
                cv2.waitKey(2000) # Show failure for 2s
                final_status = "FAILURE"
                break
                
            if state == SentinelAuthenticator.STATE_2FA:
                logger.info(f"2FA REQUIRED: {message}")
                cv2.waitKey(2000)
                final_status = "REQUIRE_2FA"
                break

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                logger.info("Cancelled by user.")
                final_status = "CANCELLED"
                break

    except KeyboardInterrupt:
        pass
    finally:
        camera.stop()
        cv2.destroyAllWindows()
    
    return final_status

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--user', '-u', type=str, default=None)
    args = parser.parse_args()
    
    status = main(args.user)
    
    if status == "SUCCESS":
        sys.exit(0)
    elif status == "REQUIRE_2FA":
        sys.exit(2)
    elif status == "FAILURE":
        sys.exit(1)
    else:
        sys.exit(1) # Cancelled or other error