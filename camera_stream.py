import cv2
import threading
import time
import logging

logger = logging.getLogger(__name__)

class CameraStream:
    """
    Threaded camera capture to improve performance.
    Always creates a dedicated thread to read frames from the camera,
    so the main application doesn't block while waiting for I/O.
    """
    def __init__(self, src=0, width=640, height=480, fps=15):
        self.src = src
        self.width = width
        self.height = height
        self.fps = fps
        self.stream = None
        self.stopped = False
        self.grabbed = False
        self.frame = None
        self.thread = None
        self.lock = threading.Lock()

    def start(self):
        """Starts the video stream thread."""
        try:
            self.stream = cv2.VideoCapture(self.src)
            if not self.stream.isOpened():
                logger.warning(f"Camera {self.src} failed to open. Trying index 1...")
                self.stream = cv2.VideoCapture(1)
                if not self.stream.isOpened():
                    logger.error("Failed to open any camera.")
                    return self

            # optimization settings
            self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.stream.set(cv2.CAP_PROP_FPS, self.fps)
            
            # Read first frame to ensure it works
            (self.grabbed, self.frame) = self.stream.read()
            if not self.grabbed:
                logger.error("Failed to grab first frame from camera.")
                self.stop()
                return self

            self.stopped = False
            self.thread = threading.Thread(target=self.update, args=())
            self.thread.daemon = True
            self.thread.start()
            logger.info(f"Camera stream started on device {self.src} ({self.width}x{self.height} @ {self.fps}fps)")
            return self

        except Exception as e:
            logger.error(f"Error starting camera stream: {e}")
            return self

    def update(self):
        """Background thread loop to keep reading frames."""
        while True:
            if self.stopped:
                if self.stream:
                    self.stream.release()
                return

            try:
                (grabbed, frame) = self.stream.read()
                with self.lock:
                    self.grabbed = grabbed
                    if grabbed:
                        self.frame = frame
            except Exception as e:
                logger.error(f"Error in camera read thread: {e}")
                time.sleep(0.1)
            
            # small sleep to prevent burning CPU if camera is slow, 
            # though usually read() blocks essentially acting as sleep.
            # But since we set FPS, read might return fast? 
            # Actually read() blocks until next frame is available.
    
    def read(self):
        """Return the most recent frame."""
        with self.lock:
            if not self.grabbed:
                return None
            return self.frame.copy() if self.frame is not None else None

    def stop(self):
        """Stop the thread and release resources."""
        self.stopped = True
        if self.thread is not None:
            self.thread.join(timeout=1.0)
    
    def __del__(self):
        self.stop()
