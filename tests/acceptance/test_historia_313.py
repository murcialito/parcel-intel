"""Historia #313: cobertura histórica de la tabla de convergencia desde `curated/historico`
(hija A de #246, ADR 0057). Los docstrings copian el criterio literal.

Todas las unidades son sintéticas: la `280075-w1` es la fixture de #137 y las demás se generan
en `tmp_path` copiándola (otro `unit_id`, otro tipo de documento, puntos desplazados...).
"""

import hashlib
import json
import shutil
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.curated_historic import CuratedHistoricFiles
from parcel_intel.adapters.ign_historic import IgnHistoricImageAdapter
from parcel_intel.application.historic_coverage import CuratedHistoricCoverageSource
from parcel_intel.application.load_historic_trails import HistoricUnitUseCase
from parcel_intel.domain.convergence import historic_row
from parcel_intel.domain.digitization import DigitizedTrail
from parcel_intel.domain.georeferencing import (
    IGN_HISTORIC_LICENSE,
    ControlPointSet,
    GeoreferenceUnit,
    SyncOutcome,
    UnitSpec,
    unit_footprint,
)
from parcel_intel.domain.historic_coverage import HistoricCoverage
from parcel_intel.domain.historic_trail import HistoricDocumentKind, HistoricTrail
from parcel_intel.ports.errors import HistoricCoverageError
from parcel_intel.ports.historic_coverage import HistoricCoverageSource
from tests.convergence_support import lines, stretch

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
PLANIMETRIAS = REPO / "tests" / "fixtures" / "caminos" / "planimetrias"
HISTORICO = PLANIMETRIAS / "historico"
RECORTE = PLANIMETRIAS / "planimetria_colmenar_280075_recorte_casco_2mpx.png"
UNIT_ID = "280075-w1"
TODAY = date(2026, 11, 28)


def _no_network(url: str, headers: Mapping[str, str]) -> bytes:
    raise AssertionError(f"llamada de red inesperada: {url}")


def _write_cache(
    cache: Path, unit_id: str, body: bytes | None = None, source: str | None = None
) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    content = RECORTE.read_bytes() if body is None else body
    spec = CuratedHistoricFiles(HISTORICO).read_unit(UNIT_ID)
    (cache / f"{unit_id}.png").write_bytes(content)
    (cache / f"{unit_id}.provenance.json").write_text(
        json.dumps(
            {
                "fuente": source or spec.provenance_source,
                "url": spec.image_url,
                "fecha_descarga": "2026-11-25",
                "licencia": IGN_HISTORIC_LICENSE,
                "sha256": hashlib.sha256(content).hexdigest(),
                "formato": "image/png",
                "ancho_px": 500,
                "alto_px": 500,
                "crs": "EPSG:25830",
            }
        ),
        encoding="utf-8",
    )


def _add_unit(curated: Path, cache: Path, unit_id: str, document_kind: str | None = None) -> None:
    shutil.copytree(HISTORICO / UNIT_ID, curated / unit_id)
    path = curated / unit_id / "unidad.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["unit_id"] = unit_id
    source = None
    if document_kind is not None:
        data["document_kind"] = document_kind
        source = "Primera edición MTN50, IGN, hoja 280075"
        data["provenance_source"] = source
    path.write_text(json.dumps(data), encoding="utf-8")
    _write_cache(cache, unit_id, source=source)


class CountingInputs:
    """Doble transparente de `CuratedHistoricInputPort`: cuenta las lecturas de cada unidad."""

    def __init__(self, inner: CuratedHistoricFiles) -> None:
        self._inner = inner
        self.unit_reads: dict[str, int] = {}

    def read_unit(self, unit_id: str) -> UnitSpec:
        self.unit_reads[unit_id] = self.unit_reads.get(unit_id, 0) + 1
        return self._inner.read_unit(unit_id)

    def read_control_points(self, unit_id: str) -> ControlPointSet:
        return self._inner.read_control_points(unit_id)

    def read_trails(self, unit_id: str) -> tuple[DigitizedTrail, ...]:
        return self._inner.read_trails(unit_id)


class _Recorder:
    def __init__(self) -> None:
        self.approved: tuple[HistoricTrail, ...] = ()

    def sync_unit(self, unit: GeoreferenceUnit, approved: Sequence[HistoricTrail]) -> SyncOutcome:
        self.approved = tuple(approved)
        return SyncOutcome(inserted=(), updated=(), unchanged=(), withdrawn=())

    def get_unit(self, unit_id: str) -> GeoreferenceUnit:  # pragma: no cover
        raise AssertionError("no se usa")

    def list_unit_trail_ids(self, unit_id: str) -> tuple[str, ...]:  # pragma: no cover
        raise AssertionError("no se usa")


def _source(curated: Path, cache: Path) -> tuple[CuratedHistoricCoverageSource, CountingInputs]:
    files = CuratedHistoricFiles(curated)
    inputs = CountingInputs(files)
    images = IgnHistoricImageAdapter(cache, _no_network, lambda: TODAY, offline=True)
    return CuratedHistoricCoverageSource(files, inputs, images, lambda: TODAY), inputs


@pytest.fixture
def world(tmp_path: Path) -> tuple[Path, Path]:
    """(curated, cache) con la unidad sintética 280075-w1 aceptada."""
    curated = tmp_path / "curated"
    cache = tmp_path / "cache"
    curated.mkdir()
    _add_unit(curated, cache, UNIT_ID)
    return curated, cache


def _edit_csv(curated: Path, unit_id: str, old: str, new: str) -> None:
    path = curated / unit_id / "puntos_control.csv"
    path.write_bytes(path.read_bytes().replace(old.encode(), new.encode()))


# --- CA1 -----------------------------------------------------------------


@pytest.mark.parametrize("kind", ["planimetria", "mtn50"])
def test_ca1_sin_directorio_o_sin_unidades_la_cobertura_sale_vacia(
    tmp_path: Path, kind: HistoricDocumentKind
) -> None:
    """CA1 (CA7 de #246). Dado un directorio `curated/historico/` inexistente o sin unidades
    del tipo pedido, cuando se pide la cobertura de `planimetria` o `mtn50`, entonces se
    devuelve una `HistoricCoverage` con `units == ()` y `trails == ()`, sin excepción. Con
    ella, `historic_row` da «Sin cobertura»."""
    # (a) directorio inexistente
    source, _ = _source(tmp_path / "no_existe", tmp_path / "cache")
    coverage = source.get_coverage(kind)
    assert isinstance(coverage, HistoricCoverage)
    assert coverage.units == () and coverage.trails == ()
    # (b) directorio con un LEEME y sin unidades
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    (vacio / "LEEME.md").write_text("sin unidades", encoding="utf-8")
    source, _ = _source(vacio, tmp_path / "cache")
    coverage = source.get_coverage(kind)
    assert coverage.units == () and coverage.trails == ()
    assert coverage.provenance.license == "CC BY 4.0"
    # El tipo de documento ausente en un directorio que sí tiene otra unidad.
    assert _row_text_sin_cobertura(coverage)


def _row_text_sin_cobertura(coverage: HistoricCoverage) -> bool:
    shape = lines([(0.0, 0.0), (100.0, 100.0)])
    row = historic_row(stretch(shape), coverage)
    return row.value == "sin_cobertura"


def test_ca1_otro_tipo_con_unidades_tambien_sale_vacio(world: tuple[Path, Path]) -> None:
    """CA1 (variante): hay unidades, pero ninguna del tipo pedido."""
    curated, cache = world
    source, _ = _source(curated, cache)
    coverage = source.get_coverage("mtn50")
    assert coverage.units == () and coverage.trails == ()
    assert _row_text_sin_cobertura(coverage)


# --- CA2 -----------------------------------------------------------------


def test_ca2_unidad_aceptada_da_footprint_fechas_y_los_trazados_de_cargar(
    world: tuple[Path, Path],
) -> None:
    """CA2. Dada la unidad sintética `280075-w1` aceptada, con su imagen de trabajo en la
    caché y sin red, cuando se pide su cobertura, entonces sale 1 unidad cuyo `footprint` es
    `unit_footprint(puntos, afín)`, con `document_date` y `retrieved_at` de `unidad.json`.
    Sus trazados son exactamente los que cargaría `historico cargar` (mismos `identifier` y
    geometría, comparados con `to_historic_trail`), sin propuestos, rechazados ni
    extrapolados."""
    curated, cache = world
    source, _ = _source(curated, cache)
    coverage = source.get_coverage("planimetria")

    files = CuratedHistoricFiles(curated)
    images = IgnHistoricImageAdapter(cache, _no_network, lambda: TODAY, offline=True)
    use_case = HistoricUnitUseCase(files, images)
    assessment = use_case.assess(UNIT_ID)
    assert len(coverage.units) == 1
    unit = coverage.units[0]
    assert unit.unit_id == UNIT_ID
    assert unit.footprint == unit_footprint(assessment.control_points, assessment.fit.transform)
    assert unit.document_date == assessment.spec.document_date == date(1875, 8, 6)
    assert unit.retrieved_at == assessment.spec.image_retrieved_at

    recorder = _Recorder()
    loader = HistoricUnitUseCase(files, images, recorder)
    loader.load(UNIT_ID)
    assert recorder.approved  # la fixture trae aprobados
    assert [(t.identifier, t.geometry) for t in coverage.trails] == sorted(
        [(t.identifier, t.geometry) for t in recorder.approved], key=lambda p: p[0]
    )
    assert coverage.trails == tuple(sorted(recorder.approved, key=lambda t: t.identifier))
    assert all(t.status == "approved" for t in coverage.trails)
    # La procedencia es la de la imagen de la unidad.
    assert coverage.provenance == assessment.image.provenance


# --- CA3 -----------------------------------------------------------------


def test_ca3_veredicto_negativo_no_cuenta_y_se_informa(world: tuple[Path, Path]) -> None:
    """CA3. Dada una unidad con veredicto negativo (por ejemplo, con los puntos retenidos
    reducidos en una copia en `tmp_path`), entonces no cuenta en la cobertura,
    `skipped_units()` la lista con sus motivos y no es un fallo."""
    curated, cache = world
    _add_unit(curated, cache, "280075-w2")
    # P05 +100 m en X: el LOO de la unidad pasa de los 15 m (veredicto negativo).
    _edit_csv(curated, "280075-w2", "467082.0", "467182.0")
    source, _ = _source(curated, cache)
    coverage = source.get_coverage("planimetria")
    assert [u.unit_id for u in coverage.units] == [UNIT_ID]
    skipped = source.skipped_units()
    assert [unit_id for unit_id, _ in skipped] == ["280075-w2"]
    assert skipped[0][1]  # con motivos


# --- CA4 -----------------------------------------------------------------


def test_ca4_aprobacion_caducada(world: tuple[Path, Path]) -> None:
    """CA4 (aprobación caducada). `get_coverage` lanza `HistoricCoverageError` con el
    `unit_id` y un motivo fijo, y no devuelve ninguna cobertura a medias."""
    curated, cache = world
    # Cambiar la descripción de un punto cambia el sha256 del CSV sin cambiar el ajuste.
    _edit_csv(curated, UNIT_ID, "Plaza en el centro", "Plaza central")
    source, _ = _source(curated, cache)
    with pytest.raises(HistoricCoverageError) as caught:
        source.get_coverage("planimetria")
    assert caught.value.unit_id == UNIT_ID
    assert caught.value.reason.startswith("aprobaciones caducadas: ")
    assert caught.value.reason.endswith("; vuelve a revisar la unidad")
    assert "T001" in caught.value.reason


def test_ca4_imagen_fuera_de_la_cache(world: tuple[Path, Path]) -> None:
    """CA4 (imagen fuera de la caché)."""
    curated, cache = world
    shutil.rmtree(cache)
    cache.mkdir()
    source, _ = _source(curated, cache)
    with pytest.raises(HistoricCoverageError) as caught:
        source.get_coverage("planimetria")
    assert caught.value.unit_id == UNIT_ID
    assert caught.value.reason == (
        f"falta la imagen de trabajo en la caché; ejecuta historico ajuste {UNIT_ID}"
    )


def test_ca4_sha256_distinto(world: tuple[Path, Path]) -> None:
    """CA4 (sha256 distinto)."""
    curated, cache = world
    _write_cache(cache, UNIT_ID, body=RECORTE.read_bytes() + b"x")
    source, _ = _source(curated, cache)
    with pytest.raises(HistoricCoverageError) as caught:
        source.get_coverage("planimetria")
    assert caught.value.unit_id == UNIT_ID
    assert caught.value.reason == "la imagen de trabajo no es la declarada"


@pytest.mark.parametrize(
    ("name", "content", "field"),
    [
        ("puntos_control.csv", b"basura\n", "puntos_control"),
        ("trazados.geojson", b"{no es json", "trazados"),
        ("unidad.json", b'{"unit_id": "280075-w1"}', "unidad"),
    ],
)
def test_ca4_fichero_que_no_valida(
    world: tuple[Path, Path], name: str, content: bytes, field: str
) -> None:
    """CA4 (un fichero que no valida)."""
    curated, cache = world
    (curated / UNIT_ID / name).write_bytes(content)
    source, _ = _source(curated, cache)
    with pytest.raises(HistoricCoverageError) as caught:
        source.get_coverage("planimetria")
    assert caught.value.unit_id == UNIT_ID
    assert caught.value.reason == f"entrada no válida: {field}"


def test_ca4_un_fallo_no_devuelve_cobertura_a_medias(world: tuple[Path, Path]) -> None:
    """CA4: con una unidad buena y otra rota no se devuelve la buena sola."""
    curated, cache = world
    _add_unit(curated, cache, "280075-w2")
    (curated / "280075-w2" / "trazados.geojson").write_bytes(b"{")
    source, _ = _source(curated, cache)
    with pytest.raises(HistoricCoverageError) as caught:
        source.get_coverage("planimetria")
    assert caught.value.unit_id == "280075-w2"


# --- CA5 -----------------------------------------------------------------


def test_ca5_tipos_separados_y_orden_por_unit_id(world: tuple[Path, Path]) -> None:
    """CA5. Una unidad de planimetría no aparece en la cobertura de `mtn50`, ni al revés.
    Con dos unidades del mismo tipo (la de 280075 y una segunda sintética en `tmp_path`), las
    dos están ordenadas por `unit_id`."""
    curated, cache = world
    _add_unit(curated, cache, "280075-w0")  # se crea después pero ordena antes
    _add_unit(curated, cache, "280075-h1", document_kind="mtn50")
    source, _ = _source(curated, cache)
    planimetria = source.get_coverage("planimetria")
    mtn50 = source.get_coverage("mtn50")
    assert [u.unit_id for u in planimetria.units] == ["280075-w0", UNIT_ID]
    assert [u.unit_id for u in mtn50.units] == ["280075-h1"]
    assert all(t.document_kind == "planimetria" for t in planimetria.trails)
    assert all(t.document_kind == "mtn50" for t in mtn50.trails)
    identifiers = [t.identifier for t in planimetria.trails]
    assert identifiers == sorted(identifiers)
    assert any(i.startswith("280075-w0-") for i in identifiers)


# --- CA6 -----------------------------------------------------------------


def test_ca6_sin_red_y_cada_unidad_se_lee_una_sola_vez(world: tuple[Path, Path]) -> None:
    """CA6. Ninguna llamada usa la red: el adapter de imágenes se compone con `offline=True`
    y un `http_get` que falla si se llama. Dos llamadas a `get_coverage` del mismo tipo leen
    cada unidad una sola vez."""
    curated, cache = world
    _add_unit(curated, cache, "280075-w2")
    source, inputs = _source(curated, cache)  # `_no_network` falla si se llama
    first = source.get_coverage("planimetria")
    second = source.get_coverage("planimetria")
    assert first == second
    assert inputs.unit_reads == {UNIT_ID: 1, "280075-w2": 1}
    source.get_coverage("mtn50")
    assert inputs.unit_reads == {UNIT_ID: 1, "280075-w2": 1}


# --- CA7 -----------------------------------------------------------------


def test_ca7_cumple_el_port_y_respeta_las_capas() -> None:
    """CA7. `lint-imports` en verde: `CuratedHistoricCoverageSource` vive en `application/`
    y solo importa `ports` y `domain` (el contrato lo comprueba `uv run lint-imports`; aquí
    se comprueba además que ningún import del módulo es de `adapters`/`cli`/`api` y que la
    clase cumple el port)."""
    module = (REPO / "src/parcel_intel/application/historic_coverage.py").read_text(
        encoding="utf-8"
    )
    for layer in ("adapters", "cli", "api"):
        assert f"parcel_intel.{layer}" not in module

    def _use(source: HistoricCoverageSource) -> None: ...

    class _Catalog:
        def unit_ids(self) -> tuple[str, ...]:
            return ()

    files = CuratedHistoricFiles(Path("no_existe"))
    images = IgnHistoricImageAdapter(Path("no_existe"), _no_network, lambda: TODAY, offline=True)
    _use(CuratedHistoricCoverageSource(_Catalog(), files, images, lambda: TODAY))
