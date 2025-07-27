import os
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
from PIL import Image, ImageTk
import shutil
import json
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from libs.face_db import build_face_embeddings

from libs.utils import load_people

PEOPLE_DIR = os.path.join(os.path.dirname(__file__), '..', 'people')

class AddPersonApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Add New Person")
        self.image_paths = []
        self.custom_fields = []

        self.build_ui()

    def build_ui(self):
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill="both", expand=True)

        # Name Entry
        ttk.Label(frame, text="Full Name *").grid(row=0, column=0, sticky="w")
        self.name_entry = ttk.Entry(frame, width=30)
        self.name_entry.grid(row=0, column=1, pady=5)

        # Custom fields
        self.fields_frame = ttk.LabelFrame(frame, text="Additional Info", padding=10)
        self.fields_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.render_custom_fields()

        ttk.Button(frame, text="➕ Add Field", command=self.add_custom_field).grid(row=2, column=0, columnspan=2, pady=5)

        # Image section
        self.img_frame = ttk.LabelFrame(frame, text="Images", padding=10)
        self.img_frame.grid(row=3, column=0, columnspan=2, pady=10, sticky="ew")

        self.image_canvas = tk.Canvas(self.img_frame, height=160)
        self.image_scroll = ttk.Scrollbar(self.img_frame, orient="horizontal", command=self.image_canvas.xview)
        self.image_canvas.configure(xscrollcommand=self.image_scroll.set)

        self.image_scroll.pack(side="bottom", fill="x")
        self.image_canvas.pack(side="top", fill="both", expand=True)

        self.image_container = ttk.Frame(self.image_canvas)
        self.image_canvas.create_window((0, 0), window=self.image_container, anchor="nw")

        self.image_container.bind("<Configure>", lambda e: self.image_canvas.configure(scrollregion=self.image_canvas.bbox("all")))

        # Upload button
        upload_btn = ttk.Button(frame, text="Upload Images", command=self.upload_images)
        upload_btn.grid(row=4, column=0, columnspan=2, pady=5)

        # Action Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=10)

        ttk.Button(btn_frame, text="Save", command=self.save_person).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.root.destroy).pack(side="right", padx=5)

    def render_custom_fields(self):
        for widget in self.fields_frame.winfo_children():
            widget.destroy()

        for i, (key_var, val_var) in enumerate(self.custom_fields):
            ttk.Entry(self.fields_frame, textvariable=key_var, width=15).grid(row=i, column=0, padx=2, pady=2)
            ttk.Entry(self.fields_frame, textvariable=val_var, width=25).grid(row=i, column=1, padx=2, pady=2)
            del_btn = ttk.Button(self.fields_frame, text="❌", command=lambda i=i: self.remove_custom_field(i))
            del_btn.grid(row=i, column=2, padx=2)

    def add_custom_field(self):
        key_var = tk.StringVar()
        val_var = tk.StringVar()
        self.custom_fields.append((key_var, val_var))
        self.render_custom_fields()

    def remove_custom_field(self, index):
        del self.custom_fields[index]
        self.render_custom_fields()

    def upload_images(self):
        paths = filedialog.askopenfilenames(filetypes=[("Image files", "*.jpg *.jpeg *.png")])
        if paths:
            self.image_paths = paths
            self.show_previews()

    def show_previews(self):
        for widget in self.image_container.winfo_children():
            widget.destroy()

        self.image_container.thumbnails = []

        for i, img_path in enumerate(self.image_paths):
            try:
                img = Image.open(img_path)
                img.thumbnail((100, 100))
                img_tk = ImageTk.PhotoImage(img)
                self.image_container.thumbnails.append(img_tk)

                frame = ttk.Frame(self.image_container, padding=5)
                frame.grid(row=0, column=i)

                label = ttk.Label(frame, image=img_tk)
                label.pack()

                ttk.Label(frame, text=f"Image {i+1}").pack()
            except Exception as e:
                print(f"Error loading image {img_path}: {e}")

    def save_person(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showerror("Missing Name", "Name is required.")
            return

        existing = load_people()
        if name in existing:
            messagebox.showerror("Duplicate", f"Person '{name}' already exists.")
            return

        if not self.image_paths:
            messagebox.showerror("No Images", "At least one image must be uploaded.")
            return

        person_dir = os.path.join(PEOPLE_DIR, name)
        os.makedirs(person_dir, exist_ok=True)

        # Save images
        for i, img_path in enumerate(self.image_paths):
            ext = os.path.splitext(img_path)[1]
            target = os.path.join(person_dir, f"img{i+1}{ext}")
            shutil.copy(img_path, target)

        # Save info.json
        info = {"Name": name}
        for key_var, val_var in self.custom_fields:
            k = key_var.get().strip()
            v = val_var.get().strip()
            if k:
                info[k] = v

        with open(os.path.join(person_dir, "info.json"), "w") as f:
            json.dump(info, f, indent=2)

        try:
            from libs.face_db import build_face_embeddings
            build_face_embeddings()
            print("[AUTO] Face database rebuilt successfully.")
        except Exception as e:
            print(f"[ERROR] Failed to rebuild database: {e}")

        messagebox.showinfo("Success", f"{name} added successfully!")
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = AddPersonApp(root)
    root.mainloop()