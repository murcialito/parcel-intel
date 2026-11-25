"""Historia #14: entidad `Discrepancy` y criterio de discrepancia entre trazados con
tolerancia métrica por tipo de fuente.

Geometrías sintéticas escritas a mano (EPSG:25830) salvo CA13, que usa la fixture real
de vías pecuarias de Colmenar de Oreja ya grabada. Valores-oráculo de la tabla del
diseño de la historia (calculados antes de implementar, lección 0017).
"""

import ast
import dataclasses
import random
import sys
import unicodedata
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.livestock_trails.parsing import parse_wfs_livestock_trails
from parcel_intel.domain.discrepancy import (
    DESCRIPTION_TEMPLATES,
    ComparableTrail,
    Discrepancy,
    NonMetricCrsError,
    SourceRef,
    TrailRef,
    compare_trail,
    describe,
)
from parcel_intel.domain.discrepancy_criterion import (
    CRITERION,
    SOURCE_PRECISION,
    SourceKind,
    pair_tolerance_m,
)
from parcel_intel.domain.geometry import (
    Geometry,
    Line,
    MultiLineGeometry,
    Ring,
    TrailShape,
    ring_perimeter,
)
from parcel_intel.domain.provenance import Provenance

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
VIAS_PECUARIAS_FIXTURE = (
    REPO
    / "tests"
    / "fixtures"
    / "livestock_trails"
    / "wfs_cql_colmenar_municipio_completo_15_tramos.xml"
)

_DATA_DATE: dict[SourceKind, date | None] = {
    "via_pecuaria_oficial": date(2014, 1, 1),
    "catastro_vt": date(2026, 6, 1),
    "ign_red_transporte": date(2025, 3, 15),
    "planimetria_historica": date(1875, 1, 1),
    "mtn50_historico": date(1881, 1, 1),
}


def _source(kind: SourceKind) -> SourceRef:
    return SourceRef(
        kind=kind,
        provenance=Provenance(
            source=f"fuente sintética {kind}",
            url=f"https://example.invalid/{kind}",
            retrieved_at=date(2026, 11, 25),
            license="licencia sintética",
        ),
        data_date=_DATA_DATE[kind],
    )


def _line(*points: tuple[float, float]) -> MultiLineGeometry:
    return MultiLineGeometry(lines=(tuple(points),), srid=25830)


def _trail(trail_id: str, kind: SourceKind, shape: TrailShape) -> ComparableTrail:
    return ComparableTrail(ref=TrailRef(trail_id=trail_id, source=_source(kind)), shape=shape)


def _compare(
    subject: ComparableTrail, kind_b: SourceKind, others: list[ComparableTrail]
) -> Discrepancy | None:
    return compare_trail(subject, _source(kind_b), others)


def _rectangle(x0: float, x1: float, y0: float, y1: float) -> Ring:
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))


def test_ca1_ausente_en_fuente_indica_donde_falta() -> None:
    """CA1. Dado un trazado presente en la fuente A y sin equivalente en la fuente B dentro
    de la tolerancia, cuando se evalúa el criterio, entonces se produce una `Discrepancia`
    de tipo `AUSENTE_EN_FUENTE` que indica en cuál de las dos falta."""
    subject = _trail("ign-1", "ign_red_transporte", _line((0.0, 0.0), (100.0, 0.0)))
    far = _trail("vt-1", "catastro_vt", _line((0.0, 500.0), (100.0, 500.0)))

    for others in ([far], []):
        result = _compare(subject, "catastro_vt", others)

        assert result is not None
        assert result.kind == "AUSENTE_EN_FUENTE"
        assert result.counterpart_source.kind == "catastro_vt"
        assert result.subject.source.kind == "ign_red_transporte"
        assert result.counterpart_trails == ()
        assert result.measurement("longitud_sin_equivalente_m") == 100.0
        assert result.confidence == 0.78


def test_ca2_desplazamiento_por_encima_de_la_tolerancia() -> None:
    """CA2. Dados dos trazados equivalentes cuyo eje queda desplazado más que la tolerancia
    del par de fuentes, cuando se evalúa, entonces se produce una `Discrepancia` de tipo
    `DESPLAZAMIENTO` con la distancia medida en metros (EPSG:25830). Si el desplazamiento
    es menor o igual que la tolerancia, no se produce discrepancia."""
    subject = _trail("ign-1", "ign_red_transporte", _line((0.0, 0.0), (100.0, 0.0)))
    shifted = _trail("vt-1", "catastro_vt", _line((0.0, 12.0), (100.0, 12.0)))

    result = _compare(subject, "catastro_vt", [shifted])

    assert result is not None
    assert result.kind == "DESPLAZAMIENTO"
    assert result.measurement("desplazamiento_mediano_m") == 12.0
    assert result.measurement("tolerancia_par_m") == 7.071
    assert result.confidence == 0.543
    assert result.zone.srid == 25830
    assert {m.unit for m in result.evidence if m.name.startswith("desplazamiento")} == {"m"}

    within = _trail("vt-1", "catastro_vt", _line((0.0, 7.0), (100.0, 7.0)))
    assert _compare(subject, "catastro_vt", [within]) is None


def test_ca3_solape_parcial_con_fraccion_y_longitud_no_coincidente() -> None:
    """CA3. Dados dos trazados que solo se solapan en parte, cuando se evalúa, entonces se
    produce una `Discrepancia` de tipo `SOLAPE` con la fracción solapada y la longitud no
    coincidente."""
    subject = _trail("ign-1", "ign_red_transporte", _line((0.0, 0.0), (100.0, 0.0)))
    partial = _trail("vt-1", "catastro_vt", _line((0.0, 0.0), (60.0, 0.0)))

    result = _compare(subject, "catastro_vt", [partial])

    assert result is not None
    assert result.kind == "SOLAPE"
    assert result.measurement("fraccion_solapada") == 0.65
    assert result.measurement("longitud_no_coincidente_m") == 35.0
    assert result.confidence == 0.273
    assert isinstance(result.zone, MultiLineGeometry)
    assert len(result.zone.lines) == 1
    zone_line = result.zone.lines[0]
    assert zone_line[0] == pytest.approx((65.0, 0.0))
    assert zone_line[-1] == pytest.approx((100.0, 0.0))


def test_ca4_tolerancia_mayor_con_fuentes_menos_precisas_y_declarada_en_un_sitio() -> None:
    """CA4. Dada la misma pareja de trazados, cuando se evalúa con fuentes de menor
    precisión (p. ej. planimetría de 1875 frente a red del IGN), entonces la tolerancia
    aplicada es mayor que con dos fuentes vectoriales, y es un valor declarado por tipo de
    fuente en un único sitio (no números mágicos repartidos)."""
    vectorial = pair_tolerance_m("ign_red_transporte", "catastro_vt")
    historical = pair_tolerance_m("planimetria_historica", "ign_red_transporte")
    assert round(vectorial, 3) == 7.071
    assert round(historical, 3) == 40.311
    assert historical > vectorial

    subject = _trail("plan-1", "planimetria_historica", _line((0.0, 0.0), (100.0, 0.0)))
    shifted = _trail("ign-1", "ign_red_transporte", _line((0.0, 12.0), (100.0, 12.0)))
    assert _compare(subject, "ign_red_transporte", [shifted]) is None

    # Un único sitio: cada tipo de fuente tiene su tolerancia en la tabla, y ningún otro
    # módulo del criterio declara números de tolerancia.
    assert set(SOURCE_PRECISION) == set(_DATA_DATE)
    criterion_source = (REPO / "src" / "parcel_intel" / "domain" / "discrepancy.py").read_text(
        encoding="utf-8"
    )
    for precision in SOURCE_PRECISION.values():
        assert f"{precision.positional_tolerance_m}" not in criterion_source


def test_ca5_discrepancia_rastreable_hasta_ambas_fuentes_y_su_regla() -> None:
    """CA5. Dada una `Discrepancia`, entonces lleva: tipo, geometría de la zona en
    discrepancia (EPSG:25830), las dos fuentes con su `Provenance` (fuente, URL, fecha de
    descarga, licencia) y la fecha del dato de cada una, una confianza, la evidencia
    (medidas que la sustentan) y el identificador de la regla/criterio que la produjo, de
    modo que se pueda rastrear hasta ambos."""
    subject = _trail("ign-1", "ign_red_transporte", _line((0.0, 0.0), (100.0, 0.0)))
    shifted = _trail("vt-1", "catastro_vt", _line((0.0, 12.0), (100.0, 12.0)))

    result = _compare(subject, "catastro_vt", [shifted])

    assert result is not None
    assert result.kind == "DESPLAZAMIENTO"
    assert result.zone.srid == 25830
    for source, kind in (
        (result.subject.source, "ign_red_transporte"),
        (result.counterpart_source, "catastro_vt"),
    ):
        assert source.kind == kind
        assert source.provenance.source
        assert source.provenance.url
        assert source.provenance.retrieved_at == date(2026, 11, 25)
        assert source.provenance.license
        assert source.data_date == _DATA_DATE[kind]
    assert result.subject.trail_id == "ign-1"
    assert result.counterpart_trails == (shifted.ref,)
    assert 0.0 < result.confidence <= 1.0
    assert [m.name for m in result.evidence] == [
        "tolerancia_par_m",
        "radio_busqueda_m",
        "paso_muestreo_m",
        "longitud_sujeto_m",
        "desplazamiento_mediano_m",
        "desplazamiento_min_m",
        "desplazamiento_max_m",
    ]
    assert result.criterion == CRITERION
    assert result.criterion.identifier == "discrepancia_trazados"
    assert result.criterion.version == 1


def test_ca6_confianza_determinista_y_menor_con_tolerancia_grande() -> None:
    """CA6. Dada la confianza, entonces se calcula de forma determinista a partir de las
    medidas y de la precisión de las fuentes (misma entrada, misma salida), sin ningún LLM,
    y baja cuando la tolerancia aplicada es grande."""
    vectorial = _compare(
        _trail("ign-1", "ign_red_transporte", _line((0.0, 0.0), (100.0, 0.0))),
        "catastro_vt",
        [],
    )
    subject = _trail("plan-1", "planimetria_historica", _line((0.0, 0.0), (100.0, 0.0)))
    first = _compare(subject, "ign_red_transporte", [])
    second = _compare(subject, "ign_red_transporte", [])

    assert vectorial is not None and first is not None
    assert first.kind == "AUSENTE_EN_FUENTE"
    assert first.confidence == 0.383
    assert first.confidence < vectorial.confidence == 0.78
    assert first == second

    # Sin ningún LLM: el criterio no importa nada fuera de stdlib y del dominio.
    for module in ("discrepancy.py", "discrepancy_criterion.py"):
        text = (REPO / "src" / "parcel_intel" / "domain" / module).read_text(encoding="utf-8")
        assert "deepseek" not in text.lower()
        assert "llm" not in text.lower()


_FORBIDDEN = (
    "usurp",
    "ilegal",
    "delito",
    "ocupaci",
    "invasi",
    "intrus",
    "propietari",
    "titular",
    "dueñ",
    "culpa",
)


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def test_ca7_sin_titularidad_y_solo_lenguaje_de_indicio() -> None:
    """CA7. La entidad `Discrepancia` no tiene ningún campo de titularidad ni de
    propietario, y su descripción usa solo lenguaje de indicio ("trazado en X y ausente en
    Y"), nunca "usurpación", "ilegal" o similar; un test lo comprueba sobre las plantillas
    de descripción."""
    for entity in (Discrepancy, TrailRef, SourceRef, ComparableTrail):
        for field in dataclasses.fields(entity):
            name = field.name.lower()
            assert not any(word in name for word in ("owner", "titular", "propiet"))

    subject = _trail("ign-1", "ign_red_transporte", _line((0.0, 0.0), (100.0, 0.0)))
    cases = {
        "AUSENTE_EN_FUENTE": [],
        "DESPLAZAMIENTO": [_trail("vt-1", "catastro_vt", _line((0.0, 12.0), (100.0, 12.0)))],
        "SOLAPE": [_trail("vt-1", "catastro_vt", _line((0.0, 0.0), (60.0, 0.0)))],
    }
    texts = list(DESCRIPTION_TEMPLATES.values())
    for kind, others in cases.items():
        result = _compare(subject, "catastro_vt", others)
        assert result is not None and result.kind == kind
        text = describe(result)
        assert "Indicio a verificar" in text
        texts.append(text)
    assert set(DESCRIPTION_TEMPLATES) == set(cases)

    for text in texts:
        normalized = _normalize(text)
        for word in _FORBIDDEN:
            assert _normalize(word) not in normalized, (word, text)


def test_ca8_geometrias_vacias_y_multiparte() -> None:
    """CA8. Dadas geometrías vacías (`rings=()`) o multi-parte (2 o más anillos/partes),
    cuando se evalúa el criterio, entonces no falla y trata ambos casos correctamente
    (lecciones 0001 y 0006)."""
    empty_polygon = _trail("vp-0", "via_pecuaria_oficial", Geometry(rings=(), srid=25830))
    empty_lines = _trail("ign-0", "ign_red_transporte", MultiLineGeometry(lines=(), srid=25830))
    assert _compare(empty_polygon, "ign_red_transporte", []) is None
    assert _compare(empty_lines, "catastro_vt", []) is None

    subject = _trail("ign-1", "ign_red_transporte", _line((0.0, 0.0), (100.0, 0.0)))
    empty_b = _trail("vt-0", "catastro_vt", Geometry(rings=(), srid=25830))
    same_b = _trail("vt-1", "catastro_vt", _line((0.0, 0.0), (100.0, 0.0)))
    assert _compare(subject, "catastro_vt", [empty_b, same_b]) is None

    two_strips = _trail(
        "vp-1",
        "via_pecuaria_oficial",
        Geometry(
            rings=(_rectangle(0, 200, -10, 10), _rectangle(1000, 1200, -10, 10)),
            srid=25830,
        ),
    )
    axis = _trail("ign-2", "ign_red_transporte", _line((0.0, 0.0), (200.0, 0.0)))

    result = _compare(two_strips, "ign_red_transporte", [axis])

    assert result is not None
    assert result.kind == "SOLAPE"
    assert result.measurement("fraccion_solapada") == 0.5
    assert result.measurement("longitud_no_coincidente_m") == 220.0
    assert result.measurement("longitud_sujeto_m") == 440.0


def _l_shaped_strip() -> Geometry:
    ring: Ring = (
        (0.0, -10.0),
        (210.0, -10.0),
        (210.0, 200.0),
        (190.0, 200.0),
        (190.0, 10.0),
        (0.0, 10.0),
        (0.0, -10.0),
    )
    return Geometry(rings=(ring,), srid=25830)


def test_ca10_franja_y_su_propio_eje_no_discrepan_en_ningun_sentido() -> None:
    """CA10. Dada una franja poligonal (vía pecuaria) y la polilínea de su propio eje en
    otra fuente, tanto recta (rectángulo 200 × 20 m frente a su eje) como en forma de L
    (dos brazos de 20 m de ancho frente a su eje quebrado), cuando se evalúa el criterio en
    los dos sentidos (franja frente a eje y eje frente a franja), entonces no se produce
    ninguna discrepancia."""
    straight_axis: Line = ((0.0, 0.0), (200.0, 0.0))
    l_axis: Line = ((0.0, 0.0), (200.0, 0.0), (200.0, 200.0))
    pairs = (
        (Geometry(rings=(_rectangle(0, 200, -10, 10),), srid=25830), straight_axis),
        (_l_shaped_strip(), l_axis),
    )
    for strip_shape, axis_line in pairs:
        strip = _trail("vp-1", "via_pecuaria_oficial", strip_shape)
        axis = _trail("ign-1", "ign_red_transporte", _line(*axis_line))
        assert _compare(strip, "ign_red_transporte", [axis]) is None
        assert _compare(axis, "via_pecuaria_oficial", [strip]) is None


def test_ca11_srid_no_metrico_lanza_error_sin_reproyectar() -> None:
    """CA11. Dado un trazado (sujeto o contraparte) con `srid` distinto de 25830, cuando se
    evalúa, entonces el criterio lanza `NonMetricCrsError` y no reproyecta ni compara en
    silencio."""
    metric = _trail("ign-1", "ign_red_transporte", _line((0.0, 0.0), (100.0, 0.0)))
    geographic = _trail(
        "vt-1",
        "catastro_vt",
        MultiLineGeometry(lines=(((-3.4, 40.1), (-3.39, 40.1)),), srid=4326),
    )
    with pytest.raises(NonMetricCrsError):
        _compare(metric, "catastro_vt", [geographic])

    geographic_subject = _trail(
        "vt-1",
        "catastro_vt",
        MultiLineGeometry(lines=(((-3.4, 40.1), (-3.39, 40.1)),), srid=4326),
    )
    with pytest.raises(NonMetricCrsError):
        _compare(geographic_subject, "ign_red_transporte", [])


def test_ca12_resultado_igual_con_contrapartes_en_otro_orden() -> None:
    """CA12. Dados los mismos trazados con los de la fuente B en otro orden, cuando se
    evalúa dos veces, entonces las dos `Discrepancia` son iguales (`==`), incluidos el orden
    de `counterpart_trails` y los valores redondeados de confianza y evidencia."""
    subject = _trail("ign-1", "ign_red_transporte", _line((0.0, 0.0), (100.0, 0.0)))
    others = [
        _trail("vt-c", "catastro_vt", _line((0.0, 12.0), (40.0, 12.0))),
        _trail("vt-a", "catastro_vt", _line((40.0, 13.0), (100.0, 13.0))),
        _trail("vt-b", "catastro_vt", _line((0.0, 800.0), (100.0, 800.0))),
        _trail("vt-d", "catastro_vt", _line((40.0, 13.0), (100.0, 13.0))),
    ]
    reference = _compare(subject, "catastro_vt", others)
    assert reference is not None
    assert reference.kind == "DESPLAZAMIENTO"
    assert [ref.trail_id for ref in reference.counterpart_trails] == ["vt-a", "vt-c"]

    rng = random.Random(14)
    for _ in range(5):
        shuffled = others[:]
        rng.shuffle(shuffled)
        assert _compare(subject, "catastro_vt", shuffled) == reference


def _vereda_de_la_mesa() -> ComparableTrail:
    raw = [
        trail
        for trail in parse_wfs_livestock_trails(VIAS_PECUARIAS_FIXTURE.read_bytes())
        if trail["name"] == "Vereda de la Mesa"
    ]
    assert len(raw) == 1
    return _trail(raw[0]["trail_code"], "via_pecuaria_oficial", Geometry(raw[0]["rings"], 25830))


def test_ca13_vereda_de_la_mesa_real_multiparte() -> None:
    """CA13. Dado el tramo real multi-parte "Vereda de la Mesa" de la fixture
    `tests/fixtures/livestock_trails/wfs_cql_colmenar_municipio_completo_15_tramos.xml`
    (2 anillos), cuando se evalúa (a) contra sí mismo como contraparte, entonces no hay
    discrepancia; y (b) contra una fuente B sin trazados, entonces hay una
    `AUSENTE_EN_FUENTE` cuya `longitud_sujeto_m` es la suma de los semiperímetros de
    **los dos** anillos (no solo del primero)."""
    vereda = _vereda_de_la_mesa()
    assert isinstance(vereda.shape, Geometry)
    assert len(vereda.shape.rings) == 2

    assert _compare(vereda, "via_pecuaria_oficial", [vereda]) is None

    result = _compare(vereda, "ign_red_transporte", [])
    assert result is not None
    assert result.kind == "AUSENTE_EN_FUENTE"
    semiperimeters = [ring_perimeter(ring) / 2 for ring in vereda.shape.rings]
    assert result.measurement("longitud_sujeto_m") == pytest.approx(
        round(sum(semiperimeters), 3), abs=1e-3
    )
    assert result.measurement("longitud_sujeto_m") > max(semiperimeters) + 1.0


def test_ca9_dominio_solo_stdlib_y_sin_otras_capas() -> None:
    """CA9. `lint-imports`, `mypy` y `ruff` siguen en verde: dominio solo stdlib, sin
    importar otras capas."""
    for module in ("discrepancy.py", "discrepancy_criterion.py", "geometry.py"):
        tree = ast.parse(
            (REPO / "src" / "parcel_intel" / "domain" / module).read_text(encoding="utf-8")
        )
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                top = name.split(".")[0]
                assert top in sys.stdlib_module_names or name.startswith("parcel_intel.domain"), (
                    module,
                    name,
                )
