from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

from cli_any_app.config import settings


def _private_target(path: Path) -> Path:
    root = settings.secrets_dir.resolve()
    parent = path.parent.resolve()
    if parent != root and root not in parent.parents:
        raise RuntimeError("Refusing to access secret outside secrets directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    target = parent / path.name
    if target.is_symlink():
        raise RuntimeError("Refusing to access secret through symlink")
    if target.exists() and target.stat().st_nlink > 1:
        raise RuntimeError("Refusing to access hard-linked secret file")
    return target


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
        fd = os.open(tmp, flags, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp, target)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def write_private_text(path: Path, content: str) -> None:
    write_private_bytes(path, content.encode())
