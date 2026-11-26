"""Lector de capas derivadas de trazados (historia #32, ADR 0030).

Lee `<directorio de la fuente>/<ine>.geojson` en el formato común, lo valida con
pydantic y lo convierte a `TrailLayer`. Sin fichero: `TrailLayerUnavailableError`
("no hay capa"). Fichero inválido: `TrailLayerFormatError` (fallo real, nunca se
convierte en "ausente").
"""

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import ValidationError

from parcel_intel.adapters.trail_layers.models import (
    FeatureModel,
    LayerFileModel,
    LineStringModel,
    MultiLineStringModel,
    MultiPolygonModel,
    PolygonModel,
    ProvenanceModel,
)
from parcel_intel.domain.discrepancy_report import TrailLayer
from parcel_intel.domain.geometry import Geometry, Line, MultiLineGeometry, Ring, TrailShape
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.trail import METRIC_SRID, InvalidTrailError, SourceKind, Trail
from parcel_intel.ports.errors import TrailLayerUnavailableError

_MUNICIPALITY_RE = re.compile(r"\d{5}")
_DEFAULT_CHARACTER = "capa derivada sin carácter declarado"


class TrailLayerFormatError(Exception):
    """El fichero de una capa existe pero no cumple el formato común."""

    def __init__(self, source: str, path: Path, detail: str) -> None:
        super().__init__(f"Capa {source!r} no válida en {path}: {detail}")
        self.source = source
        self.path = path
        self.detail = detail


def _provenance(model: ProvenanceModel) -> Provenance:
    return Provenance(
        source=model.fuente,
        url=model.url,
        retrieved_at=model.fecha_descarga,
        license=model.licencia,
    )


def _line(positions: Sequence[Sequence[float]]) -> Line:
    """Descarta la Z; exige al menos X e Y."""
    points: list[tuple[float, float]] = []
    for position in positions:
        if len(position) < 2:
            raise ValueError(f"posición con menos de 2 coordenadas: {list(position)!r}")
        points.append((position[0], position[1]))
    return tuple(points)


def _shape(model: FeatureModel) -> TrailShape:
    geometry = model.geometry
    if isinstance(geometry, PolygonModel):
        # Solo el anillo exterior (ADR 0011/0014: `Geometry` no modela huecos).
        rings: tuple[Ring, ...] = (_line(geometry.coordinates[0]),) if geometry.coordinates else ()
        return Geometry(rings=rings, srid=METRIC_SRID)
    if isinstance(geometry, MultiPolygonModel):
        # Conserva todas las partes (lección 0001).
        return Geometry(
            rings=tuple(_line(polygon[0]) for polygon in geometry.coordinates if polygon),
            srid=METRIC_SRID,
        )
    if isinstance(geometry, LineStringModel):
        return MultiLineGeometry(lines=(_line(geometry.coordinates),), srid=METRIC_SRID)
    assert isinstance(geometry, MultiLineStringModel)
    return MultiLineGeometry(
        lines=tuple(_line(line) for line in geometry.coordinates), srid=METRIC_SRID
    )


class GeoJsonTrailLayerReader:
    """Implementa `MunicipalTrailLayerPort` sobre ficheros derivados."""

    def __init__(self, paths: Mapping[SourceKind, Path]) -> None:
        self._paths = paths

    def get_layer(self, source: SourceKind, municipality_code: str) -> TrailLayer:
        if not _MUNICIPALITY_RE.fullmatch(municipality_code):
            raise ValueError(f"código INE de 5 dígitos esperado: {municipality_code!r}")
        directory = self._paths.get(source)
        if directory is None:
            raise TrailLayerUnavailableError(
                source, municipality_code, "fuente sin directorio de capas configurado"
            )
        path = directory / f"{municipality_code}.geojson"
        if not path.is_file():
            raise TrailLayerUnavailableError(
                source, municipality_code, f"sin capa derivada en caché ({path})"
            )
        return self._parse(source, municipality_code, path)

    def _parse(self, source: SourceKind, municipality_code: str, path: Path) -> TrailLayer:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as error:
            raise TrailLayerFormatError(source, path, f"JSON ilegible: {error}") from error
        try:
            model = LayerFileModel.model_validate(raw)
        except ValidationError as error:
            raise TrailLayerFormatError(source, path, _summarize(error)) from error

        if not model.crs.properties.name.endswith(("EPSG::25830", "EPSG:25830")):
            raise TrailLayerFormatError(
                source, path, f"CRS {model.crs.properties.name!r}; solo se admite EPSG:25830"
            )
        if model.properties.fuente != source:
            raise TrailLayerFormatError(
                source,
                path,
                f"la capa declara la fuente {model.properties.fuente!r}, se esperaba {source!r}",
            )
        if model.properties.municipio != municipality_code:
            raise TrailLayerFormatError(
                source,
                path,
                f"la capa declara el municipio {model.properties.municipio!r}, "
                f"se esperaba {municipality_code!r}",
            )

        layer_provenance = _provenance(model.properties.procedencia)
        character = model.properties.aviso or _DEFAULT_CHARACTER
        trails: list[Trail] = []
        for feature in model.features:
            try:
                trails.append(
                    Trail(
                        identifier=str(feature.id),
                        source=source,
                        role=feature.properties.papel,
                        name=feature.properties.nombre or None,
                        trail_type=feature.properties.tipo or None,
                        municipality_code=municipality_code,
                        geometry=_shape(feature),
                        provenance=(
                            _provenance(feature.properties.procedencia)
                            if feature.properties.procedencia is not None
                            else layer_provenance
                        ),
                        data_date=feature.properties.fecha_dato,
                        character=character,
                    )
                )
            except (ValueError, InvalidTrailError) as error:
                raise TrailLayerFormatError(
                    source, path, f"feature {feature.id!r}: {error}"
                ) from error
        return TrailLayer(
            source=source,
            municipality_code=municipality_code,
            provenance=layer_provenance,
            trails=tuple(trails),
        )


def _summarize(error: ValidationError) -> str:
    first = error.errors()[0]
    location = ".".join(str(part) for part in first["loc"])
    return f"{location}: {first['msg']}"
