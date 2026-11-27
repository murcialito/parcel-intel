"""Generador de las fixtures SINTÉTICAS de Catastro de `tests/fixtures/catastro/`.

Historia #45 (ADR 0033). Las fixtures se generan con plantillas por tipo de
respuesta (Consulta_CPMRC, WFS `cp:CadastralParcel`, WFS `bu:Building` y
GetCapabilities) que copian la ESTRUCTURA del esquema real, nunca sus datos:

- referencias inventadas con provincia `99` (no existe) y, en urbanas, hoja `ZZ`
  (no es una cuadrícula válida);
- geometrías inventadas: de lo real solo se conserva la envolvente de las tres
  parcelas que otros tests cruzan con respuestas reales de otras fuentes; dentro
  de ella la parcela es un rombo con vértices en los puntos medios de los lados.

Determinista: sin `random`, sin reloj y sin red. Solo stdlib y sin importar
`parcel_intel`, para no generar los datos con el mismo parser que los comprueba.

Uso:

    uv run python -m tests.fixtures.generate_catastro            # escribe
    uv run python -m tests.fixtures.generate_catastro --check    # compara, no escribe

`--destino <dir>` cambia el directorio (por defecto `tests/fixtures/catastro/`).
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

Point = tuple[float, float]
Ring = tuple[Point, ...]  # cerrado: primer punto == último
Envelope = tuple[float, float, float, float]  # (minx, miny, maxx, maxy)

FIXTURES_DIR = Path(__file__).parent / "catastro"
README_NAME = "README.md"

HEADER_COMMENT = (
    "<!-- FIXTURE SINTÉTICA generada por tests/fixtures/generate_catastro.py (historia #45). "
    "No es una respuesta de Catastro ni cartografía catastral. -->"
)

_TIMESTAMP = "2026-11-25T00:00:00"
_BEGIN_LIFESPAN = "2010-01-01T00:00:00"
_SRS_CP = "http://www.opengis.net/def/crs/EPSG/0/25830"
_SRS_BU = "urn:ogc:def:crs:EPSG::25830"
_WFS_PARCEL_URL = "https://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx"
_WFS_BUILDING_URL = "https://ovc.catastro.meh.es/INSPIRE/wfsBU.aspx"


# --- Tipos -----------------------------------------------------------------


@dataclass(frozen=True)
class SyntheticSurface:
    exterior: Ring
    interiors: tuple[Ring, ...] = ()


@dataclass(frozen=True)
class SyntheticParcel:
    reference: str  # 14 caracteres, empieza por "99"
    area_m2: int  # cp:areaValue declarado
    surfaces: tuple[SyntheticSurface, ...]  # 1 surfaceMember por superficie


@dataclass(frozen=True)
class SyntheticBuilding:
    reference: str
    area_m2: int  # bu-ext2d:officialArea/value
    construction_year: int  # bu-core2d:beginning = f"{year}-01-01T00:00:00"
    rings: tuple[Ring, ...]  # 1 PolygonPatch por anillo


# --- Geometría ---------------------------------------------------------------


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _round2(value: float) -> float:
    return float(_fmt(value))


def diamond(envelope: Envelope) -> Ring:
    """Rombo con vértices en los puntos medios de los lados de la envolvente.

    Conserva la envolvente exacta: sus extremos son los lados de la envolvente.
    Orden B (abajo), R, T, L, B.
    """
    minx, miny, maxx, maxy = envelope
    cx = _round2((minx + maxx) / 2)
    cy = _round2((miny + maxy) / 2)
    return ((cx, miny), (maxx, cy), (cx, maxy), (minx, cy), (cx, miny))


def rectangle(minx: float, miny: float, maxx: float, maxy: float) -> Ring:
    """Rectángulo en sentido antihorario, cerrado."""
    return ((minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy), (minx, miny))


def _centered_rectangle(cx: float, cy: float, width: float, height: float) -> Ring:
    return rectangle(cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)


def _envelope_of(rings: Sequence[Ring]) -> Envelope:
    xs = [x for ring in rings for x, _ in ring]
    ys = [y for ring in rings for _, y in ring]
    return (min(xs), min(ys), max(xs), max(ys))


def _center_of(envelope: Envelope) -> Point:
    minx, miny, maxx, maxy = envelope
    return (_round2((minx + maxx) / 2), _round2((miny + maxy) / 2))


def _pos_list(ring: Ring) -> str:
    return " ".join(f"{_fmt(x)} {_fmt(y)}" for x, y in ring)


def _diamond_area(envelope: Envelope) -> int:
    minx, miny, maxx, maxy = envelope
    return round((maxx - minx) * (maxy - miny) / 2)


def _rectangle_area(ring: Ring) -> float:
    minx, miny, maxx, maxy = _envelope_of((ring,))
    return (maxx - minx) * (maxy - miny)


# --- Plantillas: Consulta_CPMRC ---------------------------------------------

_CPMRC_ROOT = (
    '<consulta_coordenadas xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xmlns="http://www.catastro.meh.es/">'
)


def cpmrc_found(reference: str, x: float, y: float, ldt: str) -> bytes:
    """Respuesta de `Consulta_CPMRC` con el centroide de una referencia (14 caracteres)."""
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        HEADER_COMMENT,
        _CPMRC_ROOT,
        "  <control>",
        "    <cucoor>1</cucoor>",
        "    <cuerr>0</cuerr>",
        "  </control>",
        "  <coordenadas>",
        "    <coord>",
        "      <pc>",
        f"        <pc1>{reference[:7]}</pc1>",
        f"        <pc2>{reference[7:]}</pc2>",
        "      </pc>",
        "      <geo>",
        f"        <xcen>{_fmt(x)}</xcen>",
        f"        <ycen>{_fmt(y)}</ycen>",
        "        <srs>EPSG:25830</srs>",
        "      </geo>",
        f"      <ldt>{ldt}</ldt>",
        "    </coord>",
        "  </coordenadas>",
        "</consulta_coordenadas>",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def cpmrc_not_found() -> bytes:
    """Respuesta de `Consulta_CPMRC` para una referencia bien formada e inexistente."""
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        HEADER_COMMENT,
        _CPMRC_ROOT,
        "  <control>",
        "    <cucoor>0</cucoor>",
        "    <cuerr>1</cuerr>",
        "  </control>",
        "  <lerr>",
        "    <err>",
        "      <cod>62</cod>",
        "      <des>NO EXISTE EL INMUEBLE</des>",
        "    </err>",
        "  </lerr>",
        "</consulta_coordenadas>",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


# --- Plantillas: WFS cp:CadastralParcel -------------------------------------

_CP_ROOT_ATTRS = (
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xmlns:gml="http://www.opengis.net/gml/3.2" '
    'xmlns:xlink="http://www.w3.org/1999/xlink" '
    'xmlns:cp="http://inspire.ec.europa.eu/schemas/cp/4.0" '
    'xmlns:gmd="http://www.isotc211.org/2005/gmd" '
    'xsi:schemaLocation="http://www.opengis.net/wfs/2.0 '
    "http://schemas.opengis.net/wfs/2.0/wfs.xsd "
    "http://inspire.ec.europa.eu/schemas/cp/4.0 "
    'http://inspire.ec.europa.eu/schemas/cp/4.0/CadastralParcels.xsd" '
    'xmlns="http://www.opengis.net/wfs/2.0"'
)


def _cp_label(reference: str) -> str:
    # Rústica (letra en la posición 6): número de parcela; urbana: dígitos de la parcela.
    return reference[9:14] if reference[5].isalpha() else reference[5:7]


def _linear_ring(tag: str, ring: Ring, indent: str) -> list[str]:
    return [
        f"{indent}<gml:{tag}>",
        f"{indent}    <gml:LinearRing>",
        f'{indent}      <gml:posList srsDimension="2" count="{len(ring)}">'
        f"{_pos_list(ring)}</gml:posList>",
        f"{indent}    </gml:LinearRing>",
        f"{indent}</gml:{tag}>",
    ]


def _cp_member(parcel: SyntheticParcel) -> list[str]:
    ref = parcel.reference
    gml_id = f"ES.SDGC.CP.{ref}"
    rings = [s.exterior for s in parcel.surfaces]
    ref_x, ref_y = _center_of(_envelope_of(rings))
    lines = [
        "  <member>",
        f'    <cp:CadastralParcel gml:id="{gml_id}">',
        f'      <cp:areaValue uom="m2">{parcel.area_m2}</cp:areaValue>',
        f"      <cp:beginLifespanVersion>{_BEGIN_LIFESPAN}</cp:beginLifespanVersion>",
        '      <cp:endLifespanVersion xsi:nil="true" '
        'nilReason="http://inspire.ec.europa.eu/codelist/VoidReasonValue/Unpopulated">'
        "</cp:endLifespanVersion>",
        "      <cp:geometry>",
        f'        <gml:MultiSurface gml:id="MultiSurface_{gml_id}" srsName="{_SRS_CP}">',
    ]
    for index, surface in enumerate(parcel.surfaces, start=1):
        lines += [
            "          <gml:surfaceMember>",
            f'            <gml:Surface gml:id="Surface_{gml_id}.{index}" srsName="{_SRS_CP}">',
            "              <gml:patches>",
            "                <gml:PolygonPatch>",
        ]
        lines += _linear_ring("exterior", surface.exterior, "                ")
        for interior in surface.interiors:
            lines += _linear_ring("interior", interior, "                ")
        lines += [
            "                </gml:PolygonPatch>",
            "              </gml:patches>",
            "            </gml:Surface>",
            "          </gml:surfaceMember>",
        ]
    lines += [
        "        </gml:MultiSurface>",
        "      </cp:geometry>",
        "      <cp:inspireId>",
        '        <Identifier xmlns="http://inspire.ec.europa.eu/schemas/base/3.3">',
        f"          <localId>{ref}</localId>",
        "          <namespace>ES.SDGC.CP</namespace>",
        "        </Identifier>",
        "      </cp:inspireId>",
        f"      <cp:label>{_cp_label(ref)}</cp:label>",
        f"      <cp:nationalCadastralReference>{ref}</cp:nationalCadastralReference>",
        "      <cp:referencePoint>",
        f'        <gml:Point gml:id="ReferencePoint_{gml_id}" srsName="{_SRS_CP}">',
        f"          <gml:pos>{_fmt(ref_x)} {_fmt(ref_y)}</gml:pos>",
        "        </gml:Point>",
        "      </cp:referencePoint>",
        "    </cp:CadastralParcel>",
        "  </member>",
    ]
    return lines


def wfs_cp_collection(parcels: Sequence[SyntheticParcel]) -> bytes:
    """`GetFeature` de `cp:CadastralParcel` (WFS 2.0, GML 3.2, EPSG:25830)."""
    n = len(parcels)
    lines = [
        '<?xml version="1.0" encoding="ISO-8859-1"?>',
        HEADER_COMMENT,
        f'<FeatureCollection {_CP_ROOT_ATTRS} timeStamp="{_TIMESTAMP}" '
        f'numberMatched="{n}" numberReturned="{n}">',
    ]
    for parcel in parcels:
        lines += _cp_member(parcel)
    lines.append("</FeatureCollection>")
    return ("\n".join(lines) + "\n").encode("latin-1")


# --- Plantillas: WFS bu:Building --------------------------------------------

_BU_NAMESPACES = (
    'xmlns:ad="urn:x-inspire:specification:gmlas:Addresses:3.0" '
    'xmlns:base="urn:x-inspire:specification:gmlas:BaseTypes:3.2" '
    'xmlns:bu-base="http://inspire.jrc.ec.europa.eu/schemas/bu-base/3.0" '
    'xmlns:bu-core2d="http://inspire.jrc.ec.europa.eu/schemas/bu-core2d/2.0" '
    'xmlns:bu-ext2d="http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0" '
    'xmlns:cp="urn:x-inspire:specification:gmlas:CadastralParcels:3.0" '
    'xmlns:el-bas="http://inspire.jrc.ec.europa.eu/schemas/el-bas/2.0" '
    'xmlns:el-cov="http://inspire.jrc.ec.europa.eu/schemas/el-cov/2.0" '
    'xmlns:el-tin="http://inspire.jrc.ec.europa.eu/schemas/el-tin/2.0" '
    'xmlns:el-vec="http://inspire.jrc.ec.europa.eu/schemas/el-vec/2.0" '
    'xmlns:gco="http://www.isotc211.org/2005/gco" '
    'xmlns:gmd="http://www.isotc211.org/2005/gmd" '
    'xmlns:gml="http://www.opengis.net/gml/3.2" '
    'xmlns:gmlcov="http://www.opengis.net/gmlcov/1.0" '
    'xmlns:gn="urn:x-inspire:specification:gmlas:GeographicalNames:3.0" '
    'xmlns:gsr="http://www.isotc211.org/2005/gsr" '
    'xmlns:gss="http://www.isotc211.org/2005/gss" '
    'xmlns:gts="http://www.isotc211.org/2005/gts" '
    'xmlns:swe="http://www.opengis.net/swe/2.0" '
    'xmlns:xlink="http://www.w3.org/1999/xlink" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xsi:schemaLocation="http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0 '
    'http://inspire.ec.europa.eu/draft-schemas/bu-ext2d/2.0/BuildingExtended2D.xsd"'
)


def _bu_member(building: SyntheticBuilding) -> list[str]:
    ref = building.reference
    gml_id = f"ES.SDGC.BU.{ref}"
    minx, miny, maxx, maxy = _envelope_of(building.rings)
    lines = [
        "  <gml:featureMember>",
        f'    <bu-ext2d:Building gml:id="{gml_id}">',
        "    <gml:boundedBy>",
        f'      <gml:Envelope srsName="{_SRS_BU}">',
        f"         <gml:lowerCorner>{_fmt(minx)} {_fmt(miny)}</gml:lowerCorner>",
        f"         <gml:upperCorner>{_fmt(maxx)} {_fmt(maxy)}</gml:upperCorner>",
        "      </gml:Envelope>",
        "    </gml:boundedBy>",
        f"      <bu-core2d:beginLifespanVersion>{_BEGIN_LIFESPAN}</bu-core2d:beginLifespanVersion>",
        "      <bu-core2d:conditionOfConstruction>functional</bu-core2d:conditionOfConstruction>",
        "      <bu-core2d:dateOfConstruction>",
        "        <bu-core2d:DateOfEvent>",
        f"          <bu-core2d:beginning>{building.construction_year}-01-01T00:00:00"
        "</bu-core2d:beginning>",
        "        </bu-core2d:DateOfEvent>",
        "      </bu-core2d:dateOfConstruction>",
        '      <bu-core2d:endLifespanVersion xsi:nil="true" nilReason="other:unpopulated">'
        "</bu-core2d:endLifespanVersion>",
        "      <bu-core2d:inspireId>",
        "        <base:Identifier>",
        f"          <base:localId>{ref}</base:localId>",
        "          <base:namespace>ES.SDGC.BU</base:namespace>",
        "        </base:Identifier>",
        "      </bu-core2d:inspireId>",
        "      <bu-ext2d:geometry>",
        "       <bu-core2d:BuildingGeometry>",
        "        <bu-core2d:geometry>",
        f'         <gml:Surface gml:id="Surface_{gml_id}" srsName="{_SRS_BU}">',
        "           <gml:patches>",
    ]
    for ring in building.rings:
        lines.append("                <gml:PolygonPatch>")
        lines += _linear_ring("exterior", ring, "                ")
        lines.append("                </gml:PolygonPatch>")
    lines += [
        "              </gml:patches>",
        "            </gml:Surface>",
        "        </bu-core2d:geometry>",
        '        <bu-core2d:horizontalGeometryEstimatedAccuracy uom="m">0.1'
        "</bu-core2d:horizontalGeometryEstimatedAccuracy>",
        "        <bu-core2d:horizontalGeometryReference>footPrint"
        "</bu-core2d:horizontalGeometryReference>",
        "        <bu-core2d:referenceGeometry>true</bu-core2d:referenceGeometry>",
        "       </bu-core2d:BuildingGeometry>",
        "      </bu-ext2d:geometry>",
        "      <bu-ext2d:currentUse>1_residential</bu-ext2d:currentUse>",
        "      <bu-ext2d:numberOfBuildingUnits>1</bu-ext2d:numberOfBuildingUnits>",
        "      <bu-ext2d:numberOfDwellings>1</bu-ext2d:numberOfDwellings>",
        "      <bu-ext2d:officialArea>",
        "         <bu-ext2d:OfficialArea>",
        "          <bu-ext2d:officialAreaReference>grossFloorArea</bu-ext2d:officialAreaReference>",
        f'          <bu-ext2d:value uom="m2">{building.area_m2}</bu-ext2d:value>',
        "         </bu-ext2d:OfficialArea>",
        "      </bu-ext2d:officialArea>",
        "    </bu-ext2d:Building>",
        "  </gml:featureMember>",
    ]
    return lines


def wfs_bu_collection(buildings: Sequence[SyntheticBuilding]) -> bytes:
    """`GetFeature` de `bu:Building` (INSPIRE Buildings 2D extendido, EPSG:25830)."""
    lines = [
        '<?xml version="1.0" encoding="ISO-8859-1"?>',
        HEADER_COMMENT,
        f'<gml:FeatureCollection gml:id="ES.SDGC.BU" {_BU_NAMESPACES}>',
    ]
    for building in buildings:
        lines += _bu_member(building)
    lines.append("</gml:FeatureCollection>")
    return ("\n".join(lines) + "\n").encode("latin-1")


# --- Plantillas: GetCapabilities --------------------------------------------


def _capabilities(endpoint: str, feature_type: list[str]) -> bytes:
    operations: list[str] = []
    for name in ("GetCapabilities", "DescribeFeatureType", "GetFeature"):
        operations += [
            f'    <ows:Operation name="{name}">',
            "      <ows:DCP>",
            "        <ows:HTTP>",
            f'          <ows:Get xlink:type="simple" xlink:href="{endpoint}?"/>',
            "        </ows:HTTP>",
            "      </ows:DCP>",
            "    </ows:Operation>",
        ]
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        HEADER_COMMENT,
        '<WFS_Capabilities version="2.0.0" '
        'xmlns="http://www.opengis.net/wfs/2.0" '
        'xmlns:ows="http://www.opengis.net/ows/1.1" '
        'xmlns:gml="http://www.opengis.net/gml/3.2" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:schemaLocation="http://www.opengis.net/wfs/2.0 '
        'http://schemas.opengis.net/wfs/2.0/wfs.xsd">',
        "  <ows:ServiceIdentification>",
        "    <ows:Title>Servicio WFS sintético para tests</ows:Title>",
        "    <ows:ServiceType>WFS</ows:ServiceType>",
        "    <ows:ServiceTypeVersion>2.0.0</ows:ServiceTypeVersion>",
        "  </ows:ServiceIdentification>",
        "  <ows:OperationsMetadata>",
        *operations,
        "  </ows:OperationsMetadata>",
        "  <FeatureTypeList>",
        *feature_type,
        "  </FeatureTypeList>",
        "</WFS_Capabilities>",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def wfs_cp_capabilities() -> bytes:
    return _capabilities(
        _WFS_PARCEL_URL,
        [
            '    <FeatureType xmlns:cp="http://inspire.ec.europa.eu/schemas/cp/4.0">',
            "      <Name>cp:CadastralParcel</Name>",
            "      <Title>Parcelas sintéticas</Title>",
            "      <DefaultCRS>urn:ogc:def:crs:EPSG::4326</DefaultCRS>",
            "      <OtherCRS>urn:ogc:def:crs:EPSG::25830</OtherCRS>",
            "    </FeatureType>",
        ],
    )


def wfs_bu_capabilities() -> bytes:
    return _capabilities(
        _WFS_BUILDING_URL,
        [
            '    <FeatureType xmlns:bu="urn:x-inspire:specification:gmlas:Buildings:3.0">',
            "      <Name>bu:Building</Name>",
            "      <Title>Edificios sintéticos</Title>",
            "      <DefaultCRS>urn:ogc:def:crs:EPSG::25830</DefaultCRS>",
            "    </FeatureType>",
        ],
    )


# --- Datos sintéticos (tabla cerrada del diseño de la historia #45) ---------

# Envolventes conservadas: otras fixtures reales (IDEM, DPH, vías pecuarias,
# Red Natura, inundación, PNOA, Sentinel-2) se grabaron con bbox derivados de ellas.
ENVELOPE_COLMENAR_RUSTICA: Envelope = (467550.15, 4442011.35, 467614.92, 4442037.40)
ENVELOPE_VILLACONEJOS_RUSTICA: Envelope = (454555.78, 4441394.86, 454825.45, 4441582.42)
ENVELOPE_PARCELA_CON_EDIFICIOS: Envelope = (457153.87, 4436018.27, 457183.48, 4436055.23)

REF_COLMENAR_RUSTICA = "99043A90100001"
REF_COLMENAR_RUSTICA_20 = "99043A901000010000ZZ"
REF_VILLACONEJOS_RUSTICA = "99170A90100001"
REF_VILLACONEJOS_RUSTICA_20 = "99170A901000010000ZZ"
REF_COLMENAR_BBOX_DENSO = "99043A93700001"
REF_PARCELA_CON_EDIFICIOS = "9900105ZZ0000S"
REF_EDIFICIO_FUERA_DEL_ROMBO = "9900108ZZ0000S"
REF_NO_ENCONTRADA = "99043A99999999"

_DENSE_CENTER: Point = (460000.00, 4440000.00)
_DENSE_CELL_M = 30.0
_DENSE_SIDE_M = 20.0
_DENSE_GRID = 11


def _diamond_parcel(reference: str, envelope: Envelope) -> SyntheticParcel:
    return SyntheticParcel(
        reference=reference,
        area_m2=_diamond_area(envelope),
        surfaces=(SyntheticSurface(exterior=diamond(envelope)),),
    )


def _rectangle_parcel(reference: str, ring: Ring) -> SyntheticParcel:
    return SyntheticParcel(
        reference=reference,
        area_m2=round(_rectangle_area(ring)),
        surfaces=(SyntheticSurface(exterior=ring),),
    )


def colmenar_rustica_parcels() -> tuple[SyntheticParcel, ...]:
    """Objetivo + 14 vecinas rectangulares (7 al norte y 7 al sur de la envolvente)."""
    neighbours: list[SyntheticParcel] = []
    for i in range(14):
        row_north = i < 7
        col = i % 7
        minx = 467500.00 + 45.0 * col
        miny = 4442045.00 if row_north else 4441970.00
        ring = rectangle(minx, miny, minx + 40.0, miny + 30.0)
        neighbours.append(_rectangle_parcel(f"99043A901000{i + 2:02d}", ring))
    target = _diamond_parcel(REF_COLMENAR_RUSTICA, ENVELOPE_COLMENAR_RUSTICA)
    return (target, *neighbours)


def villaconejos_rustica_parcels() -> tuple[SyntheticParcel, ...]:
    """3 vecinas al norte, el objetivo y 3 vecinas al sur; la `…02` tiene un hueco."""
    north: list[SyntheticParcel] = []
    south: list[SyntheticParcel] = []
    for i in range(6):
        ref = f"99170A901000{i + 2:02d}"
        minx = 454560.00 + 90.0 * (i % 3)
        miny = 4441590.00 if i < 3 else 4441320.00
        ring = rectangle(minx, miny, minx + 80.0, miny + 60.0)
        if i == 0:
            cx, cy = minx + 40.0, miny + 30.0
            hole = tuple(reversed(_centered_rectangle(cx, cy, 20.0, 20.0)))
            parcel = SyntheticParcel(
                reference=ref,
                area_m2=round(_rectangle_area(ring) - 400.0),
                surfaces=(SyntheticSurface(exterior=ring, interiors=(hole,)),),
            )
        else:
            parcel = _rectangle_parcel(ref, ring)
        (north if i < 3 else south).append(parcel)
    target = _diamond_parcel(REF_VILLACONEJOS_RUSTICA, ENVELOPE_VILLACONEJOS_RUSTICA)
    return (*north, target, *south)


def colmenar_bbox_denso_parcels() -> tuple[SyntheticParcel, ...]:
    """Rejilla 11×11 de celdas de 30 m: 120 cuadrados de 20 m y el objetivo de 2 superficies."""
    x0, y0 = _DENSE_CENTER
    half_grid = _DENSE_GRID // 2
    parcels: list[SyntheticParcel] = []
    sequence = 0
    for row in range(_DENSE_GRID):
        for col in range(_DENSE_GRID):
            cx = x0 + _DENSE_CELL_M * (col - half_grid)
            cy = y0 + _DENSE_CELL_M * (row - half_grid)
            if row == half_grid and col == half_grid:
                left = rectangle(cx - 10.0, cy - 10.0, cx - 2.0, cy + 10.0)
                right = rectangle(cx + 2.0, cy - 10.0, cx + 10.0, cy + 10.0)
                parcels.append(
                    SyntheticParcel(
                        reference=REF_COLMENAR_BBOX_DENSO,
                        area_m2=320,
                        surfaces=(SyntheticSurface(left), SyntheticSurface(right)),
                    )
                )
                continue
            sequence += 1
            ring = _centered_rectangle(cx, cy, _DENSE_SIDE_M, _DENSE_SIDE_M)
            parcels.append(_rectangle_parcel(f"99043A938{sequence:05d}", ring))
    return tuple(parcels)


# Rejilla 3×3 alrededor de la envolvente de la parcela con edificios: la celda
# central es el objetivo (NN=05) y las 8 de alrededor, vecinas fuera de la envolvente.
_EDIFICIOS_COLS = ((457120.00, 457150.00), (457155.00, 457182.00), (457187.00, 457217.00))
_EDIFICIOS_ROWS = ((4436058.00, 4436088.00), (4436020.00, 4436053.00), (4435985.00, 4436015.00))


def _edificios_cell(nn: int) -> Ring:
    row, col = divmod(nn - 1, 3)
    (minx, maxx), (miny, maxy) = _EDIFICIOS_COLS[col], _EDIFICIOS_ROWS[row]
    return rectangle(minx, miny, maxx, maxy)


def parcela_con_edificios_parcels() -> tuple[SyntheticParcel, ...]:
    """Objetivo `9900105ZZ0000S` + 8 vecinas rectangulares fuera de su envolvente."""
    parcels: list[SyntheticParcel] = []
    for nn in range(1, 10):
        ref = f"99001{nn:02d}ZZ0000S"
        if nn == 5:
            parcels.append(_diamond_parcel(ref, ENVELOPE_PARCELA_CON_EDIFICIOS))
        else:
            parcels.append(_rectangle_parcel(ref, _edificios_cell(nn)))
    return tuple(parcels)


def dense_bbox_buildings() -> tuple[SyntheticBuilding, ...]:
    """11 edificios: el de la parcela objetivo (3 cuerpos), uno dentro de la envolvente
    pero fuera del rombo y 9 en parcelas vecinas (uno con 2 cuerpos)."""
    cx, cy = (457168.675, 4436036.75)  # centro del rombo (semiejes 14.805 × 18.48)
    own = SyntheticBuilding(
        reference=REF_PARCELA_CON_EDIFICIOS,
        area_m2=96,
        construction_year=1975,
        rings=(
            _centered_rectangle(cx, cy, 8.0, 6.0),
            _centered_rectangle(cx, cy + 11.0, 2.0, 2.0),
            _centered_rectangle(cx, cy - 11.0, 2.0, 2.0),
        ),
    )
    outside_diamond = SyntheticBuilding(
        reference=REF_EDIFICIO_FUERA_DEL_ROMBO,
        area_m2=4,
        construction_year=1990,
        rings=(_centered_rectangle(457181.00, 4436052.50, 2.0, 2.0),),
    )
    neighbours: list[SyntheticBuilding] = []
    for index, nn in enumerate((1, 2, 3, 4, 6, 7, 9)):
        minx, miny, maxx, maxy = _envelope_of((_edificios_cell(nn),))
        bx, by = (minx + maxx) / 2, (miny + maxy) / 2
        rings: tuple[Ring, ...] = (_centered_rectangle(bx, by, 10.0, 8.0),)
        if nn == 3:
            rings = (
                _centered_rectangle(bx - 5.0, by, 8.0, 8.0),
                _centered_rectangle(bx + 7.0, by, 4.0, 4.0),
            )
        neighbours.append(
            SyntheticBuilding(
                reference=f"99001{nn:02d}ZZ0000S",
                area_m2=80 + 10 * index,
                construction_year=1960 + 5 * index,
                rings=rings,
            )
        )
    for nn, bx in ((10, 457230.00), (11, 457250.00)):
        neighbours.append(
            SyntheticBuilding(
                reference=f"99001{nn:02d}ZZ0000S",
                area_m2=60,
                construction_year=2001,
                rings=(_centered_rectangle(bx, 4436036.00, 8.0, 8.0),),
            )
        )
    return (own, outside_diamond, *neighbours)


# --- Plantillas: WFS cp:CadastralZoning (historia #217) -----------------------


@dataclass(frozen=True)
class SyntheticZone:
    reference: str  # zona, p. ej. "99043A040"; el parser no la lee
    label: str
    level: str  # "1stOrder" | "2ndOrder"
    surfaces: tuple[SyntheticSurface, ...]


def _cz_member(zone: SyntheticZone) -> list[str]:
    ref = zone.reference
    gml_id = f"ES.SDGC.CP.Z.{ref}"
    ref_x, ref_y = _center_of(_envelope_of([s.exterior for s in zone.surfaces]))
    lines = [
        "  <member>",
        f'    <cp:CadastralZoning gml:id="{gml_id}">',
        '      <cp:estimatedAccuracy uom="m">1</cp:estimatedAccuracy>',
        "      <cp:geometry>",
        f'        <gml:MultiSurface gml:id="MultiSurface_{gml_id}" srsName="{_SRS_CP}">',
    ]
    for index, surface in enumerate(zone.surfaces, start=1):
        lines += [
            "          <gml:surfaceMember>",
            f'            <gml:Surface gml:id="Surface_{gml_id}.{index}" srsName="{_SRS_CP}">',
            "              <gml:patches>",
            "                <gml:PolygonPatch>",
        ]
        lines += _linear_ring("exterior", surface.exterior, "                ")
        for interior in surface.interiors:
            lines += _linear_ring("interior", interior, "                ")
        lines += [
            "                </gml:PolygonPatch>",
            "              </gml:patches>",
            "            </gml:Surface>",
            "          </gml:surfaceMember>",
        ]
    lines += [
        "        </gml:MultiSurface>",
        "      </cp:geometry>",
        f"      <cp:label>{zone.label}</cp:label>",
        "      <cp:level "
        'xlink:href="http://inspire.ec.europa.eu/codelist/CadastralZoningLevelValue/'
        f'{zone.level}"></cp:level>',
        "      <cp:levelName>",
        '        <gmd:LocalisedCharacterString locale="esp">POLIGONO '
        "</gmd:LocalisedCharacterString>",
        "      </cp:levelName>",
        f"      <cp:nationalCadastalZoningReference>{ref}</cp:nationalCadastalZoningReference>",
        "      <cp:originalMapScaleDenominator>5000</cp:originalMapScaleDenominator>",
        "      <cp:referencePoint>",
        f'        <gml:Point gml:id="ReferencePoint_{gml_id}" srsName="{_SRS_CP}">',
        f"          <gml:pos>{_fmt(ref_x)} {_fmt(ref_y)}</gml:pos>",
        "        </gml:Point>",
        "      </cp:referencePoint>",
        "    </cp:CadastralZoning>",
        "  </member>",
    ]
    return lines


def wfs_cz_collection(zones: Sequence[SyntheticZone]) -> bytes:
    """`GetFeature` de `cp:CadastralZoning` (WFS 2.0, GML 3.2, EPSG:25830)."""
    n = len(zones)
    lines = [
        '<?xml version="1.0" encoding="ISO-8859-1"?>',
        HEADER_COMMENT,
        f'<FeatureCollection {_CP_ROOT_ATTRS} timeStamp="{_TIMESTAMP}" '
        f'numberMatched="{n}" numberReturned="{n}">',
    ]
    for zone in zones:
        lines += _cz_member(zone)
    lines.append("</FeatureCollection>")
    return ("\n".join(lines) + "\n").encode("latin-1")


ZONING_SHARED_LABEL = "901"
ZONING_SHARED_RING = rectangle(460000.0, 4436000.0, 460800.0, 4436700.0)
ZONING_ONLY_TILE_1_LABEL = "902"
ZONING_ONLY_TILE_2_LABEL = "903"


def zoning_tile_1_zones() -> tuple[SyntheticZone, ...]:
    """Primera tesela: un polígono compartido, uno con dos partes y el término (1stOrder)."""
    return (
        SyntheticZone(
            "99043A901",
            ZONING_SHARED_LABEL,
            "2ndOrder",
            (SyntheticSurface(ZONING_SHARED_RING),),
        ),
        SyntheticZone(
            "99043A902",
            ZONING_ONLY_TILE_1_LABEL,
            "2ndOrder",
            (
                SyntheticSurface(rectangle(459000.0, 4435000.0, 459300.0, 4435300.0)),
                SyntheticSurface(rectangle(459400.0, 4435000.0, 459700.0, 4435300.0)),
            ),
        ),
        SyntheticZone(
            "99043",
            "99043",
            "1stOrder",
            (SyntheticSurface(rectangle(458000.0, 4434000.0, 462000.0, 4438000.0)),),
        ),
    )


def zoning_tile_2_zones() -> tuple[SyntheticZone, ...]:
    """Segunda tesela: el mismo polígono compartido y uno nuevo."""
    return (
        SyntheticZone(
            "99043A901",
            ZONING_SHARED_LABEL,
            "2ndOrder",
            (SyntheticSurface(ZONING_SHARED_RING),),
        ),
        SyntheticZone(
            "99043A903",
            ZONING_ONLY_TILE_2_LABEL,
            "2ndOrder",
            (SyntheticSurface(rectangle(460900.0, 4436000.0, 461200.0, 4436300.0)),),
        ),
    )


def _zoning_limit_exception() -> bytes:
    """`ExceptionReport` con el texto en español que Catastro da a `CadastralZoning` cuando el
    bbox supera el límite (comprobado el 2026-11-27 contra el servicio real)."""
    lines = [
        '<?xml version=\'1.0\' encoding="ISO-8859-1" standalone="no"?>',
        HEADER_COMMENT,
        '<ExceptionReport xmlns="http://www.opengis.net/ows/1.1" version="2.0.0">',
        '<Exception exceptionCode="OperationProcessingFailed">',
        "<ExceptionText><![CDATA[Area de la extensión fuera de los límites]]></ExceptionText>",
        "</Exception>",
        "</ExceptionReport>",
    ]
    return ("\n".join(lines) + "\n").encode("latin-1")


def _cpmrc_of(parcel: SyntheticParcel, ldt: str) -> bytes:
    x, y = _center_of(_envelope_of([s.exterior for s in parcel.surfaces]))
    return cpmrc_found(parcel.reference, x, y, ldt)


def _target(parcels: Sequence[SyntheticParcel], reference: str) -> SyntheticParcel:
    return next(p for p in parcels if p.reference == reference)


FIXTURES: Mapping[str, Callable[[], bytes]] = {
    "cpmrc_colmenar_14char.xml": lambda: _cpmrc_of(
        _target(colmenar_rustica_parcels(), REF_COLMENAR_RUSTICA),
        "Polígono 901 Parcela 1 PARAJE SINTÉTICO. MUNICIPIO SINTÉTICO (PROVINCIA 99)",
    ),
    "cpmrc_villaconejos_14char.xml": lambda: _cpmrc_of(
        _target(villaconejos_rustica_parcels(), REF_VILLACONEJOS_RUSTICA),
        "Polígono 901 Parcela 1 PARAJE SINTÉTICO. MUNICIPIO SINTÉTICO (PROVINCIA 99)",
    ),
    "cpmrc_colmenar_urbano_14char.xml": lambda: _cpmrc_of(
        _target(colmenar_bbox_denso_parcels(), REF_COLMENAR_BBOX_DENSO),
        "Polígono 937 Parcela 1 PARAJE SINTÉTICO. MUNICIPIO SINTÉTICO (PROVINCIA 99)",
    ),
    "cpmrc_colmenar_edificio.xml": lambda: _cpmrc_of(
        _target(parcela_con_edificios_parcels(), REF_PARCELA_CON_EDIFICIOS),
        "CL SINTÉTICA 5 MUNICIPIO SINTÉTICO (PROVINCIA 99)",
    ),
    "cpmrc_no_encontrada.xml": cpmrc_not_found,
    "wfsCP_colmenar_rustica_por_centroide.xml": lambda: wfs_cp_collection(
        colmenar_rustica_parcels()
    ),
    "wfsCP_villaconejos_rustica_por_centroide.xml": lambda: wfs_cp_collection(
        villaconejos_rustica_parcels()
    ),
    "wfsCP_colmenar_bbox_denso.xml": lambda: wfs_cp_collection(colmenar_bbox_denso_parcels()),
    "wfsCP_colmenar_parcela_con_edificios.xml": lambda: wfs_cp_collection(
        parcela_con_edificios_parcels()
    ),
    "wfsBU_colmenar_dense_bbox.xml": lambda: wfs_bu_collection(dense_bbox_buildings()),
    "wfsBU_colmenar_urbano_por_centroide.xml": lambda: wfs_bu_collection(()),
    "wfsCP_zoning_tesela1.xml": lambda: wfs_cz_collection(zoning_tile_1_zones()),
    "wfsCP_zoning_tesela2.xml": lambda: wfs_cz_collection(zoning_tile_2_zones()),
    "wfsCP_zoning_limite.xml": lambda: _zoning_limit_exception(),
    "wfsCP_getcapabilities.xml": wfs_cp_capabilities,
    "wfsBU_getcapabilities.xml": wfs_bu_capabilities,
}


def build_all() -> dict[str, bytes]:
    """Contenido de cada fixture, por nombre de fichero."""
    return {name: build() for name, build in FIXTURES.items()}


def _differences(directory: Path, expected: Mapping[str, bytes]) -> list[str]:
    problems: list[str] = []
    for name, content in expected.items():
        path = directory / name
        if not path.exists():
            problems.append(f"falta {name}")
        elif path.read_bytes() != content:
            problems.append(f"difiere {name}")
    if directory.exists():
        for path in sorted(directory.iterdir()):
            if path.name not in expected and path.name != README_NAME:
                problems.append(f"sobra {path.name}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Escribe las fixtures; con `--check` solo compara y devuelve 1 si difieren."""
    args = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in args
    if check:
        args.remove("--check")
    directory = FIXTURES_DIR
    # Con el directorio por defecto se generan también las fixtures de `caminos/` (#46);
    # con `--destino` solo las de Catastro (las de caminos tienen su propio directorio).
    with_caminos = True
    if len(args) == 2 and args[0] == "--destino":
        directory = Path(args[1])
        with_caminos = False
        args = []
    if args:
        print(
            "uso: python -m tests.fixtures.generate_catastro [--check] [--destino <dir>]",
            file=sys.stderr,
        )
        return 2
    from tests.fixtures import generate_caminos  # import diferido: ese módulo importa este

    expected = build_all()
    if check:
        problems = _differences(directory, expected)
        if with_caminos:
            problems += generate_caminos.differences(generate_caminos.CAMINOS_DIR)
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in expected.items():
        (directory / name).write_bytes(content)
    if with_caminos:
        generate_caminos.generate(generate_caminos.CAMINOS_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
