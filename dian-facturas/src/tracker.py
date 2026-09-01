"""Estado persistente para idempotencia y observabilidad.

Guarda por CUFE: estado (done/failed), archivo de salida, error y timestamp.
Si se vuelve a ejecutar, los CUFE 'done' se saltan (no se re-descargan).
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path


class Tracker:
    def __init__(self, state_path: str | Path):
        self.path = Path(state_path)
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}  # estado corrupto: se reconstruye

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def is_done(self, cufe: str) -> bool:
        return self._data.get(cufe, {}).get("status") == "done"

    def get(self, cufe: str) -> dict:
        return self._data.get(cufe, {})

    def mark_done(self, cufe: str, output: str, run_id: str) -> None:
        self._set(cufe, status="done", output=output, error=None, run_id=run_id)

    def mark_failed(self, cufe: str, error: str, run_id: str) -> None:
        self._set(cufe, status="failed", output=None, error=error, run_id=run_id)

    def _set(self, cufe: str, **fields) -> None:
        with self._lock:
            entry = self._data.setdefault(cufe, {})
            entry.update({k: v for k, v in fields.items() if v is not None or k == "error"})
            entry["updated_at"] = self._now()
            self._flush()

    def _flush(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)  # escritura atomica

    def summary(self) -> dict[str, int]:
        counts = {"done": 0, "failed": 0}
        for entry in self._data.values():
            counts[entry.get("status", "failed")] = counts.get(entry.get("status", "failed"), 0) + 1
        return counts
