from parcel_intel.domain.report import ParcelReport
from parcel_intel.ports.geometry import BuildingGeometryPort, ParcelGeometryPort


class GenerateParcelReportUseCase:
    """Caso de uso: componer el informe de una parcela a partir de sus datos
    de Catastro. No decide nada sobre normativa ni hallazgos todavía — eso
    llega con el motor de reglas (historia 0007); hoy solo compone lo que
    ya se puede obtener: geometría y atributos de parcela y edificios."""

    def __init__(
        self,
        parcel_port: ParcelGeometryPort,
        building_port: BuildingGeometryPort,
    ) -> None:
        self._parcel_port = parcel_port
        self._building_port = building_port

    def execute(self, cadastral_reference: str) -> ParcelReport:
        parcel = self._parcel_port.get_parcel(cadastral_reference)
        buildings = tuple(self._building_port.get_buildings(cadastral_reference))
        return ParcelReport(parcel=parcel, buildings=buildings)
