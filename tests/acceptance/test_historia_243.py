"""Historia #243: señal de camino de Catastro más estrecho que la anchura oficial de la vía
pecuaria. Todo sintético y sin red; CA8 necesita `data/` local."""

import json
import re
from pathlib import Path

import pytest

from parcel_intel.adapters.raw_cache import RawCacheMissError
from parcel_intel.adapters.shapely_geometry import ShapelyPolygonClipper
from parcel_intel.adapters.width_signal_files import (
    GeoJsonWidthSignalWriter,
    parse_width_file,
    report_to_geojson_text,
)
from parcel_intel.application.detect_width_narrowing import DetectWidthNarrowingUseCase
from parcel_intel.cli import main
from parcel_intel.domain.geometry import BBox
from parcel_intel.domain.municipal_livestock_trails import MunicipalLivestockTrailLayer
from parcel_intel.domain.parcel import Parcel
from parcel_intel.domain.width_signal import MunicipalWidthReport
from parcel_intel.ports.errors import CadastralServiceError
from tests.cut_signal_support import INFRASTRUCTURE_VT, ParcelsPort, parcel, rect
from tests.width_signal_support import TILE_SIDE_M, Layers, WidthSink, layer_of, piece

pytestmark = pytest.mark.acceptance

DEFAULT_OUT = Path("data/derived/estrechamiento/interno")
SRC = Path(__file__).resolve().parents[2] / "src" / "parcel_intel"


def _report(
    piece_: object, parcels: list[Parcel], fail: bool = False, sink: WidthSink | None = None
) -> MunicipalWidthReport:
    def failing(_bbox: BBox) -> Exception | None:
        return CadastralServiceError("tesela sin datos") if fail else None

    use_case = DetectWidthNarrowingUseCase(
        Layers(layer_of(piece_)),  # type: ignore[arg-type]
        lambda _code: ParcelsPort(parcels, fail=failing),
        ShapelyPolygonClipper(),
        sink or WidthSink(),
        TILE_SIDE_M,
    )
    return use_case.execute("28043")


def test_ca1_indicio_con_ratio_anchuras_confianza_y_evidencia() -> None:
    """CA1. Dada una pieza de vía pecuaria con anchura oficial W (`area_m2 / length_m` del
    tramo completo) cuyas parcelas VT de Catastro, recortadas a la franja, dan una anchura
    catastral media A con A / W menor que el umbral de estrechez, cuando se evalúa, entonces
    hay indicio con `ratio = A / W`, A y W en metros, la confianza y la evidencia (tipo de
    vía, W, A, recuento de parcelas VT usadas, sin referencias)."""
    parcels = [
        parcel(INFRASTRUCTURE_VT, rect(0, 0, 1000, 3)),
        parcel("28043A99109005", rect(0, 3, 1000, 4)),
    ]
    [result] = _report(piece(), parcels).pieces
    assessment = result.assessment
    assert assessment.outcome == "indicio"
    assert assessment.ratio is not None and abs(assessment.ratio - 0.4) < 1e-6
    assert assessment.confidence is not None and 0 < assessment.confidence <= 1
    evidence = assessment.evidence
    assert evidence is not None
    assert evidence.trail_type == "Vereda"
    assert abs(evidence.official_width_m - 10.0) < 1e-6
    assert abs(evidence.cadastral_width_m - 4.0) < 1e-6
    assert evidence.road_parcel_count == 2
    assert INFRASTRUCTURE_VT not in repr(result)


def test_ca2_sin_indicio_con_anchura_catastral_cercana_a_la_oficial() -> None:
    """CA2. Dada una pieza con A / W igual o superior al umbral (p. ej. A cercana a W o
    mayor), cuando se evalúa, entonces no hay indicio."""
    for width in (5.0, 9.5, 10.0, 25.0):
        [result] = _report(piece(), [parcel(INFRASTRUCTURE_VT, rect(0, -5, 1000, width))]).pieces
        assert result.assessment.outcome == "sin_indicio", width
        assert result.assessment.evidence is None


def test_ca3_sin_parcela_de_camino_en_la_franja() -> None:
    """CA3. Dada una pieza sin ninguna parcela VT dentro de la franja, cuando se evalúa,
    entonces no hay indicio de estrechez y el resultado es `sin_parcela_camino` (el caso lo
    cubre la discrepancia de #32, no se duplica)."""
    far = parcel(INFRASTRUCTURE_VT, rect(0, 500, 1000, 510))
    [result] = _report(piece(), [far]).pieces
    assert result.assessment.outcome == "sin_parcela_camino"
    assert result.assessment.ratio is None and result.assessment.evidence is None


def test_ca4_sin_datos_con_motivo_nunca_indicio() -> None:
    """CA4. Dado un tramo sin anchura oficial derivable (`length_m` o `area_m2` nulos, cero o
    no finitos), o una tesela de Catastro no disponible (`TILE_UNAVAILABLE`), cuando se
    evalúa, entonces `sin_datos` con motivo, y nunca indicio."""
    narrow = [parcel(INFRASTRUCTURE_VT, rect(0, 0, 1000, 1))]
    cases = [
        _report(piece(source_length_m=None), narrow),
        _report(piece(source_area_m2=None), narrow),
        _report(piece(source_area_m2=float("nan")), narrow),
        _report(piece(), narrow, fail=True),
    ]
    for report in cases:
        [result] = report.pieces
        assert result.assessment.outcome == "sin_datos"
        assert result.assessment.reason


def _use_case(
    out: Path, layers: object, parcels: object = None
) -> DetectWidthNarrowingUseCase:
    port = parcels or ParcelsPort([parcel(INFRASTRUCTURE_VT, rect(0, 0, 1000, 4))])
    return DetectWidthNarrowingUseCase(
        layers,  # type: ignore[arg-type]
        lambda _code: port,  # type: ignore[arg-type,return-value]
        ShapelyPolygonClipper(),
        GeoJsonWidthSignalWriter(out),
        TILE_SIDE_M,
    )


class _PerCode:
    def __init__(self, failing: set[str], empty: set[str]) -> None:
        self._failing, self._empty = failing, empty

    def get_layer(self, municipality_code: str) -> MunicipalLivestockTrailLayer:
        if municipality_code in self._failing:
            raise RuntimeError("fallo sintético")
        if municipality_code in self._empty:
            return layer_of()
        return layer_of(piece("A"), piece("B", source_length_m=None))


def _patch(monkeypatch: pytest.MonkeyPatch, use_case: DetectWidthNarrowingUseCase) -> None:
    monkeypatch.setattr(main, "build_width_narrowing_use_case", lambda *a, **k: use_case)


def _run(*argv: str) -> int:
    parser = main._build_parser()
    return int(
        main._estrechamiento_via_pecuaria(parser.parse_args(["estrechamiento-via-pecuaria", *argv]))
    )


def test_ca5_fichero_interno_por_municipio_y_el_lote_sigue_tras_un_fallo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA5. Dado un municipio con piezas de vía pecuaria, cuando se ejecuta el comando,
    entonces escribe `data/derived/estrechamiento/interno/<ine>.geojson` (EPSG:25830) con una
    feature por pieza evaluada (indicio, sin indicio, `sin_parcela_camino` o `sin_datos`), con
    procedencia (fuente, URL, fecha, licencia) y versión del método. Un municipio sin vías
    pecuarias sale «sin vías» y no es fallo; uno que falla no frena el lote y el comando sale
    con 1."""
    layers = _PerCode(failing={"28013"}, empty={"28002"})
    _patch(monkeypatch, _use_case(tmp_path / "salida", layers))
    code = _run("--municipio", "28043", "--municipio", "28013", "--municipio", "28002")
    assert code == 1
    out = capsys.readouterr()
    assert "FALLO 28013" in out.err
    assert "28002: sin vías" in out.out
    assert sorted(p.name for p in (tmp_path / "salida").iterdir()) == ["28043.geojson"]
    data = json.loads((tmp_path / "salida" / "28043.geojson").read_text(encoding="utf-8"))
    assert data["crs"]["properties"]["name"].endswith("25830")
    assert [f["properties"]["resultado"] for f in data["features"]] == ["indicio", "sin_datos"]
    assert data["properties"]["metodo"] == "estrechamiento_via_pecuaria@1"
    for key in ("procedencia_vias", "procedencia_catastro"):
        [entry] = data["properties"][key]
        assert {"fuente", "url", "fecha_descarga", "licencia"} <= set(entry)
    # sin fallo: exit 0
    assert _run("--municipio", "28043", "--municipio", "28002") == 0


def test_ca6_sin_titularidad_ni_referencias_y_nada_fuera_de_la_salida(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CA6. Dado cualquier fichero producido, cuando se inspecciona, entonces no contiene
    campos de titularidad ni referencias catastrales, y el comando no escribe nada fuera de
    `data/derived/estrechamiento/interno/` (nada va a `site/`)."""
    monkeypatch.chdir(tmp_path)
    _patch(monkeypatch, _use_case(DEFAULT_OUT, Layers(layer_of(piece()))))
    assert _run("--municipio", "28043") == 0
    written = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file())
    assert written == [Path("data/derived/estrechamiento/interno/28043.geojson")]
    text = written[0].read_text(encoding="utf-8")
    assert not re.search(r"\d{5}[A-Z]\d{3}\d{5}", text)  # referencia rústica
    assert INFRASTRUCTURE_VT not in text
    lowered = text.lower()
    for word in ("titular", "propietari", "owner", "referencia"):
        assert word not in lowered
    parse_width_file(text)  # extra="forbid": una propiedad ajena lo invalida
    assert not (tmp_path / "site").exists()


def test_ca7_sin_red_una_tesela_que_falta_deja_sin_datos_y_sin_municipio_sale_con_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA7. Dado `--sin-red`, cuando falta una tesela en la caché, entonces las piezas
    afectadas quedan `sin_datos` con su motivo (como en #128). Sin `--municipio` ni
    `--ambito` el comando sale con 1."""

    class MissingFromCache:
        def get_parcels_in_bbox(self, bbox: BBox) -> list[Parcel]:
            raise RawCacheMissError("no cacheada")

    use_case = DetectWidthNarrowingUseCase(
        Layers(layer_of(piece())),
        lambda _code: main._CachedParcels(MissingFromCache()),  # type: ignore[arg-type]
        ShapelyPolygonClipper(),
        WidthSink(),
        TILE_SIDE_M,
    )
    [result] = use_case.execute("28043").pieces
    assert result.assessment.outcome == "sin_datos"
    assert result.assessment.reason and "sin red" in result.assessment.reason
    assert _run() == 1
    assert "--municipio" in capsys.readouterr().err
    args = main._build_parser().parse_args(["estrechamiento-via-pecuaria", "--sin-red"])
    assert args.sin_red is True


@pytest.mark.integration
@pytest.mark.fuera_de_ci  # depende de data/ local (cachés de IGN, IDEM y Catastro)
def test_ca8_colmenar_real_valida_el_esquema_y_el_resumen_cuenta_cada_resultado(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA8. [integración] Dado Colmenar de Oreja (28043) con la caché real de Catastro, cuando
    se ejecuta, entonces el fichero valida el esquema y el resumen cuenta cada resultado. Sin
    umbrales ajustados a casos concretos."""
    if not (Path("data/raw/catastro")).is_dir():
        pytest.skip("falta la caché de Catastro en data/raw (ejecuta `catastro-caminos`)")
    code = _run("--municipio", "28043", "--sin-red", "--salida", str(tmp_path))
    assert code == 0
    report = parse_width_file((tmp_path / "28043.geojson").read_text(encoding="utf-8"))
    counted = sum(int(n) for n in re.findall(r"=(\d+)", capsys.readouterr().out.split("(")[1]))
    assert counted == len(report.features)


def test_escritor_es_determinista(tmp_path: Path) -> None:
    sink = WidthSink()
    report = _report(piece(), [parcel(INFRASTRUCTURE_VT, rect(0, 0, 1000, 4))], sink=sink)
    assert report_to_geojson_text(report) == report_to_geojson_text(report)
    assert sink.written == [report]
