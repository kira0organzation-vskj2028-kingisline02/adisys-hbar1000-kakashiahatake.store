"""Server-side (Pi) camera. Used when the UI camera source is 'pi'.
Backends tried in order: picamera2 (CSI camera) -> OpenCV VideoCapture (USB/other).
The camera starts on first request and stops itself after IDLE_STOP seconds with no viewer.
Env:
  PI_CAM_W, PI_CAM_H (default 1600x1200 = 2 MP full inspection resolution)
  PI_CAM_FPS (default 25; target 25-30 fps per 11-11-26.md Section 3.5)
  PI_CAM_EXPOSURE_US (default 0=auto; e.g. 60 for blur <= 0.1mm at 100 m/min)
  PI_CAM_GAIN (default 0=auto; e.g. 1.0 - 16.0 analog gain)
  PI_CAM_INDEX (OpenCV fallback device index)
"""
import sys, os, threading, time
for _p in [
    "/usr/lib/python3/dist-packages",
    "/usr/local/lib/python3/dist-packages",
    f"/usr/lib/python3.{sys.version_info.minor}/dist-packages"
]:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import cv2
except Exception:
    cv2 = None

W = int(os.environ.get("PI_CAM_W", 1600))
H = int(os.environ.get("PI_CAM_H", 1200))
FPS = int(os.environ.get("PI_CAM_FPS", 25))
EXPOSURE_US = int(os.environ.get("PI_CAM_EXPOSURE_US", 0))
GAIN = float(os.environ.get("PI_CAM_GAIN", 0.0))
IDLE_STOP = int(os.environ.get("PI_CAM_IDLE_STOP", 30))

class PiCamera:
    def __init__(self):
        self.lock = threading.Lock()
        self.start_lock = threading.Lock()
        self._want_stop = False
        self.running = False
        self.backend = None
        self.error = None
        self.full = None
        self.preview = None
        self.frame_id = 0
        self.frame_time = 0.0
        self._cond = threading.Condition()
        self.last_access = 0.0
        self.last_attempt = 0.0
        self._cam = None
        self._t = None

    def touch(self):
        self.last_access = time.time()

    def start(self, force=False):
        with self.start_lock:
            with self.lock:
                if self.running:
                    self.touch()
                    return
                now = time.time()
                if not force and self.error and (now - self.last_attempt < 2.0):
                    raise RuntimeError(self.error)
                self.last_attempt = now
                self.error = None
                self._want_stop = False

            new_cam = None
            backend = None
            try:
                try:
                    from picamera2 import Picamera2
                    cam = Picamera2()
                    controls = {"FrameRate": FPS}
                    if EXPOSURE_US > 0:
                        controls["ExposureTime"] = EXPOSURE_US
                    if GAIN > 0.0:
                        controls["AnalogueGain"] = GAIN
                    configured = False
                    for fmt in ("RGB888", "BGR888", "XBGR8888"):
                        try:
                            config = cam.create_video_configuration(
                                main={"size": (W, H), "format": fmt},
                                controls=controls
                            )
                            cam.configure(config)
                            configured = True
                            break
                        except Exception:
                            pass
                    if not configured:
                        try:
                            config = cam.create_preview_configuration(main={"size": (W, H)})
                            cam.configure(config)
                            configured = True
                        except Exception:
                            pass
                    if not configured:
                        config = cam.create_preview_configuration()
                        cam.configure(config)
                    cam.start()
                    new_cam = cam
                    backend = "picamera2"
                except Exception as pi_err:
                    if cv2 is None:
                        raise RuntimeError(f"no Pi camera ({pi_err}) and OpenCV is not installed")
                    target_indices = [int(os.environ.get("PI_CAM_INDEX", 0))]
                    for idx in [0, 1, 2, 3, 4, 6, 8]:
                        if idx not in target_indices:
                            target_indices.append(idx)
                    cap = None
                    last_v4l2_err = None
                    for cam_idx in target_indices:
                        if os.name != "nt" and not os.path.exists(f"/dev/video{cam_idx}"):
                            continue
                        api_pref = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
                        c = cv2.VideoCapture(cam_idx, api_pref)
                        if not c.isOpened():
                            c.release()
                            continue
                        try:
                            c.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                        except Exception:
                            pass
                        c.set(cv2.CAP_PROP_FRAME_WIDTH, W)
                        c.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
                        c.set(cv2.CAP_PROP_FPS, FPS)
                        if EXPOSURE_US > 0:
                            try:
                                c.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)     # manual mode on V4L2
                                c.set(cv2.CAP_PROP_EXPOSURE, EXPOSURE_US)
                            except Exception:
                                pass
                        if GAIN > 0.0:
                            try:
                                c.set(cv2.CAP_PROP_GAIN, GAIN)
                            except Exception:
                                pass
                        ok, test_f = c.read()
                        if ok and test_f is not None:
                            cap = c
                            break
                        c.release()
                        last_v4l2_err = f"camera at index {cam_idx} cannot grab frames"

                    if cap is None:
                        raise RuntimeError(f"Pi camera failed ({pi_err}) and no working V4L2 camera found ({last_v4l2_err or 'no devices'})")
                    new_cam = cap
                    backend = "opencv"

                with self.lock:
                    if self._want_stop:
                        if backend == "picamera2":
                            try:
                                new_cam.stop()
                                new_cam.close()
                            except Exception: pass
                        else:
                            try: new_cam.release()
                            except Exception: pass
                        return
                    self._cam = new_cam
                    self.backend = backend
                    self.running = True
                    self.touch()
                    self._t = threading.Thread(target=self._loop, daemon=True)
                    self._t.start()
            except Exception as e:
                with self.lock:
                    self.error = str(e)
                    self._cam = None
                raise

    def _grab(self):
        if self.backend == "picamera2":
            f = self._cam.capture_array()
            if f is not None and len(f.shape) == 3 and f.shape[2] == 4:
                if cv2 is not None:
                    return cv2.cvtColor(f, cv2.COLOR_BGRA2BGR)
                return f[:, :, :3]
            return f
        ok, f = self._cam.read()
        return f if ok else None

    def _loop(self):
        period = 1.0 / FPS
        consecutive_errors = 0
        while self.running:
            if IDLE_STOP > 0 and (time.time() - self.last_access > IDLE_STOP):
                break
            t0 = time.time()
            try:
                f = self._grab()
                if f is not None:
                    consecutive_errors = 0
                    with self._cond:
                        self.full = f
                        self.frame_id += 1
                        self.frame_time = time.time()
                        self._cond.notify_all()
                else:
                    consecutive_errors += 1
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors > 15:
                    if self.running:
                        self.error = str(e)
                    break
            if consecutive_errors > 15:
                break
            time.sleep(max(0.0, period - (time.time() - t0)))
        self.stop()

    def stop(self):
        self._want_stop = True
        with self.lock:
            self.running = False
            with self._cond:
                self._cond.notify_all()
            cam_to_release = self._cam
            self._cam = None
            self.full = None
            self.preview = None
            self.error = None
        if cam_to_release is not None:
            try:
                if self.backend == "picamera2":
                    cam_to_release.stop()
                    cam_to_release.close()
                else:
                    cam_to_release.release()
            except Exception:
                pass

    def wait_new(self, last_id, timeout=1.0):
        """Return (full_frame, frame_id) when a newer frame exists, else (None, last_id)."""
        with self._cond:
            while self.running and (self.full is None or self.frame_id == last_id):
                if not self._cond.wait(timeout):
                    break
            f, fid = self.full, self.frame_id
        if f is not None and fid != last_id:
            self.touch()
            return (f, fid)
        return (None, last_id)

    def preview_if_new(self, last_id, timeout=1.0):
        f, fid = self.wait_new(last_id, timeout)
        if f is None or cv2 is None:
            return None, last_id
        self.touch()
        try:
            h, w = f.shape[:2]
            target_w = 640
            target_h = int(target_w * h / w) if w > 0 else 480
            small = cv2.resize(f, (target_w, target_h))
            return cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes(), fid
        except Exception:
            return None, last_id

    def _wait_frame(self, attr, timeout=1.5):
        self.start()
        t0 = time.time()
        while getattr(self, attr) is None and time.time() - t0 < timeout:
            time.sleep(0.05)
        self.touch()
        v = getattr(self, attr)
        if v is None:
            raise RuntimeError(self.error or "no frame from camera")
        return v

    def full_frame(self, timeout=1.5):
        """Return the uncompressed full-resolution frame (W x H) as a numpy BGR ndarray."""
        return self._wait_frame("full", timeout=timeout)

    def preview_jpeg(self, timeout=1.5):
        f = self._wait_frame("full", timeout=timeout)
        small = cv2.resize(f, (640, int(640 * f.shape[0] / f.shape[1])))
        return cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes()

    def still_jpeg(self, q=90, timeout=1.5):
        f = self._wait_frame("full", timeout=timeout)
        return cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, q])[1].tobytes()

    def info(self):
        return {
            "running": self.running,
            "backend": self.backend,
            "error": self.error,
            "frame_id": self.frame_id,
            "frame_time": self.frame_time,
            "size": [W, H],
            "width": W,
            "height": H,
            "fps": FPS,
            "exposure_us": EXPOSURE_US,
            "gain": GAIN
        }

camera = PiCamera()
