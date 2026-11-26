"""Índice `site/datos/indice.json` del visor (historia #84, contrato con #85).

`{"municipios": [{"ine", "nombre", "bbox", "capas": {"<capa>": "<capa>/<ine>.geojson"}}]}`,
ordenado por `nombre` y luego `ine`; `bbox` = `[oeste, sur, este, norte]` en EPSG:4326
de todas las coordenadas publicadas del municipio (ya redondeadas, así las contiene
todas). Se construye siempre entero a partir de los GeoJSON publicados, sin fecha de
generación.
"""

import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

INDEX_SOURCE = "Parcel Intel, índice de capas publicadas"
INDEX_LICENSE = "CC BY 4.0"


class PublishedLayerError(ValueError):
    """Un fichero publicado (o por publicar) no se puede usar; no se escribe nada."""


@dataclass(frozen=True)
class IndexEntry:
    layer_id: str
    municipality_code: str
    municipality_name: str
    bbox: tuple[float, float, float, float]
    retrieved_at: str  # ISO, `fecha_descarga` de la procedencia de la capa


def _collation_key(name: str) -> str:
    """Orden alfabético sin depender del locale: «Ávila» va con la A, no al final."""
    decomposed = unicodedata.normalize("NFD", name.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _positions(value: object) -> Iterator[tuple[float, float]]:
    if (
        isinstance(value, list)
        and len(value) >= 2
        and all(isinstance(item, int | float) for item in value)
    ):
        yield float(value[0]), float(value[1])
        return
    if not isinstance(value, list):
        raise PublishedLayerError(f"coordenadas no válidas: {value!r}")
    for item in value:
        yield from _positions(item)


def entry_from_document(layer_id: str, municipality_code: str, document: object) -> IndexEntry:
    """Lee del GeoJSON publicado lo que necesita el índice."""
    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise PublishedLayerError("no es una FeatureCollection")
    properties = document.get("properties")
    if not isinstance(properties, dict):
        raise PublishedLayerError("sin propiedades de colección")
    name = properties.get("nombre_municipio")
    provenance = properties.get("procedencia")
    if not isinstance(name, str) or not name:
        raise PublishedLayerError("sin nombre_municipio")
    if not isinstance(provenance, dict) or not isinstance(provenance.get("fecha_descarga"), str):
        raise PublishedLayerError("sin procedencia.fecha_descarga")
    features = document.get("features")
    if not isinstance(features, list):
        raise PublishedLayerError("sin features")
    lons: list[float] = []
    lats: list[float] = []
    for feature in features:
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if not isinstance(geometry, dict):
            raise PublishedLayerError("feature sin geometría")
        for lon, lat in _positions(geometry.get("coordinates")):
            lons.append(lon)
            lats.append(lat)
    if not lons:
        raise PublishedLayerError("capa publicada sin coordenadas")
    return IndexEntry(
        layer_id=layer_id,
        municipality_code=municipality_code,
        municipality_name=name,
        bbox=(min(lons), min(lats), max(lons), max(lats)),
        retrieved_at=provenance["fecha_descarga"],
    )


def build_index(
    entries: Iterable[IndexEntry], repository_url: str
) -> tuple[dict[str, object], dict[str, object]]:
    """Devuelve `(indice, procedencia del índice)`."""
    by_code: dict[str, list[IndexEntry]] = {}
    for entry in entries:
        by_code.setdefault(entry.municipality_code, []).append(entry)
    municipalities: list[dict[str, object]] = []
    for code, group in by_code.items():
        names = {entry.municipality_name for entry in group}
        if len(names) != 1:
            raise PublishedLayerError(
                f"el municipio {code} tiene nombres distintos en sus capas: {sorted(names)}"
            )
        municipalities.append(
            {
                "ine": code,
                "nombre": names.pop(),
                "bbox": [
                    round(min(entry.bbox[0] for entry in group), 6),
                    round(min(entry.bbox[1] for entry in group), 6),
                    round(max(entry.bbox[2] for entry in group), 6),
                    round(max(entry.bbox[3] for entry in group), 6),
                ],
                "capas": {
                    entry.layer_id: f"{entry.layer_id}/{code}.geojson"
                    for entry in sorted(group, key=lambda item: item.layer_id)
                },
            }
        )
    municipalities.sort(
        key=lambda item: (_collation_key(str(item["nombre"])), str(item["ine"]))
    )
    all_entries = [entry for group in by_code.values() for entry in group]
    provenance: dict[str, object] = {
        "fuente": INDEX_SOURCE,
        "url": repository_url,
        "fecha_descarga": max((entry.retrieved_at for entry in all_entries), default=None),
        "licencia": INDEX_LICENSE,
        "redistribucion": "publicable",
    }
    return {"municipios": municipalities}, provenance
