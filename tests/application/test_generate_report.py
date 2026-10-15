from parcel_intel.application.generate_report import GenerateParcelReportUseCase
from parcel_intel.domain.building import Building
from parcel_intel.domain.parcel import Parcel
from tests.factories import make_building, make_parcel


class FakeParcelPort:
    def __init__(self, parcel: Parcel) -> None:
        self._parcel = parcel
        self.requested_references: list[str] = []

    def get_parcel(self, cadastral_reference: str) -> Parcel:
        self.requested_references.append(cadastral_reference)
        return self._parcel


class FakeBuildingPort:
    def __init__(self, buildings: list[Building]) -> None:
        self._buildings = buildings
        self.requested_references: list[str] = []

    def get_buildings(self, cadastral_reference: str) -> list[Building]:
        self.requested_references.append(cadastral_reference)
        return self._buildings


def test_execute_compone_parcela_y_edificios() -> None:
    parcel = make_parcel()
    building = make_building()
    use_case = GenerateParcelReportUseCase(
        parcel_port=FakeParcelPort(parcel),
        building_port=FakeBuildingPort([building]),
    )

    report = use_case.execute("REFCAT-RETIRADA")

    assert report.parcel == parcel
    assert report.buildings == (building,)


def test_execute_sin_edificios_devuelve_tupla_vacia() -> None:
    parcel = make_parcel()
    use_case = GenerateParcelReportUseCase(
        parcel_port=FakeParcelPort(parcel),
        building_port=FakeBuildingPort([]),
    )

    report = use_case.execute("REFCAT-RETIRADA")

    assert report.buildings == ()


def test_execute_pasa_la_misma_referencia_a_ambos_ports() -> None:
    parcel_port = FakeParcelPort(make_parcel())
    building_port = FakeBuildingPort([])
    use_case = GenerateParcelReportUseCase(parcel_port=parcel_port, building_port=building_port)

    use_case.execute("REFCAT-RETIRADA")

    assert parcel_port.requested_references == ["REFCAT-RETIRADA"]
    assert building_port.requested_references == ["REFCAT-RETIRADA"]
