import xml.etree.ElementTree as ET
from typing import TypedDict

from parcel_intel.domain.geometry import Ring

_GML_NS = "http://www.opengis.net/gml/3.2"
_FEATURE_LOCAL_NAME = "IDEM_MA_VIAS_PECUARIAS"


class RawLivestockTrail(TypedDict):
    trail_type: str
    name: str
    municipality_code: str
    municipality_name: str
    trail_code: str
    length_m: float
    area_m2: float
    rings: tuple[Ring, ...]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(feature: ET.Element, local_name: str) -> str:
    child = next((c for c in feature if _local_name(c.tag) == local_name), None)
    if child is None or child.text is None:
        return ""
    return child.text


def _rings_from_feature(feature: ET.Element) -> tuple[Ring, ...]:
    # Mismo patrón que `adapters/idem/parsing.py` (ADR 0011): solo
    # `gml:exterior`, nunca `gml:interior`. Confirmado real (REGISTRY.md,
    # hallazgo 3) que esta capa no tiene anillos interiores en los 17
    # features observados, pero se mantiene la misma guarda defensiva por
    # si un municipio no muestreado sí los tuviera.
    rings: list[Ring] = []
    for exterior in feature.iter(f"{{{_GML_NS}}}exterior"):
        pos_list = exterior.find(f".//{{{_GML_NS}}}posList")
        if pos_list is None or pos_list.text is None:
            continue
        values = [float(v) for v in pos_list.text.split()]
        points = tuple(zip(values[0::2], values[1::2], strict=True))
        rings.append(points)
    return tuple(rings)


def parse_wfs_livestock_trails(xml_bytes: bytes) -> list[RawLivestockTrail]:
    """Parsea un `GetFeature` de `Zonas:IDEM_MA_VIAS_PECUARIAS` a una lista
    de dicts planos. Una `FeatureCollection` vacía (sin vía pecuaria
    cercana, confirmado real en REGISTRY.md) produce una lista vacía."""
    root = ET.fromstring(xml_bytes)
    trails: list[RawLivestockTrail] = []
    for feature in root.iter():
        if _local_name(feature.tag) != _FEATURE_LOCAL_NAME:
            continue
        length_text = _child_text(feature, "NM_LONG")
        area_text = _child_text(feature, "NM_AREA")
        trails.append(
            {
                "trail_type": _child_text(feature, "DS_TIPO"),
                "name": _child_text(feature, "DS_NOMBRE"),
                "municipality_code": _child_text(feature, "CD_MUNI"),
                "municipality_name": _child_text(feature, "DS_MUNI"),
                "trail_code": _child_text(feature, "CD_VP"),
                "length_m": float(length_text) if length_text else 0.0,
                "area_m2": float(area_text) if area_text else 0.0,
                "rings": _rings_from_feature(feature),
            }
        )
    return trails
