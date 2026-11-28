"""Tests unitarios de `domain/normative_citation.py` (historia #187). Datos sintéticos."""

from datetime import date
from typing import Any

import pytest

from parcel_intel.domain.normative_citation import (
    BOE_REUSE_LICENSE,
    MAX_TEXT_LENGTH,
    InvalidNormativeCitationError,
    NormativeCatalog,
    NormativeCitation,
    build_catalog,
    catalog_fingerprint,
    citation_payload,
    is_citation_id,
    text_fingerprint,
)
from tests.fixtures.normativa import generar


def _citation(**overrides: Any) -> NormativeCitation:
    text = overrides.pop("text", "Texto sintético de prueba.")
    fields: dict[str, Any] = {
        "citation_id": "sintetica-art-01",
        "norm_title": "Ley sintética 9/2090",
        "boe_id": "BOE-A-9999-1",
        "article": "Artículo 1",
        "norm_date": date(2090, 3, 23),
        "last_updated": date(2090, 3, 23),
        "text": text,
        "url": "https://www.boe.es/buscar/act.php?id=BOE-A-9999-1",
        "retrieved_at": date(2090, 3, 23),
        "license": BOE_REUSE_LICENSE,
        "catalog_version": 1,
        "text_sha256": text_fingerprint(text),
        "source_kinds": ("via_pecuaria_oficial",),
    }
    fields.update(overrides)
    return NormativeCitation(**fields)


def test_fechas_iguales_y_url_sin_ancla_valen() -> None:
    citation = _citation()
    assert citation.note is None


@pytest.mark.parametrize("anchor", ["a2", "da1", "dt", "a10bis"])
def test_anclas_validas(anchor: str) -> None:
    _citation(url=f"https://www.boe.es/buscar/act.php?id=BOE-A-9999-1#{anchor}")


@pytest.mark.parametrize("anchor", ["", "A2", "a-2", "a2/x"])
def test_anclas_no_validas(anchor: str) -> None:
    with pytest.raises(InvalidNormativeCitationError, match="url"):
        _citation(url=f"https://www.boe.es/buscar/act.php?id=BOE-A-9999-1#{anchor}")


def test_ultima_actualizacion_anterior_a_la_norma() -> None:
    with pytest.raises(InvalidNormativeCitationError, match="ultima_actualizacion: anterior"):
        _citation(last_updated=date(2090, 3, 22))


@pytest.mark.parametrize("version", [0, -1, True])
def test_version_de_cita_no_valida(version: object) -> None:
    with pytest.raises(InvalidNormativeCitationError, match="version_catalogo"):
        _citation(catalog_version=version)


@pytest.mark.parametrize(
    "kinds",
    [
        (),
        ("vereda",),
        ("via_pecuaria_oficial", "via_pecuaria_oficial"),
        ("via_pecuaria_oficial", "catastro_vt"),
    ],
)
def test_tipos_de_fuente_no_validos(kinds: tuple[str, ...]) -> None:
    with pytest.raises(InvalidNormativeCitationError, match="tipos_fuente"):
        _citation(source_kinds=kinds)


@pytest.mark.parametrize("citation_id", ["", "Art-1", "art--1", "-art", "art_1", "a" * 81])
def test_id_no_valido_no_se_repite(citation_id: str) -> None:
    assert not is_citation_id(citation_id)
    with pytest.raises(InvalidNormativeCitationError) as info:
        _citation(citation_id=citation_id)
    assert str(info.value).startswith("cita: id: ")


def test_texto_demasiado_largo() -> None:
    text = "x" * (MAX_TEXT_LENGTH + 1)
    with pytest.raises(InvalidNormativeCitationError, match="texto: pasa de"):
        _citation(text=text, text_sha256=text_fingerprint(text))


def test_huella_en_mayusculas_se_rechaza() -> None:
    text = "Texto sintético de prueba."
    with pytest.raises(InvalidNormativeCitationError, match="64 hexadecimales"):
        _citation(text_sha256=text_fingerprint(text).upper())


def test_nota_vacia_se_rechaza() -> None:
    with pytest.raises(InvalidNormativeCitationError, match="nota"):
        _citation(note="  ")


def test_huella_del_texto_es_sha256_utf8_sin_normalizar() -> None:
    assert text_fingerprint("ñ") == generar.sha256_text("ñ")
    assert text_fingerprint("ñ") != text_fingerprint("ñ")


def test_payload_y_huella_coinciden_con_el_oraculo_independiente() -> None:
    cites = generar.citations()
    citations = [
        _citation(
            citation_id=c["id"],
            norm_title=c["norma"],
            article=c["articulo"],
            norm_date=date.fromisoformat(c["fecha_norma"]),
            last_updated=date.fromisoformat(c["ultima_actualizacion"]),
            text=c["texto"],
            url=c["url"],
            retrieved_at=date.fromisoformat(c["consultado"]),
            source_kinds=tuple(c["tipos_fuente"]),
            note=c.get("nota"),
        )
        for c in cites
    ]
    assert catalog_fingerprint(1, citations) == generar.catalog_fingerprint(1, cites)
    assert catalog_fingerprint(1, citations[::-1]) == catalog_fingerprint(1, citations)
    payload = citation_payload(citations[1])
    assert payload["nota"] is None
    assert set(payload) == set(cites[0]) | {"nota"}


def test_catalogo_vacio_y_por_fuente() -> None:
    catalog = build_catalog(1, [])
    assert catalog.citations == ()
    assert len(catalog.by_source()) == 5
    assert catalog.fingerprint == generar.catalog_fingerprint(1, [])


def test_catalogo_rechaza_repetidos_version_orden_y_huella() -> None:
    a = _citation(citation_id="a")
    b = _citation(citation_id="b")
    with pytest.raises(InvalidNormativeCitationError, match="a: id: repetido"):
        build_catalog(1, [a, a])
    with pytest.raises(InvalidNormativeCitationError, match="version_catalogo"):
        build_catalog(2, [a])
    with pytest.raises(InvalidNormativeCitationError, match="ordenadas"):
        NormativeCatalog(1, (b, a), catalog_fingerprint(1, [a, b]))
    with pytest.raises(InvalidNormativeCitationError, match="huella calculada"):
        NormativeCatalog(1, (a, b), "0" * 64)
    with pytest.raises(InvalidNormativeCitationError, match="version"):
        NormativeCatalog(0, (), catalog_fingerprint(0, []))


def test_for_source_con_cita_de_dos_tipos() -> None:
    a = _citation(citation_id="a", source_kinds=("catastro_vt", "via_pecuaria_oficial"))
    b = _citation(citation_id="b", source_kinds=("catastro_vt",))
    catalog = build_catalog(1, [b, a])
    assert [c.citation_id for c in catalog.for_source("catastro_vt")] == ["a", "b"]
    assert [c.citation_id for c in catalog.for_source("via_pecuaria_oficial")] == ["a"]
    assert catalog.for_source("mtn50_historico") == ()
