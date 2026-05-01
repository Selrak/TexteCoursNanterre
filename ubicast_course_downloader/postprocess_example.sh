#!/bin/sh
set -eu

COURSE_DIR="${1:?course_dir is required}"
VTT_DIR="${2:?vtt_dir is required}"

python3 ../traiter_texte_cours.py --input "$VTT_DIR" --outdir "$COURSE_DIR/processed"
