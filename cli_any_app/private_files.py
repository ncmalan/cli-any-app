from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

from cli_any_app.config import settings

PRIVATE_DIR_MODE = stat.S_IRWXU
PRIVATE_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR


def _private_target(path: Path) -> Path:
    root = settings.secrets_dir.resolve()
    parent = path.parent.resolve()
    if parent != root and root not in parent.parents:
        raise RuntimeError("Refusing to access secret outside secrets directory")
    _ensure_private_directories(root, parent)
    target = parent / path.name
    if target.is_symlink():
        raise RuntimeError("Refusing to access secret through symlink")
    if target.exists() and target.stat().st_nlink > 1:
        raise RuntimeError("Refusing to access hard-linked secret file")
    return target


def _ensure_private_directories(root: Path, parent: Path) -> None:
    parent.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
    current = root
    _ensure_private_directory(current)
    for part in parent.relative_to(root).parts:
        current = current / part
        _ensure_private_directory(current)


def _ensure_private_directory(path: Path) -> None:
    if path.is_symlink():
        raise RuntimeError("Refusing to use symlinked secrets directory")
    if not path.is_dir():
        raise RuntimeError("Secrets path is not a directory")
    if stat.S_IMODE(path.stat().st_mode) != PRIVATE_DIR_MODE:
        os.chmod(path, PRIVATE_DIR_MODE)
    if stat.S_IMODE(path.stat().st_mode) != PRIVATE_DIR_MODE:
        raise RuntimeError("Secrets directory permissions are too open")


def private_file_exists(path: Path) -> bool:
    return _private_target(path).exists()


def read_private_bytes(path: Path) -> bytes | None:
    target = _private_target(path)
    if not target.exists():
        return None
    return target.read_bytes()


def write_private_bytes(path: Path, content: bytes) -> None:
    target = _private_target(path)
    tmp = target.with_name(f".{target.name}.{secrets.token_hex(8)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(tmp, flags, PRIVATE_FILE_MODE)
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        os.chmod(tmp, PRIVATE_FILE_MODE)
        os.replace(tmp, target)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def write_private_text(path: Path, content: str) -> None:
    write_private_bytes(path, content.encode())
