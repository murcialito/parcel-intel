"""Capas que se publican en el sitio estático y resultado de publicarlas (historia #84).

`PUBLISHED_LAYERS` es la única lista de capas publicables: identificador (nombre del
directorio en `site/datos/` y en `data/derived/`), fuente, atribución literal de
`NOTICE` (ADR 0035: lo que ve el público es `NOTICE`) y aviso de carácter del dato.
Catastro no está, ni puede añadirse sin ADR. El dominio no conoce EPSG:4326: la
reproyección es del adapter de salida.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from parcel_intel.domain.livestock_trail import LIVESTOCK_TRAIL_CHARACTER
from parcel_intel.domain.municipal_road_layer import ROAD_LAYER_NOTICE
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.publication import PublishableLayer
from parcel_intel.domain.trail import SourceKind, Trail

PublishedLayerId = Literal["vias_pecuarias", "camino_actual"]
"""Nombre del directorio en `site/datos/` y en `data/derived/`."""

IndexedLayerId = Literal["vias_pecuarias", "camino_actual", "discrepancias", "candidatos"]
"""Directorios de `site/datos/` que entran en el índice (historias #94 y #170, ADR 0044
y 0048)."""

INDEXED_LAYER_IDS: tuple[IndexedLayerId, ...] = (
    "camino_actual",
    "candidatos",
    "discrepancias",
    "vias_pecuarias",
)
"""Única lista de capas del índice: las de trazados de `PUBLISHED_LAYERS` más la de
indicios (`discrepancias`) y la de tramos a verificar (`candidatos`), que no son capas
de trazados de una sola fuente. Los tres sinks reconstruyen el índice con ella, así
ningún comando borra la capa de otro."""


@dataclass(frozen=True)
class PublishedLayerSpec:
    layer_id: PublishedLayerId
    source: SourceKind
    attribution: str  # literal de NOTICE
    notice: str  # aviso de carácter del dato


PUBLISHED_LAYERS: MappingProxyType[PublishedLayerId, PublishedLayerSpec] = MappingProxyType(
    {
        "vias_pecuarias": PublishedLayerSpec(
            layer_id="vias_pecuarias",
            source="via_pecuaria_oficial",
            attribution="CC BY 4.0 Comunidad de Madrid",
            notice=LIVESTOCK_TRAIL_CHARACTER,
        ),
        "camino_actual": PublishedLayerSpec(
            layer_id="camino_actual",
            source="ign_red_transporte",
            attribution="Obra derivada de IGR-RT 2026 CC-BY 4.0 Instituto Geográfico Nacional",
            notice=ROAD_LAYER_NOTICE,
        ),
    }
)
"""Única lista de capas publicables. Catastro no está, ni puede añadirse sin ADR."""


@dataclass(frozen=True)
class TrailLayerPublication:
    """Una capa de un municipio que ya pasó la puerta `PublishableLayer`."""

    spec: PublishedLayerSpec
    municipality_code: str
    municipality_name: str
    content: PublishableLayer[Trail]  # layer_provenance = procedencia de la capa
    boundary_provenance: Provenance | None


@dataclass(frozen=True)
class Simplification:
    tolerance_m: float
    bytes_before: int


@dataclass(frozen=True)
class PublishedFile:
    layer_id: IndexedLayerId
    municipality_code: str
    path: str  # relativo al directorio de salida, p. ej. "camino_actual/28043.geojson"
    size_bytes: int
    simplification: Simplification | None
    over_threshold: bool  # sigue por encima del umbral tras simplificar


@dataclass(frozen=True)
class PublicationFailure:
    layer_id: PublishedLayerId
    municipality_code: str
    reason: str  # "sin capa: …", "no redistribuible: …"


@dataclass(frozen=True)
class PublicationResult:
    published: tuple[PublishedFile, ...]
    empty: tuple[tuple[PublishedLayerId, str], ...]  # (capa, ine) vacías, no publicadas
    failures: tuple[PublicationFailure, ...]  # si hay alguna, `published` es ()
