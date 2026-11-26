"""Trazado común: lo que se publica y se compara, venga de la fuente que venga
(historia #22, ADR 0029). Sin ningún campo de titularidad, propietario,
referencia catastral de finca ni parcela colindante (ADR 0029, decisión 3).

Cada fuente escribe su conversión a `Trail` en su propio módulo de dominio
(p. ej. `livestock_trail.livestock_trail_to_trail`); este módulo no conoce
las entidades de origen.
"""

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, get_args

from parcel_intel.domain.geometry import Geometry, MultiLineGeometry, TrailShape
from parcel_intel.domain.provenance import Provenance

SourceKind = Literal[
    "via_pecuaria_oficial",  # IDEM Zonas:IDEM_MA_VIAS_PECUARIAS
    "catastro_vt",  # parcelas 9xxx con subparcela VT
    "ign_red_transporte",  # roadlink, OGC API Features
    "planimetria_historica",  # planimetrías/minutas IGN 1870-1880, vectorizadas
    "mtn50_historico",  # MTN50 1.ª edición (1881…), vectorizado
]
"""Vocabulario único de fuentes de trazado (#14 y #22). La cadena es el valor
que se escribe en ficheros y define el orden canónico (`sorted()`)."""
# PNOA no figura: es referencia visual, no trazado (REGISTRY.md, historia 0021).

TrailRole = Literal["via", "anejo"]  # anejo: abrevadero, descansadero… (no es una vía)

METRIC_SRID = 25830

_MUNICIPALITY_CODE_RE = re.compile(r"\d{5}")


class InvalidTrailError(ValueError):
    """Un `Trail` no cumple sus invariantes; el mensaje nombra el campo."""


@dataclass(frozen=True)
class Trail:
    """Trazado común con fuente, papel (vía o anejo), geometría en EPSG:25830,
    procedencia con licencia y nota de carácter del dato.

    La clave única de un trazado es `(source, municipality_code, identifier)`:
    las piezas de un recorte por municipio comparten `identifier`.

    La geometría puede no tener partes: decidir qué hacer con un trazado
    vacío es del consumidor (#31), no de la entidad."""

    identifier: str  # estable en su fuente (CD_VP en vías pecuarias)
    source: SourceKind
    role: TrailRole
    name: str | None  # nombre en la fuente (DS_NOMBRE); None si la fuente no lo da
    trail_type: str | None  # tipo en la fuente, texto libre (DS_TIPO); None si no lo da
    municipality_code: str  # INE, 5 dígitos
    geometry: TrailShape  # EPSG:25830; puede no tener partes
    provenance: Provenance  # licencia obligatoria
    data_date: date | None  # fecha del DATO, no de descarga
    character: str  # carácter del dato, p. ej. "cartografía informativa, no deslinde"

    def __post_init__(self) -> None:
        _require_text(self.identifier, "identifier")
        if self.source not in get_args(SourceKind):
            raise InvalidTrailError(f"source no reconocida: {self.source!r}")
        if self.role not in get_args(TrailRole):
            raise InvalidTrailError(f"role no reconocido: {self.role!r}")
        if self.name is not None:
            _require_text(self.name, "name")
        if self.trail_type is not None:
            _require_text(self.trail_type, "trail_type")
        if not (
            isinstance(self.municipality_code, str)
            and _MUNICIPALITY_CODE_RE.fullmatch(self.municipality_code)
        ):
            raise InvalidTrailError(
                f"municipality_code debe ser un código INE de 5 dígitos: {self.municipality_code!r}"
            )
        _validate_geometry(self.geometry)
        if not isinstance(self.provenance, Provenance):
            raise InvalidTrailError("provenance es obligatoria")
        license_ = self.provenance.license
        if not isinstance(license_, str) or not license_.strip():
            raise InvalidTrailError("provenance.license es obligatoria")
        # `datetime` es subclase de `date`: se excluye para no mezclar hora.
        if self.data_date is not None and (
            not isinstance(self.data_date, date) or isinstance(self.data_date, datetime)
        ):
            raise InvalidTrailError(f"data_date debe ser una fecha o None: {self.data_date!r}")
        _require_text(self.character, "character")


def _require_text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidTrailError(f"{field} no puede estar vacío")


def _validate_geometry(geometry: object) -> None:
    """Tipo, srid y coordenadas finitas. No exige puntos (a diferencia de
    `HistoricTrail`): `Geometry(rings=(), srid=25830)` es válida."""
    if isinstance(geometry, Geometry):
        parts = geometry.rings
    elif isinstance(geometry, MultiLineGeometry):
        parts = geometry.lines
    else:
        raise InvalidTrailError("geometry debe ser una Geometry o una MultiLineGeometry")
    if geometry.srid != METRIC_SRID:
        raise InvalidTrailError(f"geometry.srid debe ser {METRIC_SRID}, no {geometry.srid!r}")
    for part in parts:
        for point in part:
            if not all(math.isfinite(coordinate) for coordinate in point):
                raise InvalidTrailError(f"geometry tiene una coordenada no finita: {point!r}")
