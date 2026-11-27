import xml.etree.ElementTree as ET
from typing import TypedDict

from parcel_intel.domain.geometry import Ring

_GML_NS = "http://www.opengis.net/gml/3.2"
_FEATURE_LOCAL_NAME = "IDEM_MA_MONTES_UP"

ALLOWED_FIELDS = ("CD_UP", "DS_NOMBRE", "DS_MUNICIPIO")
"""Lista blanca de campos que se leen (más la geometría). Los campos de titularidad
(`DS_PROPIETARIO`, `DS_NOM_PROPIETARIO`) no se leen nunca: `_child_text` solo se llama
con estos nombres y el resultado no contiene nada más."""


class RawPublicUtilityForest(TypedDict):
    forest_code: str
    name: str
    municipality_name: str
    rings: tuple[Ring, ...]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(feature: ET.Element, local_name: str) -> str:
    if local_name not in ALLOWED_FIELDS:
        raise ValueError(f"campo fuera de la lista blanca: {local_name}")
    child = next((c for c in feature if _local_name(c.tag) == local_name), None)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _rings_from_feature(feature: ET.Element) -> tuple[Ring, ...]:
    # Mismo criterio que las vías pecuarias (ADR 0011): solo `gml:exterior`; los anillos
    # interiores (huecos) no se modelan. Esta capa SÍ los trae (REGISTRY.md): la pieza
    # recortada puede sobrestimar el área del monte si hay claros dentro.
    rings: list[Ring] = []
    for exterior in feature.iter(f"{{{_GML_NS}}}exterior"):
        pos_list = exterior.find(f".//{{{_GML_NS}}}posList")
        if pos_list is None or pos_list.text is None:
            continue
        values = [float(v) for v in pos_list.text.split()]
        rings.append(tuple(zip(values[0::2], values[1::2], strict=True)))
    return tuple(rings)


def parse_number_matched(xml_bytes: bytes) -> int | None:
    """`numberMatched` de la `FeatureCollection`, o `None` si falta o no es numérico."""
    raw = ET.fromstring(xml_bytes).get("numberMatched")
    return int(raw) if raw is not None and raw.isdigit() else None


def _code(text: str) -> str:
    """`CD_UP` es `xsd:decimal`: «208» o, si el servidor lo escribiera así, «208.0»."""
    return text[:-2] if text.endswith(".0") else text


def parse_wfs_public_utility_forests(xml_bytes: bytes) -> list[RawPublicUtilityForest]:
    """Parsea un `GetFeature` de `Zonas:IDEM_MA_MONTES_UP`. Una colección vacía
    (sin montes en el bbox) produce una lista vacía."""
    root = ET.fromstring(xml_bytes)
    forests: list[RawPublicUtilityForest] = []
    for feature in root.iter():
        if _local_name(feature.tag) != _FEATURE_LOCAL_NAME:
            continue
        forests.append(
            {
                "forest_code": _code(_child_text(feature, "CD_UP")),
                "name": _child_text(feature, "DS_NOMBRE"),
                "municipality_name": _child_text(feature, "DS_MUNICIPIO"),
                "rings": _rings_from_feature(feature),
            }
        )
    return forests
