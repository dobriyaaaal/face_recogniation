import os
import sys

# --- Add YOLOv5 path ---
YOLO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '.', 'yolov5'))

if YOLO_PATH not in sys.path:
    sys.path.insert(0, YOLO_PATH)
    print(f"[INFO] YOLOv5 path added to sys.path: {YOLO_PATH}")
else:
    print(f"[INFO] YOLOv5 path already in sys.path: {YOLO_PATH}")
