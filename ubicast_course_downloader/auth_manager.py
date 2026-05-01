#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


DEFAULT_RUNTIME_DIR = "~/Library/Application Support/ubicast-course-downloader"
SECRET_NAMES = (
    "WEBTV_COOKIE",
    "MOODLE_COOKIE",
    "csrftoken",
    "mssessionid",
    "MoodleSession",
    "sessionid",
)


@dataclass
class AuthContext:
    runtime_dir: Path
    env: Dict[str, str]
    moodle_session: object
    webtv_session: object


def redact(text: object) -> str:
    value = "" if text is None else str(text)
    value = re.sub(r"(?i)(Cookie|Authorization)\s*:\s*[^\r\n]+", r"\1: [REDACTED]", value)
    for name in SECRET_NAMES:
        value = re.sub(rf"(?i)({re.escape(name)}=)[^;\s&]+", r"\1[REDACTED]", value)
        value = re.sub(rf"(?i)({re.escape(name)}\s*=\s*)[^\n]+", r"\1[REDACTED]", value)
    return value


def runtime_path(runtime_dir: Optional[str] = None) -> Path:
    raw = runtime_dir or os.environ.get("UBICAST_RUNTIME_DIR") or DEFAULT_RUNTIME_DIR
    return Path(raw).expanduser()


def ensure_runtime_dir(runtime_dir: Optional[str] = None) -> Path:
    path = runtime_path(runtime_dir)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        path.chmod(stat.S_IRWXU)
    except OSError:
        pass
    return path


def _parse_env_file(path: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not path.exists():
        return env
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            env[key] = value
    return env


def load_runtime_env(runtime_dir: Optional[str] = None) -> Dict[str, str]:
    path = ensure_runtime_dir(runtime_dir) / ".env"
    try:
        from dotenv import dotenv_values
    except ImportError:
        return _parse_env_file(path)
    values = dotenv_values(str(path)) if path.exists() else {}
    return {k: v for k, v in values.items() if k and v is not None}


def _require_requests():
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError(
            "requests non installé. Lancez: python3 -m pip install -r requirements.txt"
        ) from exc
    return requests


def _build_session(cookie: str = "", referer: str = ""):
    requests = _require_requests()
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:102.0) "
            "Gecko/20100101 Firefox/102.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    if referer:
        session.headers["Referer"] = referer
    if cookie and "..." not in cookie:
        session.headers["Cookie"] = cookie
    return session


def ensure_authenticated(
    course_url: str,
    force_login: bool = False,
    runtime_dir: Optional[str] = None,
) -> AuthContext:
    runtime = ensure_runtime_dir(runtime_dir)
    env = load_runtime_env(str(runtime))
    if force_login:
        raise RuntimeError(
            "Mode --force-login: ouvrez un navigateur dédié via --login, puis relancez en mode auto."
        )

    moodle_session = _build_session(env.get("MOODLE_COOKIE", ""), referer=course_url)
    webtv_session = _build_session(env.get("WEBTV_COOKIE", ""), referer=course_url)
    webtv_session.headers.update({
        "Accept": "*/*",
        "X-Requested-With": "XMLHttpRequest",
    })

    return AuthContext(
        runtime_dir=runtime,
        env=env,
        moodle_session=moodle_session,
        webtv_session=webtv_session,
    )


def browser_login_message(runtime_dir: Optional[str] = None) -> str:
    runtime = ensure_runtime_dir(runtime_dir)
    return (
        "Le login navigateur automatisé n'est pas encore implémenté dans cette version. "
        "Utilisez un .env dans le dossier runtime hors workspace: "
        f"{runtime / '.env'}"
    )
