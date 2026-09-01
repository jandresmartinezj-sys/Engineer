"""Verifica idempotencia y persistencia del estado."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.tracker import Tracker  # noqa: E402


def test_done_y_persistencia(tmp_path):
    p = tmp_path / "estado.json"
    t = Tracker(p)
    assert not t.is_done("X")
    t.mark_done("X", "salida.pdf", "run1")
    assert t.is_done("X")

    # Se recarga desde disco en una instancia nueva.
    t2 = Tracker(p)
    assert t2.is_done("X")
    assert t2.get("X")["output"] == "salida.pdf"


def test_failed_no_es_done(tmp_path):
    t = Tracker(tmp_path / "e.json")
    t.mark_failed("Y", "captcha timeout", "run1")
    assert not t.is_done("Y")
    assert t.get("Y")["status"] == "failed"
    assert t.get("Y")["error"] == "captcha timeout"


def test_summary(tmp_path):
    t = Tracker(tmp_path / "e.json")
    t.mark_done("A", "a.pdf", "r")
    t.mark_done("B", "b.pdf", "r")
    t.mark_failed("C", "err", "r")
    s = t.summary()
    assert s["done"] == 2 and s["failed"] == 1


def test_estado_corrupto_se_reinicia(tmp_path):
    p = tmp_path / "e.json"
    p.write_text("{no es json", encoding="utf-8")
    t = Tracker(p)  # no debe lanzar
    assert t.summary()["done"] == 0
