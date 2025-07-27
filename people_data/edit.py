import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
from PIL import Image, ImageTk
import json
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from libs.face_db import build_face_embeddings

PEOPLE_DIR = os.path.join(os.path.dirname(__file__), '..', 'people')

class EditPersonApp:
    def __init__(self, root, person_name):
        self.root = root
        self.original_name = person_name
        self.person_path = os.path.join(PEOPLE_DIR, person_name)
        self.image_paths = []
        self.deleted_images = []
        self.custom_fields = []  # (key_var, val_var)

        self.root.title(f"Edit Person - {person_name}")
        self.build_ui()
        self.load_person_data()

    def build_ui(self):
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Full Name *").grid(row=0, column=0, sticky="w")
        self.name_entry = ttk.Entry(frame, width=30)
        self.name_entry.grid(row=0, column=1, pady=5)

        # Dynamic fields
        self.fields_frame = ttk.LabelFrame(frame, text="Additional Info", padding=10)
        self.fields_frame.grid(row=1, column=0, columnspan=2, sticky="ew")

        self.render_custom_fields()
        ttk.Button(frame, text="➕ Add Field", command=self.add_custom_field).grid(row=2, column=0, columnspan=2, pady=5)

        # Images
        self.img_frame = ttk.LabelFrame(frame, text="Images", padding=10)
        self.img_frame.grid(row=3, column=0, columnspan=2, pady=10, sticky="ew")

        self.img_canvas = tk.Canvas(self.img_frame, height=160)
        self.img_scroll = ttk.Scrollbar(self.img_frame, orient="horizontal", command=self.img_canvas.xview)
        self.img_canvas.configure(xscrollcommand=self.img_scroll.set)
        self.img_scroll.pack(side="bottom", fill="x")
        self.img_canvas.pack(side="left", fill="both", expand=True)

        self.img_inner = ttk.Frame(self.img_canvas)
        self.img_canvas.create_window((0, 0), window=self.img_inner, anchor="nw")

        self.img_inner.bind("<Configure>", lambda e: self.img_canvas.configure(scrollregion=self.img_canvas.bbox("all")))

        # Buttons
        btns = ttk.Frame(frame)
        btns.grid(row=4, column=0, columnspan=2, pady=5)
        ttk.Button(btns, text="➕ Add Images", command=self.add_images).pack(side="left", padx=5)

        bottom = ttk.Frame(frame)
        bottom.grid(row=5, column=0, columnspan=2, pady=10)
        ttk.Button(bottom, text="Save", command=self.save_changes).pack(side="left", padx=5)
        ttk.Button(bottom, text="Cancel", command=self.root.destroy).pack(side="right", padx=5)

    def render_custom_fields(self):
        for widget in self.fields_frame.winfo_children():
            widget.destroy()

        for i, (k, v) in enumerate(self.custom_fields):
            ttk.Entry(self.fields_frame, textvariable=k, width=15).grid(row=i, column=0, padx=2, pady=2)
            ttk.Entry(self.fields_frame, textvariable=v, width=25).grid(row=i, column=1, padx=2, pady=2)
            ttk.Button(self.fields_frame, text="❌", command=lambda i=i: self.remove_custom_field(i)).grid(row=i, column=2)

    def add_custom_field(self, key="", value=""):
        key_var = tk.StringVar(value=key)
        val_var = tk.StringVar(value=value)
        self.custom_fields.append((key_var, val_var))
        self.render_custom_fields()

    def remove_custom_field(self, index):
        del self.custom_fields[index]
        self.render_custom_fields()

    def load_person_data(self):
        # Load info.json
        info_path = os.path.join(self.person_path, "info.json")
        if os.path.exists(info_path):
            with open(info_path, "r") as f:
                data = json.load(f)

                self.name_entry.insert(0, data.get("Name", self.original_name))

                for k, v in data.items():
                    if k == "Name":
                        continue
                    self.add_custom_field(k, v)

        # Load images
        for file in os.listdir(self.person_path):
            if file.lower().endswith(('.jpg', '.jpeg', '.png')) and file != "info.json":
                self.image_paths.append(os.path.join(self.person_path, file))

        self.refresh_image_preview()

    def refresh_image_preview(self):
        for widget in self.img_inner.winfo_children():
            widget.destroy()

        self.thumbnails = []

        for i, path in enumerate(self.image_paths):
            try:
                img = Image.open(path)
                img.thumbnail((100, 100))
                img_tk = ImageTk.PhotoImage(img)
                self.thumbnails.append(img_tk)

                panel = ttk.Frame(self.img_inner, padding=5)
                panel.grid(row=0, column=i)

                lbl = ttk.Label(panel, image=img_tk)
                lbl.pack()

                btn = ttk.Button(panel, text="❌", width=3, command=lambda p=path: self.delete_image(p))
                btn.pack()
            except Exception as e:
                print(f"Failed to load {path}: {e}")

    def delete_image(self, path):
        if path in self.image_paths:
            self.image_paths.remove(path)
            self.deleted_images.append(path)
            self.refresh_image_preview()

    def add_images(self):
        new_paths = filedialog.askopenfilenames(filetypes=[("Images", "*.jpg *.jpeg *.png")])
        self.image_paths.extend(new_paths)
        self.refresh_image_preview()

    def save_changes(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showerror("Missing Name", "Name is required.")
            return

        new_path = os.path.join(PEOPLE_DIR, name)
        if name != self.original_name:
            if os.path.exists(new_path):
                messagebox.showerror("Error", f"Person '{name}' already exists.")
                return
            shutil.move(self.person_path, new_path)
            self.person_path = new_path

        # Save info
        info = {"Name": name}
        for key_var, val_var in self.custom_fields:
            k = key_var.get().strip()
            v = val_var.get().strip()
            if k:
                info[k] = v

        with open(os.path.join(self.person_path, "info.json"), "w") as f:
            json.dump(info, f, indent=2)

        # Remove deleted images
        for img_path in self.deleted_images:
            try:
                os.remove(img_path)
            except:
                pass

        # Copy new images (from outside person folder)
        existing_files = os.listdir(self.person_path)
        img_count = len([f for f in existing_files if f.lower().endswith(('.jpg', '.jpeg', '.png'))])

        for path in self.image_paths:
            if not path.startswith(self.person_path):
                ext = os.path.splitext(path)[1]
                dest = os.path.join(self.person_path, f"img{img_count+1}{ext}")
                shutil.copy(path, dest)
                img_count += 1

        try:
            from libs.face_db import build_face_embeddings
            build_face_embeddings()
            print("[AUTO] Face database rebuilt successfully.")
        except Exception as e:
            print(f"[ERROR] Failed to rebuild database: {e}")

        messagebox.showinfo("Updated", f"{name} updated successfully.")
        self.root.destroy()

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python edit.py 'Person Name'")
        sys.exit(1)

    name = sys.argv[1]
    path = os.path.join(PEOPLE_DIR, name)
    if not os.path.exists(path):
        print(f"Person '{name}' does not exist.")
        sys.exit(1)

    root = tk.Tk()
    app = EditPersonApp(root, name)
    root.mainloop()