from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


PRINTABLE_RE = re.compile(rb"[\x20-\x7e]{4,}")
KV_RE = re.compile(
    r"(?i)(?:pass(?:word)?|pwd|user(?:name)?|login|admin|root|token|secret|key)[\s:=]+([^\s\"';,]{1,64})"
)
ASSIGNMENT_RE = re.compile(r"(?i)\b([A-Z0-9_]{3,32})=([^\s\"';]{1,64})")
URL_USERINFO_RE = re.compile(r"(?i)\b[a-z][a-z0-9+.-]+://([^:/@\s]+):([^/@\s]+)@")


def extract_strings(firmware_path: str | Path, min_length: int = 4) -> list[str]:
    blob = Path(firmware_path).read_bytes()
    matches = PRINTABLE_RE.findall(blob)
    return [m.decode("utf-8", errors="ignore") for m in matches if len(m) >= min_length]


def score_candidates(strings: list[str]) -> tuple[list[str], list[str]]:
    usernames: Counter[str] = Counter()
    passwords: Counter[str] = Counter()

    for entry in strings:
        line = entry.strip()
        if not line:
            continue

        lowered = line.lower()
        if lowered in {"admin", "root", "user", "guest", "support"}:
            usernames[line] += 3

        for match in KV_RE.finditer(line):
            candidate = match.group(1).strip()
            if candidate:
                passwords[candidate] += 5

        for match in ASSIGNMENT_RE.finditer(line):
            key, value = match.groups()
            if any(term in key.lower() for term in ("user", "login")):
                usernames[value.strip()] += 4
            if any(term in key.lower() for term in ("pass", "pwd", "secret", "token", "key")):
                passwords[value.strip()] += 4

        for match in URL_USERINFO_RE.finditer(line):
            usernames[match.group(1).strip()] += 4
            passwords[match.group(2).strip()] += 4

        if any(term in lowered for term in ("password", "passwd", "pwd")):
            for token in _tokenize(line):
                passwords[token] += 1

        if any(term in lowered for term in ("username", "login", "admin", "root")):
            for token in _tokenize(line):
                usernames[token] += 1

    usernames = _filter_ranked(usernames)
    passwords = _filter_ranked(passwords)
    return usernames, passwords


def write_wordlists(out_dir: str | Path, usernames: list[str], passwords: list[str], raw_strings: list[str]) -> None:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    (out_path / "usernames.txt").write_text("\n".join(usernames) + ("\n" if usernames else ""))
    (out_path / "passwords.txt").write_text("\n".join(passwords) + ("\n" if passwords else ""))
    (out_path / "strings.txt").write_text("\n".join(raw_strings) + ("\n" if raw_strings else ""))


def _tokenize(line: str) -> list[str]:
    tokens = re.split(r"[^A-Za-z0-9._@:$!#%-]+", line)
    return [token for token in tokens if 1 <= len(token) <= 64]


def _filter_ranked(counter: Counter[str]) -> list[str]:
    filtered: list[tuple[str, int]] = []
    for value, score in counter.items():
        if len(value) < 1 or len(value) > 64:
            continue
        if value.isspace():
            continue
        if value.lower().startswith(("http://", "https://", "/dev/")):
            continue
        filtered.append((value, score))

    filtered.sort(key=lambda item: (-item[1], item[0]))
    seen: set[str] = set()
    result: list[str] = []
    for value, _score in filtered:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
