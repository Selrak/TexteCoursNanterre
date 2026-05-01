#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import contextlib
import io
import json
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
MASTER_ROOT = PROJECT_ROOT.parent
DEFAULT_OUT = ROOT / "downloads"
LOG_DIR = DEFAULT_OUT / "logs"
POSTPROCESS_SCRIPT = PROJECT_ROOT / "traiter_texte_cours.py"
PLACEHOLDER_URL = "https://coursenligne.parisnanterre.fr/course/view.php?id=758"


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
        self.placeholder_active = False

        tk.Label(self.root, text="Collez ci-dessous l'URL coursenligne du cours", bg="#f4f4f4").pack(
            anchor="w", padx=16, pady=(16, 4)
        )
        self.url_entry = tk.Entry(self.root, width=100)
        self.url_entry.pack(fill="x", padx=16)
        self.url_entry.bind("<FocusIn>", self.clear_placeholder)
        self.url_entry.bind("<FocusOut>", self.restore_placeholder)
        self.url_entry.bind("<KeyPress>", self.clear_placeholder_on_key)
        self.url_entry.focus_set()
        self.restore_placeholder()

        self.button = tk.Button(self.root, text="Télécharger et traiter", command=self.start)
        self.button.pack(anchor="w", padx=16, pady=12)
        self.root.bind("<Return>", self.start_from_enter)

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

    def clear_placeholder(self, event=None):
        if self.placeholder_active:
            self.url_entry.delete(0, "end")
            self.url_entry.config(fg="#111111")
            self.placeholder_active = False

    def clear_placeholder_on_key(self, event=None):
        if event and event.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Tab"):
            return
        self.clear_placeholder()

    def restore_placeholder(self, event=None):
        if not self.url_entry.get().strip():
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, PLACEHOLDER_URL)
            self.url_entry.config(fg="#777777")
            self.placeholder_active = True

    def get_url(self):
        if self.placeholder_active:
            return ""
        return self.url_entry.get().strip()

    def start_from_enter(self, event=None):
        if str(self.button["state"]) != "disabled":
            self.start()

    def start(self):
        url = self.get_url()
        if not url:
            messagebox.showerror("URL manquante", "Collez l'URL coursenligne du cours.")
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

    def load_manifest_results(self, course_dir):
        manifest_path = Path(course_dir) / "manifest.json"
        if not manifest_path.exists():
            return []
        with manifest_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def result_label(self, result):
        index = result.get("index", "?")
        title = (result.get("activity_title") or "").strip()
        return f"Séance {index}" + (f" - {title}" if title else "")

    def issue_lines(self, results):
        lines = []
        for result in results:
            if result.get("status") == "downloaded":
                continue
            status = result.get("status") or "problème"
            error = result.get("error") or "problème non détaillé"
            lines.append(f"- {self.result_label(result)} : {status} - {error}")
        return lines

    def downloaded_results(self, results):
        return [result for result in results if result.get("status") == "downloaded"]

    def processed_output_dir(self, course_dir):
        return MASTER_ROOT / Path(course_dir).name

    def title_processed_files(self, results, processed_dir):
        processed_dir = Path(processed_dir)
        for result in self.downloaded_results(results):
            vtt_file = Path(result.get("output_vtt_file", ""))
            if not vtt_file.name:
                continue
            generated = processed_dir / f"{vtt_file.stem} traité.txt"
            target = processed_dir / f"Séance {result.get('index')}.txt"
            if not generated.exists():
                self.append_log(f"\nAttention: fichier traité introuvable pour {self.result_label(result)}: {generated}\n")
                continue
            text = generated.read_text(encoding="utf-8")
            title = f"Séance {result.get('index')}"
            if not text.startswith(title + "\n"):
                text = f"{title}\n\n{text}"
            target.write_text(text, encoding="utf-8")
            if generated != target:
                generated.unlink()

    def final_message(self, processed_dir, issue_lines):
        message = f"Cours téléchargé et traité.\n\nDossier: {processed_dir}"
        if issue_lines:
            message += "\n\nSéances non récupérées complètement:\n" + "\n".join(issue_lines)
        return message

    def run_pipeline(self, url):
        writer = RunLogWriter(self._append_log_async, self.current_log_path or self.make_log_path())
        self.log_writer = writer
        try:
            self.set_status("Téléchargement des sous-titres...")
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                code = process_course_url(url, out=str(DEFAULT_OUT), mode="requests")
            if code == 2:
                self.set_status("Authentification CAS/MFA requise...")
                self.append_log("\nAuthentification CAS/MFA requise. Ouverture du navigateur...\n")
                with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                    browser_login(url, wait_for_auth=True)
                self.append_log("\nAuthentification CAS/MFA enregistrée. Reprise du téléchargement...\n")
                self.set_status("Téléchargement des sous-titres...")
                with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                    code = process_course_url(url, out=str(DEFAULT_OUT), mode="requests")

            course_dir = last_course_dir()
            if course_dir is None:
                raise RuntimeError("Aucun dossier de cours produit.")
            results = self.load_manifest_results(course_dir)
            issues = self.issue_lines(results)
            if code != 0 and not self.downloaded_results(results):
                if issues:
                    self.append_log("\nSéances non récupérées:\n" + "\n".join(issues) + "\n")
                raise RuntimeError("Le téléchargement n'a pas abouti pour les séances du cours.")
            vtt_dir = course_dir / "vtt"
            processed_dir = self.processed_output_dir(course_dir)
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
            self.title_processed_files(results, processed_dir)
            self.set_status("Terminé.")
            if issues:
                self.append_log("\nSéances non récupérées complètement:\n" + "\n".join(issues) + "\n")
            self.append_log(f"\nTerminé.\nDossier: {processed_dir}\n")
            message = self.final_message(processed_dir, issues)
            self.root.after(0, lambda: messagebox.showinfo("Terminé", message))
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
