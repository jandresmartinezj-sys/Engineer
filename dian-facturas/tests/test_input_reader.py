"""Verifica lectura/normalizacion de la lista de CUFEs (CSV y variantes)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.input_reader import read_jobs  # noqa: E402

CUFE1 = "a" * 96
CUFE2 = "b" * 96


def test_csv_basico(tmp_path):
    f = tmp_path / "f.csv"
    f.write_text(f"cufe,nombre,proveedor\n{CUFE1},ene,EPM\n{CUFE2},feb,Claro\n", encoding="utf-8")
    jobs = read_jobs(f)
    assert [j.cufe for j in jobs] == [CUFE1, CUFE2]
    assert jobs[0].nombre == "ene" and jobs[0].proveedor == "EPM"


def test_encabezados_con_acentos_y_punto_y_coma(tmp_path):
    f = tmp_path / "f.csv"
    # 'código' con acento, delimitador ';', columna 'contraseña'
    f.write_text(f"Código;Contraseña\n{CUFE1};900999\n", encoding="utf-8")
    jobs = read_jobs(f)
    assert jobs[0].cufe == CUFE1
    assert jobs[0].nit == "900999"


def test_dedupe(tmp_path):
    f = tmp_path / "f.csv"
    f.write_text(f"cufe\n{CUFE1}\n{CUFE1}\n{CUFE2}\n", encoding="utf-8")
    jobs = read_jobs(f)
    assert len(jobs) == 2


def test_cufe_no_hex_genera_warning(tmp_path):
    f = tmp_path / "f.csv"
    f.write_text("cufe\nNO-ES-HEX-123\n", encoding="utf-8")
    jobs = read_jobs(f)
    assert jobs and jobs[0].warnings  # se acepta pero avisa


def test_sin_columna_cufe_falla(tmp_path):
    f = tmp_path / "f.csv"
    f.write_text("factura,valor\n001,5000\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_jobs(f)


def test_encabezado_cufe_cude_y_naming(tmp_path):
    # Encabezado 'CUFE/CUDE' y nombre derivado de PREFIJO-FOLIO.
    f = tmp_path / "f.csv"
    f.write_text(
        f"Tipo de documento;CUFE/CUDE;Folio;Prefijo;Nombre Emisor\n"
        f"Factura electronica;{CUFE1};20809;FEIN;INNOVA SAS\n",
        encoding="utf-8",
    )
    jobs = read_jobs(f)
    j = jobs[0]
    assert j.cufe == CUFE1
    assert j.tipo == "Factura electronica"
    assert j.safe_name() == "FEIN-20809"
    assert j.folder() == "INNOVA SAS"


def test_nit_emisor_no_es_password(tmp_path):
    # 'NIT Emisor' NO debe usarse como contrasena (la clave es el NIT global).
    f = tmp_path / "f.csv"
    f.write_text(f"CUFE/CUDE;NIT Emisor\n{CUFE1};900346567\n", encoding="utf-8")
    jobs = read_jobs(f)
    assert jobs[0].nit is None


def test_safe_name_sanitiza(tmp_path):
    f = tmp_path / "f.csv"
    f.write_text(f'cufe,nombre\n{CUFE1},"a/b:c*?"\n', encoding="utf-8")
    jobs = read_jobs(f)
    name = jobs[0].safe_name()
    assert "/" not in name and ":" not in name and "*" not in name
