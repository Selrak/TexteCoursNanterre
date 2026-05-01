#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import platform
import re
import shutil
import stat
import time
from http.cookies import SimpleCookie
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional
from urllib.parse import urlparse


APP_NAME = "ubicast-course-downloader"
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
    raw = runtime_dir or os.environ.get("UBICAST_RUNTIME_DIR")
    if not raw:
        if platform.system() == "Windows":
            appdata = os.environ.get("APPDATA")
            raw = str(Path(appdata) / APP_NAME) if appdata else str(Path.home() / "AppData" / "Roaming" / APP_NAME)
        else:
            raw = DEFAULT_RUNTIME_DIR
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


def write_runtime_env(updates: Dict[str, str], runtime_dir: Optional[str] = None) -> None:
    runtime = ensure_runtime_dir(runtime_dir)
    env_path = runtime / ".env"
    env = load_runtime_env(str(runtime))
    env.update({k: v for k, v in updates.items() if v})
    lines = []
    for key in sorted(env):
        value = env[key].replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key}="{value}"\n')
    env_path.write_text("".join(lines), encoding="utf-8")
    try:
        env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


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
        parsed = SimpleCookie()
        parsed.load(cookie)
        for name, morsel in parsed.items():
            session.cookies.set(name, morsel.value)
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


def _require_selenium():
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        from selenium.webdriver.firefox.options import Options
    except ImportError as exc:
        raise RuntimeError(
            "selenium non installé. Lancez: python3 -m pip install -r requirements.txt"
        ) from exc
    return webdriver, Options, ChromeOptions


def _cookie_header(cookies) -> str:
    pairs = []
    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        if name and value:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def _browser_candidates(runtime: Path, force_login: bool):
    firefox_profile = runtime / "browser-profile"
    chrome_profile = runtime / "browser-profile-chrome"
    if force_login:
        for profile_dir in (firefox_profile, chrome_profile):
            if profile_dir.exists():
                shutil.rmtree(profile_dir)
    firefox_profile.mkdir(mode=0o700, parents=True, exist_ok=True)
    chrome_profile.mkdir(mode=0o700, parents=True, exist_ok=True)

    webdriver, FirefoxOptions, ChromeOptions = _require_selenium()

    firefox_options = FirefoxOptions()
    if platform.system() == "Darwin":
        firefox_app = Path("/Applications/Firefox.app/Contents/MacOS/firefox")
        if firefox_app.exists():
            firefox_options.binary_location = str(firefox_app)
    firefox_options.add_argument("-profile")
    firefox_options.add_argument(str(firefox_profile))

    chrome_options = ChromeOptions()
    chrome_options.add_argument(f"--user-data-dir={chrome_profile}")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--no-default-browser-check")

    return (
        ("Firefox", lambda: webdriver.Firefox(options=firefox_options)),
        ("Chrome", lambda: webdriver.Chrome(options=chrome_options)),
    )


def browser_login(
    course_url: str,
    force_login: bool = False,
    runtime_dir: Optional[str] = None,
    confirm_callback: Optional[Callable[[], None]] = None,
    wait_for_auth: bool = False,
    wait_timeout: int = 300,
) -> Path:
    runtime = ensure_runtime_dir(runtime_dir)

    driver = None
    errors = []
    for browser_name, make_driver in _browser_candidates(runtime, force_login):
        try:
            driver = make_driver()
            print(f"Navigateur d'authentification ouvert: {browser_name}.")
            break
        except Exception as exc:
            errors.append(f"{browser_name}: {exc}")
    if driver is None:
        raise RuntimeError(
            "Impossible de démarrer Firefox ou Chrome avec Selenium. "
            "Vérifiez qu'un de ces navigateurs s'ouvre normalement et que Selenium Manager peut fournir le pilote."
        )
    try:
        driver.get(course_url)
        if wait_for_auth:
            print("Connectez-vous dans la fenêtre du navigateur dédiée. Le téléchargement reprendra automatiquement après connexion.")
            deadline = time.monotonic() + wait_timeout
            while time.monotonic() < deadline:
                current_host = urlparse(driver.current_url).netloc
                cookies = _cookie_header(driver.get_cookies())
                if "coursenligne.parisnanterre.fr" in current_host and "MoodleSession=" in cookies:
                    print("Connexion CAS/MFA détectée.")
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Authentification CAS/MFA non détectée avant expiration du délai.")
        elif confirm_callback is None:
            print("Connectez-vous dans la fenêtre du navigateur dédiée, puis appuyez sur Entrée ici.")
            try:
                input()
            except EOFError:
                raise RuntimeError("Login interrompu avant confirmation dans le terminal.")
        else:
            print("Connectez-vous dans la fenêtre du navigateur dédiée, puis confirmez dans l'interface.")
            confirm_callback()

        driver.get(course_url)
        current_host = urlparse(driver.current_url).netloc
        moodle_cookies = _cookie_header(driver.get_cookies()) if "coursenligne.parisnanterre.fr" in current_host else ""
        webtv_cookies = ""
        try:
            driver.get("https://webtv.parisnanterre.fr/")
            current_host = urlparse(driver.current_url).netloc
            webtv_cookies = _cookie_header(driver.get_cookies()) if "webtv.parisnanterre.fr" in current_host else ""
        except Exception:
            webtv_cookies = ""

        updates = {}
        if moodle_cookies:
            updates["MOODLE_COOKIE"] = moodle_cookies
        if webtv_cookies:
            updates["WEBTV_COOKIE"] = webtv_cookies
        if updates:
            write_runtime_env(updates, str(runtime))
    finally:
        driver.quit()

    return runtime
