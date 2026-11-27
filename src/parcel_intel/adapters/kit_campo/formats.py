"""Serialización a GPX 1.1 y KML 2.2 con la biblioteca estándar (historia #213).

Determinista: sin reloj (la fecha llega en `MunicipalKit`), orden de entrada y atributos fijos.
GPX no tiene polígonos: cada anillo se escribe como un segmento de pista.
"""

import xml.etree.ElementTree as ET
from collections.abc import Sequence

from parcel_intel.domain.kit_campo import (
    LAYER_TITLE,
    Coordinate,
    KitGeometry,
    KitLayer,
    MunicipalKit,
)

GPX_NS = "http://www.topografix.com/GPX/1/1"
KML_NS = "http://www.opengis.net/kml/2.2"
CREATOR = "Paso Común"
KIT_NOTICE = "Indicios y trazados a verificar sobre el terreno; no son un dictamen ni un deslinde."


def kit_title(kit: MunicipalKit) -> str:
    return f"Paso Común — kit de campo del municipio {kit.municipality_code}"


def kit_description(kit: MunicipalKit, repository_url: str) -> str:
    lines = [KIT_NOTICE, f"Generado el {kit.generated_on.isoformat()}. {repository_url}"]
    for layer in kit.layers:
        lines.append(
            f"{LAYER_TITLE[layer.layer]}: fuente {layer.source}; licencia {layer.license}; "
            f"atribución: {' | '.join(layer.attribution)}; aviso: {layer.notice}"
        )
    if kit.missing:
        lines.append(f"Capas no publicadas para el municipio: {', '.join(kit.missing)}.")
    return "\n".join(lines)


def _pt(coordinate: Coordinate) -> str:
    return f"{coordinate[0]:.6f},{coordinate[1]:.6f}"


def _text(parent: ET.Element, tag: str, text: str) -> ET.Element:
    element = ET.SubElement(parent, tag)
    element.text = text
    return element


def _segments(geometry: KitGeometry) -> list[Sequence[Coordinate]]:
    segments: list[Sequence[Coordinate]] = list(geometry.lines)
    for polygon in geometry.polygons:
        segments.extend(polygon)
    return segments


def _serialize(root: ET.Element) -> str:
    ET.indent(root, space=" ")
    body = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{body}\n'


def to_gpx(kit: MunicipalKit, repository_url: str) -> str:
    root = ET.Element(
        "gpx",
        {
            "version": "1.1",
            "creator": CREATOR,
            "xmlns": GPX_NS,
        },
    )
    metadata = ET.SubElement(root, "metadata")
    _text(metadata, "name", kit_title(kit))
    _text(metadata, "desc", kit_description(kit, repository_url))
    copyright_ = ET.SubElement(metadata, "copyright", {"author": CREATOR})
    _text(copyright_, "year", str(kit.generated_on.year))
    _text(metadata, "time", f"{kit.generated_on.isoformat()}T00:00:00Z")
    for layer in kit.layers:
        for tramo in layer.tramos:
            track = ET.SubElement(root, "trk")
            _text(track, "name", tramo.name)
            _text(track, "desc", tramo.description)
            _text(track, "type", layer.layer)
            for segment in _segments(tramo.geometry):
                seg = ET.SubElement(track, "trkseg")
                for lon, lat in segment:
                    ET.SubElement(seg, "trkpt", {"lat": f"{lat:.6f}", "lon": f"{lon:.6f}"})
    return _serialize(root)


def _linear_ring(parent: ET.Element, tag: str, ring: Sequence[Coordinate]) -> None:
    boundary = ET.SubElement(parent, tag)
    linear = ET.SubElement(boundary, "LinearRing")
    _text(linear, "coordinates", " ".join(_pt(c) for c in ring))


def _kml_geometry(parent: ET.Element, geometry: KitGeometry) -> None:
    shapes: list[ET.Element] = []
    holder = ET.Element("holder")
    for line in geometry.lines:
        element = ET.SubElement(holder, "LineString")
        _text(element, "coordinates", " ".join(_pt(c) for c in line))
        shapes.append(element)
    for polygon in geometry.polygons:
        element = ET.SubElement(holder, "Polygon")
        _linear_ring(element, "outerBoundaryIs", polygon[0])
        for hole in polygon[1:]:
            _linear_ring(element, "innerBoundaryIs", hole)
        shapes.append(element)
    if len(shapes) == 1:
        parent.append(shapes[0])
    else:
        multi = ET.SubElement(parent, "MultiGeometry")
        multi.extend(shapes)


def _folder(document: ET.Element, layer: KitLayer) -> None:
    folder = ET.SubElement(document, "Folder")
    _text(folder, "name", LAYER_TITLE[layer.layer])
    _text(
        folder,
        "description",
        f"Fuente {layer.source}; licencia {layer.license}; "
        f"atribución: {' | '.join(layer.attribution)}; aviso: {layer.notice}",
    )
    for tramo in layer.tramos:
        mark = ET.SubElement(folder, "Placemark")
        _text(mark, "name", tramo.name)
        _text(mark, "description", tramo.description)
        _kml_geometry(mark, tramo.geometry)


def to_kml(kit: MunicipalKit, repository_url: str) -> str:
    root = ET.Element("kml", {"xmlns": KML_NS})
    document = ET.SubElement(root, "Document")
    _text(document, "name", kit_title(kit))
    _text(document, "description", kit_description(kit, repository_url))
    for layer in kit.layers:
        _folder(document, layer)
    return _serialize(root)
