"""Tests unitarios de `application/build_convergence_tables.py` (historia #240).

Dobles SINTÉTICOS de los tres ports (`tests/convergence_support.py`), que registran las
llamadas: cada fuente se carga una sola vez por municipio."""

import dataclasses

import pytest

from parcel_intel.application.build_convergence_tables import (
    NO_MANIFEST,
    BuildConvergenceTablesUseCase,
    StretchConvergence,
)
from parcel_intel.domain.convergence import (
    APPEARS_MIN_FRACTION,
    CONVERGENCE_ROW_SOURCES,
    HistoricRowSource,
    LayerRowSource,
    OrthophotoRowSource,
    RowSource,
)
from parcel_intel.domain.published_comparison import TOO_LONG
from tests.convergence_support import (
    FakeComparisons,
    FakeHistoric,
    FakeLayers,
    comparison_for,
    coverage,
    empty_coverages,
    layer,
    line,
    manifest,
    stretch,
)

INE = "28043"
AXIS_A = line((0, 0), (200, 0))
AXIS_B = line((0, 0), (0, 150))
A = stretch(AXIS_A, stretch_id="aaaaaaaaaaaaaaaa")
B = stretch(AXIS_B, stretch_id="bbbbbbbbbbbbbbbb")


def _use_case(
    sources: tuple[RowSource, ...] = CONVERGENCE_ROW_SOURCES,
    appears_min_fraction: float = APPEARS_MIN_FRACTION,
) -> tuple[BuildConvergenceTablesUseCase, FakeLayers, FakeHistoric, FakeComparisons]:
    layers = FakeLayers({"ign_red_transporte": layer("ign_red_transporte", {"T": AXIS_A})})
    historic = FakeHistoric()
    comparisons = FakeComparisons(
        manifest(comparison_for(AXIS_A, A.stretch_id), comparison_for(AXIS_B, B.stretch_id))
    )
    use_case = BuildConvergenceTablesUseCase(
        layers, historic, comparisons, sources, appears_min_fraction
    )
    return use_case, layers, historic, comparisons


def test_carga_cada_fuente_una_vez_por_municipio() -> None:
    use_case, layers, historic, comparisons = _use_case()
    result = use_case.execute(INE, [B, A])
    assert [r.stretch_id for r in result.results] == ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"]
    assert layers.calls == [
        ("via_pecuaria_oficial", INE),
        ("ign_red_transporte", INE),
        ("catastro_vt", INE),
    ]
    assert historic.calls == ["planimetria", "mtn50"]
    assert comparisons.calls == [INE]
    table = result.results[0].table
    assert table is not None
    assert len(table.rows) == len(CONVERGENCE_ROW_SOURCES)
    assert [row.value for row in table.rows[:3]] == ["sin_cobertura", "aparece", "sin_cobertura"]


def test_sin_fuentes_de_imagen_no_pide_el_manifiesto() -> None:
    sources = (LayerRowSource("ign_red_transporte"), HistoricRowSource("mtn50"))
    use_case, _, historic, comparisons = _use_case(sources=sources)
    result = use_case.execute(INE, [A])
    assert comparisons.calls == []
    assert historic.calls == ["mtn50"]
    table = result.results[0].table
    assert table is not None and [row.source_key for row in table.rows] == [
        "ign_red_transporte",
        "mtn50_historico",
    ]


def test_sin_manifiesto_todos_los_tramos_llevan_el_motivo() -> None:
    use_case, _, _, comparisons = _use_case()
    comparisons.manifest = None
    result = use_case.execute(INE, [A, B])
    assert [(r.table, r.failure) for r in result.results] == [(None, NO_MANIFEST)] * 2


def test_un_tramo_sin_tabla_no_frena_a_los_demas() -> None:
    use_case, _, _, comparisons = _use_case()
    assert comparisons.manifest is not None
    too_long = dataclasses.replace(
        comparisons.manifest.stretches[0], status="tramo_demasiado_largo", windows=()
    )
    comparisons.manifest = dataclasses.replace(
        comparisons.manifest, stretches=(too_long, comparisons.manifest.stretches[1])
    )
    first, second = use_case.execute(INE, [A, B]).results
    assert (first.table, first.failure) == (None, TOO_LONG)
    assert second.table is not None and second.failure is None


def test_umbral_configurable_en_el_caso_de_uso() -> None:
    use_case, layers, _, _ = _use_case(appears_min_fraction=0.6)
    layers.layers["ign_red_transporte"] = layer("ign_red_transporte", {"T": line((0, 0), (100, 0))})
    table = use_case.execute(INE, [A]).results[0].table
    assert table is not None and table.appears_min_fraction == 0.6
    assert table.rows[1].value == "no_aparece"  # 0,525 < 0,6
    with pytest.raises(ValueError, match="appears_min_fraction"):
        _use_case(appears_min_fraction=0)


def test_valida_los_tramos() -> None:
    use_case, *_ = _use_case()
    with pytest.raises(ValueError, match="mismo stretch_id"):
        use_case.execute(INE, [A, A])
    with pytest.raises(ValueError, match="otro municipio"):
        use_case.execute("28013", [A])
    assert use_case.execute(INE, []).results == ()


def test_fuentes_repetidas() -> None:
    with pytest.raises(ValueError, match="repetidas"):
        _use_case(sources=(OrthophotoRowSource("reciente"), OrthophotoRowSource("reciente")))


def test_port_de_capas_incoherente() -> None:
    use_case, layers, _, _ = _use_case()
    layers.layers["via_pecuaria_oficial"] = layer("catastro_vt", {})
    with pytest.raises(ValueError, match="al pedir via_pecuaria_oficial"):
        use_case.execute(INE, [A])


def test_port_historico_incoherente() -> None:
    use_case, _, historic, _ = _use_case()
    historic.coverages = {**empty_coverages(), "planimetria": coverage("mtn50")}
    with pytest.raises(ValueError, match="al pedir planimetria"):
        use_case.execute(INE, [A])


def test_resultado_con_tabla_o_motivo() -> None:
    with pytest.raises(ValueError, match="exactamente"):
        StretchConvergence("aaaaaaaaaaaaaaaa", None, None)


def test_sin_imagenes_si_es_demasiado_largo() -> None:
    """#315 (ADR 0057 §4): con la opción, el tramo largo sale sin filas de ortofoto."""
    _, layers, historic, comparisons = _use_case()
    assert comparisons.manifest is not None
    too_long = dataclasses.replace(
        comparisons.manifest.stretches[0], status="tramo_demasiado_largo", windows=()
    )
    comparisons.manifest = dataclasses.replace(
        comparisons.manifest, stretches=(too_long, comparisons.manifest.stretches[1])
    )
    use_case = BuildConvergenceTablesUseCase(
        layers, historic, comparisons, without_images_if_too_long=True
    )
    first, second = use_case.execute(INE, [A, B]).results
    assert first.table is not None and first.table.images_unavailable
    assert all(row.evidence_kind == "trazado" for row in first.table.rows)
    assert len(first.table.rows) == 5
    assert second.table is not None and not second.table.images_unavailable
