#!/usr/bin/env python3
# sentinel-greeter.py - GTK4 Wayland Login Screen with Biometric Authentication
# Primary application for Project Sentinel on Fedora Silverblue with greetd
# type: ignore
import gi
import sys
import os
import json
import socket
import logging
import cv2
import numpy as np
from threading import Thread, Event
from queue import Queue

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf

# Import core biometric engine
from biometric_processor import (
    BiometricProcessor,
    BiometricConfig,
    LivenessValidator,
    FaceEmbeddingStore
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/sentinel/greeter.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ========== GREETD IPC COMMUNICATION ==========
class GreetdIPC:
    """Handles JSON IPC communication with greetd."""
    
    def __init__(self, socket_path='/run/greetd/greeter_socket'):
        self.socket_path = socket_path
        self.socket = None
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def connect(self):
        """Connect to greetd socket."""
        try:
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.connect(self.socket_path)
            self.logger.info("Connected to greetd.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to greetd: {e}")
            return False
    
    def send_message(self, msg_type, **kwargs):
        """Send JSON message to greetd.
        
        Args:
            msg_type: Message type string
            **kwargs: Additional message fields
        """
        try:
            message = {"type": msg_type, **kwargs}
            msg_json = json.dumps(message)
            self.socket.sendall((msg_json + '\n').encode())
            self.logger.info(f"Sent to greetd: {msg_type}")
        except Exception as e:
            self.logger.error(f"Error sending message to greetd: {e}")
    
    def receive_message(self):
        """Receive JSON message from greetd.
        
        Returns:
            dict: Parsed JSON message or None
        """
        try:
            data = self.socket.recv(4096).decode()
            if data:
                message = json.loads(data.strip())
                self.logger.info(f"Received from greetd: {message.get('type', 'unknown')}")
                return message
        except Exception as e:
            self.logger.error(f"Error receiving message from greetd: {e}")
        return None
    
    def close(self):
        """Close connection to greetd."""
        if self.socket:
            self.socket.close()
            self.logger.info("Disconnected from greetd.")


# ========== CAMERA FRAME WORKER ==========
class CameraFrameWorker(Thread):
    """Background thread for camera frame capture and biometric processing."""
    
    def __init__(self, processor, validator, gallery):
        super().__init__(daemon=True)
        self.processor = processor
        self.validator = validator
        self.gallery = gallery
        self.running = False
        self.frame_queue = Queue(maxsize=2)
        self.result_queue = Queue(maxsize=1)
        self.stop_event = Event()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def run(self):
        """Main camera processing loop."""
        self.running = True
        cap = cv2.VideoCapture(0)
        
        if not cap.isOpened():
            self.logger.error("Failed to open camera.")
            self.running = False
            return
        
        self.logger.info("Camera opened successfully.")
        
        while not self.stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                break
            
            try:
                # Try to put frame in queue (skip if full)
                self.frame_queue.put_nowait(frame)
            except:
                pass  # Queue full, skip frame
        
        cap.release()
        self.running = False
        self.logger.info("Camera closed.")
    
    def get_latest_frame(self):
        """Get latest frame from queue.
        
        Returns:
            np.ndarray: BGR image or None
        """
        try:
            return self.frame_queue.get_nowait()
        except:
            return None
    
    def stop(self):
        """Stop the camera worker."""
        self.stop_event.set()


# ========== MAIN GREETER WINDOW ==========
class SentinelGreeterWindow(Gtk.ApplicationWindow):
    """Main GTK4 window for Project Sentinel login screen."""
    
    def __init__(self, app):
        super().__init__(application=app)
        self.app = app
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Initialize components
        self.processor = BiometricProcessor()
        self.validator = LivenessValidator()
        self.store = FaceEmbeddingStore()
        self.greetd = GreetdIPC()
        self.camera_worker = None
        self.matched_user = None
        
        # Load galleries
        self.user_galleries, self.user_names = self.store.load_all_galleries()
        
        if not self.user_galleries:
            self.logger.error("No enrolled users found.")
            self.show_error("No enrolled users found. Please enroll first.")
            return
        
        self.logger.info(f"Loaded {len(self.user_names)} users: {self.user_names}")
        
        # Initialize models
        if not self.processor.initialize_models():
            self.logger.error("Failed to initialize biometric models.")
            self.show_error("Failed to load biometric models.")
            return
        
        # Setup window
        self.set_title("Project Sentinel - Login")
        self.set_default_size(1920, 1080)
        self.set_decorated(False)  # Fullscreen, no decorations
        
        # Make fullscreen
        self.fullscreen()
        
        # Setup UI
        self.setup_ui()
        
        # Connect to greetd
        if not self.greetd.connect():
            self.logger.warning("Not connected to greetd (may be testing locally)")
        
        # Start camera worker
        self.start_camera()
        
        # Start main loop
        self.start_processing()
    
    def setup_ui(self):
        """Setup GTK4 UI components."""
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(main_box)
        
        # CSS styling
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            window {
                background-color: #1a1a1a;
            }
            label {
                color: #ffffff;
            }
            button {
                background-color: #3a3a3a;
                color: #ffffff;
                padding: 10px 20px;
            }
            button:hover {
                background-color: #4a4a4a;
            }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        
        # Top area: Status and user selection
        top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20, margin_top=20, margin_start=20)
        
        self.status_label = Gtk.Label(label="Initializing...")
        self.status_label.set_css_classes(["title"])
        top_box.append(self.status_label)
        
        # User dropdown
        user_model = Gtk.StringList()
        for user in self.user_names:
            user_model.append(user)
        
        self.user_combo = Gtk.DropDown(model=user_model)
        self.user_combo.set_selected(0)
        self.user_combo.connect("notify::selected", self.on_user_changed)
        top_box.append(self.user_combo)
        
        # Spacer
        spacer = Gtk.Box(hexpand=True)
        top_box.append(spacer)
        
        # Password button
        password_btn = Gtk.Button(label="Use Password")
        password_btn.connect("clicked", self.on_password_clicked)
        top_box.append(password_btn)
        
        main_box.append(top_box)
        
        # Central area: Camera feed (using DrawingArea)
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_draw_func(self.draw_camera_frame)
        self.drawing_area.set_hexpand(True)
        self.drawing_area.set_vexpand(True)
        main_box.append(self.drawing_area)
        
        # Bottom area: Prompts and info
        bottom_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            margin_bottom=20,
            margin_start=20,
            margin_end=20
        )
        
        self.prompt_label = Gtk.Label(label="Initializing biometric authentication...")
        bottom_box.append(self.prompt_label)
        
        self.progress_label = Gtk.Label(label="")
        bottom_box.append(self.progress_label)
        
        main_box.append(bottom_box)
    
    def start_camera(self):
        """Start camera worker thread."""
        self.camera_worker = CameraFrameWorker(
            self.processor,
            self.validator,
            self.user_galleries
        )
        self.camera_worker.start()
        self.logger.info("Camera worker started.")
    
    def start_processing(self):
        """Start main authentication processing loop."""
        GLib.timeout_add(33, self.process_frame)  # ~30 FPS
    
    def process_frame(self):
        """Process camera frame and update UI."""
        if not self.camera_worker.running:
            return False
        
        frame = self.camera_worker.get_latest_frame()
        if frame is None:
            return True
        
        # Store frame for drawing
        self.current_frame = frame
        self.drawing_area.queue_draw()
        
        # Process biometrics
        display_frame = frame.copy()
        frame_height, frame_width, _ = display_frame.shape
        
        # Detect faces
        processed_frame, faces = self.processor.detect_faces(frame)
        
        if len(faces) > 0:
            best_face = faces[0]
            
            # Quality check
            is_valid, quality_status = self.processor.validate_face_quality(best_face)
            if not is_valid:
                self.status_label.set_text("Move Closer")
                self.validator.session_active = False
                return True
            
            # Update tracker
            x, y, w, h = self.processor.update_kalman_stability(best_face)
            
            # Check stability
            if not self.processor.is_face_stable():
                self.status_label.set_text("Hold Still...")
                return True
            
            # Spoof detection
            is_live, conf, info = self.processor.check_spoof(frame, best_face)
            if is_live is None:
                self.status_label.set_text("Calibrating...")
                return True
            elif is_live is False:
                self.logger.warning("Spoof detected!")
                self.status_label.set_text("Spoof Detected - Try Again")
                self.validator.reset_session()
                return True
            
            # Start session
            if not self.validator.session_active:
                self.validator.start_session()
            
            # Check timeout
            if self.validator.is_timed_out():
                self.logger.info("Authentication timeout.")
                self.status_label.set_text("Timeout - Please Try Again")
                self.validator.reset_session()
                return True
            
            # Update liveness checks
            self.validator.mark_spoof_check_passed()
            
            # Head movement challenge
            nose_pos = best_face[8:10].astype(int)
            self.validator.update_challenge_progress(best_face, nose_pos)
            
            # Blink detection
            blink_detected, ear = self.processor.detect_blink(frame)
            if blink_detected:
                self.validator.mark_blink_detected()
            
            # Recognition
            if self.validator.all_checks_passed():
                face_roi = self.processor.extract_face_roi(frame, best_face)
                if face_roi is not None:
                    embedding = self.processor.generate_embedding(face_roi)
                    if embedding is not None:
                        matched_user, distance, all_dists = self.processor.identify_user_1n(
                            embedding, self.user_galleries
                        )
                        
                        if distance < BiometricConfig.RECOGNITION_THRESHOLD:
                            self.status_label.set_text(f"Access Granted: {matched_user}")
                            self.logger.info(f"Authentication successful for {matched_user}")
                            
                            # Template adaptation
                            if distance > BiometricConfig.ADAPTATION_THRESHOLD:
                                gallery = self.user_galleries[matched_user]
                                self.processor.adapt_gallery(matched_user, gallery, embedding)
                            
                            # Notify greetd of success
                            self.authenticate_success(matched_user)
                            return False  # Stop processing
                        else:
                            self.status_label.set_text("Unknown User")
                            self.logger.warning(f"No match found. Best: {matched_user} ({distance:.3f})")
                            self.validator.reset_session()
            
            # Update pending checks display
            pending = self.validator.get_pending_checks()
            if pending:
                prompt_text = f"Challenge: Move {self.validator.challenge_type}" if self.validator.challenge_type else ""
                if "blink" in pending:
                    prompt_text += " | Blink to continue"
                self.prompt_label.set_text(prompt_text)
            
            # Draw on display frame
            cv2.rectangle(display_frame, (int(x), int(y)), (int(x+w), int(y+h)), (0, 255, 0), 2)
        
        else:  # No face
            self.processor.reset_kalman_tracker()
            self.validator.increment_face_loss_counter()
            
            if self.validator.session_active and self.validator.should_reset_on_face_loss():
                self.logger.info("Face lost, resetting session.")
                self.validator.reset_session()
                self.status_label.set_text("Face Lost")
            elif not self.validator.session_active:
                self.status_label.set_text("Waiting for face...")
        
        return True
    
    def draw_camera_frame(self, area, cr, width, height, data):
        """Draw camera frame on GTK drawing area."""
        if not hasattr(self, 'current_frame'):
            return
        
        frame = self.current_frame
        h, w, c = frame.shape
        
        # Convert BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Resize to fit window
        aspect_ratio = w / h
        if width / height > aspect_ratio:
            new_h = height
            new_w = int(height * aspect_ratio)
        else:
            new_w = width
            new_h = int(width / aspect_ratio)
        
        frame_rgb = cv2.resize(frame_rgb, (new_w, new_h))
        
        # Convert to GdkPixbuf
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
            GLib.Bytes.new(frame_rgb.tobytes()),
            GdkPixbuf.Colorspace.RGB,
            False,
            8,
            new_w,
            new_h,
            new_w * 3
        )
        
        # Draw on cairo surface
        Gdk.cairo_set_source_pixbuf(cr, pixbuf, (width - new_w) / 2, (height - new_h) / 2)
        cr.paint()
    
    def authenticate_success(self, username):
        """Handle successful authentication."""
        self.logger.info(f"User {username} authenticated successfully.")
        
        # Send success to greetd
        self.greetd.send_message(
            "post_auth_message_response",
            response=f"FACE_AUTH_SUCCESS"
        )
        
        # Notify greetd of successful login
        self.greetd.send_message(
            "start_session",
            session="gnome"
        )
    
    def on_user_changed(self, combo, param):
        """Handle user selection change."""
        selected = self.user_combo.get_selected()
        if selected < len(self.user_names):
            username = self.user_names[selected]
            self.logger.info(f"User selected: {username}")
            self.validator.reset_session()
    
    def on_password_clicked(self, button):
        """Handle password fallback button."""
        self.logger.info("Password fallback requested.")
        self.greetd.send_message("cancel")
    
    def show_error(self, error_msg):
        """Show error message and close."""
        dialog = Gtk.AlertDialog(message=error_msg)
        dialog.choose(self, None, None)
        self.close()


# ========== APPLICATION ==========
class SentinelGreeterApp(Gtk.Application):
    """Main application class."""
    
    def __init__(self):
        super().__init__(application_id='com.projectsentinel.greeter')
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def do_activate(self):
        """Activate application."""
        window = SentinelGreeterWindow(self)
        window.present()


# ========== MAIN ENTRY POINT ==========
if __name__ == "__main__":
    logger.info("Starting Project Sentinel Greeter (Wayland GTK4)")
    app = SentinelGreeterApp()
    exit_code = app.run(sys.argv)
    logger.info("Project Sentinel Greeter closed.")
    sys.exit(exit_code)
