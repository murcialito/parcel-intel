from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from parcel_intel.api import main
from parcel_intel.domain.building import Building
from parcel_intel.domain.parcel import Parcel
from parcel_intel.ports.errors import InvalidCadastralReferenceError, ParcelNotFoundError
from tests.factories import make_building, make_parcel


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


@pytest.fixture(autouse=True)
def _reset_fake_behavior() -> Iterator[None]:
    _FakeCatastroAdapter.behavior = "ok"
    _FakeCatastroAdapter.parcel = make_parcel()
    _FakeCatastroAdapter.buildings = [make_building()]
    yield


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(main, "CatastroAdapter", _FakeCatastroAdapter)
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
