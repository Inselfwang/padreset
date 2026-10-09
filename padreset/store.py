"""Settings, backups and logs under %APPDATA%\\PadReset."""

import json
import os
import re
import time
from pathlib import Path


def data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    path = Path(base) / "PadReset"
    path.mkdir(parents=True, exist_ok=True)
    return path


def backup_dir() -> Path:
    path = data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
        fp.flush()
        os.fsync(fp.fileno())
    os.replace(tmp, path)


def load_settings() -> dict:
    try:
        with open(data_dir() / "settings.json", encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(**changes) -> dict:
    data = load_settings()
    data.update(changes)
    _write_json(data_dir() / "settings.json", data)
    return data


def save_backup(record: dict) -> str:
    """Write a backup record to disk (fsynced) and return its id."""
    serial = re.sub(r"[^A-Za-z0-9]", "", record.get("serial") or "unknown")
    base = f"{serial}_{time.strftime('%Y%m%d-%H%M%S')}"
    backup_id, n = base, 1
    while (backup_dir() / f"{backup_id}.json").exists():  # never overwrite a backup
        n += 1
        backup_id = f"{base}-{n}"
    record = {**record, "id": backup_id}
    _write_json(backup_dir() / f"{backup_id}.json", record)
    return backup_id


def load_backup(backup_id: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", backup_id or ""):
        raise ValueError("bad backup id")
    with open(backup_dir() / f"{backup_id}.json", encoding="utf-8") as fp:
        return json.load(fp)


def list_backups(serial: str) -> list:
    """Backups for one printer, newest first."""
    out = []
    for path in backup_dir().glob("*.json"):
        try:
            with open(path, encoding="utf-8") as fp:
                rec = json.load(fp)
        except (OSError, ValueError):
            continue
        if rec.get("serial") == serial and isinstance(rec.get("cells"), dict):
            out.append(rec)
    out.sort(key=lambda r: r.get("created", ""), reverse=True)
    return out
