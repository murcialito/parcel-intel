"""Datos sintéticos de `medir-candidatos` (historia #111). Nada es real; sin red."""

import dataclasses
import datetime
import json
from pathlib import Path

from parcel_intel.adapters.cut_candidate_files import GeoJsonCutCandidateWriter
from parcel_intel.adapters.validation_cases.congelacion import congelar
from parcel_intel.cli import main
from parcel_intel.domain.geometry import MultiLineGeometry
from tests.adapters.cut_candidate_files.support import sample_report

CONGELADO_EN = datetime.date(2026, 12, 1)
LINEA_COLMENAR = [[450000.0, 4435000.0], [450200.0, 4435000.0]]
LINEA_ARANJUEZ = [[440000.0, 4420000.0], [440200.0, 4420000.0]]


def caso(identificador: str, municipio: str, ambito: str, **extra: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": identificador,
        "fuente_url": "https://www.ejemplo.es/noticia",
        "fuente_tipo": "prensa",
        "fecha_consulta": "2026-11-26",
        "municipio": municipio,
        "ambito": ambito,
        "tramo_descripcion": "camino entre dos puntos",
        "cierre_fecha_aproximada": "2019",
    }
    base.update(extra)
    return base


def casos_sinteticos() -> list[dict[str, object]]:
    return [
        caso("colmenar-con-candidato", "Colmenar de Oreja", "hito", tramo_linea=LINEA_COLMENAR),
        caso("aranjuez-sin-informe", "Aranjuez", "hito", tramo_linea=LINEA_ARANJUEZ),
        caso("chinchon-sin-geometria", "Chinchón", "hito"),
        caso("fuera-uno", "El Escorial", "comunidad"),
        caso("fuera-dos", "Segovia", "comunidad"),
        caso("fuera-tres", "Toledo", "comunidad"),
    ]


def escribir_casos(carpeta: Path, congelar_conjunto: bool = True) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / "casos.json"
    ruta.write_text(
        json.dumps({"casos": casos_sinteticos()}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if congelar_conjunto:
        congelar(ruta, CONGELADO_EN, carpeta)
    return ruta


def escribir_candidatos(carpeta: Path) -> None:
    """Informe de Colmenar con un candidato que cubre el caso y otro lejano."""
    base = sample_report("28043")
    acierto = dataclasses.replace(
        base.candidates[0],
        stretch=MultiLineGeometry(
            lines=(((450000.0, 4435005.0), (450200.0, 4435005.0)),), srid=25830
        ),
    )
    lejano = dataclasses.replace(
        acierto,
        candidate_id="abababababababab",
        stretch=MultiLineGeometry(
            lines=(((455000.0, 4438000.0), (455200.0, 4438000.0)),), srid=25830
        ),
    )
    GeoJsonCutCandidateWriter(carpeta).write(
        dataclasses.replace(base, candidates=(acierto, lejano))
    )


def medir(casos: Path, entrada: Path, salida: Path) -> int:
    args = main._build_parser().parse_args(
        [
            "medir-candidatos",
            "--casos",
            str(casos),
            "--entrada",
            str(entrada),
            "--salida",
            str(salida),
        ]
    )
    code: int = args.func(args)
    return code
