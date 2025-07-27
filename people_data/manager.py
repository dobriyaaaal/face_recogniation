import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

# ✅ Corrected import from libs
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(BASE_DIR, 'libs'))

from utils import load_people, delete_person

PEOPLE_DIR = "people"

class PersonManagerMain:
    def __init__(self, root):
        self.root = root
        self.root.title("Person Manager")

        self.people_listbox = tk.Listbox(root, width=40, height=20)
        self.people_listbox.grid(row=0, column=0, rowspan=4, padx=10, pady=10)
        self.people_listbox.bind("<Double-Button-1>", self.edit_selected)

        ttk.Button(root, text="➕ Add Person", command=self.add_person).grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        ttk.Button(root, text="✏️ Edit Person", command=self.edit_selected).grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        ttk.Button(root, text="🗑 Delete Person", command=self.delete_selected).grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        ttk.Button(root, text="🔁 Refresh List", command=self.load_people_list).grid(row=3, column=1, sticky="ew", padx=5, pady=5)

        self.load_people_list()
        self.python_exec = sys.executable  # ✅ ensures subprocess uses the right Python

    def load_people_list(self):
        self.people_listbox.delete(0, tk.END)
        people = load_people()
        for person in people:
            self.people_listbox.insert(tk.END, person)

    def get_selected_person(self):
        selection = self.people_listbox.curselection()
        if not selection:
            return None
        return self.people_listbox.get(selection[0])

    def add_person(self):
        subprocess.Popen([self.python_exec, os.path.join("people_data", "add.py")])

    def edit_selected(self, event=None):
        person = self.get_selected_person()
        if person:
            subprocess.Popen([self.python_exec, os.path.join("people_data", "edit.py"), person])

    def delete_selected(self):
        person = self.get_selected_person()
        if not person:
            messagebox.showwarning("No selection", "Please select a person to delete.")
            return

        confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{person}'?")
        if confirm:
            success = delete_person(person)
            if success:
                self.load_people_list()
                messagebox.showinfo("Deleted", f"'{person}' has been deleted.")
            else:
                messagebox.showerror("Error", f"Failed to delete '{person}'.")

if __name__ == "__main__":
    root = tk.Tk()
    app = PersonManagerMain(root)
    root.mainloop()