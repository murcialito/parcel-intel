from dataclasses import dataclass

from parcel_intel.domain.building import Building
from parcel_intel.domain.bulletin import BulletinNotice
from parcel_intel.domain.flood_hazard import FloodHazardSample
from parcel_intel.domain.land_classification import LandClassification
from parcel_intel.domain.livestock_trail import LivestockTrail
from parcel_intel.domain.ndvi import NdviSummary
from parcel_intel.domain.orthophoto import Orthophoto
from parcel_intel.domain.parcel import Parcel
from parcel_intel.domain.protected_area import ProtectedArea
from parcel_intel.domain.watercourse import Watercourse


@dataclass(frozen=True)
class ParcelReport:
    parcel: Parcel
    buildings: tuple[Building, ...]


@dataclass(frozen=True)
class EnrichedParcelReport:
    """Envuelve `ParcelReport` (cacheado, historia 0005) con evidencia de
    nueve fuentes nunca cacheadas (historia 0010 + historia 0013 + historia
    0016, ver ADR 0010/0013/0016). Cada campo es `None` cuando la fuente
    correspondiente falló o no tuvo evidencia disponible — nunca el mensaje
    técnico de la excepción, que `application/` descarta antes de construir
    esta entidad. La semántica exacta de `None` frente a una tupla varía por
    campo, documentada en cada uno (no es uniforme entre fuentes):

    - `boe_notices`/`bocm_notices`: tupla vacía (no `None`) es un resultado
      válido y distinto de `None` — la fuente respondió pero ninguna
      disposición mencionaba el municipio ese día (ADR 0008/0009).
    - `land_classifications`: `None` cuando la fuente falla **o** cuando
      `NoLandClassificationFoundError` se captura — el port nunca devuelve
      una lista vacía como resultado válido (ADR 0011). No existe un
      estado de "tupla vacía" legítimo para este campo.
    - `watercourses`, `livestock_trails`, `protected_areas`: `None` solo si
      la llamada de red falla; una tupla vacía es un resultado real y
      distinto ("sin cauce/vía pecuaria/espacio protegido cercano", ADR
      0012/0014/0015).
    - `flood_hazard`: `None` si la llamada falla (incluye el fallo de
      cualquiera de las 5 peticiones, que hace fallar las 5 a la vez); el
      único resultado de éxito es una tupla de exactamente 5
      `FloodHazardSample` (cada una con `water_depth_m` posiblemente
      `None` = "NO DATA" del servicio) — ADR 0012/0013."""

    report: ParcelReport
    orthophoto: Orthophoto | None
    ndvi_summary: NdviSummary | None
    boe_notices: tuple[BulletinNotice, ...] | None
    bocm_notices: tuple[BulletinNotice, ...] | None
    land_classifications: tuple[LandClassification, ...] | None
    watercourses: tuple[Watercourse, ...] | None
    flood_hazard: tuple[FloodHazardSample, ...] | None
    livestock_trails: tuple[LivestockTrail, ...] | None
    protected_areas: tuple[ProtectedArea, ...] | None
