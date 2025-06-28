# Switch to customtkinter for modern, rounded UI elements.
import os
import io
import customtkinter as ctk
from tkinter import filedialog, messagebox, PhotoImage  # <-- add PhotoImage import
from PIL import Image, ImageTk
from mutagen import File
from mutagen.id3 import ID3, APIC, error as ID3Error
import urllib.request
import tempfile
import datetime
import shutil
import tkinter as tk

def update_metadata(source_path, dest_path):
    # 1. Copy metadata from source to dest
    src = File(source_path, easy=True)
    dst = File(dest_path, easy=True)

    if src is None or dst is None:
        raise Exception("Unsupported file format.")

    dst.clear()
    for key, value in src.tags.items():
        dst[key] = value

    # For MP3: Copy album art
    if source_path.lower().endswith('.mp3') and dest_path.lower().endswith('.mp3'):
        try:
            src_id3 = ID3(source_path)
            dst_id3 = ID3(dest_path)
        except ID3Error:
            src_id3 = ID3()
            dst_id3 = ID3()
        dst_id3.delall("APIC")
        for tag in src_id3.getall("APIC"):
            dst_id3.add(tag)
        dst_id3.save(dest_path)
    dst.save()

    # Write comments to ID3 COMM frame for MP3s
    if dest_path.lower().endswith('.mp3'):
        try:
            notes = getattr(update_metadata, "_update_notes", None)
            now = getattr(update_metadata, "_update_time", None)
            comment_text = ""
            if notes or now:
                comment_text = ""
                if now:
                    comment_text += f"Updated: {now}"
                if notes:
                    if comment_text:
                        comment_text += "\n"
                    comment_text += f"Notes: {notes}"
            else:
                comment_text = dst.tags.get("comment", [""])[0] if dst.tags and "comment" in dst.tags else ""

            id3 = ID3(dest_path)
            id3.delall("COMM")
            from mutagen.id3 import COMM
            id3.add(COMM(encoding=3, lang='XXX', desc='', text=comment_text))
            id3.save(dest_path)
        except Exception:
            pass

    # 2. Replace the source file with the updated dest file
    shutil.move(dest_path, source_path)

def get_album_art_and_title(filepath):
    audio = File(filepath)
    title = ""
    image_data = None

    if audio is None:
        return None, None

    # Title
    if audio.tags is not None:
        if 'TIT2' in audio.tags:
            title = str(audio.tags['TIT2'])
        elif 'title' in audio.tags:
            title = audio.tags['title'][0]
        else:
            title = os.path.basename(filepath)

    # Album art (MP3)
    if filepath.lower().endswith('.mp3'):
        try:
            id3 = ID3(filepath)
            for tag in id3.getall("APIC"):
                image_data = tag.data
                break
        except Exception:
            pass
    # Album art (other formats)
    elif hasattr(audio, 'pictures') and audio.pictures:
        image_data = audio.pictures[0].data

    return image_data, title

class SourcePage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        ctk.CTkLabel(self, text="Select the original file (with metadata)", font=("Segoe UI", 18, "bold")).pack(pady=(30,10))
        self.source_path = ctk.StringVar()
        entry = ctk.CTkEntry(self, textvariable=self.source_path, width=350, state="readonly")
        entry.pack(pady=5, padx=30)
        ctk.CTkButton(
            self, text="Browse", width=120, command=self.browse_source, corner_radius=20
        ).pack(pady=10)
        ctk.CTkButton(
            self, text="Next", width=120, command=self.go_next, fg_color="#22bb33", corner_radius=20
        ).pack(pady=10)

    def browse_source(self):
        path = filedialog.askopenfilename(
            title="Select Source Audio File",
            filetypes=[("Audio Files", "*.mp3 *.flac *.m4a *.wav *.ogg *.aac"), ("All Files", "*.*")]
        )
        if path:
            self.source_path.set(path)

    def go_next(self):
        src = self.source_path.get()
        if not src:
            messagebox.showerror("Error", "Please select a source file.")
            return
        self.controller.source_file = src
        self.controller.show_frame("PreviewPage")

class PreviewPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.temp_download_path = None
        self.canvas = ctk.CTkCanvas(self, width=128, height=128, highlightthickness=0)
        self.canvas.pack(pady=(30,10))
        self.title_label = ctk.CTkLabel(self, font=("Segoe UI", 14, "bold"), text="")
        self.title_label.pack(pady=(0,10))
        self.prompt_label = ctk.CTkLabel(self, text="Which file is the update for this file?", font=("Segoe UI", 12))
        self.prompt_label.pack(pady=(0,10))
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(pady=10)
        ctk.CTkButton(
            btn_frame, text="Select Update File", width=160, command=self.browse_dest, corner_radius=20
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_frame, text="Download from Link", width=180, command=self.download_from_link, corner_radius=20
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            self, text="Back", width=100, command=lambda: controller.show_frame("SourcePage"), corner_radius=20
        ).pack(pady=(10,0))

    def tkraise(self, *args, **kwargs):
        image_data, title = get_album_art_and_title(self.controller.source_file)
        self.canvas.delete("all")
        if image_data:
            image = Image.open(io.BytesIO(image_data)).resize((128,128), Image.LANCZOS)
            # Create rounded square mask (rounded rectangle)
            mask = Image.new("L", (128, 128), 0)
            from PIL import ImageDraw
            radius = 28  # adjust for more/less rounding
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, 128, 128), radius=radius, fill=255)
            # Create a white background with rounded corners
            bg = Image.new("RGBA", (128, 128), (255, 255, 255, 255))
            bg.putalpha(mask)
            # Composite the album art onto the white rounded background
            image = Image.alpha_composite(bg, image.convert("RGBA"))
            self.photo = ImageTk.PhotoImage(image)
            self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        else:
            self.canvas.create_rectangle(0, 0, 128, 128, outline="#cccccc")
            self.canvas.create_text(64, 64, text="No\nAlbum Art", font=("Segoe UI", 10, "italic"), fill="#888888")
        self.title_label.configure(text=title or "Unknown Title")
        super().tkraise(*args, **kwargs)

    def browse_dest(self):
        path = filedialog.askopenfilename(
            title="Select Destination Audio File",
            filetypes=[("Audio Files", "*.mp3 *.flac *.m4a *.wav *.ogg *.aac"), ("All Files", "*.*")]
        )
        if path:
            self.controller.dest_file = path
            self.controller.show_frame("CopyPage")

    def download_from_link(self):
        def do_download():
            url = url_var.get().strip()
            if not url:
                messagebox.showerror("Error", "Please enter a download link.")
                return
            try:
                temp_fd, temp_path = tempfile.mkstemp(suffix=os.path.splitext(url)[-1])
                os.close(temp_fd)
                url_entry.configure(state="disabled")
                download_btn.configure(state="disabled")
                self.update()
                urllib.request.urlretrieve(url, temp_path)
                self.temp_download_path = temp_path
                self.controller.dest_file = temp_path
                top.destroy()
                self.controller.show_frame("CopyPage")
            except Exception as e:
                messagebox.showerror("Download Failed", f"Could not download file:\n{e}")
                url_entry.configure(state="normal")
                download_btn.configure(state="normal")

        top = ctk.CTkToplevel(self)
        top.title("Download Update File")
        ctk.CTkLabel(top, text="Paste the download link for the update file:").pack(padx=20, pady=(20,5))
        url_var = ctk.StringVar()
        url_entry = ctk.CTkEntry(top, textvariable=url_var, width=350)
        url_entry.pack(padx=20, pady=5)
        download_btn = ctk.CTkButton(top, text="Download", command=do_download, corner_radius=20)
        download_btn.pack(pady=(10,20))
        url_entry.focus_set()

class CopyPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.status_label = ctk.CTkLabel(self, font=("Segoe UI", 12), text="")
        self.status_label.pack(pady=(40,10))
        ctk.CTkLabel(self, text="Update Notes (will be saved in Comments):", font=("Segoe UI", 11)).pack()
        self.notes_text = ctk.CTkTextbox(self, width=350, height=60, font=("Segoe UI", 10))
        self.notes_text.pack(pady=(5, 10))
        ctk.CTkButton(
            self, text="Update", width=160, command=self.update_metadata, fg_color="#22bb33", corner_radius=20
        ).pack(pady=10)
        ctk.CTkButton(
            self, text="Back", width=100, command=lambda: controller.show_frame("PreviewPage"), corner_radius=20
        ).pack(pady=(10,0))

    def tkraise(self, *args, **kwargs):
        src = self.controller.source_file
        dst = self.controller.dest_file
        self.status_label.configure(text=f"Update metadata from:\n{os.path.basename(src)}\nto\n{os.path.basename(dst)}")
        self.notes_text.delete("1.0", "end")
        super().tkraise(*args, **kwargs)

    def update_metadata(self):
        try:
            notes = self.notes_text.get("1.0", "end").strip()
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            update_metadata._update_notes = notes
            update_metadata._update_time = now
            update_metadata(self.controller.source_file, self.controller.dest_file)
            del update_metadata._update_notes
            del update_metadata._update_time
            messagebox.showinfo("Success", "Metadata updated successfully!\nUpdate notes and timestamp saved in Comments.\nThe original file has been replaced.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update metadata:\n{e}")

class MetadataCopierApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("KMco. Music ID Updater")
        self.geometry("500x400")
        self.resizable(False, False)
        self.source_file = ""
        self.dest_file = ""

        # Set window icon (favicon) using resources\KMco Logo.ico
        try:
            icon_path = os.path.join("resources", "KMco Logo.ico")
            self.iconbitmap(icon_path)
        except Exception:
            pass

        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True)
        self.frames = {}
        for F in (SourcePage, PreviewPage, CopyPage):
            page_name = F.__name__
            frame = F(self.container, self)
            self.frames[page_name] = frame
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.current_frame = self.frames["SourcePage"]
        self.show_frame("SourcePage", animate=False)

    def show_frame(self, page_name, animate=True):
        new_frame = self.frames[page_name]
        new_frame.tkraise()
        self.current_frame = new_frame

if __name__ == "__main__":
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    app = MetadataCopierApp()
    app.mainloop()