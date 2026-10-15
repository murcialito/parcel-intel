from dataclasses import dataclass

from parcel_intel.domain.building import Building
from parcel_intel.domain.bulletin import BulletinNotice
from parcel_intel.domain.ndvi import NdviSummary
from parcel_intel.domain.orthophoto import Orthophoto
from parcel_intel.domain.parcel import Parcel


@dataclass(frozen=True)
class ParcelReport:
    parcel: Parcel
    buildings: tuple[Building, ...]


@dataclass(frozen=True)
class EnrichedParcelReport:
    """Envuelve `ParcelReport` (cacheado, historia 0005) con evidencia de
    cuatro fuentes nunca cacheadas (historia 0010, ver ADR 0010). Cada campo
    es `None` cuando la fuente correspondiente falló o no tuvo evidencia
    disponible ese día/rango — nunca el mensaje técnico de la excepción, que
    `application/` descarta antes de construir esta entidad. Una tupla
    vacía (no `None`) en `boe_notices`/`bocm_notices` es un resultado válido
    y distinto: la fuente respondió pero ninguna disposición mencionaba el
    municipio ese día (mismo matiz ya confirmado real en ADR 0008/0009 para
    BOE, "0 coincidencias" es un resultado, no un fallo)."""

    report: ParcelReport
    orthophoto: Orthophoto | None
    ndvi_summary: NdviSummary | None
    boe_notices: tuple[BulletinNotice, ...] | None
    bocm_notices: tuple[BulletinNotice, ...] | None
