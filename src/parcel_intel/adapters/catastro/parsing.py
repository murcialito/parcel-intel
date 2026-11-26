import xml.etree.ElementTree as ET
from typing import TypedDict

from parcel_intel.domain.geometry import Geometry, Ring
from parcel_intel.ports.errors import ParcelNotFoundError

_CATASTRO_NS = "http://www.catastro.meh.es/"
_GML_NS = "http://www.opengis.net/gml/3.2"
_CRS_25830 = 25830


class RawParcel(TypedDict):
    reference: str
    area_m2: float
    rings: tuple[Ring, ...]


class RawBuilding(TypedDict):
    reference: str
    area_m2: float
    construction_year: int | None
    rings: tuple[Ring, ...]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_cpmrc_centroid(xml_bytes: bytes, reference: str) -> tuple[float, float]:
    """Extrae el centroide (x, y) de una respuesta de `Consulta_CPMRC`.

    Lanza `ParcelNotFoundError` si el servicio responde con un error de
    control (`cuerr=1`), que es lo que devuelve para una referencia bien
    formada pero inexistente en el municipio consultado.
    """
    root = ET.fromstring(xml_bytes)
    ns = {"c": _CATASTRO_NS}
    error = root.find(".//c:lerr/c:err/c:des", ns)
    if error is not None:
        raise ParcelNotFoundError(reference)
    xcen = root.find(".//c:coord/c:geo/c:xcen", ns)
    ycen = root.find(".//c:coord/c:geo/c:ycen", ns)
    if xcen is None or ycen is None or xcen.text is None or ycen.text is None:
        raise ParcelNotFoundError(reference)
    return float(xcen.text), float(ycen.text)


def _rings_from_feature(feature: ET.Element) -> tuple[Ring, ...]:
    rings: list[Ring] = []
    for pos_list in feature.iter(f"{{{_GML_NS}}}posList"):
        if pos_list.text is None:
            continue
        values = [float(v) for v in pos_list.text.split()]
        points = tuple(zip(values[0::2], values[1::2], strict=True))
        rings.append(points)
    return tuple(rings)


def parse_wfs_parcels(xml_bytes: bytes) -> list[RawParcel]:
    """Parsea un `GetFeature` de `cp:CadastralParcel` a una lista de dicts planos."""
    root = ET.fromstring(xml_bytes)
    parcels: list[RawParcel] = []
    for feature in root.iter():
        if _local_name(feature.tag) != "CadastralParcel":
            continue
        ref_el = next(
            (
                child
                for child in feature.iter()
                if _local_name(child.tag) == "nationalCadastralReference"
            ),
            None,
        )
        area_el = next(
            (child for child in feature.iter() if _local_name(child.tag) == "areaValue"),
            None,
        )
        if ref_el is None or ref_el.text is None:
            continue
        parcels.append(
            {
                "reference": ref_el.text,
                "area_m2": float(area_el.text) if area_el is not None and area_el.text else 0.0,
                "rings": _rings_from_feature(feature),
            }
        )
    return parcels


def parse_wfs_buildings(xml_bytes: bytes) -> list[RawBuilding]:
    """Parsea un `GetFeature` de edificios (`bu-ext2d:Building`) a una lista de dicts planos."""
    root = ET.fromstring(xml_bytes)
    buildings: list[RawBuilding] = []
    for feature in root.iter():
        if _local_name(feature.tag) != "Building":
            continue
        gml_id = feature.get(f"{{{_GML_NS}}}id") or feature.get("id") or ""
        reference = gml_id.rsplit(".", 1)[-1] if gml_id else ""
        area_el = next(
            (child for child in feature.iter() if _local_name(child.tag) == "value"),
            None,
        )
        year_el = next(
            (child for child in feature.iter() if _local_name(child.tag) == "beginning"),
            None,
        )
        construction_year: int | None = None
        if year_el is not None and year_el.text:
            construction_year = int(year_el.text[:4])
        buildings.append(
            {
                "reference": reference,
                "area_m2": float(area_el.text) if area_el is not None and area_el.text else 0.0,
                "construction_year": construction_year,
                "rings": _rings_from_feature(feature),
            }
        )
    return buildings


def geometry_from_rings(rings: tuple[Ring, ...]) -> Geometry:
    return Geometry(rings=rings, srid=_CRS_25830)


class RawSubparcel(TypedDict):
    class_code: str
    description: str
    area_m2: float


class RawDnppp(TypedDict):
    paraje: str | None
    subparcels: tuple[RawSubparcel, ...]


def parse_dnppp(xml_bytes: bytes, reference: str) -> RawDnppp:
    """Extrae paraje y subparcelas (clase, descripción, superficie) de `Consulta_DNPPP`.

    Solo lee los datos de cultivo (`lspr/spr/dspr`) y el paraje (`npa`); no toca
    ningún dato de titularidad. Lanza `ParcelNotFoundError` si el servicio
    responde con un error de control (`lerr`).
    """
    root = ET.fromstring(xml_bytes)
    ns = {"c": _CATASTRO_NS}
    if root.find(".//c:lerr/c:err/c:des", ns) is not None:
        raise ParcelNotFoundError(reference)
    paraje_el = root.find(".//c:dt//c:npa", ns)
    paraje = paraje_el.text.strip() if paraje_el is not None and paraje_el.text else None
    subparcels: list[RawSubparcel] = []
    for dspr in root.iterfind(".//c:lspr/c:spr/c:dspr", ns):
        code = dspr.findtext("c:ccc", default="", namespaces=ns).strip()
        description = dspr.findtext("c:dcc", default="", namespaces=ns).strip()
        ssp = dspr.findtext("c:ssp", default="", namespaces=ns).strip()
        subparcels.append(
            {
                "class_code": code,
                "description": description,
                "area_m2": float(ssp) if ssp else 0.0,
            }
        )
    return {"paraje": paraje, "subparcels": tuple(subparcels)}
