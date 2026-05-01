#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import glob
import json
import os
import re
import subprocess
from typing import List, Dict, Tuple, Optional
import pathlib

TS_LINE_RE = re.compile(
    r'^(\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2}\.\d{3})'
)

def ts_to_seconds(ts: str) -> float:
    hh, mm, rest = ts.split(":")
    ss, ms = rest.split(".")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0

def seconds_to_ts(s: float) -> str:
    hh = int(s // 3600)
    s -= hh * 3600
    mm = int(s // 60)
    s -= mm * 60
    ss = int(s)
    ms = int(round((s - ss) * 1000))
    if ms == 1000:
        ss += 1
        ms = 0
    if ss == 60:
        mm += 1
        ss = 0
    if mm == 60:
        hh += 1
        mm = 0
    return f"{hh:02d}:{mm:02d}:{ss:02d}.{ms:03d}"

def parse_vtt(path: str, keep_tags: bool) -> List[Dict]:
    """
    Return a list of cues:
      {i, start, end, start_s, end_s, text}
    text is the original cue text (words unchanged), with VTT display line breaks merged by spaces.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = [ln.rstrip("\r\n") for ln in f]

    # Skip WEBVTT header block (until blank line after header)
    i = 0
    # header can have "WEBVTT" + metadata lines
    while i < len(lines) and lines[i].strip() != "":
        i += 1
    while i < len(lines) and lines[i].strip() == "":
        i += 1

    cues = []
    cue_index = 0

    tag_re = re.compile(r"<[^>]+>")

    while i < len(lines):
        # optional numeric index
        if re.fullmatch(r"\d+", lines[i].strip() or ""):
            i += 1
            if i >= len(lines):
                break

        m = TS_LINE_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue

        start_ts, end_ts = m.group(1), m.group(2)
        i += 1

        cue_lines = []
        while i < len(lines) and lines[i].strip() != "":
            t = lines[i]
            if not keep_tags:
                t = tag_re.sub("", t)
            cue_lines.append(t)
            i += 1

        # Merge display lines with spaces (words unchanged)
        text = " ".join([ln.strip() for ln in cue_lines if ln.strip() != ""]).strip()

        if text != "":
            cues.append({
                "i": cue_index,
                "start": start_ts,
                "end": end_ts,
                "start_s": ts_to_seconds(start_ts),
                "end_s": ts_to_seconds(end_ts),
                "text": text,
            })
            cue_index += 1

        while i < len(lines) and lines[i].strip() == "":
            i += 1

    return cues

def heuristic_paragraph_breaks(cues: List[Dict], max_para_seconds: float) -> List[int]:
    """
    Paragraph breaks inside a section: returns indices where a new paragraph starts.
    Purely temporal + punctuation heuristic.
    """
    if not cues:
        return []

    breaks = [0]
    section_start_s = cues[0]["start_s"]
    last_break_idx = 0

    for k in range(1, len(cues)):
        if cues[k]["end_s"] - section_start_s < max_para_seconds:
            continue

        # choose a nice cut within last ~25 seconds if possible, preferring sentence end
        window_start = cues[k]["end_s"] - 25.0
        candidates = [j for j in range(last_break_idx + 1, k + 1) if cues[j]["end_s"] >= window_start]
        cut = k
        for j in reversed(candidates):
            if re.search(r"[\.!\?…]\s*$", cues[j]["text"]):
                cut = j
                break

        breaks.append(cut)
        section_start_s = cues[cut]["start_s"]
        last_break_idx = cut

    return sorted(set(breaks))

def call_openai_sections_tsv(
    cues: List[Dict],
    model: str,
    max_section_seconds: float,
    api_key: str
) -> List[Tuple[int, str]]:
    """
    Ask the model for semantic section breaks + titles.
    Output required: TSV lines "cue_index<TAB>Title"
    """
    # Provide compact input: one cue per line
    lines = []
    for c in cues:
        lines.append(f'{c["i"]}\t{c["start"]}\t{c["end"]}\t{c["text"]}')
    cue_blob = "\n".join(lines)

    # Plain-text (no JSON) output format, still machine-readable.
    instructions = (
        "Découpe cette transcription (cues horodatés) en PARTIES cohérentes (changements de thème, fin d'exemple, nouvelle étape du cours).\n"
        "Objectif principal: coupures sémantiques pertinentes (pas une coupe toutes les X secondes).\n"
        f"Contrainte secondaire: éviter des parties trop longues; si une partie dépasse environ {int(max_section_seconds)} secondes, la subdiviser.\n"
        "\n"
        "Règles impératives:\n"
        "- Ne réécris aucun passage du texte: ne fais QUE proposer des points de coupure + des titres.\n"
        "- La sortie doit être STRICTEMENT en TSV (pas de JSON, pas de texte autour, pas de puces):\n"
        "  une ligne par partie: cue_index<TAB>Titre\n"
        "- La première ligne doit être: 0<TAB><Titre>\n"
        "- cue_index doit être un entier existant.\n"
        "- Titres: courts, informatifs, en français, sans guillemets.\n"
        "\n"
        "Entrée: chaque ligne = cue_index<TAB>start<TAB>end<TAB>texte.\n"
    )

    payload = {
        "model": model,
        "instructions": instructions,
        "input": cue_blob,
    }

    p = subprocess.run(
        [
            "curl", "-sS", "https://api.openai.com/v1/responses",
            "-H", "Content-Type: application/json",
            "-H", f"Authorization: Bearer {api_key}",
            "-d", json.dumps(payload)
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if p.returncode != 0:
        raise RuntimeError("curl a échoué: " + (p.stderr or "").strip())

    resp = json.loads(p.stdout)

    # Extract output text from Responses API structure
    out_text = ""
    for item in resp.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    out_text += c.get("text", "")

    out_text = out_text.strip()
    if not out_text:
        debug_path = "openai_response_debug.json"
        try:
            with open(debug_path, "w", encoding="utf-8") as f:
                json.dump(resp, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
        raise RuntimeError(f"Réponse API vide (aucun output_text). Log: {debug_path}")

    sections = []
    for raw_line in out_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        idx_s, title = parts[0].strip(), parts[1].strip()
        if not re.fullmatch(r"\d+", idx_s):
            continue
        sections.append((int(idx_s), title))

    if not sections:
        raise RuntimeError("Impossible de parser le TSV renvoyé par le modèle.")
    if sections[0][0] != 0:
        sections.insert(0, (0, "Début"))

    # dedupe + sort, keep first title for each idx
    seen = {}
    for idx, title in sections:
        if idx not in seen:
            seen[idx] = title
    sections = sorted(seen.items(), key=lambda x: x[0])
    return sections

def build_output_text(
    cues: List[Dict],
    section_starts: List[Tuple[int, str]],
    max_para_seconds: float,
    with_timestamps: bool
) -> str:
    # section boundaries
    starts = [idx for idx, _ in section_starts]
    titles = {idx: title for idx, title in section_starts}

    out_lines = []
    n = len(cues)

    for s_i, start_idx in enumerate(starts):
        if start_idx < 0 or start_idx >= n:
            continue
        end_idx = (starts[s_i + 1] - 1) if (s_i + 1) < len(starts) else (n - 1)
        if end_idx < start_idx:
            continue

        sec_start_ts = cues[start_idx]["start"]
        sec_end_ts = cues[end_idx]["end"]
        title = titles.get(start_idx, f"Partie {s_i + 1}")

        # Section header
        if with_timestamps:
            out_lines.append(f"=== PARTIE {s_i + 1} — {title} [{sec_start_ts}–{sec_end_ts}] ===")
        else:
            out_lines.append(f"=== PARTIE {s_i + 1} — {title} ===")
        out_lines.append("")

        # Build paragraphs inside section (heuristic)
        sec_cues = cues[start_idx:end_idx + 1]
        para_breaks = heuristic_paragraph_breaks(sec_cues, max_para_seconds)

        # para_breaks are relative to sec_cues
        for p_bi, p_start_rel in enumerate(para_breaks):
            p_end_rel = (para_breaks[p_bi + 1] - 1) if (p_bi + 1) < len(para_breaks) else (len(sec_cues) - 1)
            chunk = sec_cues[p_start_rel:p_end_rel + 1]
            # Keep words unchanged; just join cues with spaces
            para_text = " ".join([c["text"] for c in chunk]).strip()
            if para_text:
                out_lines.append(para_text)
                out_lines.append("")

        out_lines.append("")  # extra blank line between sections

    return "\n".join(out_lines).rstrip() + "\n"

def build_output_text_no_sections(
    cues: List[Dict],
    max_para_seconds: float
) -> str:
    para_breaks = heuristic_paragraph_breaks(cues, max_para_seconds)
    out_lines = []
    for p_bi, p_start in enumerate(para_breaks):
        p_end = (para_breaks[p_bi + 1] - 1) if (p_bi + 1) < len(para_breaks) else (len(cues) - 1)
        chunk = cues[p_start:p_end + 1]
        para_text = " ".join([c["text"] for c in chunk]).strip()
        if para_text:
            out_lines.append(para_text)
            out_lines.append("")
    return "\n".join(out_lines).rstrip() + "\n"

def process_one_file(
    vtt_path: str,
    out_path: str,
    use_openai: bool,
    model: str,
    max_section_seconds: float,
    max_para_seconds: float,
    keep_tags: bool,
    with_timestamps: bool
) -> None:
    cues = parse_vtt(vtt_path, keep_tags=keep_tags)
    if not cues:
        raise RuntimeError(f"Aucun cue extrait depuis: {vtt_path}")

    if use_openai:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY manquant dans l'environnement.")
        section_starts = call_openai_sections_tsv(
            cues=cues,
            model=model,
            max_section_seconds=max_section_seconds,
            api_key=api_key
        )
        txt = build_output_text(
            cues=cues,
            section_starts=section_starts,
            max_para_seconds=max_para_seconds,
            with_timestamps=with_timestamps
        )
    else:
        txt = build_output_text_no_sections(
            cues=cues,
            max_para_seconds=max_para_seconds
        )

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(txt)

def main():
    ap = argparse.ArgumentParser(description="VTT -> TXT avec titres (coupures sémantiques via OpenAI) sans modifier le texte.")
    ap.add_argument("--input", help="Fichier .vtt ou dossier contenant des .vtt")
    ap.add_argument("inputs", nargs="*", help="Fichiers .vtt et/ou dossiers contenant des .vtt")
    ap.add_argument("--outdir", help="Dossier de sortie .txt (sinon: à côté du fichier d'entrée)")
    ap.add_argument("--pattern", default="*.vtt", help="Glob si un input est un dossier (défaut: *.vtt)")

    ap.add_argument("--use-openai", action="store_true", help="Utiliser l'API OpenAI pour les coupures + titres")
    ap.add_argument("--model", default="gpt-5-mini", help="Modèle (défaut: gpt-5-mini)")

    ap.add_argument("--max-section-seconds", type=float, default=900.0, help="Durée cible max d'une PARTIE (secondaire)")
    ap.add_argument("--max-para-seconds", type=float, default=180.0, help="Durée max d'un paragraphe (heuristique)")

    ap.add_argument("--keep-tags", action="store_true", help="Conserver les balises VTT <...> dans le texte")
    ap.add_argument("--with-timestamps", action="store_true", help="Afficher les timestamps dans les titres de PARTIE")

    args = ap.parse_args()

    in_paths = []
    if args.input:
        in_paths.append(args.input)
    if args.inputs:
        in_paths.extend(args.inputs)
    if not in_paths:
        raise SystemExit("Aucun input fourni. Donnez un fichier/dir ou utilisez --input.")

    outdir = args.outdir

    def out_path_for_vtt(vtt_path: str) -> str:
        p = pathlib.Path(vtt_path)
        suffix = " traité IA.txt" if args.use_openai else " traité.txt"
        out_name = p.stem + suffix
        if outdir:
            return str(pathlib.Path(outdir) / out_name)
        return str(p.with_name(out_name))

    for in_path in in_paths:
        if os.path.isdir(in_path):
            vtts = sorted(glob.glob(os.path.join(in_path, args.pattern)))
            if not vtts:
                raise SystemExit(f"Aucun .vtt trouvé dans le dossier: {in_path}")
            for vtt in vtts:
                out_path = out_path_for_vtt(vtt)
                process_one_file(
                    vtt_path=vtt,
                    out_path=out_path,
                    use_openai=args.use_openai,
                    model=args.model,
                    max_section_seconds=args.max_section_seconds,
                    max_para_seconds=args.max_para_seconds,
                    keep_tags=args.keep_tags,
                    with_timestamps=args.with_timestamps
                )
        else:
            out_path = out_path_for_vtt(in_path)
            process_one_file(
                vtt_path=in_path,
                out_path=out_path,
                use_openai=args.use_openai,
                model=args.model,
                max_section_seconds=args.max_section_seconds,
                max_para_seconds=args.max_para_seconds,
                keep_tags=args.keep_tags,
                with_timestamps=args.with_timestamps
            )

if __name__ == "__main__":
    main()
