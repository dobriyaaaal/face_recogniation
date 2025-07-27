import tkinter as tk
from tkinter import messagebox
import subprocess
import sys
import os
from libs.face_db import build_face_embeddings
from ui.camera_ui import run_camera_ui

def launch_script(script_path):
    try:
        abs_path = os.path.abspath(script_path)
        print(f"[INFO] Attempting to launch: {abs_path}")

        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Script not found: {abs_path}")

        subprocess.Popen([sys.executable, abs_path])
        print(f"[SUCCESS] Launched: {abs_path}")

    except Exception as e:
        print(f"[ERROR] Failed to launch {script_path}: {e}")
        messagebox.showerror("Launch Error", f"Failed to launch {script_path}\n\n{e}")

def start_real_time_detection():
    PEOPLE_DIR = os.path.join(os.path.dirname(__file__), "people")

    def has_valid_person_data():
        if not os.path.exists(PEOPLE_DIR):
            return False
        for name in os.listdir(PEOPLE_DIR):
            person_path = os.path.join(PEOPLE_DIR, name)
            if os.path.isdir(person_path):
                images = [f for f in os.listdir(person_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                if images:
                    return True
        return False

    if not has_valid_person_data():
        messagebox.showerror("Error", "No valid person data found.\nPlease add at least one person with an image.")
        return

    print("[INFO] Building face embeddings...")
    build_face_embeddings()
    print("[DONE] Face embeddings updated.")

    print("[INFO] Starting multi-stream detection...")

    from libs.multi_stream_detector import run_multi_stream_detection
    run_multi_stream_detection()

def open_camera_manager():
    from ui.camera_manager import CameraManagerUI
    win = tk.Toplevel()
    CameraManagerUI(win)

def main():
    root = tk.Tk()
    root.title("Face Recognition System Launcher")
    window_width = 400
    window_height = 330

    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width // 2) - (window_width // 2)
    y = (screen_height // 2) - (window_height // 2)
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")

    tk.Label(root, text="🎛 Face Recognition Launcher", font=("Helvetica", 16, "bold")).pack(pady=20)

    tk.Button(root, text="🎥 Start Real-Time Detection", width=30,
              command=start_real_time_detection).pack(pady=10)

    tk.Button(root, text="📡 Manage & View Cameras", width=30,
              command=open_camera_manager).pack(pady=10)

    tk.Button(root, text="👤 Open Person Manager", width=30,
              command=lambda: launch_script("people_data/manager.py")).pack(pady=10)

    tk.Button(root, text="🖼 Open Detection Gallery", width=30,
              command=lambda: launch_script("ui/gallery_viewer.py")).pack(pady=10)

    tk.Button(root, text="❌ Exit", width=30, command=root.quit).pack(pady=10)

    root.mainloop()

if __name__ == "__main__":
    main()