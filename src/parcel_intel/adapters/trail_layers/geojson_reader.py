"""Lector de capas derivadas de trazados (historia #32, ADR 0030).

Lee `<directorio de la fuente>/<ine>.geojson` en el formato común, lo valida con
pydantic y lo convierte a `TrailLayer`. Sin fichero: `TrailLayerUnavailableError`
("no hay capa"). Fichero inválido: `TrailLayerFormatError` (fallo real, nunca se
convierte en "ausente").
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
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
from parcel_intel.domain.provenance import Provenance, Redistribution
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
        # Sin marca: solo uso interno (ficheros escritos antes de #84).
        redistribution=(
            Redistribution(model.redistribucion)
            if model.redistribucion is not None
            else Redistribution.INTERNAL_ONLY
        ),
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
    return geometry_to_shape(model.geometry)


def geometry_to_shape(
    geometry: PolygonModel | MultiPolygonModel | LineStringModel | MultiLineStringModel,
) -> TrailShape:
    """GeoJSON validado → forma del dominio en EPSG:25830. La comparte el lector de
    discrepancias (#94); lanza `ValueError` si una posición no tiene X e Y."""
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


class IncompleteTrailLayerError(TrailLayerFormatError):
    """Una fuente con fichero complementario tiene solo uno de los dos ficheros
    (p. ej. `camino_actual/` sin `camino_asfaltado/`, historia #183). `path` es el
    fichero que falta. Es un fallo real: leer solo la mitad daría en silencio
    discrepancias distintas."""


_COMPLEMENT_MISSING_DETAIL = (
    "falta la capa complementaria (tramos asfaltados del IGN); la capa es anterior a "
    "la historia #183: regenera con `camino-actual-municipios` (con red: la caché no "
    "tiene aún las consultas `paved`)"
)
_PRINCIPAL_MISSING_DETAIL = (
    "falta la capa principal (tramos sin asfaltar del IGN) junto a la complementaria: "
    "regenera las dos con `camino-actual-municipios`"
)
_PRINCIPAL_SURFACE = "unpaved"
_COMPLEMENT_SURFACE = "paved"


class GeoJsonTrailLayerReader:
    """Implementa `MunicipalTrailLayerPort` sobre ficheros derivados.

    `complements` da, por fuente, un segundo directorio cuyo fichero se une al
    principal en una sola capa (ADR 0050): para `discrepancias`,
    `ign_red_transporte` = `camino_actual` (sin asfaltar) ∪ `camino_asfaltado`
    (asfaltado). Los trazados del complemento entran con `counterpart_only=True`.
    Sin `complements`, el lector se comporta como en #32 (así lo usa `publicar-capas`)."""

    def __init__(
        self,
        paths: Mapping[SourceKind, Path],
        complements: Mapping[SourceKind, Path] | None = None,
    ) -> None:
        self._paths = paths
        self._complements: Mapping[SourceKind, Path] = complements or {}

    def get_layer(self, source: SourceKind, municipality_code: str) -> TrailLayer:
        if not _MUNICIPALITY_RE.fullmatch(municipality_code):
            raise ValueError(f"código INE de 5 dígitos esperado: {municipality_code!r}")
        directory = self._paths.get(source)
        if directory is None:
            raise TrailLayerUnavailableError(
                source, municipality_code, "fuente sin directorio de capas configurado"
            )
        path = directory / f"{municipality_code}.geojson"
        complement_directory = self._complements.get(source)
        if complement_directory is None:
            if not path.is_file():
                raise TrailLayerUnavailableError(
                    source, municipality_code, f"sin capa derivada en caché ({path})"
                )
            return self._parse(source, municipality_code, path)

        complement_path = complement_directory / f"{municipality_code}.geojson"
        has_principal, has_complement = path.is_file(), complement_path.is_file()
        if not has_principal and not has_complement:
            raise TrailLayerUnavailableError(
                source, municipality_code, f"sin capa derivada en caché ({path})"
            )
        if not has_complement:
            raise IncompleteTrailLayerError(source, complement_path, _COMPLEMENT_MISSING_DETAIL)
        if not has_principal:
            raise IncompleteTrailLayerError(source, path, _PRINCIPAL_MISSING_DETAIL)
        principal = self._parse(source, municipality_code, path, surface=_PRINCIPAL_SURFACE)
        complement = self._parse(
            source, municipality_code, complement_path, surface=_COMPLEMENT_SURFACE
        )
        return _union(source, principal, complement, complement_path)

    def _parse(
        self,
        source: SourceKind,
        municipality_code: str,
        path: Path,
        surface: str | None = None,
    ) -> TrailLayer:
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
        if surface is not None:
            _check_surface(source, path, model, surface)

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
            municipality_name=model.properties.nombre_municipio or None,
            boundary_provenance=(
                _provenance(model.properties.procedencia_limite)
                if model.properties.procedencia_limite is not None
                else None
            ),
        )


def _check_surface(source: str, path: Path, model: LayerFileModel, expected: str) -> None:
    """El principal admite `superficie` ausente (ficheros de #27) o `unpaved`; el
    complemento exige `paved`. Lo mismo en cada feature que la declare (CA11 de #183)."""
    declared = model.properties.superficie
    allowed = (None, expected) if expected == _PRINCIPAL_SURFACE else (expected,)
    if declared not in allowed:
        raise TrailLayerFormatError(
            source,
            path,
            f"la capa declara la superficie {declared!r}, se esperaba {expected!r} "
            "(¿directorios camino_actual/ y camino_asfaltado/ intercambiados?)",
        )
    for feature in model.features:
        feature_surface = feature.properties.superficie
        if feature_surface is not None and feature_surface != expected:
            raise TrailLayerFormatError(
                source,
                path,
                f"feature {feature.id!r}: superficie {feature_surface!r}, "
                f"se esperaba {expected!r}",
            )


def _union(
    source: SourceKind, principal: TrailLayer, complement: TrailLayer, complement_path: Path
) -> TrailLayer:
    """Una sola capa: la procedencia, el nombre y el límite del principal; los
    trazados del complemento marcados como solo contraparte (ADR 0050)."""
    if (
        principal.municipality_name
        and complement.municipality_name
        and principal.municipality_name != complement.municipality_name
    ):
        raise TrailLayerFormatError(
            source,
            complement_path,
            f"la capa declara el municipio {complement.municipality_name!r}, "
            f"la principal {principal.municipality_name!r}",
        )
    principal_ids = {trail.identifier for trail in principal.trails}
    repeated = sorted(t.identifier for t in complement.trails if t.identifier in principal_ids)
    if repeated:
        raise TrailLayerFormatError(
            source,
            complement_path,
            f"identificador presente también en la capa principal: {repeated[0]!r}",
        )
    return TrailLayer(
        source=source,
        municipality_code=principal.municipality_code,
        provenance=principal.provenance,
        trails=principal.trails
        + tuple(replace(trail, counterpart_only=True) for trail in complement.trails),
        municipality_name=principal.municipality_name,
        boundary_provenance=principal.boundary_provenance,
    )


def _summarize(error: ValidationError) -> str:
    first = error.errors()[0]
    location = ".".join(str(part) for part in first["loc"])
    return f"{location}: {first['msg']}"
