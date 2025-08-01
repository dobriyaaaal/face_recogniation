import os
import sys
import time
import pickle
import threading
import datetime
import numpy as np
import cv2
from insightface.app import FaceAnalysis
import pygame
import torch
from pathlib import Path

# --- Add YOLOv5 path ---
YOLO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'yolov5'))
if YOLO_PATH not in sys.path:
    sys.path.insert(0, YOLO_PATH)

from yolov5.models.common import DetectMultiBackend
from yolov5.utils.general import non_max_suppression

# --- Init sound ---
pygame.mixer.init()
alert_lock = threading.Lock()
last_sound_time = {}
sound_cooldown_seconds = 10

# --- Screenshot cooldown ---
last_screenshot_time = {}
screenshot_cooldown_seconds = 10

# --- Devices ---
yolo_device = torch.device('cpu')  # run YOLO on CPU
face_device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# --- Globals ---
app = None
face_db = {}
_initialized = False
init_lock = threading.Lock()
yolo_model = None


def log(msg):
    print(f"[INFO] {msg}")

def warn(msg):
    print(f"[WARNING] {msg}")

def scale_coords(img1_shape, coords, img0_shape, ratio_pad=None):
    gain = min(img1_shape[0] / img0_shape[0], img1_shape[1] / img0_shape[1])
    pad = ((img1_shape[1] - img0_shape[1] * gain) / 2, (img1_shape[0] - img0_shape[0] * gain) / 2)
    coords[:, [0, 2]] -= pad[0]
    coords[:, [1, 3]] -= pad[1]
    coords[:, :4] /= gain
    coords[:, 0].clamp_(0, img0_shape[1])
    coords[:, 1].clamp_(0, img0_shape[0])
    coords[:, 2].clamp_(0, img0_shape[1])
    coords[:, 3].clamp_(0, img0_shape[0])
    return coords

def letterbox(im, new_shape=(640, 640), color=(114, 114, 114)):
    shape = im.shape[:2]
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]
    dw /= 2
    dh /= 2
    im = cv2.resize(im, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    im = cv2.copyMakeBorder(im, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)
    return im, r, (dw, dh)

def initialize_detector():
    global app, face_db, _initialized, yolo_model
    with init_lock:
        if _initialized:
            return
        try:
            log("Preparing face recognition model (InsightFace)...")
            app = FaceAnalysis(name='buffalo_s')
            app.prepare(ctx_id=0 if face_device.type == 'cuda' else -1)

            log("Loading known face embeddings...")
            with open('embeddings/face_db.pkl', 'rb') as f:
                face_db.update(pickle.load(f))

            yolo_weights = os.path.join(YOLO_PATH, 'yolov5n.pt')
            if not os.path.exists(yolo_weights):
                raise FileNotFoundError(f"YOLOv5 weights not found at {yolo_weights}")

            log("Loading object detection model (YOLOv5) on CPU...")
            yolo_model = DetectMultiBackend(yolo_weights, device=yolo_device)
            yolo_model.eval()

            log("Detector initialized successfully.")
            _initialized = True
        except Exception as e:
            warn(f"Detector initialization failed: {e}")
            import traceback
            traceback.print_exc()
            _initialized = False

def recognize_face(face_embedding):
    max_sim = -1
    identity = "Unknown"
    info = {}
    for name, data in face_db.items():
        db_embedding = data["embedding"]
        sim = np.dot(face_embedding, db_embedding) / (
            np.linalg.norm(face_embedding) * np.linalg.norm(db_embedding)
        )
        if sim > 0.4 and sim > max_sim:
            max_sim = sim
            identity = name
            info = data.get("info", {})
    return identity, max_sim, info

def play_alert(name):
    with alert_lock:
        now = time.time()
        if name in last_sound_time and (now - last_sound_time[name]) < sound_cooldown_seconds:
            return
        last_sound_time[name] = now
        try:
            pygame.mixer.music.load("alert.mp3")
            pygame.mixer.music.play()
        except Exception as e:
            warn(f"Sound error: {e}")

def detect_people(frame):
    try:
        img, ratio, (dw, dh) = letterbox(frame, new_shape=(640, 640))
        img = img[:, :, ::-1].transpose(2, 0, 1)
        img = np.ascontiguousarray(img)

        im_tensor = torch.from_numpy(img).to(yolo_device).float() / 255.0
        if im_tensor.ndimension() == 3:
            im_tensor = im_tensor.unsqueeze(0)

        pred = yolo_model(im_tensor)
        pred = non_max_suppression(pred, conf_thres=0.4, iou_thres=0.45, classes=[0])[0]

        boxes = []
        if pred is not None and len(pred):
            pred[:, :4] = scale_coords(im_tensor.shape[2:], pred[:, :4], frame.shape).round()
            for *xyxy, _, _ in pred:
                boxes.append([int(x.item()) for x in xyxy])
        return boxes

    except Exception as e:
        warn(f"detect_people failed: {e}")
        import traceback
        traceback.print_exc()
        return []

def process_frame(frame):
    if not _initialized:
        return frame

    now = time.time()
    person_boxes = detect_people(frame)

    for box in person_boxes:
        x1, y1, x2, y2 = box
        crop = frame[max(y1-20, 0):min(y2, frame.shape[0]), max(x1, 0):min(x2, frame.shape[1])]

        if crop.size == 0:
            continue

        faces = app.get(crop)
        for face in faces:
            bbox = face.bbox.astype(int)
            embedding = face.normed_embedding
            name, sim, info = recognize_face(embedding)

            label = f"{name} ({sim:.2f})" if name != "Unknown" else "Unknown"
            abs_box = [bbox[0] + x1, bbox[1] + y1 - 20, bbox[2] + x1, bbox[3] + y1 - 20]
            cv2.rectangle(frame, tuple(abs_box[:2]), tuple(abs_box[2:]), (0, 255, 0), 2)
            cv2.putText(frame, label, (abs_box[0], abs_box[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            if name != "Unknown":
                log(f"Person detected: {name}")
                if (name not in last_screenshot_time) or ((now - last_screenshot_time[name]) > screenshot_cooldown_seconds):
                    folder = os.path.join("detections", name)
                    os.makedirs(folder, exist_ok=True)
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    filepath = os.path.join(folder, f"{timestamp}.jpg")
                    try:
                        cv2.imwrite(filepath, frame)
                    except Exception as e:
                        warn(f"Screenshot error: {e}")
                    last_screenshot_time[name] = now
                threading.Thread(target=play_alert, args=(name,), daemon=True).start()

    return frame