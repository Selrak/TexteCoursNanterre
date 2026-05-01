#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import contextlib
import io
import os
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

from auth_manager import browser_login
from ubicast_course_downloader import last_course_dir, process_course_url


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
DEFAULT_OUT = ROOT / "downloads"
LOG_DIR = DEFAULT_OUT / "logs"
POSTPROCESS_SCRIPT = PROJECT_ROOT / "traiter_texte_cours.py"


class RunLogWriter:
    def __init__(self, callback, log_path):
        self.callback = callback
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_path.open("a", encoding="utf-8", newline="")
        self.buffer = ""
        self.lock = threading.Lock()

    def write(self, text):
        if text:
            self.callback(text)
            with self.lock:
                self.buffer += text
                self._drain_complete_lines()

    def flush(self):
        with self.lock:
            if self.buffer:
                self._write_line(self.buffer, ending="")
                self.buffer = ""
            self.log_file.flush()

    def close(self):
        with self.lock:
            if self.buffer:
                self._write_line(self.buffer, ending="")
                self.buffer = ""
            self.log_file.flush()
            self.log_file.close()

    def _drain_complete_lines(self):
        while True:
            newline_index = self.buffer.find("\n")
            if newline_index < 0:
                break
            line = self.buffer[:newline_index]
            self.buffer = self.buffer[newline_index + 1 :]
            self._write_line(line, ending="\n")

    def _write_line(self, line, ending):
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_file.write(f"[{stamp}] {line}{ending}")
        self.log_file.flush()


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Télécharger un cours")
        self.root.geometry("720x460")
        self.root.configure(bg="#f4f4f4")

        self.url_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Prêt.")
        self.current_log_path = None
        self.log_writer = None

        tk.Label(self.root, text="Collez ci-dessous l'URL Moodle du cours", bg="#f4f4f4").pack(
            anchor="w", padx=16, pady=(16, 4)
        )
        self.url_entry = tk.Entry(self.root, textvariable=self.url_var, width=100)
        self.url_entry.pack(fill="x", padx=16)
        self.url_entry.focus_set()

        self.button = tk.Button(self.root, text="Télécharger et traiter", command=self.start)
        self.button.pack(anchor="w", padx=16, pady=12)

        tk.Label(self.root, textvariable=self.status_var, bg="#f4f4f4").pack(anchor="w", padx=16)

        tk.Label(self.root, text="Activité", bg="#f4f4f4").pack(anchor="w", padx=16, pady=(12, 4))

        log_frame = tk.Frame(self.root, bg="#e9e9e9", bd=1, relief="solid")
        log_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self.log = tk.Text(
            log_frame,
            height=18,
            wrap="word",
            bg="#f7f7f7",
            fg="#222222",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            state=tk.DISABLED,
        )
        self.log.pack(fill="both", expand=True, padx=12, pady=12)

    def append_log(self, text):
        if self.log_writer is not None:
            self.log_writer.write(text)
        else:
            self.root.after(0, self._append_log, text)

    def _append_log_async(self, text):
        self.root.after(0, self._append_log, text)

    def _append_log(self, text):
        self.log.config(state=tk.NORMAL)
        self.log.insert("end", text)
        self.log.see("end")
        self.log.config(state=tk.DISABLED)

    def set_status(self, text):
        self.root.after(0, self.status_var.set, text)

    def start(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("URL manquante", "Collez l'URL Moodle du cours.")
            return
        self.current_log_path = self.make_log_path()
        self.button.config(state="disabled")
        self.log.config(state=tk.NORMAL)
        self.log.delete("1.0", "end")
        self.log.config(state=tk.DISABLED)
        thread = threading.Thread(target=self.run_pipeline, args=(url,), daemon=True)
        thread.start()

    def make_log_path(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return LOG_DIR / f"session_{stamp}.log"

    def run_pipeline(self, url):
        writer = RunLogWriter(self._append_log_async, self.current_log_path or self.make_log_path())
        self.log_writer = writer
        try:
            self.set_status("Téléchargement des sous-titres...")
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                code = process_course_url(url, out=str(DEFAULT_OUT), mode="requests")
            if code == 2:
                self.set_status("Authentification Moodle requise...")
                self.append_log("\nAuthentification Moodle requise. Ouverture du navigateur...\n")
                with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                    browser_login(url, wait_for_auth=True)
                self.append_log("\nAuthentification enregistrée. Reprise du téléchargement...\n")
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
            completed = subprocess.run(
                [
                    sys.executable,
                    str(POSTPROCESS_SCRIPT),
                    "--input",
                    str(vtt_dir),
                    "--outdir",
                    str(processed_dir),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if completed.stdout:
                writer.write(completed.stdout)
            if completed.returncode != 0:
                raise RuntimeError("Le post-traitement n'a pas abouti.")
            self.set_status("Terminé.")
            self.append_log(f"\nTerminé.\nDossier: {course_dir}\n")
            self.root.after(0, lambda: messagebox.showinfo("Terminé", f"Cours téléchargé et traité.\n\n{course_dir}"))
        except Exception as exc:
            self.set_status("Erreur.")
            self.append_log(f"\nErreur: {exc}\n")
            self.root.after(0, lambda: messagebox.showerror("Erreur", str(exc)))
        finally:
            writer.close()
            self.log_writer = None
            self.root.after(0, lambda: self.button.config(state="normal"))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
