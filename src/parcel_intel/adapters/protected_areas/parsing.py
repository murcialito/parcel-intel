import xml.etree.ElementTree as ET
from typing import TypedDict

from parcel_intel.domain.geometry import Ring

_GML_NS = "http://www.opengis.net/gml/3.2"
_FEATURE_LOCAL_NAME = "IDEM_MA_RED_NATURA_PLAN"


class RawProtectedArea(TypedDict):
    plan_code: str
    plan_name: str
    zone_code: str
    zone_name: str
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
    # `gml:exterior`, nunca `gml:interior`. A diferencia de vías pecuarias
    # (ADR 0014), esta fuente SÍ tiene anillos interiores reales
    # (confirmado en REGISTRY.md, hallazgo 4: 2 huecos reales) -- tratar
    # cada `posList` como anillo exterior rellenaría visualmente los
    # huecos reales del polígono.
    rings: list[Ring] = []
    for exterior in feature.iter(f"{{{_GML_NS}}}exterior"):
        pos_list = exterior.find(f".//{{{_GML_NS}}}posList")
        if pos_list is None or pos_list.text is None:
            continue
        values = [float(v) for v in pos_list.text.split()]
        points = tuple(zip(values[0::2], values[1::2], strict=True))
        rings.append(points)
    return tuple(rings)


def parse_wfs_protected_areas(xml_bytes: bytes) -> list[RawProtectedArea]:
    """Parsea un `GetFeature` de `Zonas:IDEM_MA_RED_NATURA_PLAN` a una
    lista de dicts planos. Una `FeatureCollection` vacía (sin plan de
    gestión cercano) produce una lista vacía."""
    root = ET.fromstring(xml_bytes)
    areas: list[RawProtectedArea] = []
    for feature in root.iter():
        if _local_name(feature.tag) != _FEATURE_LOCAL_NAME:
            continue
        areas.append(
            {
                "plan_code": _child_text(feature, "CD_PLAN"),
                "plan_name": _child_text(feature, "DS_PLAN"),
                "zone_code": _child_text(feature, "CD_ZONA"),
                "zone_name": _child_text(feature, "DS_ZONA"),
                "rings": _rings_from_feature(feature),
            }
        )
    return areas
