#!/bin/sh
cd "$(dirname "$0")" || exit 1
python3 -m pip install -r requirements.txt
echo
echo "Installation terminee. Lancez telecharger_cours.command."
