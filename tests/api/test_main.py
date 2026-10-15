from collections.abc import Iterator
from datetime import date
from types import TracebackType

import psycopg
import pytest
from fastapi.testclient import TestClient

from parcel_intel.api import main
from parcel_intel.domain.building import Building
from parcel_intel.domain.bulletin import BulletinNotice
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.ndvi import NdviGrid
from parcel_intel.domain.orthophoto import HistoricalVintage, Orthophoto
from parcel_intel.domain.parcel import Parcel
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.report import ParcelReport
from parcel_intel.ports.errors import (
    InvalidCadastralReferenceError,
    ParcelNotCachedError,
    ParcelNotFoundError,
)
from tests.factories import make_building, make_parcel


def _provenance(source: str) -> Provenance:
    return Provenance(source=source, url="https://example.invalid", retrieved_at=date(2026, 10, 15))


class _FakeCatastroAdapter:
    """Doble del adapter real: sustituye `CatastroAdapter` en `api.main` para
    que los tests del endpoint no dependan de red ni de la implementación
    interna del adapter (ya cubierta por sus propios tests)."""

    behavior: str = "ok"
    parcel: Parcel = make_parcel()
    buildings: list[Building] = [make_building()]

    def __init__(self, provincia: str, municipio: str) -> None:
        self.provincia = provincia
        self.municipio = municipio

    def get_parcel(self, cadastral_reference: str) -> Parcel:
        if self.behavior == "invalid":
            raise InvalidCadastralReferenceError(cadastral_reference)
        if self.behavior == "not_found":
            raise ParcelNotFoundError(cadastral_reference)
        return self.parcel

    def get_buildings(self, cadastral_reference: str) -> list[Building]:
        return self.buildings


class _FakeRepository:
    """Doble de `PostgisParcelRepository`: siempre cache miss salvo que el
    test configure `cached_report`. No toca ninguna base de datos."""

    cached_report: ParcelReport | None = None
    saved_reports: list[ParcelReport] = []

    def __init__(self, connection: object) -> None:
        pass

    def get_report(self, cadastral_reference: str) -> ParcelReport:
        if _FakeRepository.cached_report is None:
            raise ParcelNotCachedError(cadastral_reference)
        return _FakeRepository.cached_report

    def save_report(self, report: ParcelReport) -> None:
        _FakeRepository.saved_reports.append(report)


class _FakeConnection:
    """Doble de la conexión psycopg: solo necesita comportarse como gestor
    de contexto, nunca se ejecuta SQL real contra ella en estos tests."""

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None


class _FakePnoaAdapter:
    """Doble de `PnoaAdapter`: evita red real en los tests del endpoint.
    Historia 0010 — las cuatro fuentes nuevas deben poder fallar sin
    tumbar el resto del informe, verificado a continuación una por una."""

    behavior: str = "ok"

    def __init__(self) -> None:
        pass

    def get_current_orthophoto(self, geometry: Geometry, margin_m: float) -> Orthophoto:
        if self.behavior == "fails":
            raise RuntimeError("PNOA no disponible (simulado)")
        return Orthophoto(image=b"fake-jpeg", vintage="actual", provenance=_provenance("pnoa"))

    def get_historical_orthophoto(
        self, geometry: Geometry, margin_m: float, vintage: HistoricalVintage
    ) -> Orthophoto:
        raise NotImplementedError


class _FakeSentinel2Adapter:
    """Doble de `Sentinel2Adapter`: evita red real en los tests del endpoint."""

    behavior: str = "ok"

    def __init__(self) -> None:
        pass

    def get_ndvi_series(
        self,
        geometry: Geometry,
        margin_m: float,
        start: date,
        end: date,
        max_cloud_cover_percent: float,
    ) -> list[NdviGrid]:
        if self.behavior == "fails":
            raise RuntimeError("Sentinel-2 no disponible (simulado)")
        return [
            NdviGrid(
                values=((0.3, 0.5),),
                bbox=(0.0, 0.0, 10.0, 10.0),
                srid=25830,
                scene_date=date(2026, 9, 1),
                cloud_cover_percent=10.0,
                provenance=_provenance("sentinel2"),
            )
        ]


class _FakeBoeAdapter:
    """Doble de `BoeAdapter`: evita red real en los tests del endpoint."""

    behavior: str = "ok"

    def __init__(self) -> None:
        pass

    def get_daily_bulletin(self, day: str) -> list[BulletinNotice]:
        if self.behavior == "fails":
            raise RuntimeError("BOE no disponible (simulado)")
        return []


class _FakeBocmAdapter:
    """Doble de `BocmAdapter`: evita red real en los tests del endpoint."""

    behavior: str = "ok"

    def __init__(self) -> None:
        pass

    def get_daily_bulletin(self, day: str) -> list[BulletinNotice]:
        if self.behavior == "fails":
            raise RuntimeError("BOCM no disponible (simulado)")
        return []


@pytest.fixture(autouse=True)
def _reset_fake_behavior() -> Iterator[None]:
    _FakeCatastroAdapter.behavior = "ok"
    _FakeCatastroAdapter.parcel = make_parcel()
    _FakeCatastroAdapter.buildings = [make_building()]
    _FakeRepository.cached_report = None
    _FakeRepository.saved_reports = []
    _FakePnoaAdapter.behavior = "ok"
    _FakeSentinel2Adapter.behavior = "ok"
    _FakeBoeAdapter.behavior = "ok"
    _FakeBocmAdapter.behavior = "ok"
    yield


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(main, "CatastroAdapter", _FakeCatastroAdapter)
    monkeypatch.setattr(main, "PostgisParcelRepository", _FakeRepository)
    monkeypatch.setattr(main, "get_connection", lambda: _FakeConnection())
    monkeypatch.setattr(main, "PnoaAdapter", _FakePnoaAdapter)
    monkeypatch.setattr(main, "Sentinel2Adapter", _FakeSentinel2Adapter)
    monkeypatch.setattr(main, "BoeAdapter", _FakeBoeAdapter)
    monkeypatch.setattr(main, "BocmAdapter", _FakeBocmAdapter)
    return TestClient(main.app)


def test_informe_de_parcela_existente_devuelve_html_200(client: TestClient) -> None:
    response = client.get("/reports/colmenar-de-oreja/REFCAT-RETIRADA")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "REFCAT-RETIRADA" in response.text


def test_municipio_no_soportado_devuelve_404(client: TestClient) -> None:
    response = client.get("/reports/madrid-capital/REFCAT-RETIRADA")

    assert response.status_code == 404
    assert "madrid-capital" in response.json()["detail"]


def test_referencia_mal_formada_devuelve_400(client: TestClient) -> None:
    _FakeCatastroAdapter.behavior = "invalid"

    response = client.get("/reports/colmenar-de-oreja/123")

    assert response.status_code == 400


def test_parcela_no_encontrada_devuelve_404(client: TestClient) -> None:
    _FakeCatastroAdapter.behavior = "not_found"

    response = client.get("/reports/villaconejos/28043A99999999")

    assert response.status_code == 404


def test_informe_servido_desde_cache_no_llama_a_catastro(client: TestClient) -> None:
    parcel = make_parcel(cadastral_reference="REFCAT-RETIRADA")
    _FakeRepository.cached_report = ParcelReport(parcel=parcel, buildings=())

    def _falla_si_se_llama(self: object, cadastral_reference: str) -> Parcel:
        raise AssertionError("no debería llamarse a Catastro con el informe ya cacheado")

    original_get_parcel = _FakeCatastroAdapter.get_parcel
    _FakeCatastroAdapter.get_parcel = _falla_si_se_llama  # type: ignore[method-assign]
    try:
        response = client.get("/reports/colmenar-de-oreja/REFCAT-RETIRADA")
    finally:
        _FakeCatastroAdapter.get_parcel = original_get_parcel  # type: ignore[method-assign]

    assert response.status_code == 200
    assert "REFCAT-RETIRADA" in response.text


def test_postgis_no_disponible_devuelve_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _conexion_rota() -> _FakeConnection:
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(main, "get_connection", _conexion_rota)

    response = client.get("/reports/colmenar-de-oreja/REFCAT-RETIRADA")

    assert response.status_code == 503


def test_informe_incluye_evidencia_de_las_cuatro_fuentes_nuevas(client: TestClient) -> None:
    response = client.get("/reports/colmenar-de-oreja/REFCAT-RETIRADA")

    assert response.status_code == 200
    assert "data:image/jpeg;base64," in response.text  # PNOA
    assert "NDVI medio" in response.text  # Sentinel-2
    assert "BOE" in response.text
    assert "BOCM" in response.text

    # Ninguna de las cuatro fuentes nuevas se persiste en PostGIS: lo único
    # que llega a save_report es el ParcelReport de Catastro ya existente
    # (historia 0005), nunca el EnrichedParcelReport que compone esta
    # historia -- verificado por tipo, no solo por ausencia de llamada.
    assert len(_FakeRepository.saved_reports) == 1
    assert isinstance(_FakeRepository.saved_reports[0], ParcelReport)


def test_fallo_de_pnoa_no_tumba_el_informe(client: TestClient) -> None:
    _FakePnoaAdapter.behavior = "fails"

    response = client.get("/reports/colmenar-de-oreja/REFCAT-RETIRADA")

    assert response.status_code == 200
    assert "Ortofoto actual (PNOA) no disponible." in response.text
    assert "REFCAT-RETIRADA" in response.text


def test_fallo_de_sentinel2_no_tumba_el_informe(client: TestClient) -> None:
    _FakeSentinel2Adapter.behavior = "fails"

    response = client.get("/reports/colmenar-de-oreja/REFCAT-RETIRADA")

    assert response.status_code == 200
    assert "Resumen NDVI (Sentinel-2) no disponible." in response.text
    assert "REFCAT-RETIRADA" in response.text


def test_fallo_de_boe_no_tumba_el_informe(client: TestClient) -> None:
    _FakeBoeAdapter.behavior = "fails"

    response = client.get("/reports/colmenar-de-oreja/REFCAT-RETIRADA")

    assert response.status_code == 200
    assert "BOE no disponible." in response.text
    assert "REFCAT-RETIRADA" in response.text


def test_fallo_de_bocm_no_tumba_el_informe(client: TestClient) -> None:
    _FakeBocmAdapter.behavior = "fails"

    response = client.get("/reports/colmenar-de-oreja/REFCAT-RETIRADA")

    assert response.status_code == 200
    assert "BOCM no disponible." in response.text
    assert "REFCAT-RETIRADA" in response.text
