#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import contextlib
import io
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from ubicast_course_downloader import last_course_dir, process_course_url


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
DEFAULT_OUT = ROOT / "downloads"
POSTPROCESS_SCRIPT = PROJECT_ROOT / "traiter_texte_cours.py"


class LogWriter:
    def __init__(self, callback):
        self.callback = callback

    def write(self, text):
        if text:
            self.callback(text)

    def flush(self):
        pass


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Télécharger un cours")
        self.root.geometry("720x460")

        self.url_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Collez l'URL Moodle du cours.")

        tk.Label(self.root, text="URL Moodle du cours").pack(anchor="w", padx=16, pady=(16, 4))
        self.url_entry = tk.Entry(self.root, textvariable=self.url_var, width=100)
        self.url_entry.pack(fill="x", padx=16)
        self.url_entry.focus_set()

        self.button = tk.Button(self.root, text="Télécharger et traiter", command=self.start)
        self.button.pack(anchor="w", padx=16, pady=12)

        tk.Label(self.root, textvariable=self.status_var).pack(anchor="w", padx=16)

        self.log = tk.Text(self.root, height=18, wrap="word")
        self.log.pack(fill="both", expand=True, padx=16, pady=(8, 16))

    def append_log(self, text):
        self.root.after(0, self._append_log, text)

    def _append_log(self, text):
        self.log.insert("end", text)
        self.log.see("end")

    def set_status(self, text):
        self.root.after(0, self.status_var.set, text)

    def start(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("URL manquante", "Collez l'URL Moodle du cours.")
            return
        self.button.config(state="disabled")
        self.log.delete("1.0", "end")
        thread = threading.Thread(target=self.run_pipeline, args=(url,), daemon=True)
        thread.start()

    def run_pipeline(self, url):
        writer = LogWriter(self.append_log)
        try:
            self.set_status("Téléchargement des sous-titres...")
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                code = process_course_url(url, out=str(DEFAULT_OUT), mode="requests")
            if code != 0:
                raise RuntimeError("Le téléchargement n'a pas abouti pour toutes les séances.")

            course_dir = last_course_dir()
            if course_dir is None:
                raise RuntimeError("Aucun dossier de cours produit.")
            vtt_dir = course_dir / "vtt"
            processed_dir = course_dir / "processed"
            self.set_status("Transformation des VTT en texte...")
            self.append_log(f"\nTraitement local: {vtt_dir}\n")
            subprocess.run(
                [
                    sys.executable,
                    str(POSTPROCESS_SCRIPT),
                    "--input",
                    str(vtt_dir),
                    "--outdir",
                    str(processed_dir),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self.set_status("Terminé.")
            self.append_log(f"\nTerminé.\nDossier: {course_dir}\n")
            self.root.after(0, lambda: messagebox.showinfo("Terminé", f"Cours téléchargé et traité.\n\n{course_dir}"))
        except Exception as exc:
            self.set_status("Erreur.")
            self.append_log(f"\nErreur: {exc}\n")
            self.root.after(0, lambda: messagebox.showerror("Erreur", str(exc)))
        finally:
            self.root.after(0, lambda: self.button.config(state="normal"))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
