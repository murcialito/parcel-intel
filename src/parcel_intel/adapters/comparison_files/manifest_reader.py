"""Lector completo del manifiesto interno de imágenes de comparación (historia #172,
ADR 0049).

Lee `<directorio>/<ine>.json`, el fichero que escribe `JsonComparisonManifestWriter`
(#122), lo valida con pydantic en el borde (`extra="forbid"`: el manifiesto es nuestro y
no lleva datos sensibles) y construye las entidades de `domain/comparison_image.py`. Es
hermano del lector de disponibilidad de #168, que solo mira el estado.

Lista blanca de URL: la de cada imagen debe ser exactamente `window_url(ventana, vuelo)`,
la URL canónica que pidió la caché cruda. Así servidor, capa y parámetros quedan
cerrados y la URL publicada es la que se descargó y comprobó.
"""

import json
import re
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from parcel_intel.adapters.pnoa.window import window_url
from parcel_intel.domain.comparison_image import (
    FLIGHTS,
    ComparisonImage,
    ComparisonManifest,
    ComparisonWindow,
    DeclaredGap,
    OmittedSlot,
    StretchComparison,
)
from parcel_intel.domain.discrepancy_criterion import CriterionRef
from parcel_intel.domain.orthophoto import HistoricalVintage, OrthophotoWindow
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.ports.errors import ComparisonManifestFileError

_MUNICIPALITY_RE = re.compile(r"[0-9]{5}")

_Vintage = StrictInt | Literal["AMS_1956-1957", "SIGPAC", "OLISTAT"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _PolicyModel(_Model):
    id: str = Field(min_length=1)
    version: StrictInt


class _GapModel(_Model):
    desde: StrictInt
    hasta: StrictInt
    motivo: str = Field(min_length=1)


class _ProvenanceModel(_Model):
    fuente: str = Field(min_length=1)
    url: str = Field(min_length=1)
    fecha_descarga: date
    licencia: str | None
    redistribucion: Literal["publicable", "solo_uso_interno"]


class _ImageModel(_Model):
    franja: str = Field(min_length=1)
    vuelo: _Vintage
    periodo: str = Field(min_length=1)
    resolucion_m: float = Field(gt=0)
    atribucion: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: StrictInt = Field(gt=0)
    procedencia: _ProvenanceModel


class _OmittedModel(_Model):
    franja: str = Field(min_length=1)
    motivo: Literal["sin_cobertura", "fallo"]
    probados: list[_Vintage]
    tipo_error: str | None


class _WindowModel(_Model):
    bbox: tuple[StrictInt, StrictInt, StrictInt, StrictInt]
    srid: StrictInt
    ancho_px: StrictInt = Field(gt=0)
    alto_px: StrictInt = Field(gt=0)
    trazo_px: list[list[tuple[float, float]]]
    imagenes: list[_ImageModel]
    omitidas: list[_OmittedModel]


class _StretchModel(_Model):
    id: str = Field(pattern=r"^[0-9a-f]{16}$")
    estado: Literal["generada", "tramo_demasiado_largo"]
    ventanas: list[_WindowModel]


class _ManifestModel(_Model):
    municipio: str = Field(pattern=r"^[0-9]{5}$")
    politica: _PolicyModel
    huecos: list[_GapModel]
    tramos: list[_StretchModel]


def _vintage(value: _Vintage, where: str) -> HistoricalVintage:
    if value not in FLIGHTS:
        raise ValueError(f"{where}: vuelo no reconocido")
    return value


def _window(model: _WindowModel, where: str) -> OrthophotoWindow:
    min_x, min_y, max_x, max_y = model.bbox
    try:
        return OrthophotoWindow(
            min_x, min_y, max_x, max_y, model.srid, model.ancho_px, model.alto_px
        )
    except ValueError as error:
        raise ValueError(f"{where}: {error}") from error


def _image(model: _ImageModel, window: OrthophotoWindow, where: str) -> ComparisonImage:
    vintage = _vintage(model.vuelo, f"{where}.vuelo")
    provenance = model.procedencia
    if provenance.url != window_url(window, vintage):
        raise ValueError(
            f"{where}.procedencia.url: no es la URL canónica de su ventana y su vuelo en el "
            "WMS histórico del IGN"
        )
    return ComparisonImage(
        slot=model.franja,
        vintage=vintage,
        period=model.periodo,
        resolution_m=model.resolucion_m,
        attribution=model.atribucion,
        sha256=model.sha256,
        byte_size=model.bytes,
        provenance=Provenance(
            source=provenance.fuente,
            url=provenance.url,
            retrieved_at=provenance.fecha_descarga,
            license=provenance.licencia,
            redistribution=Redistribution(provenance.redistribucion),
        ),
    )


def _omitted(model: _OmittedModel, where: str) -> OmittedSlot:
    return OmittedSlot(
        slot=model.franja,
        reason=model.motivo,
        tried=tuple(_vintage(v, f"{where}.probados") for v in model.probados),
        error_type=model.tipo_error,
    )


def _comparison_window(model: _WindowModel, where: str) -> ComparisonWindow:
    window = _window(model, where)
    return ComparisonWindow(
        window=window,
        stretch_px=tuple(tuple((x, y) for x, y in part) for part in model.trazo_px),
        images=tuple(
            _image(image, window, f"{where}.imagenes.{i}") for i, image in enumerate(model.imagenes)
        ),
        omitted=tuple(
            _omitted(omitted, f"{where}.omitidas.{i}") for i, omitted in enumerate(model.omitidas)
        ),
    )


def parse_manifest(document: object, municipality_code: str) -> ComparisonManifest:
    """Manifiesto del municipio, o `ValueError` con el campo que falla."""
    try:
        model = _ManifestModel.model_validate(document)
    except ValidationError as error:
        first = error.errors()[0]
        location = ".".join(str(part) for part in first["loc"]) or "raíz"
        raise ValueError(f"{location}: {first['msg']}") from error
    if model.municipio != municipality_code:
        raise ValueError(f"municipio: el manifiesto es del municipio {model.municipio}")
    policy = CriterionRef(model.politica.id, model.politica.version)
    gaps = tuple(DeclaredGap(g.desde, g.hasta, g.motivo) for g in model.huecos)
    seen: set[str] = set()
    stretches: list[StretchComparison] = []
    for index, stretch in enumerate(model.tramos):
        where = f"tramos.{index}"
        if stretch.id in seen:
            raise ValueError(f"{where}.id: id de tramo repetido")
        seen.add(stretch.id)
        stretches.append(
            StretchComparison(
                stretch_id=stretch.id,
                municipality_code=model.municipio,
                policy=policy,
                status=stretch.estado,
                windows=tuple(
                    _comparison_window(window, f"{where}.ventanas.{i}")
                    for i, window in enumerate(stretch.ventanas)
                ),
                gaps=gaps,
            )
        )
    return ComparisonManifest(
        municipality_code=model.municipio,
        policy=policy,
        gaps=gaps,
        stretches=tuple(sorted(stretches, key=lambda s: s.stretch_id)),
    )


class JsonComparisonManifestReader:
    """Implementa `ComparisonManifestSource` sobre `<directory>/<ine>.json`."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def get_manifest(self, municipality_code: str) -> ComparisonManifest | None:
        if not _MUNICIPALITY_RE.fullmatch(municipality_code):
            raise ValueError("código INE de 5 dígitos esperado")
        path = self._directory / f"{municipality_code}.json"
        if not path.is_file():
            return None
        try:
            document = json.loads(path.read_bytes().decode("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as error:
            raise ComparisonManifestFileError(str(path), "JSON ilegible") from error
        try:
            return parse_manifest(document, municipality_code)
        except ValueError as error:
            raise ComparisonManifestFileError(str(path), str(error)) from error
