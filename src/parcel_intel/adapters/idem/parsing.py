import xml.etree.ElementTree as ET
from datetime import date
from typing import TypedDict

from parcel_intel.domain.geometry import Ring

_GML_NS = "http://www.opengis.net/gml/3.2"
_FEATURE_LOCAL_NAME = "VPLA_V_CLASIFICACION_REF_25"


class RawLandClassification(TypedDict):
    general_category: str
    detailed_category: str
    short_code: str
    reference_date: date
    municipality_code: str
    municipality_name: str
    area_m2: float
    rings: tuple[Ring, ...]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(feature: ET.Element, local_name: str) -> str:
    child = next((c for c in feature if _local_name(c.tag) == local_name), None)
    if child is None or child.text is None:
        return ""
    return child.text


def _parse_reference_date(raw: str) -> date:
    # Confirmado real (REGISTRY.md, hallazgo 2): `FC_REF` llega como fecha
    # ISO con un sufijo `Z` de huso UTC (p. ej. "2025-06-29Z"), que
    # `date.fromisoformat` no acepta directamente.
    return date.fromisoformat(raw.rstrip("Z"))


def _rings_from_feature(feature: ET.Element) -> tuple[Ring, ...]:
    # Confirmado real (no documentado hasta este parser): a diferencia de
    # Catastro, los polígonos de IDEM SÍ tienen anillos interiores reales
    # (huecos) -- un caso real observado trae 14 `gml:interior` en un solo
    # `gml:Polygon`. `domain.geometry.Geometry` declara explícitamente que
    # no modela huecos ("ninguna fuente usada hasta ahora los tiene"), así
    # que este parser toma solo los anillos EXTERIORES (`gml:exterior`) y
    # descarta los interiores a propósito -- la alternativa (tratar cada
    # `posList`, exterior o interior, como un anillo exterior más) rellenaría
    # visualmente los huecos reales del polígono, un resultado peor que
    # omitirlos. `area_m2` no se ve afectado: viene directo de `NM_AREA`
    # (servidor), no se calcula a partir de estos anillos.
    rings: list[Ring] = []
    for exterior in feature.iter(f"{{{_GML_NS}}}exterior"):
        pos_list = exterior.find(f".//{{{_GML_NS}}}posList")
        if pos_list is None or pos_list.text is None:
            continue
        values = [float(v) for v in pos_list.text.split()]
        points = tuple(zip(values[0::2], values[1::2], strict=True))
        rings.append(points)
    return tuple(rings)


def parse_wfs_land_classifications(xml_bytes: bytes) -> list[RawLandClassification]:
    """Parsea un `GetFeature` de `VPLA_V_CLASIFICACION_REF_25` a una lista de
    dicts planos. Una `FeatureCollection` vacía (sin cobertura, confirmado
    real en REGISTRY.md) produce una lista vacía — el adapter decide qué
    excepción de dominio lanzar con esa lista vacía, no este parser."""
    root = ET.fromstring(xml_bytes)
    classifications: list[RawLandClassification] = []
    for feature in root.iter():
        if _local_name(feature.tag) != _FEATURE_LOCAL_NAME:
            continue
        area_text = _child_text(feature, "NM_AREA")
        classifications.append(
            {
                "general_category": _child_text(feature, "DS_CLASIF_GEN"),
                "detailed_category": _child_text(feature, "DS_CLASIF_DET"),
                "short_code": _child_text(feature, "CD_SIGLAS"),
                "reference_date": _parse_reference_date(_child_text(feature, "FC_REF")),
                "municipality_code": _child_text(feature, "CD_MUNICIPIO"),
                "municipality_name": _child_text(feature, "DS_MUNICIPIO"),
                "area_m2": float(area_text) if area_text else 0.0,
                "rings": _rings_from_feature(feature),
            }
        )
    return classifications
