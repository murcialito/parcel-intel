"""Serialización de la tabla de convergencia publicada (historia #315). Fixtures SINTÉTICAS."""

import dataclasses
from datetime import date

from parcel_intel.adapters.published_layers.convergence import (
    ROW_KEYS,
    SIDECAR_KEYS,
    SIDECAR_SOURCE_KEYS,
    TABLE_KEYS,
    convergence_document,
    convergence_sidecar,
)
from parcel_intel.domain.convergence import (
    CONVERGENCE_ROW_SOURCES,
    CONVERGENCE_TITLE,
    CONVERGENCE_WARNING,
    ConvergenceTable,
    YearSpan,
    build_convergence_table,
)
from parcel_intel.domain.public_card import UNKNOWN_YEAR
from parcel_intel.domain.published_comparison import NOT_AVAILABLE_TEXT
from parcel_intel.domain.published_convergence import convergence_notes, publish_convergence
from tests.convergence_support import comparison_for, empty_coverages, line, stretch

TRAMO = line((0, 0), (200, 0))


def _table() -> ConvergenceTable:
    return build_convergence_table(
        stretch(TRAMO), CONVERGENCE_ROW_SOURCES, {}, empty_coverages(), comparison_for(TRAMO)
    )


def test_documento_con_su_lista_blanca() -> None:
    document = convergence_document(publish_convergence(_table()))
    assert list(document) == list(TABLE_KEYS)
    assert document["titulo"] == CONVERGENCE_TITLE
    assert document["aviso"] == CONVERGENCE_WARNING
    assert document["imagenes"] is None
    assert (document["metodo"], document["criterio"]) == (
        "convergencia_fuentes v2",
        "discrepancia_trazados v1",
    )
    rows = document["filas"]
    assert isinstance(rows, list)
    for row in rows:
        assert list(row) == list(ROW_KEYS)
    first = rows[0]
    assert first == {
        "fuente": "via_pecuaria_oficial",
        "rotulo": "Vía pecuaria oficial",
        "tipo_evidencia": "trazado",
        "valor": "sin_cobertura",
        "texto": "Sin cobertura",
        "anio": None,
        "fecha_consulta": None,
        "enlaces": [],
        "atribucion": [],
    }
    reciente = rows[-1]
    assert reciente["valor"] == "imagen_disponible"
    assert reciente["anio"] == "2023"
    assert reciente["fecha_consulta"] == "2026-11-27"
    assert reciente["enlaces"] and all(u.startswith("https://") for u in reciente["enlaces"])


def test_anio_no_declarado_y_rango() -> None:
    table = _table()
    *others, last = table.rows
    for years, expected in ((None, UNKNOWN_YEAR), (YearSpan(2017, 2026), "2017–2026")):
        changed = dataclasses.replace(table, rows=(*others, dataclasses.replace(last, years=years)))
        document = convergence_document(publish_convergence(changed))
        rows = document["filas"]
        assert isinstance(rows, list)
        assert rows[-1]["anio"] == expected


def test_nota_de_imagenes_no_disponibles() -> None:
    table = _table()
    trazado = tuple(row for row in table.rows if row.evidence_kind == "trazado")
    no_images = dataclasses.replace(table, rows=trazado, images_unavailable=True)
    assert convergence_document(publish_convergence(no_images))["imagenes"] == NOT_AVAILABLE_TEXT


def test_bloque_de_procedencia() -> None:
    sidecar = convergence_sidecar(convergence_notes([_table()]))
    assert list(sidecar) == list(SIDECAR_KEYS)
    assert sidecar["umbral_aparece"] == 0.5
    assert sidecar["red_ign"] == "sin asfaltar y asfaltada (ADR 0050)"
    sources = sidecar["fuentes"]
    assert isinstance(sources, list)
    assert all(list(source) == list(SIDECAR_SOURCE_KEYS) for source in sources)
    assert sources[0] == {
        "fuente": "via_pecuaria_oficial",
        "atribucion": [],
        "fecha_consulta": None,
    }
    assert sources[-1]["fecha_consulta"] == date(2026, 11, 27).isoformat()
