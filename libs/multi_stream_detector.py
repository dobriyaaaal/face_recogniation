import cv2
import threading
import os
import queue
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import messagebox
import signal
import sys
import time

from libs.detector import process_frame, initialize_detector

# ----------------------------
# Config
# ----------------------------
# Limit how many frames are processed concurrently across ALL streams.
# 1–2 is usually best to avoid GPU thrash when InsightFace runs.
MAX_CONCURRENT_PROCESS = 2

# Reader queue holds raw frames per stream (keep tiny to minimize latency).
READER_QUEUE_SIZE = 3
# Processed queue is what we display (tiny as well).
PROCESSED_QUEUE_SIZE = 2

# ----------------------------
# Load stream URLs
# ----------------------------
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../config/streams.txt")
with open(CONFIG_PATH) as f:
    stream_urls = [line.strip() for line in f if line.strip()]

# ----------------------------
# Shared executor + stop event
# ----------------------------
GLOBAL_EXECUTOR = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PROCESS)
STOP_EVENT = threading.Event()

def resize_with_aspect_ratio(image, width=None, height=None, inter=cv2.INTER_AREA):
    (h, w) = image.shape[:2]
    if width is None and height is None:
        return image
    if width is not None:
        r = width / float(w)
        dim = (width, int(h * r))
    else:
        r = height / float(h)
        dim = (int(w * r), height)
    return cv2.resize(image, dim, interpolation=inter)

def _put_latest(q, item):
    """Put item into a bounded queue, dropping the oldest if full (latest frame wins)."""
    try:
        q.put_nowait(item)
    except queue.Full:
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        try:
            q.put_nowait(item)
        except queue.Full:
            pass

def stream_worker(index, url, notify_error=None):
    # Lower-latency RTSP open; consider adding params to URL like:
    # "?rtsp_transport=tcp&stimeout=5000000"
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # reduce internal buffering if backend honors it

    if not cap.isOpened():
        error_msg = f"Cannot open stream {url}"
        print(f"[ERROR] {error_msg}")
        if notify_error:
            notify_error(error_msg)
        return

    window_name = f"Camera {index}"
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    print(f"[INFO] Started stream {index}: {url}")

    frame_queue = queue.Queue(maxsize=READER_QUEUE_SIZE)
    processed_queue = queue.Queue(maxsize=PROCESSED_QUEUE_SIZE)

    def reader():
        while not STOP_EVENT.is_set():
            ret, frame = cap.read()
            if not ret:
                print(f"[WARNING] Stream {index} ended or lost connection.")
                break
            _put_latest(frame_queue, frame)

    def detector():
        while not STOP_EVENT.is_set():
            try:
                frame = frame_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            future = GLOBAL_EXECUTOR.submit(process_frame, frame.copy())

            def callback(fut):
                try:
                    processed = fut.result()
                    _put_latest(processed_queue, processed)
                except Exception as e:
                    print(f"[Detector error] Camera {index}: {e}")

            future.add_done_callback(lambda fut: callback(fut))
            frame_queue.task_done()

    threading.Thread(target=reader, daemon=True, name=f"reader-{index}").start()
    threading.Thread(target=detector, daemon=True, name=f"detector-{index}").start()

    moved = False
    while not STOP_EVENT.is_set():
        try:
            display_frame = processed_queue.get(timeout=0.5)
        except queue.Empty:
            # still pump events to keep window responsive
            if cv2.waitKey(1) & 0xFF == ord('q'):
                STOP_EVENT.set()
            continue

        cv2.imshow(window_name, display_frame)
        if not moved:
            try:
                cv2.moveWindow(window_name, 200 * index, 50 * index)
            except:
                pass
            moved = True

        # handle quit key centrally here
        if cv2.waitKey(1) & 0xFF == ord('q'):
            STOP_EVENT.set()

    cap.release()
    try:
        cv2.destroyWindow(window_name)
    except:
        pass

def show_stream_error(message):
    try:
        messagebox.showerror("Stream Error", message)
    except:
        print(f"[UI ERROR] {message}")

def _install_signal_handlers():
    def handle_sigint(sig, frame):
        STOP_EVENT.set()
    try:
        signal.signal(signal.SIGINT, handle_sigint)
        signal.signal(signal.SIGTERM, handle_sigint)
    except Exception:
        pass

def run_multi_stream_detection():
    # 1) Initialize detector synchronously so first frames aren’t wasted.
    initialize_detector()

    # 2) Start streams
    for i, url in enumerate(stream_urls):
        threading.Thread(
            target=stream_worker,
            args=(i, url, show_stream_error),
            daemon=True,
            name=f"stream-{i}"
        ).start()

    _install_signal_handlers()
    print("[INFO] Press 'q' in any window to exit.")

    # 3) Keep GUI alive until STOP_EVENT is set
    try:
        while not STOP_EVENT.is_set():
            # Pump OpenCV event loop even if nothing shown yet
            if cv2.waitKey(30) & 0xFF == ord('q'):
                STOP_EVENT.set()
            time.sleep(0.01)
    finally:
        # Give threads a moment to unwind
        time.sleep(0.2)
        cv2.destroyAllWindows()
        GLOBAL_EXECUTOR.shutdown(wait=False, cancel_futures=True)