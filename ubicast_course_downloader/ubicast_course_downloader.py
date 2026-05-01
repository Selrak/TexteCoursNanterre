#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.parse import parse_qs, quote, urljoin, urlparse

from auth_manager import browser_login_message, ensure_authenticated, redact


MOODLE_HOST = "coursenligne.parisnanterre.fr"
WEBTV_HOST = "webtv.parisnanterre.fr"
UBICAST_PATH = "/mod/ubicast/view.php"
VTT_RE = re.compile(r"https?://[^\s\"'<>]+?\.vtt(?:\?[^\s\"'<>]*)?", re.IGNORECASE)
WEBTV_RE = re.compile(r"https?://webtv\.parisnanterre\.fr/[^\s\"'<>]+", re.IGNORECASE)
SUBTITLE_HINT_RE = re.compile(r"(/[^\s\"'<>]*(?:subtitles|subtitle_)[^\s\"'<>]*?\.vtt(?:\?[^\s\"'<>]*)?)", re.IGNORECASE)


@dataclass
class ActivityResult:
    index: int
    course_title: str
    moodle_course_url: str
    moodle_activity_id: str
    moodle_activity_url: str
    activity_title: str = ""
    webtv_url: str = ""
    vtt_url: str = ""
    output_vtt_file: str = ""
    status: str = "pending"
    error: str = ""
    details: Dict[str, object] = field(default_factory=dict)


def require_bs4():
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise RuntimeError(
            "beautifulsoup4 non installé. Lancez: python3 -m pip install -r requirements.txt"
        ) from exc
    return BeautifulSoup


def optional_soup(html: str):
    try:
        return require_bs4()(html, "html.parser")
    except RuntimeError:
        return None


def is_login_page(text: str, url: str = "") -> bool:
    haystack = f"{url}\n{text[:4000]}".lower()
    return any(marker in haystack for marker in (
        "authentification requise",
        "/login/index.php",
        "cas.parisnanterre.fr/login",
        "central authentication service",
        'name="username"',
        "name='username'",
        'type="password"',
        "type='password'",
    ))


def sanitize_course_name(name: str, fallback: str) -> str:
    raw = (name or fallback).strip()
    raw = re.sub(r"[^\w .()&+-]+", "_", raw, flags=re.UNICODE)
    raw = re.sub(r"\s+", " ", raw).strip(" ._")
    return raw or fallback


def ordered_unique(items: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def get_course_id(course_url: str) -> str:
    parsed = urlparse(course_url)
    ids = parse_qs(parsed.query).get("id", [])
    return ids[0] if ids else "course"


def activity_id(activity_url: str) -> str:
    ids = parse_qs(urlparse(activity_url).query).get("id", [])
    return ids[0] if ids else ""


def soup_from_html(html: str):
    return require_bs4()(html, "html.parser")


def extract_course_title(html: str, course_url: str) -> str:
    soup = optional_soup(html)
    if soup:
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            return h1.get_text(" ", strip=True)
        if soup.title and soup.title.get_text(strip=True):
            return soup.title.get_text(" ", strip=True)
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.IGNORECASE | re.DOTALL)
    if h1_match:
        return re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if title_match:
        return re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
    return f"course_{get_course_id(course_url)}"


def extract_activity_links(html: str, base_url: str) -> List[str]:
    links = []
    soup = optional_soup(html)
    if soup:
        for node in soup.find_all("a", href=True):
            href = urljoin(base_url, node["href"])
            parsed = urlparse(href)
            if parsed.netloc == MOODLE_HOST and parsed.path == UBICAST_PATH:
                links.append(href)
    for href in re.findall(r"""href=["']([^"']+)["']""", html, flags=re.IGNORECASE):
        href = urljoin(base_url, href)
        parsed = urlparse(href)
        if parsed.netloc == MOODLE_HOST and parsed.path == UBICAST_PATH:
            links.append(href)
    raw_links = re.findall(r"https?://coursenligne\.parisnanterre\.fr/mod/ubicast/view\.php\?id=\d+", html)
    return ordered_unique(links + raw_links)


def extract_activity_title(html: str) -> str:
    soup = optional_soup(html)
    if soup:
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            return h1.get_text(" ", strip=True)
        if soup.title and soup.title.get_text(strip=True):
            return soup.title.get_text(" ", strip=True)
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.IGNORECASE | re.DOTALL)
    if h1_match:
        return re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if title_match:
        return re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
    return ""


def extract_webtv_urls(html: str, base_url: str) -> List[str]:
    urls = []
    soup = optional_soup(html)
    if soup:
        for tag in soup.find_all(["iframe", "a"], src=True):
            urls.append(urljoin(base_url, tag["src"]))
        for tag in soup.find_all(["iframe", "a"], href=True):
            urls.append(urljoin(base_url, tag["href"]))
    for value in re.findall(r"""(?:src|href)=["']([^"']+)["']""", html, flags=re.IGNORECASE):
        urls.append(urljoin(base_url, value))
    urls.extend(WEBTV_RE.findall(html))
    urls = [u.rstrip("\\") for u in urls if urlparse(u).netloc == WEBTV_HOST]
    return ordered_unique(urls)


def extract_vtt_urls(html: str, base_url: str) -> List[str]:
    urls = []
    soup = optional_soup(html)
    if soup:
        for tag_name, attr in (("track", "src"), ("a", "href"), ("source", "src")):
            for tag in soup.find_all(tag_name):
                value = tag.get(attr)
                if value and ".vtt" in value.lower():
                    urls.append(urljoin(base_url, value))
    for value in re.findall(r"""(?:src|href)=["']([^"']+\.vtt(?:\?[^"']*)?)["']""", html, flags=re.IGNORECASE):
        urls.append(urljoin(base_url, value))
    urls.extend(urljoin(base_url, u) for u in VTT_RE.findall(html))
    urls.extend(urljoin(base_url, u) for u in SUBTITLE_HINT_RE.findall(html))
    return ordered_unique([u.rstrip("\\") for u in urls])


def safe_get(session, url: str, timeout: int = 30):
    try:
        return session.get(url, timeout=timeout)
    except Exception as exc:
        raise RuntimeError(redact(exc)) from exc


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def validate_vtt(content: bytes) -> bool:
    if content.startswith(b"\xef\xbb\xbf"):
        content = content[3:]
    return content.startswith(b"WEBVTT")


def output_name(index: int, activity_url: str) -> str:
    ident = activity_id(activity_url) or str(index)
    return f"{index:02d}_id{ident}.vtt"


def make_dirs(base: Path) -> Dict[str, Path]:
    dirs = {
        "course": base,
        "moodle_pages": base / "moodle_pages",
        "webtv_pages": base / "webtv_pages",
        "vtt": base / "vtt",
        "processed": base / "processed",
        "logs": base / "logs",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def row_for_csv(result: ActivityResult) -> Dict[str, object]:
    data = asdict(result)
    data.pop("details", None)
    return data


def write_manifest(results: List[ActivityResult], csv_path: Path, json_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "index",
        "course_title",
        "moodle_course_url",
        "moodle_activity_id",
        "moodle_activity_url",
        "activity_title",
        "webtv_url",
        "vtt_url",
        "output_vtt_file",
        "status",
        "error",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow(row_for_csv(result))
    with json_path.open("w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2)


def run_postprocess(command_template: str, course_dir: Path, manifest_csv: Path, manifest_json: Path) -> None:
    command = command_template.format(
        course_dir=str(course_dir),
        vtt_dir=str(course_dir / "vtt"),
        manifest_csv=str(manifest_csv),
        manifest_json=str(manifest_json),
    )
    if not command.strip():
        return
    subprocess.run(command, shell=True, check=True)


def process_requests(args) -> int:
    context = ensure_authenticated(args.course_url, force_login=args.force_login, runtime_dir=args.runtime_dir)
    course_resp = safe_get(context.moodle_session, args.course_url)
    course_html = course_resp.text
    if is_login_page(course_html, course_resp.url):
        print("Cookie Moodle absent ou expiré", file=sys.stderr)
        return 2
    if course_resp.status_code >= 400:
        print(f"Erreur Moodle HTTP {course_resp.status_code}", file=sys.stderr)
        return 2

    course_title = extract_course_title(course_html, args.course_url)
    activity_urls = extract_activity_links(course_html, course_resp.url)
    if args.limit:
        activity_urls = activity_urls[:args.limit]

    if args.dry_run:
        for i, url in enumerate(activity_urls, start=1):
            print(f"{i:02d}\t{activity_id(url)}\t{url}")
        return 0

    course_dir = Path(args.out) / sanitize_course_name(course_title, f"course_{get_course_id(args.course_url)}")
    dirs = make_dirs(course_dir)
    write_text(dirs["moodle_pages"] / "course.html", course_html)

    results: List[ActivityResult] = []
    for i, activity_url in enumerate(activity_urls, start=1):
        result = ActivityResult(
            index=i,
            course_title=course_title,
            moodle_course_url=args.course_url,
            moodle_activity_id=activity_id(activity_url),
            moodle_activity_url=activity_url,
        )
        try:
            activity_resp = safe_get(context.moodle_session, activity_url)
            activity_html = activity_resp.text
            if is_login_page(activity_html, activity_resp.url):
                result.status = "auth_expired"
                result.error = "Cookie Moodle absent ou expiré"
                results.append(result)
                continue
            write_text(dirs["moodle_pages"] / f"{i:02d}_id{result.moodle_activity_id}.html", activity_html)
            result.activity_title = extract_activity_title(activity_html)

            webtv_urls = extract_webtv_urls(activity_html, activity_resp.url)
            if not webtv_urls:
                result.status = "needs_browser"
                result.error = "VTT non présent dans HTML : essayer mode browser"
                results.append(result)
                continue
            result.webtv_url = webtv_urls[0]

            webtv_resp = safe_get(context.webtv_session, result.webtv_url)
            webtv_html = webtv_resp.text
            if is_login_page(webtv_html, webtv_resp.url) or "Authentification requise" in webtv_html:
                result.status = "auth_expired"
                result.error = "Cookie WebTV absent ou expiré"
                results.append(result)
                continue
            write_text(dirs["webtv_pages"] / f"{i:02d}_id{result.moodle_activity_id}.html", webtv_html)

            vtt_urls = extract_vtt_urls(webtv_html, webtv_resp.url)
            if not vtt_urls:
                result.status = "needs_browser"
                result.error = "VTT non présent dans HTML : essayer mode browser"
                results.append(result)
                continue
            result.vtt_url = vtt_urls[0]

            vtt_resp = safe_get(context.webtv_session, result.vtt_url)
            content_type = vtt_resp.headers.get("Content-Type", "")
            content = vtt_resp.content
            if b"<html" in content[:500].lower() or not validate_vtt(content):
                result.status = "error"
                result.error = "Réponse HTML reçue à la place d'un VTT" if "html" in content_type.lower() else "Fichier VTT invalide"
                result.details["http_status"] = vtt_resp.status_code
                result.details["content_type"] = content_type
                results.append(result)
                continue
            out_file = dirs["vtt"] / output_name(i, activity_url)
            write_bytes(out_file, content)
            result.output_vtt_file = str(out_file)
            result.status = "downloaded"
        except Exception as exc:
            result.status = "error"
            result.error = redact(exc)
        results.append(result)

    manifest_csv = course_dir / "manifest.csv"
    manifest_json = course_dir / "manifest.json"
    write_manifest(results, manifest_csv, manifest_json)

    if args.postprocess:
        command = context.env.get("POSTPROCESS_CMD", "")
        if not command:
            print("POSTPROCESS_CMD vide dans le .env runtime", file=sys.stderr)
        else:
            run_postprocess(command, course_dir, manifest_csv, manifest_json)

    return 0 if all(r.status in ("downloaded", "dry_run") for r in results) else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Télécharge les sous-titres VTT UbiCast/WebTV d'un cours Moodle.")
    parser.add_argument("course_url", help="URL Moodle du cours")
    parser.add_argument("--out", default="downloads", help="Dossier de sortie")
    parser.add_argument("--mode", choices=["auto", "requests", "browser"], default="auto")
    parser.add_argument("--login", action="store_true", help="Préparer une authentification navigateur dédiée")
    parser.add_argument("--force-login", action="store_true")
    parser.add_argument("--postprocess", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--runtime-dir")
    args = parser.parse_args(argv)

    if args.login or args.force_login:
        print(browser_login_message(args.runtime_dir))
        return 0
    if args.mode == "browser":
        print("Selenium/Firefox requis pour ce fallback; mode browser non implémenté dans cette version.", file=sys.stderr)
        return 3
    try:
        return process_requests(args)
    except RuntimeError as exc:
        print(redact(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
