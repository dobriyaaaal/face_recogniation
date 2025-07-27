import os
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk, ImageOps
import glob
from datetime import datetime
from tkinter import filedialog

DETECTIONS_DIR = "detections"

class GalleryViewer:
    def __init__(self, master):
        self.master = master
        self.master.title("Detection Gallery")
        self.master.geometry("1000x600")

        self.frame = tk.Frame(master)
        self.frame.pack(fill=tk.BOTH, expand=True)

        # Left: Person list with scrollable thumbnails
        self.person_listbox_frame = tk.Frame(self.frame)
        self.person_listbox_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        self.person_canvas = tk.Canvas(self.person_listbox_frame, width=220)
        self.person_scroll = tk.Scrollbar(self.person_listbox_frame, orient="vertical", command=self.person_canvas.yview)
        self.person_inner = tk.Frame(self.person_canvas)

        self.person_inner.bind(
            "<Configure>",
            lambda e: self.person_canvas.configure(scrollregion=self.person_canvas.bbox("all"))
        )
        self.person_canvas.create_window((0, 0), window=self.person_inner, anchor="nw")
        self.person_canvas.configure(yscrollcommand=self.person_scroll.set)
        self.person_canvas.pack(side="left", fill="y", expand=True)
        self.person_scroll.pack(side="right", fill="y")

        # Right: Scrollable image gallery
        self.gallery_container = tk.Frame(self.frame)
        self.gallery_container.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.gallery_canvas = tk.Canvas(self.gallery_container)
        self.gallery_scrollbar = tk.Scrollbar(self.gallery_container, orient="vertical", command=self.gallery_canvas.yview)
        self.gallery_canvas.configure(yscrollcommand=self.gallery_scrollbar.set)
        self.gallery_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.gallery_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.gallery_frame = tk.Frame(self.gallery_canvas)
        self.gallery_canvas.create_window((0, 0), window=self.gallery_frame, anchor="nw")
        self.gallery_frame.bind("<Configure>", lambda e: self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all")))

        self.image_refs = []
        self.selected_person = None

        self.master.bind_all("<MouseWheel>", self._on_mousewheel)  # scroll with wheel
        self.load_persons()

    def _on_mousewheel(self, event):
        self.gallery_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def load_persons(self):
        if not os.path.exists(DETECTIONS_DIR):
            os.makedirs(DETECTIONS_DIR)

        for name in sorted(os.listdir(DETECTIONS_DIR)):
            person_folder = os.path.join(DETECTIONS_DIR, name)
            image_files = sorted(glob.glob(os.path.join(person_folder, "*.jpg")) + glob.glob(os.path.join(person_folder, "*.png")))

            if not image_files:
                continue

            try:
                img = Image.open(image_files[0])
                img.thumbnail((60, 60))
                imgtk = ImageTk.PhotoImage(img)
                self.image_refs.append(imgtk)

                person_frame = tk.Frame(self.person_inner, pady=3)
                person_frame.pack(fill="x", anchor="w")

                thumb = tk.Label(person_frame, image=imgtk)
                thumb.pack(side="left", padx=5)

                btn = tk.Button(person_frame, text=name, width=15, anchor="w",
                                command=lambda n=name: self.display_gallery(n))
                btn.pack(side="left", padx=5)

            except Exception as e:
                print(f"⚠️ Failed to load thumbnail for {name}: {e}")

    def display_gallery(self, person_name):
        self.selected_person = person_name

        for widget in self.gallery_frame.winfo_children():
            widget.destroy()

        folder = os.path.join(DETECTIONS_DIR, person_name)
        image_files = sorted(glob.glob(os.path.join(folder, "*.jpg")) + glob.glob(os.path.join(folder, "*.png")))

        for idx, path in enumerate(image_files):
            try:
                img = Image.open(path)
                img.thumbnail((150, 150))
                imgtk = ImageTk.PhotoImage(img)
                self.image_refs.append(imgtk)

                label = tk.Label(self.gallery_frame, image=imgtk, cursor="hand2")
                label.image = imgtk
                label.grid(row=idx // 4, column=idx % 4, padx=5, pady=5)
                label.bind("<Button-1>", lambda e, p=path: self.show_full_image(p))
            except Exception as e:
                print(f"⚠️ Error loading {path}: {e}")

    def show_full_image(self, path):
        try:
            img = Image.open(path)
            original_width, original_height = img.size

            # Resize only for initial viewing (up to 720p max)
            max_width, max_height = 1280, 720
            aspect_ratio = original_width / original_height

            if original_width > max_width or original_height > max_height:
                if aspect_ratio > 1:
                    # Landscape
                    display_width = max_width
                    display_height = int(max_width / aspect_ratio)
                else:
                    # Portrait
                    display_height = max_height
                    display_width = int(max_height * aspect_ratio)
            else:
                display_width, display_height = original_width, original_height

            resized_img = img.resize((display_width, display_height), Image.Resampling.LANCZOS)
            imgtk = ImageTk.PhotoImage(resized_img)

            top = tk.Toplevel(self.master)
            top.title(os.path.basename(path))
            top.geometry(f"{display_width+40}x{display_height+120}+0+0")  # room for metadata + download button

            # Scrollable canvas
            canvas_frame = tk.Frame(top)
            canvas_frame.pack(fill=tk.BOTH, expand=True)

            canvas = tk.Canvas(canvas_frame, width=display_width, height=display_height, bg="black", highlightthickness=0)
            canvas.pack(side="left", fill="both", expand=True)

            scrollbar = tk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
            scrollbar.pack(side="right", fill="y")

            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.create_image(0, 0, anchor="nw", image=imgtk)
            canvas.image = imgtk  # prevent garbage collection

            # Metadata
            timestamp = self.extract_datetime(path)
            meta = f"📸 Path: {os.path.basename(path)}\n🕒 Taken: {timestamp}"
            meta_label = tk.Label(top, text=meta, font=("Segoe UI", 10), anchor="w", justify="left", padx=10)
            meta_label.pack(side="top", fill="x", pady=(10, 0))

            # Download Button
            def download_image():
                dest_path = filedialog.asksaveasfilename(
                    defaultextension=".jpg",
                    filetypes=[("JPEG Image", "*.jpg"), ("PNG Image", "*.png"), ("All files", "*.*")],
                    initialfile=os.path.basename(path),
                    title="Save Image As"
                )
                if dest_path:
                    img.save(dest_path)
                    messagebox.showinfo("Saved", f"Image saved to:\n{dest_path}")

            download_btn = tk.Button(top, text="⬇ Download Image", command=download_image)
            download_btn.pack(side="bottom", pady=10)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open image: {e}")


    def extract_datetime(self, path):
        filename = os.path.basename(path)
        try:
            dt_str = filename.split("_")[-2] + "_" + filename.split("_")[-1].split(".")[0]
            return datetime.strptime(dt_str, "%Y-%m-%d_%H-%M-%S").strftime("%b %d, %Y %H:%M:%S")
        except:
            t = os.path.getmtime(path)
            return datetime.fromtimestamp(t).strftime("%b %d, %Y %H:%M:%S")

if __name__ == "__main__":
    root = tk.Tk()
    viewer = GalleryViewer(root)
    root.mainloop()