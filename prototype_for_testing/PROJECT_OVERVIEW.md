# Project Sentinel: The Comprehensive Guide
**Advanced Adaptive Biometric Security for 2D Camera based Laptops**

## 1. Introduction & Philosophy
Project Sentinel is not just a "face unlock" script; it is a **Software-Defined Security Architecture**. Its goal is to democratize high-security biometric authentication.

Modern security is often gated behind expensive hardware (IR cameras, LiDAR, Depth sensors). Project Sentinel challenges this by proving that **Intelligent Software** can compensate for **Hardware Limitations**. By layering Temporal Tracking, Behavioral Analysis (Liveness), and Texture Analysis (Anti-spoofing), Sentinel transforms a standard $20 webcam into a formidable security gatekeeper.

---

## 2. The Core Problem: 2D vs. 3D
To understand why Sentinel is necessary, we must understand the flaw of standard cameras.

### The "Flatness" Vulnerability
A standard webcam sees the world in 2D (Pixels on a grid). It cannot inherently distinguish between:
1.  A real human face (3D structure, biological skin texture).
2.  A high-resolution photo of that face (2D flat object).
3.  A video of that face played on an iPad (2D flat object with light).

**Why this matters:** A basic "Face Match" algorithm (like seeing if two photos look alike) will say "YES" to all three scenarios above. This renders basic face unlock unsafe.

### The Competitor: Windows Hello / FaceID
Systems like Windows Hello use **Infrared (IR)** and **Depth Projectors**.
-   They project thousands of invisible dots onto your face.
-   They read the distortion of these dots to build a 3D map.
-   A photo is flat, so the map is flat -> **Access Denied.**

### The Sentinel Solution: "Proof of Life"
Sentinel lacks depth sensors, so it relies on **Contextual Nuance**:
1.  **Texture Analysis (Micro-Surface Details):** A photo reflects light differently than skin. A phone screen emits polarized light. Our AI (MiniFASNet) detects these subtle artifacts.
2.  **Temporal Consistency (Tracking):** Real faces move smoothly. Fake faces (held by hand) jitter or appear instantly. Sentinel's Kalman Filter watches for unnatural physics.
3.  **Interactive Liveness (The "Challenge"):** A photo cannot blink on command. A video cannot turn its head left when asked. Sentinel demands active participation.

---

## 3. System Architecture & "The Loop"
The system runs in a high-speed **Sense-Think-Act** loop, processing 15-30 frames per second.

### Phase A: Sense (The Optic Nerve)
*   **File:** `camera_stream.py`
*   **Role:** Raw Data Acquisition.
*   **Why it's special:** Python is slow. If we read the camera in the main loop, the video would freeze every time the AI thinks. Sentinel uses **Threaded Capture**, keeping the latest frame in a memory buffer so the AI is always looking at "Now," not "100ms ago."

### Phase B: Analyze (The Brain)
*   **File:** `biometric_processor.py`
*   **Role:** The Intelligence Core.
*   **The Pipeline:**
    1.  **Detection (YuNet):** A lightweight Neural Network scans the frame for faces. It provides the bounding box `(x, y, w, h)`.
    2.  **Stability (Kalman Filter):** Physics math. It predicts where the face *should* be next. If the detection jumps 500 pixels in 1 frame, Sentinel knows it's a glitch or a "cut" in a video attack, and ignores it.
    3.  **Spoof Check (MiniFASNetV2):** **The Security Gate.** Before we even check *who* it is, we check *what* it is. The cropped face is analyzed for "spoof signals" (Moire patterns, bezel reflections).
        -   *Score < 0.92:* Labeled `FAKE`. Access Denied immediately.
    4.  **Recognition (SFace):** If Real, the face is converted into an **Embedding**—a vector of 128 floating-point numbers.

### Phase C: Context & Decision (The Judge)
*   **File:** `authenticate.py` & `biometric_processor.py`
*   **Role:** Multi-Factor Logic.
*   **The Logic:** We calculate the **Cosine Similarity** (mathematical angle) between the live face vector and your saved vectors.
    -   **Tier 1 (Golden Zone - Dist < 0.25):** The match is perfect. The system trusts this is you *so much* that it may adapt its memory of you (learning your new beard/glasses). -> **EXIT 0 (Success)**
    -   **Tier 2 (Standard Zone - Dist < 0.42):** It's you, but the lighting is odd. Valid login, but no learning. -> **EXIT 0 (Success)**
    -   **Tier 3 (Unsure/2FA - Dist < 0.50):** "It looks like you, but I'm not 100% sure." Secure fallback logic triggers. -> **EXIT 2 (Require Password)**
    -   **Tier 4 (Intruder - Dist > 0.50):** Not you. -> **EXIT 1 (Failure)**

### Phase D: Intrusion Response (The Immun System)
*   **File:** `biometric_processor.py` (BlacklistManager)
*   **Role:** Active Defense.
*   **Action:** If Tier 4 is triggered, the system doesn't just block; it **Records**.
    -   A screenshot is saved to `/var/lib/ProjectSentinel/blacklist/`.
    -   The vector is added to a "Blacklist Memory."
    -   **Future Blocking:** The next frame checks the Blacklist *first*. If the intruder is still there, they are blocked instantly without burning CPU power on full recognition.

---

## 4. Implementation in Linux (Wayland & PAM)
Integrating custom biometrics into modern Linux (Fedora/Ubuntu with Wayland) requires hooking into **PAM (Pluggable Authentication Modules)**.

### The Challenge of Wayland
In the old X11 days, an app could just draw a window over the login screen. Wayland is secure by default; it forbids apps from "stealing" the screen or drawing over the Lock Screen (GDM/SDDM) for security reasons.

### The Solution: `libpam_exec` / `howdy`
We do not write a "Wayland App." We write a **PAM Module Integration**.

#### 1. The Stack
1.  **The Trigger:** When you try to run `sudo` or log in via GDM, Linux calls PAM.
2.  **The Hook:** We modify `/etc/pam.d/system-auth` or `/etc/pam.d/sudo`.
3.  **The Execution:** PAM triggers `pam_exec.so` or `pam_python.so`.
4.  **Our Script:** This runs `authenticate.py`.

#### 2. Visual Feedback in Wayland
Since we cannot pop up a window easily on the GDM Login Screen in Wayland, we have two options:
*   **Option A (The "Howdy" Approach):** We use a specialized CLI interface that pipes video directly to a specific framebuffer or simply shows text status ("Identifying...") while the camera LED provides the "On" feedback.
*   **Option B (The Overlay):** Specific Display Managers (like SDDM) allow themes. We can embed the camera view into the theme, but for standard GDM (GNOME), we rely on **Text Feedback**.

#### 3. Step-by-Step Implementation Guide
**Step 1: System Installation**
Move the project to a secure, root-owned location.
```bash
sudo mkdir -p /usr/lib/project-sentinel
sudo cp -r ./* /usr/lib/project-sentinel/
sudo chmod 755 /usr/lib/project-sentinel/authenticate.py
```

**Step 2: Dependency Handling**
Sentinel needs its Python environment.
```bash
# We use a dedicated venv to avoid breaking system python
sudo python3 -m venv /usr/lib/project-sentinel/venv
sudo /usr/lib/project-sentinel/venv/bin/pip install -r requirements.txt
```

**Step 3: PAM Configuration**
We edit `/etc/pam.d/sudo` (for testing) to place our check *before* the password prompt.
```bash
# In /etc/pam.d/sudo
auth    sufficient      pam_exec.so expose_authtok quiet /usr/lib/project-sentinel/venv/bin/python3 /usr/lib/project-sentinel/authenticate.py
```
*   `sufficient`: If Sentinel exits with `0` (Success), access is granted immediately. No password needed.
*   `pam_exec.so`: The native module that runs our script.

**Step 4: Handling the "Exit Codes"**
*   **Exit 0:** PAM sees "Success". Sudo unlocks.
*   **Exit 1:** PAM sees "Failure". Sudo falls through to the next line (usually standard Password prompt).
*   **Exit 2 (The 2FA Feature):** This is tricky in standard `pam_exec`. Typically, we would map Exit 2 to "Failure" so the password prompt appears (which IS 2-Factor Authentication: Biometric failed/unsure -> Fallback to Password). Effectively, Tier 3 works natively by just failing the "sufficient" check!

**Step 5: Permissions & Hardware Access**
The script runs as `root` (during login) or the user. We must ensure the user has video access:
```bash
sudo usermod -aG video $USER
```
For the "Adaptive Gallery" to work, the directory `/usr/lib/project-sentinel/models/` must be writable by the process owner.

---

## 5. Summary: Competitive Edge
Sentinel competes with 3D cameras not by matching their raw hardware specs, but by outsmarting the attack vectors.
*   **Where 3D relies on Hardware**, Sentinel relies on **Behavior**.
*   **Where 3D is static**, Sentinel is **Adaptive**.
*   **Where 3D is opaque**, Sentinel is **Transparent** (Intrusion Review).

It is the best possible security upgrade for the billions of legacy devices currently in circulation.
