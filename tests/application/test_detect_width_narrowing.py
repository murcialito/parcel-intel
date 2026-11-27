from parcel_intel.adapters.shapely_geometry import ShapelyPolygonClipper
from parcel_intel.application.detect_width_narrowing import DetectWidthNarrowingUseCase
from parcel_intel.domain.geometry import BBox
from parcel_intel.ports.errors import CadastralServiceError, ClippedGeometryHasHolesError
from tests.cut_signal_support import INFRASTRUCTURE_VT, ORDINARY, ParcelsPort, parcel, rect
from tests.width_signal_support import TILE_SIDE_M, Layers, WidthSink, layer_of, piece


def _use_case(
    layer_pieces: list,  # type: ignore[type-arg]
    port: ParcelsPort,
    sink: WidthSink,
    clipper: object | None = None,
) -> DetectWidthNarrowingUseCase:
    return DetectWidthNarrowingUseCase(
        layers=Layers(layer_of(*layer_pieces)),
        parcels_for=lambda _code: port,
        clipper=clipper or ShapelyPolygonClipper(),  # type: ignore[arg-type]
        sink=sink,
        tile_side_m=TILE_SIDE_M,
    )


def test_indicio_con_parcela_vt_estrecha() -> None:
    sink = WidthSink()
    port = ParcelsPort([parcel(INFRASTRUCTURE_VT, rect(0, 0, 1000, 4))])
    report = _use_case([piece()], port, sink).execute("28043")
    [result] = report.pieces
    assert result.assessment.outcome == "indicio"
    assert result.assessment.ratio is not None and abs(result.assessment.ratio - 0.4) < 1e-6
    assert sink.written == [report]
    assert report.cadastral_provenance and report.trail_provenance


def test_las_parcelas_ordinarias_no_cuentan_como_camino() -> None:
    port = ParcelsPort([parcel(ORDINARY, rect(0, 0, 1000, 10))])
    [result] = _use_case([piece()], port, WidthSink()).execute("28043").pieces
    assert result.assessment.outcome == "sin_parcela_camino"


def test_sin_indicio_con_parcela_ancha() -> None:
    port = ParcelsPort([parcel(INFRASTRUCTURE_VT, rect(-5, -5, 1005, 15))])
    [result] = _use_case([piece()], port, WidthSink()).execute("28043").pieces
    assert result.assessment.outcome == "sin_indicio"
    assert result.assessment.ratio is not None and result.assessment.ratio >= 0.99


def test_una_parcela_en_varias_teselas_se_cuenta_una_vez() -> None:
    port = ParcelsPort([parcel(INFRASTRUCTURE_VT, rect(0, 0, 1000, 4))])
    use_case = DetectWidthNarrowingUseCase(
        Layers(layer_of(piece())), lambda _c: port, ShapelyPolygonClipper(), WidthSink(), 400.0
    )
    [result] = use_case.execute("28043").pieces
    assert len(port.requests) > 1
    assert result.assessment.ratio is not None and abs(result.assessment.ratio - 0.4) < 1e-6


def test_tesela_no_disponible_deja_sin_datos_con_motivo() -> None:
    def fail(_bbox: BBox) -> Exception:
        return CadastralServiceError("tesela no cacheada y sin red")

    port = ParcelsPort([parcel(INFRASTRUCTURE_VT, rect(0, 0, 1000, 4))], fail=fail)
    [result] = _use_case([piece()], port, WidthSink()).execute("28043").pieces
    assert result.assessment.outcome == "sin_datos"
    assert result.assessment.reason and "sin red" in result.assessment.reason


def test_anchura_oficial_no_derivable_no_pide_teselas() -> None:
    port = ParcelsPort([])
    [result] = _use_case([piece(source_length_m=None)], port, WidthSink()).execute("28043").pieces
    assert result.assessment.outcome == "sin_datos"
    assert port.requests == []


def test_recorte_con_huecos_es_sin_datos() -> None:
    class Holes:
        def clip(self, subject: object, boundary: object) -> object:
            raise ClippedGeometryHasHolesError(1)

    port = ParcelsPort([parcel(INFRASTRUCTURE_VT, rect(0, 0, 1000, 4))])
    [result] = _use_case([piece()], port, WidthSink(), Holes()).execute("28043").pieces
    assert result.assessment.outcome == "sin_datos"


def test_los_anejos_no_se_evaluan_y_sin_vias_no_se_escribe() -> None:
    sink = WidthSink()
    report = _use_case([piece(trail_type="Abrevadero")], ParcelsPort([]), sink).execute("28043")
    assert report.pieces == ()
    assert sink.written == []


def test_ids_con_varias_piezas_de_la_misma_via() -> None:
    port = ParcelsPort([parcel(INFRASTRUCTURE_VT, rect(0, 0, 1000, 4))])
    report = _use_case([piece("A"), piece("A"), piece("B")], port, WidthSink()).execute("28043")
    assert [p.piece_id for p in report.pieces] == ["A-1", "A-2", "B"]
