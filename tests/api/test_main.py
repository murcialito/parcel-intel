from collections.abc import Iterator
from datetime import date
from types import TracebackType

import psycopg
import pytest
from fastapi.testclient import TestClient

from parcel_intel.api import main
from parcel_intel.domain.building import Building
from parcel_intel.domain.bulletin import BulletinNotice
from parcel_intel.domain.flood_hazard import FloodHazardSample
from parcel_intel.domain.geometry import Geometry, LineGeometry
from parcel_intel.domain.land_classification import LandClassification
from parcel_intel.domain.livestock_trail import LivestockTrail
from parcel_intel.domain.ndvi import NdviGrid
from parcel_intel.domain.norm import Norm, Provision
from parcel_intel.domain.orthophoto import HistoricalVintage, Orthophoto
from parcel_intel.domain.parcel import Parcel
from parcel_intel.domain.protected_area import ProtectedArea
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.report import ParcelReport
from parcel_intel.domain.rule import AttributeCondition, Rule, RuleScope, WithinDistanceCondition
from parcel_intel.domain.watercourse import Watercourse
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


class _FakeRuleRepository:
    """Doble de `PostgisRuleRepository`: sin reglas `approved` salvo que el
    test configure `approved_rules`, o lanza `raises` si se configura (para
    simular el fallo parcial de la historia 0020). No toca ninguna base de
    datos."""

    approved_rules: list[Rule] = []
    raises: Exception | None = None

    def __init__(self, connection: object) -> None:
        pass

    def list_approved(self) -> list[Rule]:
        if _FakeRuleRepository.raises is not None:
            raise _FakeRuleRepository.raises
        return list(_FakeRuleRepository.approved_rules)


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


class _FakeIdemAdapter:
    """Doble de `IdemAdapter`: evita red real en los tests del endpoint."""

    behavior: str = "ok"

    def __init__(self) -> None:
        pass

    def get_land_classifications(
        self, geometry: Geometry, margin_m: float
    ) -> list[LandClassification]:
        if self.behavior == "fails":
            raise RuntimeError("IDEM no disponible (simulado)")
        return [
            LandClassification(
                general_category="Suelo No Urbanizable Común",
                detailed_category="suelo no urbanizable común",
                short_code="SUBNS",
                reference_date=date(2025, 6, 29),
                municipality_code="043",
                municipality_name="COLMENAR DE OREJA",
                area_m2=1000.0,
                geometry=Geometry(rings=(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)),), srid=25830),
                provenance=_provenance("idem"),
            )
        ]


class _FakeHydrographyAdapter:
    """Doble de `HydrographyAdapter`: evita red real en los tests del endpoint."""

    behavior: str = "ok"

    def __init__(self) -> None:
        pass

    def get_nearby_watercourses(self, geometry: Geometry, margin_m: float) -> list[Watercourse]:
        if self.behavior == "fails":
            raise RuntimeError("Hidrografía no disponible (simulado)")
        return [
            Watercourse(
                name="Barranco del Montero",
                hydrographic_demarcation_code="ES030",
                hydrographic_demarcation_name="Tajo",
                course_type="Curso natural",
                persistence="Estacional",
                min_width_m=1.0,
                max_width_m=5.0,
                length_m=2058.58,
                geometry=LineGeometry(points=((0.0, 0.0), (1.0, 1.0)), srid=25830),
                provenance=_provenance("idee-watercourse"),
            )
        ]


class _FakeFloodHazardAdapter:
    """Doble de `FloodHazardAdapter`: evita red real en los tests del endpoint."""

    behavior: str = "ok"

    def __init__(self) -> None:
        pass

    def get_flood_hazard(self, geometry: Geometry, margin_m: float) -> list[FloodHazardSample]:
        if self.behavior == "fails":
            raise RuntimeError("Peligrosidad por inundación no disponible (simulado)")
        return [
            FloodHazardSample(
                kind=kind,  # type: ignore[arg-type]
                return_period_years=period,
                water_depth_m=None,
                provenance=_provenance("idee-flood-hazard"),
            )
            for kind, period in (
                ("fluvial", 10),
                ("fluvial", 100),
                ("fluvial", 500),
                ("marina", 100),
                ("marina", 500),
            )
        ]


class _FakeLivestockTrailAdapter:
    """Doble de `LivestockTrailAdapter`: evita red real en los tests del endpoint."""

    behavior: str = "ok"

    def __init__(self) -> None:
        pass

    def get_nearby_livestock_trails(
        self, geometry: Geometry, margin_m: float
    ) -> list[LivestockTrail]:
        if self.behavior == "fails":
            raise RuntimeError("Vías pecuarias no disponible (simulado)")
        return [
            LivestockTrail(
                trail_type="Vereda",
                name="Vereda del Cristo",
                municipality_code="043",
                municipality_name="COLMENAR DE OREJA",
                trail_code="2804301",
                length_m=10492.0,
                area_m2=122148.0,
                geometry=Geometry(rings=(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)),), srid=25830),
                provenance=_provenance("idem"),
            )
        ]


class _FakeProtectedAreaAdapter:
    """Doble de `ProtectedAreaAdapter`: evita red real en los tests del endpoint."""

    behavior: str = "ok"

    def __init__(self) -> None:
        pass

    def get_nearby_protected_areas(
        self, geometry: Geometry, margin_m: float
    ) -> list[ProtectedArea]:
        if self.behavior == "fails":
            raise RuntimeError("Red Natura 2000 no disponible (simulado)")
        return [
            ProtectedArea(
                plan_code="SE",
                plan_name="Plan de gestión de vegas, cuestas y páramos del sureste de Madrid",
                zone_code="X",
                zone_name="Espacio previamente ordenado",
                geometry=Geometry(rings=(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)),), srid=25830),
                provenance=_provenance("idem"),
            )
        ]


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
    _FakeIdemAdapter.behavior = "ok"
    _FakeHydrographyAdapter.behavior = "ok"
    _FakeFloodHazardAdapter.behavior = "ok"
    _FakeLivestockTrailAdapter.behavior = "ok"
    _FakeProtectedAreaAdapter.behavior = "ok"
    _FakeRuleRepository.approved_rules = []
    _FakeRuleRepository.raises = None
    yield


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(main, "CatastroAdapter", _FakeCatastroAdapter)
    monkeypatch.setattr(main, "PostgisParcelRepository", _FakeRepository)
    monkeypatch.setattr(main, "PostgisRuleRepository", _FakeRuleRepository)
    monkeypatch.setattr(main, "get_connection", lambda: _FakeConnection())
    monkeypatch.setattr(main, "PnoaAdapter", _FakePnoaAdapter)
    monkeypatch.setattr(main, "Sentinel2Adapter", _FakeSentinel2Adapter)
    monkeypatch.setattr(main, "BoeAdapter", _FakeBoeAdapter)
    monkeypatch.setattr(main, "BocmAdapter", _FakeBocmAdapter)
    monkeypatch.setattr(main, "IdemAdapter", _FakeIdemAdapter)
    monkeypatch.setattr(main, "HydrographyAdapter", _FakeHydrographyAdapter)
    monkeypatch.setattr(main, "FloodHazardAdapter", _FakeFloodHazardAdapter)
    monkeypatch.setattr(main, "LivestockTrailAdapter", _FakeLivestockTrailAdapter)
    monkeypatch.setattr(main, "ProtectedAreaAdapter", _FakeProtectedAreaAdapter)
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


def test_informe_incluye_evidencia_de_las_nueve_fuentes_nuevas(client: TestClient) -> None:
    response = client.get("/reports/colmenar-de-oreja/REFCAT-RETIRADA")

    assert response.status_code == 200
    assert "data:image/jpeg;base64," in response.text  # PNOA
    assert "NDVI medio" in response.text  # Sentinel-2
    assert "BOE" in response.text
    assert "BOCM" in response.text
    assert "Suelo No Urbanizable Común" in response.text  # IDEM
    assert "Barranco del Montero" in response.text  # hidrografía
    assert "NO DATA" in response.text  # peligrosidad por inundación
    assert "Vereda del Cristo" in response.text  # vías pecuarias
    assert "Plan de gestión de vegas" in response.text  # Red Natura 2000

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


def test_fallo_de_idem_no_tumba_el_informe(client: TestClient) -> None:
    _FakeIdemAdapter.behavior = "fails"

    response = client.get("/reports/colmenar-de-oreja/REFCAT-RETIRADA")

    assert response.status_code == 200
    assert "Clasificación de suelo (IDEM) no disponible." in response.text
    assert "REFCAT-RETIRADA" in response.text


def test_fallo_de_hidrografia_no_tumba_el_informe(client: TestClient) -> None:
    _FakeHydrographyAdapter.behavior = "fails"

    response = client.get("/reports/colmenar-de-oreja/REFCAT-RETIRADA")

    assert response.status_code == 200
    assert "Cursos de agua (hidrografía) no disponible." in response.text
    assert "REFCAT-RETIRADA" in response.text


def test_fallo_de_peligrosidad_inundacion_no_tumba_el_informe(client: TestClient) -> None:
    _FakeFloodHazardAdapter.behavior = "fails"

    response = client.get("/reports/colmenar-de-oreja/REFCAT-RETIRADA")

    assert response.status_code == 200
    assert "Peligrosidad por inundación no disponible." in response.text
    assert "REFCAT-RETIRADA" in response.text


def test_fallo_de_vias_pecuarias_no_tumba_el_informe(client: TestClient) -> None:
    _FakeLivestockTrailAdapter.behavior = "fails"

    response = client.get("/reports/colmenar-de-oreja/REFCAT-RETIRADA")

    assert response.status_code == 200
    assert "Vías pecuarias (IDEM) no disponible." in response.text
    assert "REFCAT-RETIRADA" in response.text


def test_fallo_de_red_natura_no_tumba_el_informe(client: TestClient) -> None:
    _FakeProtectedAreaAdapter.behavior = "fails"

    response = client.get("/reports/colmenar-de-oreja/REFCAT-RETIRADA")

    assert response.status_code == 200
    assert "Espacios protegidos Red Natura 2000 (IDEM) no disponible." in response.text
    assert "REFCAT-RETIRADA" in response.text


# --- Historia 0020: reglas aprobadas desde la tabla `rule` ---

_CAUCE_CITATION = Provision(
    norm=Norm(title="Norma de prueba", url="https://example.org/norma"),
    article="art. 1",
    in_force_since=date(2020, 1, 1),
)


def _regla_equivalente_a_la_hardcoded_de_cauces(identifier: str) -> Rule:
    # Mismos spatial/scope/attributes/outcome que
    # "madrid-colmenar-distancia-cauce" (api/main.py) -- caso real de
    # duplicación ya verificado con una propuesta real de DeepSeek
    # (ADR 0020). Solo cambian identifier/authority/citation, igual que
    # el caso real.
    return Rule(
        identifier=identifier,
        scope=RuleScope(region="madrid", soil_classes=("no_urbanizable",)),
        spatial=WithinDistanceCondition(
            operation="within_distance", layer="dph_cauce", meters=100.0
        ),
        attributes=AttributeCondition(building_origin=("catastro", "detected")),
        outcome="requires_authorization",
        authority="organismo de cuenca",
        citation=_CAUCE_CITATION,
        status="approved",
    )


def test_regla_aprobada_duplicada_de_la_tabla_no_produce_dos_hallazgos(
    client: TestClient,
) -> None:
    # El informe por defecto (Barranco del Montero a distancia 0 del
    # cuadrado por defecto, suelo "Suelo No Urbanizable Común") ya
    # produce 1 Finding real con la regla hardcoded de cauces -- añadir
    # una regla aprobada por el flujo de autoría con la misma condición
    # real no debe duplicarlo. Desactiva vías pecuarias/Red Natura (que
    # por defecto también solapan y añaden su propio
    # "requires_authorization") para que el recuento del hallazgo de
    # cauces no se confunda con el de otra regla hardcoded distinta.
    _FakeLivestockTrailAdapter.behavior = "fails"
    _FakeProtectedAreaAdapter.behavior = "fails"
    _FakeRuleRepository.approved_rules = [
        _regla_equivalente_a_la_hardcoded_de_cauces("madrid-proposed-dph_cauce-test1234")
    ]

    response = client.get("/reports/colmenar-de-oreja/REFCAT-RETIRADA")

    assert response.status_code == 200
    assert response.text.count("Distancia a curso de agua") == 1
    assert response.text.count("requires_authorization") == 1
    # La regla a mano gana el desempate (ADR 0020, decisión 4): se ve su
    # autoridad real, no la genérica de la propuesta LLM equivalente.
    assert "Confederación Hidrográfica del Tajo" in response.text
    assert "organismo de cuenca" not in response.text


def test_regla_aprobada_distinta_no_se_deduplica(client: TestClient) -> None:
    distinta = Rule(
        identifier="madrid-proposed-dph_cauce-test5678",
        scope=RuleScope(region="madrid", soil_classes=("no_urbanizable",)),
        spatial=WithinDistanceCondition(
            operation="within_distance", layer="dph_cauce", meters=100.0
        ),
        attributes=AttributeCondition(building_origin=("catastro", "detected")),
        outcome="requires_environmental_assessment",  # outcome distinto -> no es "la misma cosa"
        authority="Otra autoridad",
        citation=_CAUCE_CITATION,
        status="approved",
    )
    _FakeRuleRepository.approved_rules = [distinta]

    response = client.get("/reports/colmenar-de-oreja/REFCAT-RETIRADA")

    assert response.status_code == 200
    assert "requires_authorization" in response.text
    assert "requires_environmental_assessment" in response.text


def test_sin_reglas_aprobadas_en_bd_no_hay_aviso_ni_diferencia(client: TestClient) -> None:
    _FakeRuleRepository.approved_rules = []

    response = client.get("/reports/colmenar-de-oreja/REFCAT-RETIRADA")

    assert response.status_code == 200
    assert "Catálogo de reglas de autoría no disponible" not in response.text


def test_fallo_al_leer_tabla_rule_muestra_aviso_visible_y_no_tumba_el_informe(
    client: TestClient,
) -> None:
    _FakeRuleRepository.raises = psycopg.errors.UndefinedTable("relation rule does not exist")

    response = client.get("/reports/colmenar-de-oreja/REFCAT-RETIRADA")

    assert response.status_code == 200
    assert "Catálogo de reglas de autoría no disponible" in response.text
    # Las reglas a mano se siguen evaluando igual pese al fallo parcial.
    assert "requires_authorization" in response.text
