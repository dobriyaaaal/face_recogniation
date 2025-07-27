import cv2
import threading
import os
from libs.detector import process_frame
import time
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed

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

def stream_worker(index, url):
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print(f"[ERROR] Cannot open stream {url}")
        return

    window_name = f"Camera {index}"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 800, 450)

    print(f"[INFO] Started stream {index}: {url}")

    frame_queue = queue.Queue(maxsize=5)
    processed_queue = queue.Queue(maxsize=3)

    # --- Reader Thread: read frames from camera ---
    def reader():
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            try:
                frame_queue.put_nowait(frame)
            except queue.Full:
                pass  # drop oldest frame silently

    # --- Detector Thread: process frames from queue ---
    def detector():
        with ThreadPoolExecutor(max_workers=2) as executor:
            while True:
                try:
                    frame = frame_queue.get(timeout=1)
                except queue.Empty:
                    continue

                # Submit detection to thread pool
                future = executor.submit(process_frame, frame.copy())

                # Once done, push to display queue
                def callback(fut):
                    try:
                        processed = fut.result()
                        try:
                            processed_queue.put_nowait(processed)
                        except queue.Full:
                            pass
                    except Exception as e:
                        print(f"[Detector error] {e}")

                future.add_done_callback(callback)


    # Start threads
    threading.Thread(target=reader, daemon=True).start()
    threading.Thread(target=detector, daemon=True).start()

    # --- Display Loop ---
    moved = False
    while True:
        try:
            display_frame = processed_queue.get(timeout=1)
        except queue.Empty:
            continue

        resized = resize_with_aspect_ratio(display_frame, width=800)
        cv2.imshow(window_name, resized)

        if not moved:
            cv2.moveWindow(window_name, 0, 0)
            moved = True

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyWindow(window_name)


def run_multi_stream_detection():
    for i, url in enumerate(stream_urls):
        threading.Thread(target=stream_worker, args=(i, url), daemon=True).start()

    print("[INFO] Press 'q' in any window to exit.")
    while True:
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cv2.destroyAllWindows()