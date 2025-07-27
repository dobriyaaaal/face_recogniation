import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

STREAMS_FILE = "config/streams.txt"

class CameraManagerUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Camera Stream Manager")

        self.streams = []
        self.entries = []

        self.build_ui()
        self.load_streams()

    def build_ui(self):
        self.main_frame = ttk.Frame(self.root, padding=10)
        self.main_frame.pack(fill="both", expand=True)

        self.streams_frame = ttk.LabelFrame(self.main_frame, text="Live Camera Streams")
        self.streams_frame.pack(fill="both", expand=True)

        btns = ttk.Frame(self.main_frame)
        btns.pack(pady=10)

        ttk.Button(btns, text="➕ Add Stream", command=self.add_stream).pack(side="left", padx=5)
        ttk.Button(btns, text="💾 Save & Apply", command=self.save_streams).pack(side="left", padx=5)
        ttk.Button(btns, text="↻ Reload", command=self.load_streams).pack(side="left", padx=5)

    def load_streams(self):
        # Clear current list
        for widget in self.streams_frame.winfo_children():
            widget.destroy()
        self.entries.clear()

        if Path(STREAMS_FILE).exists():
            with open(STREAMS_FILE, "r") as f:
                self.streams = [line.strip() for line in f if line.strip()]
        else:
            self.streams = []

        for stream in self.streams:
            self.add_stream(stream)

    def add_stream(self, url=""):
        frame = ttk.Frame(self.streams_frame, padding=5)
        frame.pack(fill="x", pady=2)

        entry = ttk.Entry(frame, width=60)
        entry.insert(0, url)
        entry.pack(side="left", fill="x", expand=True)

        del_btn = ttk.Button(frame, text="❌", command=lambda: self.remove_stream(frame, entry))
        del_btn.pack(side="right", padx=5)

        self.entries.append(entry)

    def remove_stream(self, frame, entry):
        self.entries.remove(entry)
        frame.destroy()

    def save_streams(self):
        new_streams = [e.get().strip() for e in self.entries if e.get().strip()]
        try:
            Path(STREAMS_FILE).parent.mkdir(exist_ok=True)
            with open(STREAMS_FILE, "w") as f:
                f.write("\n".join(new_streams))
            messagebox.showinfo("Saved", "Streams saved successfully.\nRestart Real-Time Detection to apply.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")
