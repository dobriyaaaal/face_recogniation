import os
import sys
import time
import pickle
import threading
import datetime
import queue
from pathlib import Path

import numpy as np
import cv2
import torch
import pygame
from insightface.app import FaceAnalysis

# --- Add YOLOv5 path (relative to repo root) ---
YOLO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'yolov5'))
if YOLO_PATH not in sys.path:
    sys.path.insert(0, YOLO_PATH)

from yolov5.models.common import DetectMultiBackend
from yolov5.utils.general import non_max_suppression, scale_boxes as yv5_scale_boxes

# =========================
# Config / Tunables
# =========================
YOLO_CONF_THRES = 0.40
YOLO_IOU_THRES  = 0.45
YOLO_CLASS_PEDESTRIAN = [0]  # 'person' class

# Run YOLO once every N frames to save CPU. In-between, reuse last boxes.
YOLO_EVERY_N = 3

# Head extraction & upsample (to help small faces)
HEAD_FRAC = 0.35                 # top 35% of person box is "head" region
UPSAMPLE_PERSON_HEIGHT_PX = 180  # if person bbox height < this, upsample head crop x2

# Face quality gates
MIN_FACE_BOX_SIDE = 30           # skip faces smaller than this (px) after mapping to full frame
MIN_FACE_DET_SCORE = 0.5         # skip low-det-score faces from InsightFace

# Similarity / recognition
SIM_THRESHOLD = 0.40

# Alert/screenshot cooldowns
SOUND_COOLDOWN_SECONDS = 10
SCREENSHOT_COOLDOWN_SECONDS = 10

# Devices
yolo_device = torch.device('cpu')  # keep YOLO on CPU (you can swap to GPU if free)
face_device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# =========================
# Globals
# =========================
app = None
face_db = {}
_initialized = False
init_lock = threading.Lock()
yolo_model = None

# frame cadence state
_frame_idx = 0
_last_person_boxes = []  # list of [x1,y1,x2,y2] in original frame coords
_last_yolo_frame_idx = -999

# audio / cooldown state
_sound = None
_alert_lock = threading.Lock()
_last_sound_time = {}

# screenshot cooldowns
_last_screenshot_time = {}

# background workers
_screenshot_q = queue.Queue(maxsize=64)
_screenshot_thread = None
_workers_started = False


# =========================
# Utilities
# =========================
def log(msg):
    print(f"[INFO] {msg}")

def warn(msg):
    print(f"[WARNING] {msg}")

def clamp_box(x1, y1, x2, y2, W, H):
    x1 = max(0, min(W - 1, x1))
    x2 = max(0, min(W - 1, x2))
    y1 = max(0, min(H - 1, y1))
    y2 = max(0, min(H - 1, y2))
    if x2 < x1: x1, x2 = x2, x1
    if y2 < y1: y1, y2 = y2, y1
    return x1, y1, x2, y2

def letterbox(im, new_shape=(640, 640), color=(114, 114, 114)):
    # keep ratio and add padding
    shape = im.shape[:2]  # (h, w)
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]  # wh padding
    dw /= 2
    dh /= 2
    im = cv2.resize(im, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    im = cv2.copyMakeBorder(im, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)
    return im, r, (dw, dh)

def head_roi_from_person(frame, box, head_frac=HEAD_FRAC):
    x1, y1, x2, y2 = box
    H, W = frame.shape[:2]
    h = max(1, y2 - y1)
    head_h = max(1, int(h * head_frac))
    hx1, hy1 = x1, y1
    hx2, hy2 = x2, y1 + head_h
    hx1, hy1, hx2, hy2 = clamp_box(hx1, hy1, hx2, hy2, W, H)
    return hx1, hy1, hx2, hy2

def _start_workers_once():
    global _workers_started, _screenshot_thread
    if _workers_started:
        return
    _screenshot_thread = threading.Thread(target=_screenshot_worker, name="screenshot-writer", daemon=True)
    _screenshot_thread.start()
    _workers_started = True

def _screenshot_worker():
    while True:
        try:
            name, frame = _screenshot_q.get()
            folder = os.path.join("detections", name)
            os.makedirs(folder, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(folder, f"{timestamp}.jpg")
            cv2.imwrite(filepath, frame)
        except Exception as e:
            warn(f"Screenshot error: {e}")
        finally:
            _screenshot_q.task_done()

# =========================
# Init / Teardown
# =========================
def initialize_detector():
    """
    Prepare InsightFace (GPU if available), load embeddings, load YOLO (CPU),
    pre-load alert sound, and start background workers.
    """
    global app, face_db, _initialized, yolo_model, _sound

    with init_lock:
        if _initialized:
            return

        try:
            log("Preparing face recognition model (InsightFace)...")
            app = FaceAnalysis(name='buffalo_s')
            # Larger det_size helps for small / far faces
            app.prepare(ctx_id=0 if face_device.type == 'cuda' else -1, det_size=(960, 960))

            log("Loading known face embeddings...")
            with open('embeddings/face_db.pkl', 'rb') as f:
                face_db.update(pickle.load(f))

            yolo_weights = os.path.join(YOLO_PATH, 'yolov5n.pt')
            if not os.path.exists(yolo_weights):
                raise FileNotFoundError(f"YOLOv5 weights not found at {yolo_weights}")

            log("Loading object detection model (YOLOv5) on CPU...")
            yolo_model = DetectMultiBackend(yolo_weights, device=yolo_device)
            yolo_model.eval()

            # Init sound (preload sound clip)
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                _sound = pygame.mixer.Sound("alert.mp3")
            except Exception as e:
                warn(f"Audio init error (continuing without sound): {e}")
                _sound = None

            _start_workers_once()
            log("Detector initialized successfully.")
            _initialized = True

        except Exception as e:
            warn(f"Detector initialization failed: {e}")
            import traceback
            traceback.print_exc()
            _initialized = False

# =========================
# Recognition helpers
# =========================
def recognize_face(face_embedding):
    """
    cosine similarity against loaded face_db
    """
    max_sim = -1.0
    identity = "Unknown"
    info = {}

    fe = face_embedding
    fe_norm = np.linalg.norm(fe) + 1e-8

    for name, data in face_db.items():
        db_embedding = data["embedding"]
        sim = float(np.dot(fe, db_embedding) / (fe_norm * (np.linalg.norm(db_embedding) + 1e-8)))
        if sim > SIM_THRESHOLD and sim > max_sim:
            max_sim = sim
            identity = name
            info = data.get("info", {})

    return identity, max_sim, info

def play_alert(name):
    """
    Play alert if cooldown elapsed. Uses preloaded Sound to avoid disk I/O per play.
    """
    if _sound is None:
        return
    with _alert_lock:
        now = time.time()
        last_t = _last_sound_time.get(name, 0)
        if (now - last_t) < SOUND_COOLDOWN_SECONDS:
            return
        _last_sound_time[name] = now
    try:
        _sound.play()
    except Exception as e:
        warn(f"Sound play error: {e}")

def queue_screenshot(name, frame):
    """
    Enqueue screenshot write (non-blocking) with per-identity cooldown.
    """
    now = time.time()
    last_t = _last_screenshot_time.get(name, 0)
    if (now - last_t) < SCREENSHOT_COOLDOWN_SECONDS:
        return
    _last_screenshot_time[name] = now
    try:
        _screenshot_q.put_nowait((name, frame.copy()))
    except queue.Full:
        warn("Screenshot queue full; dropping frame.")

# =========================
# Detection
# =========================
def _run_yolo_person(frame):
    """
    Run YOLO person detection (CPU). Returns list of [x1,y1,x2,y2] in original frame coords.
    """
    try:
        img0 = frame
        img, ratio, (dw, dh) = letterbox(img0, new_shape=(640, 640))
        img = img[:, :, ::-1].transpose(2, 0, 1)  # BGR->RGB, HWC->CHW
        img = np.ascontiguousarray(img)

        im_tensor = torch.from_numpy(img).to(yolo_device).float() / 255.0
        if im_tensor.ndimension() == 3:
            im_tensor = im_tensor.unsqueeze(0)

        with torch.inference_mode():
            pred = yolo_model(im_tensor)

        # NMS
        pred = non_max_suppression(pred, conf_thres=YOLO_CONF_THRES, iou_thres=YOLO_IOU_THRES, classes=YOLO_CLASS_PEDESTRIAN)[0]

        boxes = []
        if pred is not None and len(pred):
            # map boxes back to original frame shapes
            pred[:, :4] = yv5_scale_boxes(im_tensor.shape[2:], pred[:, :4], img0.shape).round()
            for *xyxy, conf, cls in pred:
                x1, y1, x2, y2 = [int(x.item()) for x in xyxy]
                H, W = img0.shape[:2]
                x1, y1, x2, y2 = clamp_box(x1, y1, x2, y2, W, H)
                boxes.append([x1, y1, x2, y2])
        return boxes

    except Exception as e:
        warn(f"_run_yolo_person failed: {e}")
        import traceback
        traceback.print_exc()
        return []

def detect_people(frame):
    """
    Public wrapper — kept for compatibility. Runs YOLO every N frames.
    """
    global _frame_idx, _last_person_boxes, _last_yolo_frame_idx

    # Re-run YOLO on cadence; else reuse last boxes
    if (_frame_idx - _last_yolo_frame_idx) >= YOLO_EVERY_N:
        boxes = _run_yolo_person(frame)
        _last_person_boxes = boxes
        _last_yolo_frame_idx = _frame_idx
        return boxes
    else:
        return _last_person_boxes

# =========================
# Main per-frame pipeline
# =========================
def process_frame(frame):
    """
    In:
      - frame (BGR np.ndarray)
    Out:
      - annotated frame

    Steps:
      1) detect persons (cadenced)
      2) for each person: head ROI, optional 2x upsample
      3) InsightFace on head crop -> quality gate -> embed+recognize
      4) draw labels, throttle screenshot + play alert (non-blocking)
    """
    global _frame_idx
    if not _initialized:
        return frame

    _frame_idx += 1
    H, W = frame.shape[:2]
    person_boxes = detect_people(frame)

    for box in person_boxes:
        x1, y1, x2, y2 = box
        ph = max(1, y2 - y1)

        # 1) head ROI from person
        hx1, hy1, hx2, hy2 = head_roi_from_person(frame, box, head_frac=HEAD_FRAC)
        head_crop = frame[hy1:hy2, hx1:hx2]
        if head_crop.size == 0:
            continue

        # 2) selective 2x upsample for small persons
        upscaled = False
        crop_for_face = head_crop
        if ph < UPSAMPLE_PERSON_HEIGHT_PX:
            crop_for_face = cv2.resize(head_crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            upscaled = True
        scale_back = 0.5 if upscaled else 1.0

        # 3) face detect+embed on crop
        try:
            faces = app.get(crop_for_face)
        except Exception as e:
            warn(f"InsightFace app.get error: {e}")
            faces = []

        for f in faces:
            # quality gates
            det_score = float(getattr(f, "det_score", 1.0))
            if det_score < MIN_FACE_DET_SCORE:
                continue

            # bbox in crop coords
            bx1, by1, bx2, by2 = [int(v) for v in f.bbox]
            # map back to original frame coords
            bx1 = int(hx1 + bx1 * scale_back)
            by1 = int(hy1 + by1 * scale_back)
            bx2 = int(hx1 + bx2 * scale_back)
            by2 = int(hy1 + by2 * scale_back)

            # clamp
            bx1, by1, bx2, by2 = clamp_box(bx1, by1, bx2, by2, W, H)

            # size gate
            if (bx2 - bx1) < MIN_FACE_BOX_SIDE or (by2 - by1) < MIN_FACE_BOX_SIDE:
                continue

            # embedding & recognition
            embedding = f.normed_embedding
            name, sim, info = recognize_face(embedding)
            label = f"{name} ({sim:.2f})" if name != "Unknown" else "Unknown"

            # draw
            cv2.rectangle(frame, (bx1, by1), (bx2, by2), (0, 255, 0), 2)
            tx, ty = bx1, max(0, by1 - 8)
            cv2.putText(frame, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            # side effects
            if name != "Unknown":
                log(f"Person detected: {name}")
                queue_screenshot(name, frame)
                threading.Thread(target=play_alert, args=(name,), daemon=True).start()

    return frame