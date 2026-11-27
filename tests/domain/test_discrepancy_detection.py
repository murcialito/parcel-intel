import dataclasses
from typing import get_args

import pytest

from parcel_intel.domain.discrepancy_detection import (
    CANONICAL_SOURCES,
    InconsistentLayersError,
    detect_municipal_discrepancies,
    record_id,
)
from parcel_intel.domain.discrepancy_policy import (
    ABSENCE_PAIRS,
    REDISTRIBUTABLE_SOURCES,
    kinds_kept,
    redact_for_publication,
)
from parcel_intel.domain.discrepancy_report import LayerStatus
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.trail import SourceKind
from tests.trail_factories import (
    MUNICIPALITY,
    line_shape,
    make_layer,
    make_missing,
    make_trail,
    strip_shape,
)


def test_matriz_de_ausencias_exacta_y_sin_pares_simetricos() -> None:
    assert ABSENCE_PAIRS == {
        ("via_pecuaria_oficial", "catastro_vt"),
        ("via_pecuaria_oficial", "ign_red_transporte"),
        ("via_pecuaria_oficial", "planimetria_historica"),
        ("via_pecuaria_oficial", "mtn50_historico"),
        ("catastro_vt", "ign_red_transporte"),
        ("planimetria_historica", "catastro_vt"),
        ("planimetria_historica", "ign_red_transporte"),
        ("mtn50_historico", "catastro_vt"),
        ("mtn50_historico", "ign_red_transporte"),
    }
    assert all((b, a) not in ABSENCE_PAIRS for a, b in ABSENCE_PAIRS)
    assert all(a in get_args(SourceKind) and b in get_args(SourceKind) for a, b in ABSENCE_PAIRS)


def test_redistribuibles_deniega_catastro_por_defecto() -> None:
    assert "catastro_vt" not in REDISTRIBUTABLE_SOURCES
    assert REDISTRIBUTABLE_SOURCES == {
        "via_pecuaria_oficial",
        "ign_red_transporte",
        "planimetria_historica",
        "mtn50_historico",
    }


def test_kinds_kept_por_par_y_direccion() -> None:
    # vía → IGN: par de ausencias; el desplazamiento va en la dirección canónica (ign < via).
    assert kinds_kept("via_pecuaria_oficial", "ign_red_transporte") == {
        "AUSENTE_EN_FUENTE",
        "SOLAPE",
    }
    assert kinds_kept("ign_red_transporte", "via_pecuaria_oficial") == {"DESPLAZAMIENTO"}
    # catastro → IGN: las dos cosas.
    assert kinds_kept("catastro_vt", "ign_red_transporte") == {
        "AUSENTE_EN_FUENTE",
        "SOLAPE",
        "DESPLAZAMIENTO",
    }
    assert kinds_kept("ign_red_transporte", "catastro_vt") == frozenset()
    # Un anejo no es sujeto de ausencia ni de solape.
    assert kinds_kept("via_pecuaria_oficial", "ign_red_transporte", subject_is_anejo=True) == set()


def test_un_anejo_sin_equivalente_no_genera_ausente() -> None:
    abrevadero = make_trail("A1", "via_pecuaria_oficial", strip_shape(0, 0, 30, 30), role="anejo")
    via = make_trail("V1", "via_pecuaria_oficial", strip_shape(0, 500, 200, 520))
    ign = make_trail("R1", "ign_red_transporte", line_shape((0, 5000), (10, 5000)))

    report = detect_municipal_discrepancies(
        MUNICIPALITY,
        [
            make_layer("via_pecuaria_oficial", [abrevadero, via]),
            make_layer("ign_red_transporte", [ign]),
        ],
        [],
    )

    assert [r.discrepancy.subject.trail_id for r in report.records] == ["V1"]


def test_record_id_estable_16_hex_y_cambia_con_los_datos() -> None:
    def build(length: float) -> str:
        # La zona es el trazado de A: el identificador cambia si cambia su geometría.
        layers = [
            make_layer(
                "catastro_vt", [make_trail("C1", "catastro_vt", line_shape((0, 0), (length, 0)))]
            ),
            make_layer(
                "ign_red_transporte",
                [make_trail("R1", "ign_red_transporte", line_shape((0, 12.5), (length, 12.5)))],
            ),
        ]
        [record] = detect_municipal_discrepancies(MUNICIPALITY, layers, []).records
        assert record.record_id == record_id(record.discrepancy)
        return record.record_id

    first = build(200.0)
    assert first == build(200.0)
    assert len(first) == 16 and int(first, 16) >= 0
    assert first != build(210.0)


def test_redactar_es_idempotente_y_marca_zona_solo_si_el_lado_a_no_es_publicable() -> None:
    layers = [
        make_layer("catastro_vt", [make_trail("C1", "catastro_vt", line_shape((0, 0), (200, 0)))]),
        make_layer(
            "ign_red_transporte",
            [make_trail("R1", "ign_red_transporte", line_shape((0, 12.5), (200, 12.5)))],
        ),
    ]
    report = detect_municipal_discrepancies(MUNICIPALITY, layers, [])

    once = redact_for_publication(report)

    assert redact_for_publication(once) == once
    [record] = once.records
    assert record.zone_redacted is True
    assert record.trails[0].geometry is None  # catastro
    assert record.trails[1].geometry is not None  # IGN (CC BY, #24)
    assert record.trails[1].provenance == report.records[0].trails[1].provenance
    assert report.records[0].trails[0].geometry is not None  # el original no se toca


def test_capas_incoherentes_se_rechazan() -> None:
    catastro = make_trail("C1", "catastro_vt", line_shape((0, 0), (1, 0)))
    with pytest.raises(InconsistentLayersError, match="repetido"):
        detect_municipal_discrepancies(
            MUNICIPALITY, [make_layer("catastro_vt", [catastro, catastro])], []
        )
    with pytest.raises(InconsistentLayersError, match="más de una vez"):
        detect_municipal_discrepancies(
            MUNICIPALITY, [make_layer("catastro_vt", [catastro])], [make_missing("catastro_vt")]
        )
    with pytest.raises(InconsistentLayersError, match="municipio"):
        detect_municipal_discrepancies("28999", [make_layer("catastro_vt", [catastro])], [])
    with pytest.raises(InconsistentLayersError, match="no pertenece"):
        detect_municipal_discrepancies(
            MUNICIPALITY, [make_layer("ign_red_transporte", [catastro])], []
        )
    available = dataclasses.replace(make_missing("mtn50_historico"), status=LayerStatus.DISPONIBLE)
    with pytest.raises(InconsistentLayersError, match="AUSENTE"):
        detect_municipal_discrepancies(MUNICIPALITY, [], [available])


def test_sin_capas_devuelve_informe_vacio_con_las_ausentes() -> None:
    report = detect_municipal_discrepancies(
        MUNICIPALITY, [], [make_missing(source) for source in CANONICAL_SOURCES]
    )

    assert report.records == ()
    assert [s.source for s in report.layers] == list(CANONICAL_SOURCES)
    assert CANONICAL_SOURCES == tuple(sorted(get_args(SourceKind)))


def test_trazado_con_geometria_vacia_en_la_capa_contraria_no_rompe() -> None:
    vacio = make_trail("R0", "ign_red_transporte", Geometry(rings=(), srid=25830))
    via = make_trail("V1", "via_pecuaria_oficial", strip_shape(0, 0, 200, 20))

    report = detect_municipal_discrepancies(
        MUNICIPALITY,
        [make_layer("via_pecuaria_oficial", [via]), make_layer("ign_red_transporte", [vacio])],
        [],
    )

    ign = next(s for s in report.layers if s.source == "ign_red_transporte")
    assert ign.empty_geometry_ids == ("R0",)
    assert [r.discrepancy.kind for r in report.records] == ["AUSENTE_EN_FUENTE"]


def test_el_informe_lleva_el_nombre_del_municipio_de_sus_capas() -> None:
    """#94: el nombre del municipio sale de las capas y se conserva al redactar."""
    via = make_trail("V1", "via_pecuaria_oficial", line_shape((0, 0), (100, 0)))
    road = make_trail("R1", "ign_red_transporte", line_shape((0, 500), (100, 500)))
    named = dataclasses.replace(
        make_layer("via_pecuaria_oficial", [via]), municipality_name="Colmenar de Oreja"
    )
    unnamed = make_layer("ign_red_transporte", [road])
    report = detect_municipal_discrepancies(MUNICIPALITY, [named, unnamed], [])
    assert report.municipality_name == "Colmenar de Oreja"
    assert redact_for_publication(report).municipality_name == "Colmenar de Oreja"

    nameless = detect_municipal_discrepancies(MUNICIPALITY, [unnamed], [])
    assert nameless.municipality_name is None

    other = dataclasses.replace(unnamed, municipality_name="Chinchón")
    with pytest.raises(InconsistentLayersError, match="nombres de municipio distintos"):
        detect_municipal_discrepancies(MUNICIPALITY, [named, other], [])


def test_un_trazado_solo_contraparte_nunca_es_sujeto() -> None:
    """#183, ADR 0050: un tramo asfaltado paralelo a 20 m de una vía daría un
    DESPLAZAMIENTO con el IGN de sujeto; marcado solo contraparte, no da ninguno."""
    via = make_trail("V1", "via_pecuaria_oficial", line_shape((0, 0), (1000, 0)))
    asfaltado = dataclasses.replace(
        make_trail("P1", "ign_red_transporte", line_shape((0, 20), (1000, 20))),
        counterpart_only=True,
    )
    catastro = make_trail("C1", "catastro_vt", line_shape((0, 5000), (1000, 5000)))

    report = detect_municipal_discrepancies(
        MUNICIPALITY,
        [
            make_layer("via_pecuaria_oficial", [via]),
            make_layer("ign_red_transporte", [asfaltado]),
            make_layer("catastro_vt", [catastro]),
        ],
        [],
    )

    assert all(r.discrepancy.subject.trail_id != "P1" for r in report.records)
    ign = next(s for s in report.layers if s.source == "ign_red_transporte")
    assert ign.trail_count == 1  # cuenta en el resumen aunque no sea sujeto

    # Guardia: sin la marca, el mismo tramo sí sería sujeto (la prueba discrimina).
    unmarked = detect_municipal_discrepancies(
        MUNICIPALITY,
        [
            make_layer("via_pecuaria_oficial", [via]),
            make_layer("ign_red_transporte", [dataclasses.replace(asfaltado, counterpart_only=False)]),
            make_layer("catastro_vt", [catastro]),
        ],
        [],
    )
    assert any(r.discrepancy.subject.trail_id == "P1" for r in unmarked.records)


def test_un_trazado_solo_contraparte_cuenta_como_equivalente() -> None:
    via = make_trail("V1", "via_pecuaria_oficial", line_shape((0, 0), (1000, 0)))
    asfaltado = make_trail("P1", "ign_red_transporte", line_shape((0, 2), (1000, 2)))

    def records(counterpart_only: bool) -> list[str]:
        road = dataclasses.replace(asfaltado, counterpart_only=counterpart_only)
        report = detect_municipal_discrepancies(
            MUNICIPALITY,
            [make_layer("via_pecuaria_oficial", [via]), make_layer("ign_red_transporte", [road])],
            [],
        )
        return [r.discrepancy.kind for r in report.records]

    assert records(counterpart_only=True) == []
    assert records(counterpart_only=False) == []
    vacia = detect_municipal_discrepancies(
        MUNICIPALITY,
        [make_layer("via_pecuaria_oficial", [via]), make_layer("ign_red_transporte", [])],
        [],
    )
    assert [r.discrepancy.kind for r in vacia.records] == ["AUSENTE_EN_FUENTE"]
