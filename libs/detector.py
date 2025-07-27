# detector.py

import os
import pickle
import time
import threading
import datetime
import numpy as np
import cv2
from insightface.app import FaceAnalysis


import pygame

# --- INIT SOUND ALERT SYSTEM ---
pygame.mixer.init()
alert_lock = threading.Lock()
sound_cooldown_seconds = 10
last_sound_time = {}

# --- INIT DETECTOR ---
app = None
face_db = {}
_initialized = False

init_lock = threading.Lock()

def initialize_detector():
    global app, face_db, _initialized
    with init_lock:
        if _initialized:
            return

        print("[INFO] Initializing face detector...")
        app = FaceAnalysis(name='buffalo_s')
        app.prepare(ctx_id=0)  # ctx_id=0 will fall back to CPU if no GPU

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


def process_frame(frame):
    if not _initialized:
        initialize_detector()

    faces = app.get(frame)
    recognized = []

    for face in faces:
        box = face.bbox.astype(int)
        embedding = face.normed_embedding
        name, sim, info = recognize_face(embedding)

        # Draw box & label
        label = f"{name} ({sim:.2f})" if name != "Unknown" else "Unknown"
        cv2.rectangle(frame, tuple(box[:2]), tuple(box[2:]), (0, 255, 0), 2)
        cv2.putText(frame, label, (box[0], box[1] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # Save detection & play alert
        if name != "Unknown":
            recognized.append((name, info))
            folder = os.path.join("detections", name)
            os.makedirs(folder, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(folder, f"{timestamp}.jpg")
            try:
                cv2.imwrite(filepath, frame)
            except Exception as e:
                print(f"⚠️ Screenshot error: {e}")
            threading.Thread(target=play_alert, args=(name,), daemon=True).start()

    # Display info
    if recognized:
        name, info = recognized[0]
        lines = [f"Name: {name}"] + [f"{k}: {v}" for k, v in info.items()]
        for i, line in enumerate(lines):
            y = 25 + i * 25
            cv2.putText(frame, line, (10, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (50, 200, 255), 2)

    return frame