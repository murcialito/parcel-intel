from collections.abc import Callable
from datetime import date

from parcel_intel.application.generate_report import GenerateParcelReportUseCase
from parcel_intel.domain.bulletin import BulletinNotice, filter_by_title
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.ndvi import NdviSummary, summarize_ndvi_grid
from parcel_intel.domain.orthophoto import Orthophoto
from parcel_intel.domain.report import EnrichedParcelReport
from parcel_intel.ports.bulletin import OfficialBulletinPort
from parcel_intel.ports.flood_hazard import FloodHazardPort
from parcel_intel.ports.land_classification import LandClassificationPort
from parcel_intel.ports.ndvi import NdviSeriesPort
from parcel_intel.ports.orthophoto import OrthophotoPort
from parcel_intel.ports.watercourse import WatercoursePort

# Mismos valores que los adapters concretos (`PnoaAdapter.DEFAULT_MARGIN_M`,
# `Sentinel2Adapter.DEFAULT_MARGIN_M`, `IdemAdapter.DEFAULT_MARGIN_M`,
# `HydrographyAdapter.DEFAULT_MARGIN_M`, `FloodHazardAdapter.DEFAULT_MARGIN_M`),
# duplicados deliberadamente: este módulo no puede importar esos adapters
# (regla de capas), así que no puede reutilizar sus constantes (ADR 0010,
# decisión 2; reafirmado en ADR 0013 para las tres fuentes nuevas).
ORTHOPHOTO_MARGIN_M = 10.0
NDVI_MARGIN_M = 20.0
NDVI_LOOKBACK_DAYS = 90
NDVI_MAX_CLOUD_COVER_PERCENT = 40.0
LAND_CLASSIFICATION_MARGIN_M = 2.0
WATERCOURSE_MARGIN_M = 2.0
FLOOD_HAZARD_MARGIN_M = 2.0


class GenerateEnrichedParcelReportUseCase:
    """Envuelve `GenerateParcelReportUseCase` (cacheado, sin cambios) con
    evidencia de siete fuentes nunca cacheadas (historia 0010 + historia
    0013, ADR 0010/0013): ortofoto actual (PNOA), resumen NDVI de un punto
    en el tiempo (Sentinel-2), disposiciones de BOE/BOCM del día de hoy que
    mencionan el municipio de la parcela, clasificación de suelo vigente
    (IDEM), cursos de agua cercanos y peligrosidad por inundación. Un
    fallo de cualquiera de las siete no impide generar el resto del
    informe — se captura con `except Exception` explícito porque
    `application/` no puede importar los adapters concretos donde viven
    las excepciones de red no envueltas."""

    def __init__(
        self,
        base_use_case: GenerateParcelReportUseCase,
        orthophoto_port: OrthophotoPort,
        ndvi_port: NdviSeriesPort,
        boe_port: OfficialBulletinPort,
        bocm_port: OfficialBulletinPort,
        land_classification_port: LandClassificationPort,
        watercourse_port: WatercoursePort,
        flood_hazard_port: FloodHazardPort,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._base_use_case = base_use_case
        self._orthophoto_port = orthophoto_port
        self._ndvi_port = ndvi_port
        self._boe_port = boe_port
        self._bocm_port = bocm_port
        self._land_classification_port = land_classification_port
        self._watercourse_port = watercourse_port
        self._flood_hazard_port = flood_hazard_port
        self._today = today

    def execute(self, cadastral_reference: str) -> EnrichedParcelReport:
        report = self._base_use_case.execute(cadastral_reference)
        geometry = report.parcel.geometry
        municipality = report.parcel.municipality
        today = self._today()

        orthophoto = self._safe(lambda: self._get_orthophoto(geometry))
        ndvi_summary = self._safe(lambda: self._get_ndvi_summary(geometry, today))
        day = today.strftime("%Y%m%d")
        boe_notices = self._safe_notices(self._boe_port, day, municipality)
        bocm_notices = self._safe_notices(self._bocm_port, day, municipality)
        land_classifications = self._safe(
            lambda: tuple(
                self._land_classification_port.get_land_classifications(
                    geometry, LAND_CLASSIFICATION_MARGIN_M
                )
            )
        )
        watercourses = self._safe(
            lambda: tuple(
                self._watercourse_port.get_nearby_watercourses(geometry, WATERCOURSE_MARGIN_M)
            )
        )
        flood_hazard = self._safe(
            lambda: tuple(self._flood_hazard_port.get_flood_hazard(geometry, FLOOD_HAZARD_MARGIN_M))
        )

        return EnrichedParcelReport(
            report=report,
            orthophoto=orthophoto,
            ndvi_summary=ndvi_summary,
            boe_notices=boe_notices,
            bocm_notices=bocm_notices,
            land_classifications=land_classifications,
            watercourses=watercourses,
            flood_hazard=flood_hazard,
        )

    def _get_orthophoto(self, geometry: Geometry) -> Orthophoto:
        return self._orthophoto_port.get_current_orthophoto(geometry, ORTHOPHOTO_MARGIN_M)

    def _get_ndvi_summary(self, geometry: Geometry, end: date) -> NdviSummary:
        # `end` se recibe como parámetro (capturado una sola vez en `execute`)
        # en vez de volver a llamar a `self._today()` aquí: dos llamadas
        # independientes podrían devolver días distintos si la petición
        # cruza la medianoche, desalineando NDVI con el día pedido a BOE/BOCM.
        start = date.fromordinal(end.toordinal() - NDVI_LOOKBACK_DAYS)
        grids = self._ndvi_port.get_ndvi_series(
            geometry,
            margin_m=NDVI_MARGIN_M,
            start=start,
            end=end,
            max_cloud_cover_percent=NDVI_MAX_CLOUD_COVER_PERCENT,
        )
        return summarize_ndvi_grid(grids[-1])

    @staticmethod
    def _safe[T](get_value: Callable[[], T]) -> T | None:
        """`None` si la fuente falla o no tiene evidencia disponible — el
        mensaje técnico de la excepción se descarta siempre, nunca llega al
        dominio ni al HTML (ADR 0010, decisión 3)."""
        try:
            return get_value()
        except Exception:
            return None

    @staticmethod
    def _safe_notices(
        port: OfficialBulletinPort, day: str, municipality: str
    ) -> tuple[BulletinNotice, ...] | None:
        """`None` solo si la llamada de red falla; una tupla vacía es un
        resultado real distinto ("la fuente respondió, cero disposiciones
        mencionan el municipio hoy") — ver `EnrichedParcelReport`."""
        try:
            notices = port.get_daily_bulletin(day)
        except Exception:
            return None
        return tuple(filter_by_title(notices, municipality))
