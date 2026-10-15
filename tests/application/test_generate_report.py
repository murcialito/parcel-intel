import pytest

from parcel_intel.application.generate_report import GenerateParcelReportUseCase
from parcel_intel.domain.building import Building
from parcel_intel.domain.parcel import Parcel
from parcel_intel.domain.report import ParcelReport
from parcel_intel.ports.errors import ParcelNotCachedError, ParcelNotFoundError
from tests.factories import make_building, make_parcel


class FakeParcelPort:
    def __init__(self, parcel: Parcel | None = None, raises: Exception | None = None) -> None:
        self._parcel = parcel
        self._raises = raises
        self.requested_references: list[str] = []

    def get_parcel(self, cadastral_reference: str) -> Parcel:
        self.requested_references.append(cadastral_reference)
        if self._raises is not None:
            raise self._raises
        assert self._parcel is not None
        return self._parcel


class FakeBuildingPort:
    def __init__(self, buildings: list[Building]) -> None:
        self._buildings = buildings
        self.requested_references: list[str] = []

    def get_buildings(self, cadastral_reference: str) -> list[Building]:
        self.requested_references.append(cadastral_reference)
        return self._buildings


class FakeRepository:
    """Doble en memoria de `ParcelRepositoryPort`: simula caché vacía o ya
    poblada según cómo se construya en cada test."""

    def __init__(self, cached_report: ParcelReport | None = None) -> None:
        self._cached_report = cached_report
        self.get_calls: list[str] = []
        self.saved_reports: list[ParcelReport] = []

    def get_report(self, cadastral_reference: str) -> ParcelReport:
        self.get_calls.append(cadastral_reference)
        if self._cached_report is None:
            raise ParcelNotCachedError(cadastral_reference)
        return self._cached_report

    def save_report(self, report: ParcelReport) -> None:
        self.saved_reports.append(report)
        self._cached_report = report


def test_cache_miss_consulta_los_ports_y_guarda_el_resultado() -> None:
    parcel = make_parcel()
    building = make_building()
    parcel_port = FakeParcelPort(parcel)
    building_port = FakeBuildingPort([building])
    repository = FakeRepository(cached_report=None)
    use_case = GenerateParcelReportUseCase(
        parcel_port=parcel_port, building_port=building_port, repository=repository
    )

    report = use_case.execute("REFCAT-RETIRADA")

    assert report.parcel == parcel
    assert report.buildings == (building,)
    assert parcel_port.requested_references == ["REFCAT-RETIRADA"]
    assert building_port.requested_references == ["REFCAT-RETIRADA"]
    assert repository.saved_reports == [report]


def test_cache_hit_no_consulta_los_ports() -> None:
    parcel = make_parcel()
    cached_report = ParcelReport(parcel=parcel, buildings=(make_building(),))
    parcel_port = FakeParcelPort(parcel)
    building_port = FakeBuildingPort([])
    repository = FakeRepository(cached_report=cached_report)
    use_case = GenerateParcelReportUseCase(
        parcel_port=parcel_port, building_port=building_port, repository=repository
    )

    report = use_case.execute("REFCAT-RETIRADA")

    assert report == cached_report
    assert parcel_port.requested_references == []
    assert building_port.requested_references == []
    assert repository.saved_reports == []


def test_sin_edificios_devuelve_tupla_vacia_y_se_cachea_igual() -> None:
    parcel = make_parcel()
    use_case = GenerateParcelReportUseCase(
        parcel_port=FakeParcelPort(parcel),
        building_port=FakeBuildingPort([]),
        repository=FakeRepository(cached_report=None),
    )

    report = use_case.execute("REFCAT-RETIRADA")

    assert report.buildings == ()


def test_parcela_no_encontrada_no_se_cachea_y_reintenta_catastro_la_proxima_vez() -> None:
    parcel_port = FakeParcelPort(raises=ParcelNotFoundError("28043A99999999"))
    building_port = FakeBuildingPort([])
    repository = FakeRepository(cached_report=None)
    use_case = GenerateParcelReportUseCase(
        parcel_port=parcel_port, building_port=building_port, repository=repository
    )

    with pytest.raises(ParcelNotFoundError):
        use_case.execute("28043A99999999")

    assert repository.saved_reports == []
    assert repository.get_calls == ["28043A99999999"]

    # Segunda petición: como no se cacheó nada, vuelve a consultar el
    # repositorio (cache miss otra vez) y vuelve a intentar Catastro, no se
    # queda "atascada" en un negativo guardado.
    with pytest.raises(ParcelNotFoundError):
        use_case.execute("28043A99999999")

    assert repository.get_calls == ["28043A99999999", "28043A99999999"]
    assert parcel_port.requested_references == ["28043A99999999", "28043A99999999"]
