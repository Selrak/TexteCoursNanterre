#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import re
import sys
from typing import List, Tuple, Optional


DEFAULT_PLAN_HEADER_RE = r"^\s*(PLAN|Plan|Sommaire|SOMMAIRE)\s*:?\s*$"
DEFAULT_PLAN_ITEM_RE = r"^\s*(?:[-*]\s*)?(?:\d+[\).]\s*)?PARTIE\b.*$"
DEFAULT_TITLE_RE = (
    r"^\s*(?:##\s*)?.*\[\d{1,2}:\d{2}:\d{2}(?:\.\d{3})?\].*$"
)


def read_text(path: str, encoding: str) -> str:
    try:
        with open(path, "r", encoding=encoding, errors="strict", newline="") as f:
            text = f.read()
    except UnicodeDecodeError as exc:
        raise SystemExit(
            f"Decode error for {path}. Try --encoding (example: latin-1). Details: {exc}"
        )
    if text.startswith("\ufeff"):
        text = text[1:]
    return text


def strip_newline(line: str) -> str:
    return line.rstrip("\r\n")


def is_blank(line: str) -> bool:
    return strip_newline(line).strip(" \t") == ""


def remove_plan_lines(
    lines: List[str],
    plan_header_re: re.Pattern,
    plan_item_re: Optional[re.Pattern],
    title_re: re.Pattern,
    infer_plan: bool,
    plan_lines: Optional[int],
) -> Tuple[List[str], int]:
    if not lines:
        return lines, 0

    if plan_lines is not None:
        idx = 0
        while idx < len(lines) and is_blank(lines[idx]):
            idx += 1
        count = 0
        j = idx
        while j < len(lines) and count < plan_lines:
            if not is_blank(lines[j]):
                count += 1
            j += 1
        return lines[:idx] + lines[j:], j - idx

    idx = 0
    while idx < len(lines) and is_blank(lines[idx]):
        idx += 1
    if idx < len(lines) and plan_header_re.match(strip_newline(lines[idx])):
        j = idx + 1
        while j < len(lines) and not is_blank(lines[j]):
            j += 1
        while j < len(lines) and is_blank(lines[j]):
            j += 1
        return lines[:idx] + lines[j:], j - idx

    if infer_plan and plan_item_re is not None:
        idx = 0
        while idx < len(lines) and is_blank(lines[idx]):
            idx += 1
        j = idx
        count = 0
        while (
            j < len(lines)
            and not is_blank(lines[j])
            and plan_item_re.match(strip_newline(lines[j]))
        ):
            j += 1
            count += 1
        if count > 0 and j < len(lines) and is_blank(lines[j]):
            k = j
            while k < len(lines) and is_blank(lines[k]):
                k += 1
            if k < len(lines) and title_re.match(strip_newline(lines[k])):
                return lines[:idx] + lines[k:], k - idx

    return lines, 0


def _needs_space_between(prev_line: str, next_line: str) -> bool:
    if is_blank(prev_line) or is_blank(next_line):
        return False
    prev_text = strip_newline(prev_line)
    next_text = strip_newline(next_line)
    if not prev_text or not next_text:
        return False
    if prev_text[-1].isspace() or next_text[0].isspace():
        return False
    return True


def remove_title_lines(lines: List[str], title_re: re.Pattern) -> Tuple[List[str], int]:
    kept = []
    removed = 0
    for i, line in enumerate(lines):
        if title_re.match(strip_newline(line)):
            removed += 1
            prev_line = kept[-1] if kept else ""
            next_line = lines[i + 1] if i + 1 < len(lines) else ""
            if prev_line and next_line and _needs_space_between(prev_line, next_line):
                kept.append(" ")
        else:
            kept.append(line)
    return kept, removed


def normalize_newlines(text: str, mode: str, collapse_spaces: bool) -> str:
    if mode == "remove":
        return text.replace("\r", "").replace("\n", "")
    if mode == "space":
        text = re.sub(r"[\r\n]+", " ", text)
        if collapse_spaces:
            text = re.sub(r"[ \t]+", " ", text)
        return text
    return text


def first_mismatch(a: str, b: str) -> Optional[int]:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    if len(a) != len(b):
        return n
    return None


def char_desc(s: str, i: int) -> str:
    if i >= len(s):
        return "<EOF>"
    ch = s[i]
    return f"{ch!r} (U+{ord(ch):04X})"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Compare a raw text file with an annotated version (plan, "
            "section titles, extra newlines)."
        )
    )
    ap.add_argument("original", help="Original plain text file")
    ap.add_argument("annotated", help="Annotated text file")
    ap.add_argument("--encoding", default="utf-8", help="Input encoding (default: utf-8)")

    ap.add_argument(
        "--title-regex",
        default=DEFAULT_TITLE_RE,
        help="Regex for section title lines to remove",
    )
    ap.add_argument(
        "--plan-header-regex",
        default=DEFAULT_PLAN_HEADER_RE,
        help="Regex for the plan header line at the top",
    )
    ap.add_argument(
        "--plan-item-regex",
        default=DEFAULT_PLAN_ITEM_RE,
        help="Regex for plan item lines (used with --infer-plan)",
    )
    ap.add_argument(
        "--infer-plan",
        action="store_true",
        help="Infer a plan block at the top if it looks like a title list",
    )
    ap.add_argument(
        "--plan-lines",
        type=int,
        help="Remove the first N non-empty lines as plan items",
    )
    ap.add_argument(
        "--newline-mode",
        choices=["remove", "space", "keep"],
        default="remove",
        help="How to treat newlines in the annotated text after removals",
    )
    ap.add_argument(
        "--strip-original-newlines",
        action="store_true",
        help="Also remove newlines from the original text before comparing",
    )
    ap.add_argument(
        "--collapse-spaces",
        action="store_true",
        help="Collapse runs of spaces/tabs (only with --newline-mode space)",
    )
    ap.add_argument(
        "--context",
        type=int,
        default=60,
        help="Number of context characters to show around the first mismatch",
    )

    args = ap.parse_args()

    original = read_text(args.original, args.encoding)
    annotated = read_text(args.annotated, args.encoding)

    title_re = re.compile(args.title_regex)
    plan_header_re = re.compile(args.plan_header_regex, re.IGNORECASE)
    plan_item_re = (
        re.compile(args.plan_item_regex, re.IGNORECASE) if args.plan_item_regex else None
    )

    lines = annotated.splitlines(keepends=True)
    lines, removed_plan = remove_plan_lines(
        lines=lines,
        plan_header_re=plan_header_re,
        plan_item_re=plan_item_re,
        title_re=title_re,
        infer_plan=args.infer_plan,
        plan_lines=args.plan_lines,
    )
    lines, removed_titles = remove_title_lines(lines, title_re)

    normalized = "".join(lines)
    normalized = normalize_newlines(normalized, args.newline_mode, args.collapse_spaces)

    if args.strip_original_newlines:
        original_cmp = normalize_newlines(original, "remove", False)
    else:
        original_cmp = original

    original_cmp = original_cmp.lstrip()
    normalized = normalized.lstrip()

    if original_cmp == normalized:
        print("OK: texts match after removing plan, titles, and newlines.")
        print(f"Removed plan lines: {removed_plan}")
        print(f"Removed title lines: {removed_titles}")
        print(f"Lengths: original={len(original_cmp)} annotated={len(normalized)}")
        return 0

    idx = first_mismatch(original_cmp, normalized)
    print("MISMATCH: texts differ after normalization.")
    print(f"Removed plan lines: {removed_plan}")
    print(f"Removed title lines: {removed_titles}")
    print(f"Lengths: original={len(original_cmp)} annotated={len(normalized)}")
    if idx is not None:
        print(f"First mismatch index: {idx}")
        print(f"Original char:  {char_desc(original_cmp, idx)}")
        print(f"Annotated char: {char_desc(normalized, idx)}")
        start = max(0, idx - args.context)
        end = min(len(original_cmp), idx + args.context)
        print(f"Original context:  {original_cmp[start:end]!r}")
        end2 = min(len(normalized), idx + args.context)
        print(f"Annotated context: {normalized[start:end2]!r}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
