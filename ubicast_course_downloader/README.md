# UbiCast Course Downloader

Outil local pour récupérer les sous-titres VTT de cours Moodle / UbiCast / WebTV Paris-Nanterre auxquels vous avez accès.

Le projet contient uniquement le code. Les cookies, profils navigateur, états de session et fichiers téléchargés ne doivent pas être versionnés.

## Installation

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

## Architecture

- Dossier projet: code seulement, visible par Codex.
- Dossier runtime secret: `~/Library/Application Support/ubicast-course-downloader/`.
- Dossier runtime configurable avec `UBICAST_RUNTIME_DIR` ou `--runtime-dir`.
- Ne lancez pas Codex dans le dossier runtime.
- Ne lancez pas Codex avec accès complet au disque pour ce projet.

Le dossier runtime peut contenir `.env`, `browser-profile/`, `storage_state.json`, `session/` ou d'autres fichiers de session. Son contenu ne doit jamais être affiché, copié dans une conversation ou ajouté au dépôt.

## Configuration runtime

```sh
mkdir -p "$HOME/Library/Application Support/ubicast-course-downloader"
cp config.example.env "$HOME/Library/Application Support/ubicast-course-downloader/.env"
nano "$HOME/Library/Application Support/ubicast-course-downloader/.env"
```

Ne créez pas de vrai `.env` dans le dossier projet.

## Cookies manuels

Le mode `requests` utilise `MOODLE_COOKIE` pour `coursenligne.parisnanterre.fr` et `WEBTV_COOKIE` pour `webtv.parisnanterre.fr`.

Depuis Firefox, ouvrez les outils développeur, onglet Network, puis copiez les cookies depuis une requête authentifiée pertinente. Placez uniquement les valeurs dans le `.env` du dossier runtime.

Ne collez jamais les cookies dans une conversation. Ne les affichez pas avec `cat`.

## Authentification navigateur

La commande prévue est:

```sh
python3 ubicast_course_downloader.py "URL_DU_COURS" --login
```

Une fenêtre Firefox dédiée s'ouvre avec un profil conservé dans le runtime. Connectez-vous normalement, puis appuyez sur Entrée dans le terminal. L'outil enregistre ensuite les cookies dans le `.env` du runtime sans les afficher.

Pour recommencer avec un profil propre:

```sh
python3 ubicast_course_downloader.py "URL_DU_COURS" --force-login
```

## Utilisation

```sh
python3 ubicast_course_downloader.py "URL_DU_COURS" --dry-run
python3 ubicast_course_downloader.py "URL_DU_COURS" --limit 1
python3 ubicast_course_downloader.py "URL_DU_COURS" --mode auto
python3 ubicast_course_downloader.py "URL_DU_COURS" --mode browser
python3 ubicast_course_downloader.py "URL_DU_COURS" --postprocess
```

Structure produite:

```text
downloads/
  Nom_du_cours/
    manifest.csv
    manifest.json
    moodle_pages/
    webtv_pages/
    vtt/
    processed/
    logs/
```

`downloads/` ne doit contenir aucun cookie ni token.

## Post-traitement

Ajoutez dans le `.env` runtime:

```sh
POSTPROCESS_CMD="python3 ../traiter_texte_cours.py --input '{vtt_dir}' --outdir '{course_dir}/processed'"
```

Placeholders disponibles:

- `{course_dir}`
- `{vtt_dir}`
- `{manifest_csv}`
- `{manifest_json}`

Exemple avec découpage OpenAI:

```sh
POSTPROCESS_CMD="python3 ../traiter_texte_cours.py --input '{vtt_dir}' --outdir '{course_dir}/processed' --use-openai"
```

## Diagnostics

Messages attendus:

- `Cookie Moodle absent ou expiré`
- `Cookie WebTV absent ou expiré`
- `VTT non présent dans HTML : essayer mode browser`
- `Selenium/Firefox requis pour ce fallback`
- `Sous-titres introuvables pour cette séance`

Les diagnostics ne doivent pas contenir `Cookie`, `Authorization`, `MoodleSession`, `csrftoken`, `mssessionid` ou `sessionid`.
