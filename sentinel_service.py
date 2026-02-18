#!/usr/bin/env python3
"""
sentinel_service.py - JSON-RPC Unix Socket Daemon for Project Sentinel
Provides IPC interface between Vala GTK4 UI and Python biometric processor.
Runs as a persistent service to keep models warm.
"""

import socket
import os
import sys
import json
import logging
import threading
import time
import base64
from threading import Thread, Lock, Event

# Ensure consistent working directory (limitations of systemd)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# 1. Set Environment Variables to quiet C++ libraries
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['GLOG_minloglevel'] = '3'
os.environ['LIBGL_DEBUG'] = 'quiet'
os.environ['MESA_DEBUG'] = 'silent'

import warnings
warnings.filterwarnings('ignore')

# --- SILENCER CONTEXT MANAGER ---
class LowLevelSilence:
    """
    Redirects file descriptor 1 (stdout) to /dev/null to silence 
    C libraries (TensorFlow, EGL, OpenCV) that bypass Python's sys.stdout.
    """
    def __enter__(self):
        sys.stdout.flush()
        self.save_fd = os.dup(1)
        self.devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(self.devnull, 1)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.flush()
        os.dup2(self.save_fd, 1)
        os.close(self.devnull)
        os.close(self.save_fd)

# Initialize globals for lazy loading
cv2 = None
np = None
BiometricProcessor = None
BiometricConfig = None
LivenessValidator = None
FaceEmbeddingStore = None
SentinelAuthenticator = None
CameraStream = None

# Setup logging
script_dir = os.path.dirname(os.path.abspath(__file__))
log_dir = os.path.join(script_dir, 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'sentinel_service.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        # Also log to stdout for systemd journalling (which captures stdout)
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("SentinelDaemon")

# ---- DAEMON SOCKET CONFIG ----
DEFAULT_SOCKET_PATH = os.environ.get("SENTINEL_SOCKET_PATH", "/run/sentinel/sentinel.sock")
SOCKET_BACKLOG = 10
# 0o660 allows Owner/Group read/write.
# We expect the daemon to run as 'root' or 'sentinel' user.
# The UI user must be in the 'sentinel' group to connect.
SOCKET_MODE = 0o660  

class SentinelService:
    """JSON-RPC service wrapper for biometric processor"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config = None
        self.processor = None
        self.validator = None
        self.store = None
        self.authenticator = None
        self.camera = None
        self.current_mode = None
        self.lock = Lock()
        
        # Enrollment state
        self.enroll_user = None
        self.enroll_poses = []
        self.enroll_current_pose = 0
        self.enroll_gallery = []

        # Daemon warmup state
        self.warmed = False
        self.warmup_error = None
        self.init_in_progress = False
        self._init_done = Event()
        self._init_done.set()
        
    def initialize(self, params):
        """Initialize the biometric processor and models (Thread-safe, Idempotent)"""
        global cv2, np, BiometricProcessor, BiometricConfig, LivenessValidator, FaceEmbeddingStore, SentinelAuthenticator, CameraStream
        
        # Fast path if already warmed
        if self.warmed:
            return {"success": True, "already": True}

        # If another thread is initializing, wait for it
        if self.init_in_progress:
            timeout = float(params.get("timeout_sec", 120)) if isinstance(params, dict) else 120.0
            self._init_done.wait(timeout=timeout)
            if self.warmed:
                return {"success": True, "already": True}
            return {"success": False, "error": self.warmup_error or "Initialization in progress"}

        self.init_in_progress = True
        self._init_done.clear()
        
        try:
            self.logger.info("Initializing Sentinel Service (Warmup)...")
            
            # Lazy import heavy libraries
            with LowLevelSilence():
                import cv2 as _cv2
                import numpy as _np
                from biometric_processor import (
                    BiometricProcessor as _BP,
                    BiometricConfig as _BC,
                    LivenessValidator as _LV,
                    FaceEmbeddingStore as _FES,
                    SentinelAuthenticator as _SA
                )
                from camera_stream import CameraStream as _CS
                
                cv2 = _cv2
                np = _np
                BiometricProcessor = _BP
                BiometricConfig = _BC
                LivenessValidator = _LV
                FaceEmbeddingStore = _FES
                SentinelAuthenticator = _SA
                CameraStream = _CS
                
                # Force re-enable stdout buffering for python logic if needed
                # (LowLevelSilence restores original FD, but libraries might have messed with buffers)
                pass

            self.config = BiometricConfig()
            self.processor = BiometricProcessor()
            self.validator = LivenessValidator()
            self.store = FaceEmbeddingStore()
            
            if not self.processor.initialize_models():
                self.warmup_error = "Failed to initialize models"
                self.warmed = False
                return {"success": False, "error": self.warmup_error}
            
            self.warmup_error = None
            self.warmed = True
            self.logger.info("Sentinel Service warmup complete.")
            return {"success": True}
        except Exception as e:
            self.warmup_error = str(e)
            self.warmed = False
            self.logger.error(f"Initialization error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            self.init_in_progress = False
            self._init_done.set()

    def status(self, params):
        """Lightweight status check"""
        return {
            "success": True,
            "warmed": bool(self.warmed),
            "init_in_progress": bool(self.init_in_progress),
            "error": self.warmup_error
        }

    # --- CORE METHODS ---

    def start_authentication(self, params):
        try:
            target_user = params.get('user', None)
            
            # Re-verify store loaded
            if not self.store: self.store = FaceEmbeddingStore()
            
            user_galleries, user_names = self.store.load_all_galleries()
            if not user_galleries:
                return {"success": False, "error": "No enrolled users found"}
            
            if target_user and self.store.check_expiry(target_user, max_days=45):
                 return {"success": False, "error": "BIOMETRICS_EXPIRED"}
            
            self.authenticator = SentinelAuthenticator(target_user=target_user)
            if not self.authenticator.initialize():
                return {"success": False, "error": self.authenticator.message}
            
            width = self.config.config.getint('Camera', 'width', fallback=640)
            height = self.config.config.getint('Camera', 'height', fallback=480)
            fps = self.config.config.getint('Camera', 'fps', fallback=15)
            
            if self.camera: self.camera.stop()
            self.camera = CameraStream(src=0, width=width, height=height, fps=fps).start()
            self.current_mode = 'auth'
            
            return {"success": True, "users": user_names, "target_user": target_user}
        except Exception as e:
            self.logger.error(f"Start auth error: {e}")
            return {"success": False, "error": str(e)}

    def process_auth_frame(self, params):
        if self.current_mode != 'auth' or not self.camera or not self.authenticator:
            return {"success": False, "error": "Authentication not started"}
        
        try:
            frame = self.camera.read()
            if frame is None:
                return {"success": False, "error": "No frame available"}
            
            state, message, face_box, info = self.authenticator.process_frame(frame)
            
            # Encode frame as base64 JPEG for preview
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            frame_b64 = base64.b64encode(buffer).decode('utf-8')
            
            return {
                "success": True,
                "state": state or "UNKNOWN",
                "message": message or "",
                "face_box": face_box,
                "info": info or {},
                "frame": frame_b64 or ""
            }
        except Exception as e:
            self.logger.error(f"Frame error: {e}")
            return {"success": False, "error": str(e)}

    def stop_authentication(self, params):
        try:
            if self.camera:
                self.camera.stop()
                self.camera = None
            self.authenticator = None
            self.current_mode = None
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- HEADLESS PAM AUTHENTICATION ---
    def authenticate_pam(self, params):
        """
        Headless authentication for GDM/Lockscreen.
        Runs its own loop for up to 5 seconds. Returns SUCCESS/FAILURE immediately.
        """
        target_user = params.get('user')
        self.logger.info(f"PAM: Authentication request for user '{target_user}'")
        
        # Ensure warmed up
        if not self.processor: 
            self.initialize({})
            
        try:
            # Setup Authenticator
            auth = SentinelAuthenticator(target_user=target_user)
            if not auth.initialize():
                self.logger.warning("PAM: Authenticator init failed")
                return {"success": True, "result": "ERROR"}

            # Start Camera (Short-lived)
            width = self.config.config.getint('Camera', 'width', fallback=640)
            height = self.config.config.getint('Camera', 'height', fallback=480)
            
            cam = CameraStream(src=0, width=width, height=height, fps=15).start()
            
            # Allow camera to warmup slightly
            time.sleep(0.5)
            
            start_time = time.time()
            timeout = 5.0 
            status = "FAILED"
            
            while time.time() - start_time < timeout:
                frame = cam.read()
                if frame is None:
                    time.sleep(0.05)
                    continue
                
                # Process logic
                state, msg, _, info = auth.process_frame(frame)
                dist = info.get('dist', 1.0) if info else 1.0
                
                if state == "SUCCESS":
                    self.logger.info(f"PAM: SUCCESS for {target_user} (Dist: {dist:.3f})")
                    status = "SUCCESS"
                    break
                
                # Continue if FAILURE/LOCKOUT/etc until timeout
                time.sleep(0.03)
                
            cam.stop()
            self.logger.info(f"PAM: Finished with status {status}")
            return {"success": True, "result": status}
            
        except Exception as e:
            self.logger.error(f"PAM Error: {e}")
            return {"success": True, "result": "ERROR"}


    # --- ENROLLMENT METHODS ---
    def start_enrollment(self, params):
        try:
            if self.processor is None: self.initialize({})
            
            user_name = params.get('user_name', '').lower().strip()
            
            if not user_name: return {"success": False, "error": "User name required"}
            
            user_galleries, user_names = self.store.load_all_galleries()
            if user_name in user_names:
                return {"success": False, "error": f"User '{user_name}' already enrolled"}
            
            # Simplified Pose Logic
            base_poses = [
                {"name": "Center", "instruction": "Look directly at the camera"},
                {"name": "Left", "instruction": "Turn head LEFT"},
                {"name": "Right", "instruction": "Turn head RIGHT"},
                {"name": "Up", "instruction": "Tilt head UP"},
                {"name": "Down", "instruction": "Tilt head DOWN"},
            ]
            
            poses = base_poses
            
            self.enroll_user = user_name
            self.enroll_poses = poses
            self.enroll_current_pose = 0
            self.enroll_gallery = []
            
            width = self.config.config.getint('Camera', 'width', fallback=640)
            height = self.config.config.getint('Camera', 'height', fallback=480)
            
            if self.camera: self.camera.stop()
            self.camera = CameraStream(src=0, width=width, height=height, fps=15).start()
            self.current_mode = 'enroll'
            
            return {
                "success": True, "user_name": user_name,
                "total_poses": len(poses), "current_pose": 0, "pose_info": poses[0]
            }
        except Exception as e:
            self.logger.error(f"Enroll start error: {e}")
            return {"success": False, "error": str(e)}

    def process_enroll_frame(self, params):
        if self.current_mode != 'enroll' or not self.camera:
            return {"success": False, "error": "Enrollment not started"}
        try:
            frame = self.camera.read()
            if frame is None: return {"success": False, "error": "No frame"}
            
            if self.enroll_current_pose >= len(self.enroll_poses):
                return {"success": True, "completed": True, "message": "Enrollment complete!"}
            
            pose = self.enroll_poses[self.enroll_current_pose]
            processed_frame, faces = self.processor.detect_faces(frame)
            
            status = "no_face"
            face_box = None
            if len(faces) == 1:
                face_box = faces[0][0:4].astype(int).tolist()
                is_valid, q_stat = self.processor.validate_face_quality(faces[0])
                status = "ready" if is_valid else q_stat
            elif len(faces) > 1:
                status = "multiple_faces"
                
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            frame_b64 = base64.b64encode(buffer).decode('utf-8')
            
            return {
                "success": True, "completed": False,
                "current_pose": self.enroll_current_pose,
                "total_poses": len(self.enroll_poses),
                "pose_info": pose, "status": status,
                "face_box": face_box, "frame": frame_b64
            }
        except Exception as e:
             return {"success": False, "error": str(e)}

    def capture_enroll_pose(self, params):
        if self.current_mode != 'enroll': return {"success": False, "error": "Not enrolling"}
        try:
            frame = self.camera.read()
            if frame is None: return {"success": False, "error": "No frame"}
            
            processed_frame, faces = self.processor.detect_faces(frame)
            if len(faces) != 1: return {"success": False, "error": "Face detection failed"}
            
            face_box = faces[0][0:4].astype(int)
            x, y, w, h = face_box
            face_roi = frame[y:y+h, x:x+w]
            
            recognizer_input_shape = self.processor.recognizer.get_inputs()[0].shape[2:]
            recognizer_input_name = self.processor.recognizer.get_inputs()[0].name
            
            face_resized = cv2.resize(face_roi, recognizer_input_shape)
            face_rgb = cv2.cvtColor(face_resized, cv2.COLOR_BGR2RGB)
            face_transposed = np.transpose(face_rgb, (2, 0, 1))
            face_input = np.expand_dims(face_transposed, axis=0).astype('float32')
            
            embedding = self.processor.recognizer.run(None, {recognizer_input_name: face_input})[0]
            
            self.enroll_gallery.append(embedding)
            self.enroll_current_pose += 1
            
            if self.enroll_current_pose >= len(self.enroll_poses):
                # Save
                gallery_array = np.vstack(self.enroll_gallery)
                output_path = os.path.join(self.config.MODEL_DIR, f"gallery_{self.enroll_user}.npy")
                np.save(output_path, gallery_array)
                self.logger.info(f"Enrollment saved for {self.enroll_user}")
                
                return {"success": True, "completed": True, "message": "Enrollment Saved!"}
                
            return {
                "success": True, "completed": False, 
                "current_pose": self.enroll_current_pose,
                "pose_info": self.enroll_poses[self.enroll_current_pose]
            }
        except Exception as e:
            self.logger.error(f"Capture error: {e}")
            return {"success": False, "error": str(e)}

    def stop_enrollment(self, params):
        try:
            if self.camera: 
                self.camera.stop()
                self.camera = None
            self.current_mode = None
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- CONFIG & UTILS ---
    def get_config(self, params):
        if not self.config: self.config = BiometricConfig()
        cfg = self.config.config
        return {
            "success": True,
            "config": {
                'camera_width': cfg.getint('Camera', 'width', fallback=640),
                'camera_height': cfg.getint('Camera', 'height', fallback=480),
                'golden_threshold': cfg.getfloat('Security', 'golden_threshold', fallback=0.25),
                'standard_threshold': cfg.getfloat('Security', 'standard_threshold', fallback=0.42),
                'twofa_threshold': cfg.getfloat('Security', 'two_factor_threshold', fallback=0.50),
            }
        }
    
    def update_config(self, params):
        return {"success": True}

    def get_enrolled_users(self, params):
        if not self.store: self.store = FaceEmbeddingStore()
        _, names = self.store.load_all_galleries()
        return {"success": True, "users": names}
        
    def get_intrusions(self, params):
        import glob
        if not self.config: self.config = BiometricConfig()
        blacklist_dir = self.config.BLACKLIST_DIR
        images = sorted(glob.glob(os.path.join(blacklist_dir, "intrusion_*.jpg")))
        return {"success": True, "files": images}

    def delete_intrusion(self, params):
        filename = params.get('filename')
        from biometric_processor import BlacklistManager
        bm = BlacklistManager()
        bm.delete_intrusion_record(filename)
        return {"success": True}
        
    def confirm_intrusion(self, params):
        filename = params.get('filename')
        from biometric_processor import BlacklistManager
        bm = BlacklistManager()
        bm.confirm_intrusion(filename)
        return {"success": True}


# --- RPC DISPATCHER ---
def _build_methods(service: SentinelService):
    return {
        "status": service.status,
        "initialize": service.initialize,
        "start_authentication": service.start_authentication,
        "process_auth_frame": service.process_auth_frame,
        "stop_authentication": service.stop_authentication,
        "authenticate_pam": service.authenticate_pam,
        "start_enrollment": service.start_enrollment,
        "process_enroll_frame": service.process_enroll_frame,
        "capture_enroll_pose": service.capture_enroll_pose,
        "stop_enrollment": service.stop_enrollment,
        "get_enrolled_users": service.get_enrolled_users,
        "get_config": service.get_config,
        "update_config": service.update_config,
        "get_intrusions": service.get_intrusions,
        "delete_intrusion": service.delete_intrusion,
        "confirm_intrusion": service.confirm_intrusion,
    }

def _rpc_error(request_id, code, message):
    return {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": request_id}

def _rpc_result(request_id, result):
    return {"jsonrpc": "2.0", "result": result, "id": request_id}

def _handle_rpc_line(service: SentinelService, methods: dict, line: str):
    try:
        request = json.loads(line)
        method = request.get("method")
        params = request.get("params", {}) or {}
        request_id = request.get("id", None)

        if request_id is None: return None # Notification

        if method not in methods:
            return _rpc_error(request_id, -32601, f"Method '{method}' not found")

        func = methods[method]
        
        # Don't lock entire status check, but lock logic methods
        # to ensure thread safety on Camera/Processor
        if method == "status":
             result = func(params)
        else:
             with service.lock:
                 result = func(params)
                 
        return _rpc_result(request_id, result)
        
    except json.JSONDecodeError:
        return _rpc_error(None, -32700, "Parse error")
    except Exception as e:
        logger.exception("RPC method failed: %s", e)
        return _rpc_error(request_id, -32603, str(e))

def _handle_client(conn: socket.socket, service: SentinelService, methods: dict):
    try:
        conn.settimeout(300) # 5m timeout
        buffer = ""
        while True:
            chunk = conn.recv(4096)
            if not chunk: break
            
            buffer += chunk.decode('utf-8', errors='replace')
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line: continue
                
                # Process
                resp = _handle_rpc_line(service, methods, line)
                if resp:
                    out = (json.dumps(resp, ensure_ascii=False) + "\n").encode('utf-8')
                    conn.sendall(out)
    except socket.timeout:
        pass
    except Exception as e:
        logger.exception("Client handler error: %s", e)
    finally:
        try: conn.close()
        except: pass

def _create_server_socket(socket_path):
    sock_dir = os.path.dirname(socket_path)
    os.makedirs(sock_dir, exist_ok=True)
    
    try: os.unlink(socket_path)
    except FileNotFoundError: pass
    
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_path)
    # Important: Permissions
    try:
        os.chmod(socket_path, SOCKET_MODE) 
        # Attempt to chown to current user if running as root for testing??
        # Ideally setup.sh handles this by running as correct user or permissions
    except Exception as e:
        logger.warning(f"Could not chmod socket: {e}")
        
    server.listen(SOCKET_BACKLOG)
    return server

def main():
    service = SentinelService()
    methods = _build_methods(service)
    
    socket_path = DEFAULT_SOCKET_PATH
    logger.info(f"Sentinel daemon starting. Socket={socket_path}")
    
    try:
        server = _create_server_socket(socket_path)
    except Exception as e:
        logger.error(f"Failed to create socket: {e}")
        sys.exit(1)
        
    # Async warmup
    def _warmup():
        try:
            logger.info("Warmup thread starting...")
            # We use a long timeout for internal init
            service.initialize({"timeout_sec": 300}) 
            logger.info("Warmup finished.")
        except Exception as e:
            logger.error(f"Warmup thread failed: {e}")
            
    Thread(target=_warmup, daemon=True).start()
    
    logger.info("Sentinel daemon listening...")
    
    try:
        while True:
            conn, _ = server.accept()
            # Handle client in a thread
            Thread(target=_handle_client, args=(conn, service, methods), daemon=True).start()
    except KeyboardInterrupt:
        logger.info("Stopping...")
    finally:
        server.close()
        try: os.unlink(socket_path)
        except: pass

if __name__ == "__main__":
    main()
