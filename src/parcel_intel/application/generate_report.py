from parcel_intel.domain.report import ParcelReport
from parcel_intel.ports.errors import ParcelNotCachedError
from parcel_intel.ports.geometry import BuildingGeometryPort, ParcelGeometryPort
from parcel_intel.ports.repository import ParcelRepositoryPort


class GenerateParcelReportUseCase:
    """Caso de uso: componer el informe de una parcela, cacheando en
    `repository` lo que ya se consultó a Catastro (ADR 0005). No decide nada
    sobre normativa ni hallazgos todavía — eso llega con el motor de reglas
    (historia 0007); hoy solo compone y cachea lo que ya se puede obtener:
    geometría y atributos de parcela y edificios."""

    def __init__(
        self,
        parcel_port: ParcelGeometryPort,
        building_port: BuildingGeometryPort,
        repository: ParcelRepositoryPort,
    ) -> None:
        self._parcel_port = parcel_port
        self._building_port = building_port
        self._repository = repository

    def execute(self, cadastral_reference: str) -> ParcelReport:
        try:
            return self._repository.get_report(cadastral_reference)
        except ParcelNotCachedError:
            pass

        parcel = self._parcel_port.get_parcel(cadastral_reference)
        buildings = tuple(self._building_port.get_buildings(cadastral_reference))
        report = ParcelReport(parcel=parcel, buildings=buildings)
        self._repository.save_report(report)
        return report
