import cv2
import threading
import os
import queue
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import messagebox

from libs.detector import process_frame, initialize_detector

# Load stream URLs
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../config/streams.txt")
with open(CONFIG_PATH) as f:
    stream_urls = [line.strip() for line in f if line.strip()]


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


def stream_worker(index, url, notify_error=None):
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        error_msg = f"Cannot open stream {url}"
        print(f"[ERROR] {error_msg}")
        if notify_error:
            notify_error(error_msg)
        return

    window_name = f"Camera {index}"
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    print(f"[INFO] Started stream {index}: {url}")

    frame_queue = queue.Queue(maxsize=3)
    processed_queue = queue.Queue(maxsize=2)

    def reader():
        while True:
            ret, frame = cap.read()
            if not ret:
                print(f"[WARNING] Stream {index} ended or lost connection.")
                break
            try:
                frame_queue.put_nowait(frame)
            except queue.Full:
                pass  # drop frame if too slow

    def detector():
        with ThreadPoolExecutor(max_workers=1) as executor:
            while True:
                try:
                    frame = frame_queue.get(timeout=1)
                except queue.Empty:
                    continue
                future = executor.submit(process_frame, frame.copy())

                def callback(fut):
                    try:
                        processed = fut.result()
                        try:
                            processed_queue.put_nowait(processed)
                        except queue.Full:
                            pass
                    except Exception as e:
                        print(f"[Detector error] Camera {index}: {e}")
                future.add_done_callback(callback)

    threading.Thread(target=reader, daemon=True).start()
    threading.Thread(target=detector, daemon=True).start()

    moved = False
    while True:
        try:
            display_frame = processed_queue.get(timeout=1)
        except queue.Empty:
            continue
        cv2.imshow(window_name, display_frame)
        if not moved:
            cv2.moveWindow(window_name, 200 * index, 50 * index)
            moved = True
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyWindow(window_name)


def show_stream_error(message):
    try:
        messagebox.showerror("Stream Error", message)
    except:
        print(f"[UI ERROR] {message}")


def run_multi_stream_detection():
    # Load detector in background (once)
    threading.Thread(target=initialize_detector, daemon=True).start()

    for i, url in enumerate(stream_urls):
        threading.Thread(target=stream_worker, args=(i, url, show_stream_error), daemon=True).start()

    print("[INFO] Press 'q' in any window to exit.")
    while True:
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cv2.destroyAllWindows()