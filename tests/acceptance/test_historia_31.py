"""Historia #31: detectar discrepancias de un municipio (dominio y caso de uso)."""

import ast
import dataclasses
import random
import time
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.livestock_trails.parsing import parse_wfs_livestock_trails
from parcel_intel.application.detect_discrepancies import DetectDiscrepanciesUseCase
from parcel_intel.domain import discrepancy_detection
from parcel_intel.domain.discrepancy import (
    ComparableTrail,
    Discrepancy,
    SourceRef,
    TrailRef,
    compare_trail,
)
from parcel_intel.domain.discrepancy_criterion import CRITERION
from parcel_intel.domain.discrepancy_detection import detect_municipal_discrepancies
from parcel_intel.domain.discrepancy_policy import kinds_kept, redact_for_publication
from parcel_intel.domain.discrepancy_report import (
    DiscrepancyRecord,
    LayerStatus,
    LayerSummary,
    MunicipalDiscrepancyReport,
    TrailEvidence,
    TrailLayer,
)
from parcel_intel.domain.geometry import Geometry, MultiLineGeometry
from parcel_intel.domain.livestock_trail import LivestockTrail, livestock_trail_to_trail
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.trail import SourceKind, Trail
from parcel_intel.ports.errors import TrailLayerUnavailableError
from tests.adapters.livestock_trails.helpers import FIXTURES_DIR
from tests.trail_factories import (
    MUNICIPALITY,
    line_shape,
    make_layer,
    make_trail,
    strip_shape,
)

pytestmark = pytest.mark.acceptance

_COLMENAR = FIXTURES_DIR / "wfs_cql_colmenar_municipio_completo_15_tramos.xml"
_SRC = Path(__file__).parents[2] / "src" / "parcel_intel"


class _LayerPort:
    """Doble de `MunicipalTrailLayerPort`: registra lo que se le pide (lección 0010)."""

    def __init__(
        self,
        layers: Sequence[TrailLayer],
        unavailable: Sequence[SourceKind] = (),
        broken: Sequence[SourceKind] = (),
    ) -> None:
        self._layers = {layer.source: layer for layer in layers}
        self._unavailable = set(unavailable)
        self._broken = set(broken)
        self.requests: list[tuple[str, str]] = []

    def get_layer(self, source: SourceKind, municipality_code: str) -> TrailLayer:
        self.requests.append((source, municipality_code))
        if source in self._broken:
            raise ValueError(f"fichero corrupto de {source}")
        if source in self._unavailable or source not in self._layers:
            raise TrailLayerUnavailableError(source, municipality_code, "sin capa derivada")
        return self._layers[source]


class _Sink:
    """Doble de `DiscrepancyReportSink`: guarda lo que recibe."""

    def __init__(self) -> None:
        self.written: list[MunicipalDiscrepancyReport] = []

    def write(self, report: MunicipalDiscrepancyReport) -> None:
        self.written.append(report)


def _detect(
    layers: Sequence[TrailLayer], missing: Sequence[LayerSummary] = ()
) -> MunicipalDiscrepancyReport:
    return detect_municipal_discrepancies(MUNICIPALITY, layers, missing)


def _displaced_scenario(offset_m: float) -> list[TrailLayer]:
    """Catastro (y = 0) e IGN (y = `offset_m`), dos líneas paralelas de 200 m."""
    return [
        make_layer("catastro_vt", [make_trail("C1", "catastro_vt", line_shape((0, 0), (200, 0)))]),
        make_layer(
            "ign_red_transporte",
            [make_trail("R1", "ign_red_transporte", line_shape((0, offset_m), (200, offset_m)))],
        ),
    ]


def test_ca1_compara_cada_par_de_fuentes_y_devuelve_discrepancias_de_14() -> None:
    """Dado un municipio con trazados de varias fuentes (fixtures sintéticas), cuando se
    ejecuta `DetectDiscrepanciesUseCase`, entonces compara cada par de fuentes disponibles y
    devuelve un `MunicipalDiscrepancyReport` cuyas discrepancias son `Discrepancy` de #14 con
    su `criterion_id`."""
    layers = [
        make_layer(
            "via_pecuaria_oficial",
            [make_trail("V1", "via_pecuaria_oficial", strip_shape(0, 0, 200, 20))],
        ),
        make_layer(
            "catastro_vt", [make_trail("C1", "catastro_vt", line_shape((0, 400), (200, 400)))]
        ),
        make_layer(
            "ign_red_transporte",
            [make_trail("R1", "ign_red_transporte", line_shape((0, 412.5), (200, 412.5)))],
        ),
    ]
    port = _LayerPort(layers)
    internal, public = _Sink(), _Sink()

    report = DetectDiscrepanciesUseCase(port, internal, public).execute(MUNICIPALITY)

    assert report.municipality_code == MUNICIPALITY
    assert report.criterion_id == f"{CRITERION.identifier}@{CRITERION.version}"
    assert all(isinstance(r.discrepancy, Discrepancy) for r in report.records)
    assert all(r.discrepancy.criterion == CRITERION for r in report.records)
    # Par catastro-IGN: desplazamiento. Par vía-resto: ausencias (sin equivalente cercano).
    got = {
        (
            r.discrepancy.kind,
            r.discrepancy.subject.source.kind,
            r.discrepancy.counterpart_source.kind,
        )
        for r in report.records
    }
    assert got == {
        ("DESPLAZAMIENTO", "catastro_vt", "ign_red_transporte"),
        ("AUSENTE_EN_FUENTE", "via_pecuaria_oficial", "catastro_vt"),
        ("AUSENTE_EN_FUENTE", "via_pecuaria_oficial", "ign_red_transporte"),
    }
    # Pide las cinco fuentes, en orden canónico, del municipio pedido.
    assert port.requests == [
        (source, MUNICIPALITY)
        for source in sorted(
            [
                "via_pecuaria_oficial",
                "catastro_vt",
                "ign_red_transporte",
                "planimetria_historica",
                "mtn50_historico",
            ]
        )
    ]


def test_ca2_ausente_en_fuente_referencia_trazado_y_capa() -> None:
    """Dado un tramo de vías pecuarias sin correspondencia dentro del radio en la red del IGN,
    cuando se compara el par, entonces hay un registro `AUSENTE_EN_FUENTE` que referencia el
    trazado de vías pecuarias (id, geometría, `Provenance`) y la capa del IGN (fuente y
    `Provenance`)."""
    via = make_trail("V1", "via_pecuaria_oficial", strip_shape(0, 0, 200, 20))
    ign_layer = make_layer(
        "ign_red_transporte",
        [make_trail("R1", "ign_red_transporte", line_shape((0, 1000), (200, 1000)))],
    )
    report = _detect([make_layer("via_pecuaria_oficial", [via]), ign_layer])

    [record] = report.records
    assert record.discrepancy.kind == "AUSENTE_EN_FUENTE"
    assert record.discrepancy.subject.trail_id == "V1"
    assert record.discrepancy.counterpart_source.kind == "ign_red_transporte"
    assert record.discrepancy.counterpart_source.provenance == ign_layer.provenance
    [subject] = record.trails
    assert subject.trail_id == "V1"
    assert subject.geometry == via.geometry
    assert subject.provenance == via.provenance


def test_ca3_desplazamiento_con_la_distancia_exacta() -> None:
    """Dados dos trazados sintéticos paralelos a una distancia fijada de antemano y mayor que
    la tolerancia del par, cuando se compara, entonces hay un registro `DESPLAZAMIENTO` con
    esa distancia exacta en metros."""
    # Tolerancia catastro-IGN: hypot(5, 5) ≈ 7,07 m < 12,5 m.
    report = _detect(_displaced_scenario(12.5))

    [record] = report.records
    assert record.discrepancy.kind == "DESPLAZAMIENTO"
    assert record.discrepancy.measurement("desplazamiento_mediano_m") == 12.5
    assert record.discrepancy.measurement("desplazamiento_min_m") == 12.5
    assert record.discrepancy.measurement("desplazamiento_max_m") == 12.5


def test_ca4_desplazamiento_menor_que_la_tolerancia_no_genera_registro() -> None:
    """Dados dos trazados desplazados menos que la tolerancia del par, cuando se compara,
    entonces no hay ningún registro para ellos."""
    report = _detect(_displaced_scenario(5.0))  # 5 m < 7,07 m

    assert report.records == ()


def test_ca5_conserva_todos_los_trazados_con_su_procedencia() -> None:
    """Dada una discrepancia entre dos fuentes, cuando se construye el registro, entonces
    `trails` contiene el trazado del lado A y todos los de `counterpart_ids`, cada uno con su
    `Provenance` completa (fuente, URL, fecha de descarga, licencia) y su fecha del dato.
    Ninguno se descarta ni se prioriza."""
    catastro = make_trail(
        "C1", "catastro_vt", line_shape((0, 0), (200, 0)), data_date=date(2025, 6, 1)
    )
    ign_1 = make_trail(
        "R1", "ign_red_transporte", line_shape((0, 12.5), (100, 12.5)), data_date=date(2024, 1, 2)
    )
    ign_2 = make_trail(
        "R2", "ign_red_transporte", line_shape((100, 12.5), (200, 12.5)), data_date=date(2026, 3, 4)
    )
    report = _detect(
        [make_layer("catastro_vt", [catastro]), make_layer("ign_red_transporte", [ign_1, ign_2])]
    )

    [record] = report.records
    assert [t.trail_id for t in record.trails] == ["C1", "R1", "R2"]
    assert [ref.trail_id for ref in record.discrepancy.counterpart_trails] == ["R1", "R2"]
    for evidence, original in zip(record.trails, (catastro, ign_1, ign_2), strict=True):
        assert evidence.source == original.source
        assert evidence.provenance == original.provenance
        assert evidence.provenance.source and evidence.provenance.url
        assert evidence.provenance.retrieved_at == date(2026, 11, 26)
        assert evidence.provenance.license
        assert evidence.data_date == original.data_date
        assert evidence.geometry == original.geometry


def test_ca6_capa_no_disponible_se_registra_y_no_falla() -> None:
    """Dado un municipio cuyo port lanza `TrailLayerUnavailableError` para el histórico,
    cuando se ejecuta, entonces compara las demás fuentes y `layers` registra el histórico
    como `AUSENTE` con su motivo. No falla."""
    port = _LayerPort(_displaced_scenario(12.5), unavailable=["planimetria_historica"])
    internal, public = _Sink(), _Sink()

    report = DetectDiscrepanciesUseCase(port, internal, public).execute(MUNICIPALITY)

    assert [r.discrepancy.kind for r in report.records] == ["DESPLAZAMIENTO"]
    by_source = {s.source: s for s in report.layers}
    assert by_source["planimetria_historica"].status is LayerStatus.AUSENTE
    assert by_source["planimetria_historica"].missing_reason == "sin capa derivada"
    assert by_source["planimetria_historica"].provenance is None
    assert by_source["catastro_vt"].status is LayerStatus.DISPONIBLE
    assert by_source["catastro_vt"].trail_count == 1
    assert [s.source for s in report.layers] == sorted(by_source)
    assert len(internal.written) == len(public.written) == 1


def test_ca6_un_error_real_del_port_no_se_convierte_en_ausente() -> None:
    """Complemento de CA6 (riesgo del diseño): cualquier excepción que no sea
    `TrailLayerUnavailableError` es un fallo real y se propaga; no se escribe nada."""
    port = _LayerPort(_displaced_scenario(12.5), broken=["mtn50_historico"])
    internal, public = _Sink(), _Sink()

    with pytest.raises(ValueError, match="corrupto"):
        DetectDiscrepanciesUseCase(port, internal, public).execute(MUNICIPALITY)

    assert internal.written == [] and public.written == []


def test_ca7_no_hay_ausente_en_via_pecuaria_y_el_desplazamiento_sale_una_vez() -> None:
    """Dado un camino de la red del IGN sin equivalente en vías pecuarias, cuando se compara,
    entonces no se emite "ausente en vías pecuarias". Y dado un desplazamiento entre dos
    fuentes, aparece una sola vez (dirección canónica)."""
    via = make_trail("V1", "via_pecuaria_oficial", strip_shape(0, 0, 200, 20))
    ign = make_trail("R1", "ign_red_transporte", line_shape((0, 2000), (200, 2000)))
    report = _detect(
        [make_layer("via_pecuaria_oficial", [via]), make_layer("ign_red_transporte", [ign])]
    )

    assert not any(
        r.discrepancy.subject.source.kind == "ign_red_transporte" for r in report.records
    )
    assert [(r.discrepancy.kind, r.discrepancy.subject.trail_id) for r in report.records] == [
        ("AUSENTE_EN_FUENTE", "V1")
    ]

    displaced = _detect(_displaced_scenario(12.5))
    assert len(displaced.records) == 1
    assert displaced.records[0].discrepancy.subject.source.kind == "catastro_vt"


def _mesa_and_empty_trail() -> tuple[Trail, Trail]:
    provenance = Provenance(
        source="idem",
        url="https://idem.comunidad.madrid/geoidem/Zonas/wfs",
        retrieved_at=date(2026, 10, 16),
    )
    raw = next(
        r
        for r in parse_wfs_livestock_trails(_COLMENAR.read_bytes())
        if r["trail_code"] == "2804303"
    )
    mesa = livestock_trail_to_trail(
        LivestockTrail(
            trail_type=raw["trail_type"],
            name=raw["name"],
            municipality_code=raw["municipality_code"],
            municipality_name=raw["municipality_name"],
            trail_code=raw["trail_code"],
            length_m=raw["length_m"],
            area_m2=raw["area_m2"],
            geometry=Geometry(rings=raw["rings"], srid=25830),
            provenance=provenance,
        )
    )
    empty = dataclasses.replace(
        mesa, identifier="VACIA", geometry=Geometry(rings=(), srid=25830), name=None
    )
    return mesa, empty


def test_ca8_vereda_multiparte_cubierta_a_medias_y_trazado_vacio() -> None:
    """Dados la "Vereda de la Mesa" (multi-parte, 2 polígonos, del fixture real de Colmenar
    convertido con #22), con solo una parte cubierta por la otra fuente, y un trazado con
    `rings=()`, cuando se compara, entonces la parte no cubierta produce su discrepancia, el
    trazado vacío no hace fallar el caso de uso y su id aparece en `empty_geometry_ids`."""
    mesa, empty = _mesa_and_empty_trail()
    assert isinstance(mesa.geometry, Geometry) and len(mesa.geometry.rings) == 2
    first_part, second_part = mesa.geometry.rings
    code = mesa.municipality_code
    historic = make_trail(
        "H1",
        "planimetria_historica",
        Geometry(rings=(first_part,), srid=25830),
        municipality_code=code,
    )
    via_layer = make_layer("via_pecuaria_oficial", [mesa, empty], code)
    historic_layer = make_layer("planimetria_historica", [historic], code)

    report = detect_municipal_discrepancies(mesa.municipality_code, [via_layer, historic_layer], [])

    [record] = report.records
    discrepancy = record.discrepancy
    assert discrepancy.kind == "SOLAPE"
    assert discrepancy.subject.trail_id == "2804303"
    assert [ref.trail_id for ref in discrepancy.counterpart_trails] == ["H1"]
    # La zona en discrepancia es la parte no cubierta: ningún punto de la primera parte.
    assert isinstance(discrepancy.zone, MultiLineGeometry)
    second_min_x = min(x for x, _ in second_part)
    zone_points = [p for line in discrepancy.zone.lines for p in line]
    assert zone_points and all(x >= second_min_x - 1.0 for x, _ in zone_points)
    assert 0.0 < discrepancy.measurement("fraccion_solapada") < 1.0
    via_summary = next(s for s in report.layers if s.source == "via_pecuaria_oficial")
    assert via_summary.empty_geometry_ids == ("VACIA",)
    assert via_summary.trail_count == 2
    assert all(r.discrepancy.subject.trail_id != "VACIA" for r in report.records)


def test_ca9_redaccion_quita_la_geometria_de_fuentes_no_redistribuibles() -> None:
    """Dado un informe con trazados de Catastro y de vías pecuarias, cuando se aplica
    `redact_for_publication`, entonces los de Catastro (y los de `RED_IGN`, mientras #24 esté
    abierta) quedan con `geometry=None` y conservan id y `Provenance`. Si el lado A es
    Catastro, `zone_redacted=True`. Las medidas y la confianza no cambian, y `redacted=True`.
    El caso de uso escribe el informe completo en el sink interno y el redactado en el
    público.

    Nota: #24 ya está cerrada (licencia CC BY confirmada), así que `RED_IGN` entra en
    `REDISTRIBUTABLE_SOURCES` (ADR 0030) y su geometría no se quita."""
    layers = [
        make_layer("catastro_vt", [make_trail("C1", "catastro_vt", line_shape((0, 0), (200, 0)))]),
        make_layer(
            "ign_red_transporte",
            [make_trail("R1", "ign_red_transporte", line_shape((0, 12.5), (200, 12.5)))],
        ),
        make_layer(
            "via_pecuaria_oficial",
            [make_trail("V1", "via_pecuaria_oficial", strip_shape(0, 5000, 200, 5020))],
        ),
    ]
    internal, public = _Sink(), _Sink()
    report = DetectDiscrepanciesUseCase(_LayerPort(layers), internal, public).execute(MUNICIPALITY)

    assert internal.written == [report]
    [published] = public.written
    assert published == redact_for_publication(report)
    assert published.redacted is True and report.redacted is False
    assert all(e.geometry is not None for r in report.records for e in r.trails)

    by_subject = {r.discrepancy.subject.trail_id: r for r in published.records}
    full = {r.discrepancy.subject.trail_id: r for r in report.records}
    catastro = by_subject["C1"]
    assert catastro.zone_redacted is True
    assert catastro.discrepancy.zone == Geometry(rings=(), srid=25830)
    cat_evidence = {e.trail_id: e for e in catastro.trails}["C1"]
    assert cat_evidence.geometry is None
    assert cat_evidence.provenance == full["C1"].trails[0].provenance
    assert catastro.record_id == full["C1"].record_id
    assert catastro.discrepancy.evidence == full["C1"].discrepancy.evidence
    assert catastro.discrepancy.confidence == full["C1"].discrepancy.confidence
    assert catastro.discrepancy.confidence > 0.0

    via = by_subject["V1"]
    assert via.zone_redacted is False
    assert via.discrepancy.zone == full["V1"].discrepancy.zone
    assert via.trails[0].geometry == full["V1"].trails[0].geometry


def _random_layers(
    seed: int, per_layer: int, sources: Sequence[SourceKind], extent: int = 10000
) -> list[TrailLayer]:
    rng = random.Random(seed)
    layers = []
    for source in sources:
        trails = []
        for number in range(per_layer):
            # Parte de las coordenadas en bordes de celda (múltiplos de 250 m).
            cells = extent // 250
            x = float(
                rng.randrange(0, cells) * 250 if number % 5 == 0 else rng.randrange(0, extent)
            )
            y = float(
                rng.randrange(0, cells) * 250 if number % 7 == 0 else rng.randrange(0, extent)
            )
            dx, dy = rng.uniform(-300, 300), rng.uniform(-300, 300)
            geometry: Geometry | MultiLineGeometry
            if source == "via_pecuaria_oficial":
                geometry = strip_shape(x, y, x + abs(dx) + 20.0, y + 20.0)
            else:
                geometry = line_shape((x, y), (x + dx / 2, y + dy / 2), (x + dx, y + dy))
            trails.append(make_trail(f"{source[:3]}-{number:05d}", source, geometry))
        layers.append(make_layer(source, trails))
    return layers


_FOUR: tuple[SourceKind, ...] = (
    "via_pecuaria_oficial",
    "catastro_vt",
    "ign_red_transporte",
    "planimetria_historica",
)


def _brute_force(layers: Sequence[TrailLayer]) -> list[Discrepancy]:
    """Todas las parejas, sin índice: cada trazado contra TODA la capa B."""
    found: list[Discrepancy] = []
    for a in layers:
        for b in layers:
            if a.source == b.source:
                continue
            dates = {t.data_date for t in b.trails}
            b_ref = SourceRef(
                b.source, b.provenance, next(iter(dates)) if len(dates) == 1 else None
            )
            others = [
                ComparableTrail(TrailRef(t.identifier, b_ref), t.geometry)
                for t in sorted(b.trails, key=lambda t: t.identifier)
            ]
            for t in sorted(a.trails, key=lambda t: t.identifier):
                subject = ComparableTrail(
                    TrailRef(t.identifier, SourceRef(a.source, t.provenance, t.data_date)),
                    t.geometry,
                )
                d = compare_trail(subject, b_ref, others)
                if d is not None and d.kind in kinds_kept(a.source, b.source, t.role == "anejo"):
                    found.append(d)
    return found


def _key(d: Discrepancy) -> tuple[str, str, str, str, tuple[str, ...]]:
    return (
        d.kind,
        d.subject.source.kind,
        d.subject.trail_id,
        d.counterpart_source.kind,
        tuple(r.trail_id for r in d.counterpart_trails),
    )


def test_ca10_el_indice_de_rejilla_equivale_a_la_fuerza_bruta() -> None:
    """Dadas las mismas capas, cuando se compara con `GridIndex` y por fuerza bruta
    (implementada en el test), entonces los dos informes son iguales."""
    layers = _random_layers(seed=7, per_layer=70, sources=_FOUR[:3], extent=1500)

    report = _detect(layers)
    expected = sorted(_brute_force(layers), key=_key)

    assert len(expected) > 20  # el escenario ejercita de verdad el prefiltro
    assert [r.discrepancy for r in report.records] == expected
    assert {r.discrepancy.kind for r in report.records} >= {"AUSENTE_EN_FUENTE", "DESPLAZAMIENTO"}


def test_ca11_cuatro_fuentes_de_1500_trazados_en_menos_de_120_s() -> None:
    """Dadas capas sintéticas de 4 fuentes × 1.500 trazados generadas en el test, cuando se
    ejecuta `detect_municipal_discrepancies`, entonces termina en menos de 120 s."""
    layers = _random_layers(seed=11, per_layer=1500, sources=_FOUR)

    started = time.monotonic()
    report = _detect(layers)
    elapsed = time.monotonic() - started

    assert sum(s.trail_count for s in report.layers) == 6000
    assert elapsed < 120.0, f"tardó {elapsed:.1f} s"


def test_ca12_el_orden_de_entrada_no_cambia_el_informe() -> None:
    """Dado el mismo conjunto de capas en distinto orden de entrada, cuando se ejecuta,
    entonces el informe es igual, con registros en el orden canónico y `record_id`
    idénticos."""
    layers = _random_layers(seed=3, per_layer=60, sources=_FOUR, extent=1500)
    shuffled = []
    rng = random.Random(99)
    for layer in layers:
        trails = list(layer.trails)
        rng.shuffle(trails)
        shuffled.append(dataclasses.replace(layer, trails=tuple(trails)))
    rng.shuffle(shuffled)

    first = _detect(layers)
    second = _detect(shuffled)

    assert first.records, "el escenario debe producir registros"
    assert first == second
    assert [r.record_id for r in first.records] == [r.record_id for r in second.records]
    assert len({r.record_id for r in first.records}) == len(first.records)
    keys = [
        (
            r.discrepancy.kind,
            r.discrepancy.subject.source.kind,
            r.discrepancy.subject.trail_id,
            r.discrepancy.counterpart_source.kind,
            tuple(t.trail_id for t in r.discrepancy.counterpart_trails),
            r.record_id,
        )
        for r in first.records
    ]
    assert keys == sorted(keys)


_FORBIDDEN_FIELD_PARTS = (
    "titular",
    "propietario",
    "owner",
    "holder",
    "referencia_catastral",
    "cadastral",
    "parcela",
    "nif",
)


def _field_names(cls: type, seen: set[type] | None = None) -> set[str]:
    seen = seen if seen is not None else set()
    if cls in seen or not dataclasses.is_dataclass(cls):
        return set()
    seen.add(cls)
    names = {f.name for f in dataclasses.fields(cls)}
    for f in dataclasses.fields(cls):
        for candidate in _nested_types(f.type):
            names |= _field_names(candidate, seen)
    return names


def _nested_types(annotation: object) -> list[type]:
    found: list[type] = []
    if isinstance(annotation, type):
        found.append(annotation)
    for arg in getattr(annotation, "__args__", ()):
        found.extend(_nested_types(arg))
    return found


def test_ca13_ningun_campo_de_titularidad() -> None:
    """El informe y sus registros no tienen ningún campo de titularidad ni de propietario
    (test sobre los campos de las dataclasses)."""
    names: set[str] = set()
    for cls in (
        MunicipalDiscrepancyReport,
        DiscrepancyRecord,
        TrailEvidence,
        LayerSummary,
        TrailLayer,
    ):
        names |= _field_names(cls)
    assert {"records", "layers", "discrepancy", "trails", "kind", "zone"} <= names
    for name in names:
        assert not any(part in name.lower() for part in _FORBIDDEN_FIELD_PARTS), name


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def test_ca14_las_capas_se_respetan() -> None:
    """`uv run lint-imports`, `uv run mypy` y `uv run ruff check .` en verde. `domain/` solo
    usa stdlib y `application/detect_discrepancies.py` solo importa `ports` y `domain`.

    (Los tres comandos se ejecutan en CI; aquí se comprueban los imports de los módulos
    nuevos.)"""
    application = _imported_modules(_SRC / "application" / "detect_discrepancies.py")
    assert application
    for module in application:
        assert module.startswith(("parcel_intel.ports", "parcel_intel.domain")), module

    stdlib = {
        "hashlib",
        "json",
        "math",
        "dataclasses",
        "datetime",
        "enum",
        "typing",
        "collections.abc",
    }
    for name in (
        "spatial_index",
        "discrepancy_report",
        "discrepancy_policy",
        "discrepancy_detection",
        "geometry",
    ):
        for module in _imported_modules(_SRC / "domain" / f"{name}.py"):
            assert module.startswith("parcel_intel.domain") or module in stdlib, (name, module)
    assert discrepancy_detection.CANONICAL_SOURCES == tuple(
        sorted(discrepancy_detection.CANONICAL_SOURCES)
    )
