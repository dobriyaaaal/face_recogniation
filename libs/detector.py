import os
import sys
import pickle
import time
import threading
import datetime
import numpy as np
import cv2
import pygame
import torch

from insightface.app import FaceAnalysis

# --- INIT SOUND ALERT SYSTEM ---
pygame.mixer.init()
alert_lock = threading.Lock()
sound_cooldown_seconds = 10
last_sound_time = {}

# --- THROTTLE SCREENSHOTS ---
screenshot_cooldown_seconds = 10
last_screenshot_time = {}

# --- INIT DETECTOR ---
app = None
face_db = {}
_initialized = False
init_lock = threading.Lock()

# --- INIT PERSON DETECTOR (YOLOv5) ---
YOLO_PATH = os.path.join(os.path.dirname(__file__), '../yolov5')
if YOLO_PATH not in sys.path:
    sys.path.insert(0, YOLO_PATH)

from models.common import DetectMultiBackend
from utils.datasets import letterbox
from utils.general import non_max_suppression, scale_coords
from utils.torch_utils import select_device

device = select_device('')
person_model = DetectMultiBackend(os.path.join(YOLO_PATH, 'yolov5s.pt'), device=device)
stride, names, pt = person_model.stride, person_model.names, person_model.pt

def initialize_detector():
    global app, face_db, _initialized
    with init_lock:
        if _initialized:
            return
        print("[INFO] Initializing face detector...")
        app = FaceAnalysis(name='buffalo_s')
        app.prepare(ctx_id=0)
        with open('embeddings/face_db.pkl', 'rb') as f:
            face_db.update(pickle.load(f))
        _initialized = True
        print("[DONE] Detector ready.")

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
            print(f"[Sound error] {e}")

def detect_people_yolo(frame):
    img = letterbox(frame, 640, stride=stride, auto=True)[0]
    img = img.transpose((2, 0, 1))[::-1]  # BGR to RGB, to 3xHxW
    img = np.ascontiguousarray(img)

    im = torch.from_numpy(img).to(device)
    im = im.float() / 255.0
    if im.ndimension() == 3:
        im = im.unsqueeze(0)

    pred = person_model(im, augment=False, visualize=False)
    pred = non_max_suppression(pred, conf_thres=0.4, iou_thres=0.45, classes=[0])[0]

    person_boxes = []
    if pred is not None and len(pred):
        pred[:, :4] = scale_coords(im.shape[2:], pred[:, :4], frame.shape).round()
        for *xyxy, conf, cls in pred:
            x1, y1, x2, y2 = map(int, xyxy)
            person_boxes.append((x1, y1, x2, y2))
    return person_boxes

def crop_upper_body(frame, box):
    x1, y1, x2, y2 = box
    height = y2 - y1
    cropped = frame[y1:y1 + int(0.6 * height), x1:x2]
    return cropped

def is_face_big_enough(bbox, min_size=60):
    x1, y1, x2, y2 = bbox.astype(int)
    return (x2 - x1) >= min_size and (y2 - y1) >= min_size

def process_frame(frame):
    if not _initialized:
        initialize_detector()

    recognized = []
    now = time.time()
    person_boxes = detect_people_yolo(frame)

    for box in person_boxes:
        cropped = crop_upper_body(frame, box)
        faces = app.get(cropped)

        for face in faces:
            if not is_face_big_enough(face.bbox):
                continue

            embedding = face.normed_embedding
            name, sim, info = recognize_face(embedding)

            # Project face bbox back to original frame
            fx1, fy1, fx2, fy2 = face.bbox.astype(int)
            abs_x1 = box[0] + fx1
            abs_y1 = box[1] + fy1
            abs_x2 = box[0] + fx2
            abs_y2 = box[1] + fy2

            label = f"{name} ({sim:.2f})" if name != "Unknown" else "Unknown"
            cv2.rectangle(frame, (abs_x1, abs_y1), (abs_x2, abs_y2), (0, 255, 0), 2)
            cv2.putText(frame, label, (abs_x1, abs_y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            if name != "Unknown":
                recognized.append((name, info))
                if (name not in last_screenshot_time) or ((now - last_screenshot_time[name]) > screenshot_cooldown_seconds):
                    folder = os.path.join("detections", name)
                    os.makedirs(folder, exist_ok=True)
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    filepath = os.path.join(folder, f"{timestamp}.jpg")
                    try:
                        cv2.imwrite(filepath, frame)
                    except Exception as e:
                        print(f"⚠️ Screenshot error: {e}")
                    last_screenshot_time[name] = now
                threading.Thread(target=play_alert, args=(name,), daemon=True).start()

    if recognized:
        name, info = recognized[0]
        lines = [f"Name: {name}"] + [f"{k}: {v}" for k, v in info.items() if k.lower() != "name"]
        for i, line in enumerate(lines):
            y = 25 + i * 25
            cv2.putText(frame, line, (10, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (50, 200, 255), 2)

    return frame