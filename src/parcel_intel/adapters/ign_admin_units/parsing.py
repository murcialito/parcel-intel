import xml.etree.ElementTree as ET
from typing import TypedDict

_NS = {
    "wfs": "http://www.opengis.net/wfs/2.0",
    "gml": "http://www.opengis.net/gml/3.2",
    "au": "http://inspire.ec.europa.eu/schemas/au/4.0",
    "gn": "http://inspire.ec.europa.eu/schemas/gn/4.0",
}
_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
_FOURTH_ORDER = "4thOrder"


class AdministrativeUnitParseError(Exception):
    """El XML no es una respuesta WFS de unidades administrativas legible."""


class RawAdministrativeUnit(TypedDict):
    ine_code: str  # 5 últimos dígitos de `au:nationalCode`
    name: str
    level: str  # último segmento de `au:nationalLevel` (p. ej. "4thOrder")
    rings: list[list[tuple[float, float]]]  # (lat, lon), tal como vienen en EPSG:4258
    has_interior: bool


class ParsedAdministrativeUnits(TypedDict):
    number_matched: int | None
    units: list[RawAdministrativeUnit]


def _parse_pos_list(text: str) -> list[tuple[float, float]]:
    values = [float(v) for v in text.split()]
    if len(values) % 2 != 0 or len(values) < 6:
        raise AdministrativeUnitParseError("posList con un número de coordenadas inválido")
    return [(values[i], values[i + 1]) for i in range(0, len(values), 2)]


def parse_administrative_units(body: bytes) -> ParsedAdministrativeUnits:
    """Parsea todos los `au:AdministrativeUnit` de la respuesta, de cualquier
    nivel. El filtro por nivel y código es del adapter; `number_matched` se
    compara con `len(units)` (todas, no solo las filtradas)."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise AdministrativeUnitParseError(f"XML malformado: {exc}") from exc

    raw_matched = root.get("numberMatched")
    number_matched = int(raw_matched) if raw_matched is not None and raw_matched.isdigit() else None

    units: list[RawAdministrativeUnit] = []
    for member in root.findall("wfs:member/au:AdministrativeUnit", _NS):
        code = member.findtext("au:nationalCode", namespaces=_NS)
        level_el = member.find("au:nationalLevel", _NS)
        name = member.findtext(
            "au:name/gn:GeographicalName/gn:spelling/gn:SpellingOfName/gn:text", namespaces=_NS
        )
        if code is None or level_el is None or name is None:
            raise AdministrativeUnitParseError("au:AdministrativeUnit sin código, nivel o nombre")
        rings = [
            _parse_pos_list(pos.text or "")
            for pos in member.findall(
                "au:geometry/gml:MultiSurface/gml:surfaceMember/gml:Polygon/gml:exterior/"
                "gml:LinearRing/gml:posList",
                _NS,
            )
        ]
        units.append(
            {
                "ine_code": code.strip()[-5:],
                "name": name.strip(),
                "level": level_el.get(_XLINK_HREF, "").rsplit("/", 1)[-1],
                "rings": rings,
                "has_interior": member.find(".//gml:interior", _NS) is not None,
            }
        )
    return {"number_matched": number_matched, "units": units}


def is_municipality(unit: RawAdministrativeUnit) -> bool:
    return unit["level"] == _FOURTH_ORDER
