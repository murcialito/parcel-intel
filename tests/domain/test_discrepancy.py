"""Tests unitarios del criterio de discrepancia (historia #14), con geometrías sintéticas."""

from datetime import date

import pytest

from parcel_intel.domain.discrepancy import (
    ComparableTrail,
    SourceRef,
    TrailRef,
    compare_trail,
    describe,
)
from parcel_intel.domain.discrepancy_criterion import (
    SOURCE_LABEL,
    SOURCE_PRECISION,
    SourceKind,
    correspondence_radius_m,
    pair_tolerance_m,
    search_radius_m,
)
from parcel_intel.domain.geometry import Geometry, MultiLineGeometry, TrailShape
from parcel_intel.domain.provenance import Provenance


def _source(kind: SourceKind, data_date: date | None = date(2025, 1, 1)) -> SourceRef:
    return SourceRef(
        kind=kind,
        provenance=Provenance(
            source=kind, url=f"https://example.invalid/{kind}", retrieved_at=date(2026, 11, 25)
        ),
        data_date=data_date,
    )


def _line(*points: tuple[float, float]) -> MultiLineGeometry:
    return MultiLineGeometry(lines=(tuple(points),), srid=25830)


def _trail(trail_id: str, kind: SourceKind, shape: TrailShape) -> ComparableTrail:
    return ComparableTrail(TrailRef(trail_id, _source(kind)), shape)


_SUBJECT = _trail("ign-1", "ign_red_transporte", _line((0.0, 0.0), (100.0, 0.0)))


def test_tolerancias_de_pares_de_la_tabla_de_diseno() -> None:
    assert round(pair_tolerance_m("via_pecuaria_oficial", "ign_red_transporte"), 3) == 11.18
    assert round(pair_tolerance_m("via_pecuaria_oficial", "catastro_vt"), 3) == 11.18
    assert round(pair_tolerance_m("mtn50_historico", "planimetria_historica"), 3) == 64.031
    assert pair_tolerance_m("catastro_vt", "ign_red_transporte") == pair_tolerance_m(
        "ign_red_transporte", "catastro_vt"
    )


def test_radio_de_correspondencia_es_tres_veces_la_tolerancia_del_par() -> None:
    tolerance = pair_tolerance_m("catastro_vt", "ign_red_transporte")
    assert search_radius_m(tolerance) == 3 * tolerance
    assert correspondence_radius_m("catastro_vt", "ign_red_transporte") == 3 * tolerance


def test_cada_tipo_de_fuente_tiene_etiqueta_y_justificacion() -> None:
    assert set(SOURCE_LABEL) == set(SOURCE_PRECISION)
    assert all(p.rationale for p in SOURCE_PRECISION.values())


def test_contraparte_de_otra_fuente_es_un_error() -> None:
    wrong = _trail("ign-2", "ign_red_transporte", _line((0.0, 0.0), (100.0, 0.0)))
    with pytest.raises(ValueError, match="ign-2"):
        compare_trail(_SUBJECT, _source("catastro_vt"), [wrong])


def test_extremo_no_coincidente_menor_que_la_tolerancia_no_es_discrepancia() -> None:
    # Cubierto hasta x = 97,5 (95 + 2,5 ≤ 7,071): queda sin cubrir menos de la tolerancia.
    nearly = _trail("vt-1", "catastro_vt", _line((0.0, 0.0), (95.0, 0.0)))
    assert compare_trail(_SUBJECT, _source("catastro_vt"), [nearly]) is None


def test_desplazamiento_incluye_minimo_y_maximo() -> None:
    oblique = _trail("vt-1", "catastro_vt", _line((0.0, 10.0), (100.0, 20.0)))
    result = compare_trail(_SUBJECT, _source("catastro_vt"), [oblique])
    assert result is not None and result.kind == "DESPLAZAMIENTO"
    low = result.measurement("desplazamiento_min_m")
    high = result.measurement("desplazamiento_max_m")
    assert low < result.measurement("desplazamiento_mediano_m") < high


def test_contraparte_lejana_o_degenerada_no_cambia_el_resultado() -> None:
    shifted = _trail("vt-1", "catastro_vt", _line((0.0, 12.0), (100.0, 12.0)))
    far = _trail("vt-0", "catastro_vt", _line((5000.0, 5000.0), (5100.0, 5000.0)))
    single_point = _trail("vt-00", "catastro_vt", _line((0.0, 0.0)))
    base = compare_trail(_SUBJECT, _source("catastro_vt"), [shifted])
    assert base == compare_trail(_SUBJECT, _source("catastro_vt"), [far, single_point, shifted])


def test_franja_horaria_y_antihoraria_dan_lo_mismo() -> None:
    ccw = ((0.0, -10.0), (200.0, -10.0), (200.0, 10.0), (0.0, 10.0))
    cw = tuple(reversed(ccw))
    axis = [_trail("ign-1", "ign_red_transporte", _line((0.0, 20.0), (200.0, 20.0)))]
    results = [
        compare_trail(
            _trail("vp-1", "via_pecuaria_oficial", Geometry((ring,), 25830)),
            _source("ign_red_transporte"),
            axis,
        )
        for ring in (ccw, cw)
    ]
    first, second = results
    assert first is not None and second is not None
    assert first.kind == "DESPLAZAMIENTO"
    assert first.evidence == second.evidence


def test_zona_de_solape_une_piezas_consecutivas_y_separa_tramos() -> None:
    middle = _trail("vt-1", "catastro_vt", _line((30.0, 0.0), (70.0, 0.0)))
    result = compare_trail(_SUBJECT, _source("catastro_vt"), [middle])
    assert result is not None and result.kind == "SOLAPE"
    assert isinstance(result.zone, MultiLineGeometry)
    # Muestras en 2,5; 7,5…: sin cubrir hasta 22,5 y desde 77,5 (a más de 7,071 m).
    assert [(line[0][0], line[-1][0]) for line in result.zone.lines] == [
        (0.0, 25.0),
        (75.0, 100.0),
    ]


def test_descripciones_citan_fuentes_fechas_y_medidas() -> None:
    absent = compare_trail(_SUBJECT, _source("catastro_vt", data_date=None), [])
    assert absent is not None
    assert describe(absent) == (
        "Trazado en red de transporte del IGN (2025-01-01) sin equivalente en Catastro, "
        "vías de dominio público (sin fecha) a menos de 21 m. Indicio a verificar, no es "
        "un dictamen."
    )
    shifted = _trail("vt-1", "catastro_vt", _line((0.0, 12.0), (100.0, 12.0)))
    moved = compare_trail(_SUBJECT, _source("catastro_vt"), [shifted])
    assert moved is not None
    assert "desplazado unos 12 m" in describe(moved)
    assert "tolerancia 7 m" in describe(moved)
    partial = _trail("vt-1", "catastro_vt", _line((0.0, 0.0), (60.0, 0.0)))
    overlap = compare_trail(_SUBJECT, _source("catastro_vt"), [partial])
    assert overlap is not None
    assert describe(overlap).startswith("El 65 % del trazado")
    assert "35 m no coinciden" in describe(overlap)
