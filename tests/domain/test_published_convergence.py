"""Tests unitarios de `domain/published_convergence.py` (historia #315). Fixtures SINTÉTICAS."""

import dataclasses
from datetime import date

import pytest

from parcel_intel.domain.comparison_image import COMPARISON_SLOTS, FLIGHTS, attribution_for
from parcel_intel.domain.convergence import (
    CONVERGENCE_ROW_SOURCES,
    CONVERGENCE_WARNING,
    ConvergenceRow,
    ConvergenceTable,
    PreparedLayer,
    build_convergence_table,
    prepare_layer,
)
from parcel_intel.domain.public_card import CATASTRO_ATTRIBUTION, SOURCE_POLICY
from parcel_intel.domain.published_comparison import NOT_AVAILABLE_TEXT
from parcel_intel.domain.published_convergence import (
    IGN_NETWORK_NOTE,
    ROW_ATTRIBUTIONS,
    ROW_LABELS,
    ROW_SOURCE_KEYS,
    ConvergenceNotPublishableError,
    check_published_convergence,
    convergence_notes,
    publish_convergence,
)
from parcel_intel.domain.trail import SourceKind
from tests.convergence_support import (
    comparison_for,
    empty_coverages,
    layer,
    line,
    stretch,
)

TRAMO = line((0, 0), (200, 0))


def _table(appears_min_fraction: float = 0.5) -> ConvergenceTable:
    """Tabla con la capa del IGN (el tramo «Aparece») y las imágenes de la comparación."""
    ign = layer("ign_red_transporte", {"T": TRAMO}, {"T": date(2024, 5, 1)})
    prepared: dict[SourceKind, PreparedLayer] = {"ign_red_transporte": prepare_layer(ign)}
    return build_convergence_table(
        stretch(TRAMO),
        CONVERGENCE_ROW_SOURCES,
        prepared,
        empty_coverages(),
        comparison_for(TRAMO),
        appears_min_fraction,
    )


def test_claves_rotulos_y_atribuciones_admitidas() -> None:
    assert ROW_SOURCE_KEYS[:5] == (
        "via_pecuaria_oficial",
        "ign_red_transporte",
        "catastro_vt",
        "planimetria_historica",
        "mtn50_historico",
    )
    assert ROW_SOURCE_KEYS[5:] == tuple(f"ortofoto:{slot.name}" for slot in COMPARISON_SLOTS)
    assert "Ortofoto reciente" in ROW_LABELS and "Camino actual (IGN)" in ROW_LABELS
    assert CATASTRO_ATTRIBUTION in ROW_ATTRIBUTIONS
    for vintage, flight in FLIGHTS.items():
        assert attribution_for(vintage) in ROW_ATTRIBUTIONS
        if flight.notice is not None:
            assert flight.notice in ROW_ATTRIBUTIONS
    for policy in SOURCE_POLICY.values():
        assert policy.attribution in ROW_ATTRIBUTIONS


def test_publica_la_tabla_sin_id_ni_umbral() -> None:
    table = _table()
    published = publish_convergence(table)
    assert published.rows == table.rows
    assert published.method == "convergencia_fuentes v2"
    assert published.criterion == "discrepancia_trazados v1"
    assert published.images_note is None
    assert table.stretch_id not in repr(published)
    assert {f.name for f in dataclasses.fields(published)} == {
        "title",
        "rows",
        "warning",
        "method",
        "criterion",
        "images_note",
    }


def test_sin_imagenes_lleva_la_nota_validada() -> None:
    table = dataclasses.replace(
        _table(),
        rows=tuple(row for row in _table().rows if row.evidence_kind == "trazado"),
        images_unavailable=True,
    )
    assert publish_convergence(table).images_note == NOT_AVAILABLE_TEXT


def test_el_aviso_dice_es_publico_y_no_se_veta() -> None:
    """El aviso fijo dice «si el camino es público» (ADR 0054 §9): la barrera no lo veta."""
    assert "es público" in CONVERGENCE_WARNING
    check_published_convergence(publish_convergence(_table()))


@pytest.mark.parametrize(
    "changes",
    [
        {"title": "Otro título"},
        {"warning": "Otro aviso que es público"},
        {"images_note": "Sin fotos"},
        {"method": "convergencia_fuentes v2 es público"},
        {"criterion": "criterio 99999A00109101"},
        {"method": "https://x.invalid/?refcat=1"},
        {"criterion": "un corte"},
    ],
)
def test_barrera_rechaza_textos_ajenos(changes: dict[str, str]) -> None:
    published = dataclasses.replace(publish_convergence(_table()), **changes)  # type: ignore[arg-type]
    with pytest.raises(ConvergenceNotPublishableError):
        check_published_convergence(published)


def test_barrera_rechaza_filas_ajenas() -> None:
    published = publish_convergence(_table())
    *others, last = published.rows
    for row in (
        dataclasses.replace(last, label="Otro rótulo"),
        dataclasses.replace(last, attributions=("Otra atribución",)),
        dataclasses.replace(last, source_key="ortofoto:1900"),
    ):
        tampered = dataclasses.replace(published, rows=(*others, row))
        with pytest.raises(ConvergenceNotPublishableError):
            check_published_convergence(tampered)


def test_barrera_comprueba_la_huella(monkeypatch: pytest.MonkeyPatch) -> None:
    import parcel_intel.domain.published_convergence as module

    published = publish_convergence(_table())
    monkeypatch.setattr(module, "compute_convergence_text_hash", lambda: "0" * 64)
    with pytest.raises(ConvergenceNotPublishableError, match="validó el fundador"):
        check_published_convergence(published)


def test_notas_de_procedencia() -> None:
    notes = convergence_notes([_table(), _table()])
    assert notes.method == "convergencia_fuentes v2"
    assert notes.appears_min_fraction == 0.5
    assert notes.ign_network == IGN_NETWORK_NOTE
    assert [key for key, _, _ in notes.sources] == list(ROW_SOURCE_KEYS)
    by_key = {key: (attributions, consulted) for key, attributions, consulted in notes.sources}
    assert by_key["via_pecuaria_oficial"] == ((), None)
    assert by_key["ign_red_transporte"][0] == (SOURCE_POLICY["ign_red_transporte"].attribution,)
    assert by_key["ortofoto:reciente"][1] == date(2026, 11, 27)


def test_notas_rechazan_mezclas_y_vacio() -> None:
    with pytest.raises(ConvergenceNotPublishableError):
        convergence_notes([])
    with pytest.raises(ConvergenceNotPublishableError, match="umbrales"):
        convergence_notes([_table(), _table(appears_min_fraction=0.8)])


def test_notas_rechazan_una_fuente_desconocida() -> None:
    row = ConvergenceRow(
        "otra", "Vía pecuaria oficial", "trazado", "sin_cobertura", None, None, (), ()
    )
    table = dataclasses.replace(_table(), rows=(row,))
    with pytest.raises(ConvergenceNotPublishableError, match="desconocida"):
        convergence_notes([table])
