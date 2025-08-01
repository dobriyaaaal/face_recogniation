import os
import cv2
import threading
import tkinter as tk
from PIL import Image, ImageTk
from queue import Queue
from libs.detector import process_frame

# --- Config Folder/File Creation ---
CONFIG_DIR = "config"
STREAMS_PATH = os.path.join(CONFIG_DIR, "streams.txt")
os.makedirs(CONFIG_DIR, exist_ok=True)
if not os.path.exists(STREAMS_PATH):
    with open(STREAMS_PATH, "w") as f:
        open(STREAMS_PATH, "w").close()

# --- Load Stream URLs ---
with open(STREAMS_PATH) as f:
    stream_urls = [
        line.strip()
        for line in f
        if line.strip() and not line.strip().startswith("#")
    ]

class CameraWindow:
    def __init__(self, master, stream_url, index):
        self.master = master
        self.stream_url = stream_url
        self.index = index

        self.window = tk.Toplevel(master)
        self.window.title(f"Camera {index + 1}")
        self.window.geometry("640x480")
        self.label = tk.Label(self.window)
        self.label.pack(fill="both", expand=True)

        self.queue = Queue()
        self.running = True

        # Start capture thread
        threading.Thread(target=self.capture_loop, daemon=True).start()
        # Schedule GUI update in main thread
        self.window.after(30, self.update_gui)
        self.window.protocol("WM_DELETE_WINDOW", self.stop)

    def capture_loop(self):
        cap = cv2.VideoCapture(self.stream_url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            print(f"[ERROR] Failed to open: {self.stream_url}")
            return

        while self.running:
            ret, frame = cap.read()
            if ret:
                try:
                    processed = process_frame(frame)
                    self.queue.put(processed)
                except Exception as e:
                    print(f"[ERROR] Frame failed: {e}")
        cap.release()

    def update_gui(self):
        if not self.running:
            return
        try:
            while not self.queue.empty():
                frame = self.queue.get()
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb)
                w, h = self.window.winfo_width(), self.window.winfo_height()
                img = img.resize((w, h))
                self.photo = ImageTk.PhotoImage(img)
                self.label.configure(image=self.photo)
                self.label.image = self.photo
        except Exception as e:
            print(f"[GUI Error] {e}")

        self.window.after(30, self.update_gui)

    def stop(self):
        self.running = False
        self.window.destroy()

def run_camera_ui():
    root = tk.Tk()
    root.withdraw()  # Hide root window

    windows = []
    for i, url in enumerate(stream_urls):
        cam_win = CameraWindow(root, url, i)
        windows.append(cam_win)

    root.mainloop()

if __name__ == "__main__":
    run_camera_ui()