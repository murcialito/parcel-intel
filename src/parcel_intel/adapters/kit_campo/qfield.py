"""Proyecto de campo de QField con la biblioteca estándar (historia #222).

GeoPackage con `sqlite3` (en memoria, `serialize()`), `.qgs` con `xml.etree`, ZIP con `zipfile`.
Sin QGIS ni GDAL, sin red y sin reloj (la fecha llega en `MunicipalKit`). Determinista byte a byte.
Ningún dato de titularidad: solo salen los tramos ya filtrados por la lista blanca de #213.
"""

import io
import sqlite3
import struct
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Sequence

from parcel_intel.domain.kit_campo import (
    INCIDENCIA_FORM,
    LAYER_TITLE,
    NOTE_MAX_LENGTH,
    KitGeometry,
    KitLayer,
    MunicipalKit,
)

INCIDENCES_TABLE = "incidencias"
INCIDENCES_TITLE = "Incidencias de campo"
GPKG_APPLICATION_ID = 0x47504B47  # «GPKG»
GPKG_USER_VERSION = 10300
_POINT, _LINESTRING, _POLYGON, _MULTILINESTRING, _MULTIPOLYGON = 1, 2, 3, 5, 6
_GEOMETRY_NAMES = {_MULTILINESTRING: "MULTILINESTRING", _MULTIPOLYGON: "MULTIPOLYGON"}
_QGIS_GEOMETRY = {
    "MULTILINESTRING": "Line",
    "MULTIPOLYGON": "Polygon",
    "POINT": "Point",
    "GEOMETRY": "Unknown",
}
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def project_base(municipality_code: str) -> str:
    return f"paso_comun_{municipality_code}"


def layer_abstract(layer: KitLayer) -> str:
    return (
        f"Fuente {layer.source}; licencia {layer.license}; "
        f"atribución: {' | '.join(layer.attribution)}; aviso: {layer.notice}"
    )


def rights_text(kit: MunicipalKit) -> str:
    return " || ".join(
        f"{LAYER_TITLE[layer.layer]}: licencia {layer.license}; "
        f"atribución: {' | '.join(layer.attribution)}"
        for layer in kit.layers
    )


# --- GeoPackage ---------------------------------------------------------------------------


def _wkb_line(points: Sequence[tuple[float, float]]) -> bytes:
    body = struct.pack("<BII", 1, _LINESTRING, len(points))
    return body + b"".join(struct.pack("<dd", lon, lat) for lon, lat in points)


def _wkb_polygon(rings: Sequence[Sequence[tuple[float, float]]]) -> bytes:
    body = struct.pack("<BII", 1, _POLYGON, len(rings))
    for ring in rings:
        body += struct.pack("<I", len(ring)) + b"".join(
            struct.pack("<dd", lon, lat) for lon, lat in ring
        )
    return body


def geometry_kind(geometry: KitGeometry) -> int:
    if geometry.lines and not geometry.polygons:
        return _MULTILINESTRING
    if geometry.polygons and not geometry.lines:
        return _MULTIPOLYGON
    raise ValueError("geometría vacía o mezclada")


def gpkg_geometry(geometry: KitGeometry) -> bytes:
    """Blob GeoPackage (cabecera `GP`, EPSG:4326, sin envolvente) con WKB multi-parte."""
    kind = geometry_kind(geometry)
    if kind == _MULTILINESTRING:
        parts = [_wkb_line(line) for line in geometry.lines]
    else:
        parts = [_wkb_polygon(polygon) for polygon in geometry.polygons]
    wkb = struct.pack("<BII", 1, kind, len(parts)) + b"".join(parts)
    return b"GP" + struct.pack("<BBi", 0, 1, 4326) + wkb


def _gpkg_point(lon: float, lat: float) -> bytes:
    return b"GP" + struct.pack("<BBi", 0, 1, 4326) + struct.pack("<BIdd", 1, _POINT, lon, lat)


def _bbox(geometries: Sequence[KitGeometry]) -> tuple[float, float, float, float] | None:
    points = [point for geometry in geometries for line in geometry.lines for point in line] + [
        point
        for geometry in geometries
        for polygon in geometry.polygons
        for ring in polygon
        for point in ring
    ]
    if not points:
        return None
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    return (min(lons), min(lats), max(lons), max(lats))


def build_geopackage(kit: MunicipalKit) -> bytes:
    stamp = f"{kit.generated_on.isoformat()}T00:00:00.000Z"
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(f"PRAGMA application_id = {GPKG_APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version = {GPKG_USER_VERSION}")
        connection.executescript(
            """
            CREATE TABLE gpkg_spatial_ref_sys (
              srs_name TEXT NOT NULL, srs_id INTEGER PRIMARY KEY, organization TEXT NOT NULL,
              organization_coordsys_id INTEGER NOT NULL, definition TEXT NOT NULL,
              description TEXT);
            CREATE TABLE gpkg_contents (
              table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL,
              identifier TEXT UNIQUE, description TEXT DEFAULT '',
              last_change DATETIME NOT NULL DEFAULT '1970-01-01T00:00:00.000Z',
              min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE, srs_id INTEGER,
              CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id)
                REFERENCES gpkg_spatial_ref_sys(srs_id));
            CREATE TABLE gpkg_geometry_columns (
              table_name TEXT NOT NULL, column_name TEXT NOT NULL,
              geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL,
              z TINYINT NOT NULL, m TINYINT NOT NULL,
              CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),
              CONSTRAINT fk_gc_tn FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),
              CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id));
            """
        )
        connection.executemany(
            "INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)",
            [
                ("Undefined cartesian SRS", -1, "NONE", -1, "undefined", None),
                ("Undefined geographic SRS", 0, "NONE", 0, "undefined", None),
                (
                    "WGS 84 geodetic",
                    4326,
                    "EPSG",
                    4326,
                    'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
                    'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]',
                    "longitud/latitud en grados",
                ),
            ],
        )
        for layer in kit.layers:
            _write_layer(connection, layer, stamp)
        _write_incidences(connection, stamp)
        connection.commit()
        return connection.serialize()
    finally:
        connection.close()


def _register(
    connection: sqlite3.Connection,
    table: str,
    title: str,
    description: str,
    geometry_type: str,
    bbox: tuple[float, float, float, float] | None,
    stamp: str,
) -> None:
    box = bbox or (None, None, None, None)
    connection.execute(
        "INSERT INTO gpkg_contents VALUES (?,?,?,?,?,?,?,?,?,?)",
        (table, "features", title, description, stamp, *box, 4326),
    )
    connection.execute(
        "INSERT INTO gpkg_geometry_columns VALUES (?,?,?,?,?,?)",
        (table, "geom", geometry_type, 4326, 0, 0),
    )


def _write_layer(connection: sqlite3.Connection, layer: KitLayer, stamp: str) -> None:
    table = layer.layer
    kinds = {geometry_kind(tramo.geometry) for tramo in layer.tramos}
    geometry_type = _GEOMETRY_NAMES[next(iter(kinds))] if len(kinds) == 1 else "GEOMETRY"
    connection.execute(
        f"CREATE TABLE {table} (fid INTEGER PRIMARY KEY AUTOINCREMENT, geom {geometry_type}, "
        "nombre TEXT, descripcion TEXT)"
    )
    connection.executemany(
        f"INSERT INTO {table} (geom, nombre, descripcion) VALUES (?,?,?)",
        [(gpkg_geometry(tramo.geometry), tramo.name, tramo.description) for tramo in layer.tramos],
    )
    _register(
        connection,
        table,
        LAYER_TITLE[layer.layer],
        layer_abstract(layer),
        geometry_type,
        _bbox([tramo.geometry for tramo in layer.tramos]),
        stamp,
    )


def _write_incidences(connection: sqlite3.Connection, stamp: str) -> None:
    connection.execute(
        f"CREATE TABLE {INCIDENCES_TABLE} (fid INTEGER PRIMARY KEY AUTOINCREMENT, geom POINT, "
        f"tipo TEXT, estado TEXT, fecha DATE, nota TEXT({NOTE_MAX_LENGTH}), foto TEXT)"
    )
    _register(
        connection,
        INCIDENCES_TABLE,
        INCIDENCES_TITLE,
        "Capa editable vacía: lo que anotes se queda en este dispositivo.",
        "POINT",
        None,
        stamp,
    )


# --- Proyecto .qgs ------------------------------------------------------------------------


def _value_map(options: Sequence[tuple[str, str]]) -> ET.Element:
    widget = ET.Element("editWidget", {"type": "ValueMap"})
    config = ET.SubElement(widget, "config")
    root = ET.SubElement(config, "Option", {"type": "Map"})
    listing = ET.SubElement(root, "Option", {"name": "map", "type": "List"})
    for label, value in options:
        item = ET.SubElement(listing, "Option", {"type": "Map"})
        ET.SubElement(item, "Option", {"name": label, "type": "QString", "value": value})
    return widget


def _option_map(entries: Sequence[tuple[str, str, str]]) -> ET.Element:
    widget = ET.Element("config")
    root = ET.SubElement(widget, "Option", {"type": "Map"})
    for name, kind, value in entries:
        ET.SubElement(root, "Option", {"name": name, "type": kind, "value": value})
    return widget


def _field(parent: ET.Element, name: str, widget: ET.Element) -> None:
    field = ET.SubElement(parent, "field", {"name": name, "configurationFlags": "None"})
    field.append(widget)


def _text_edit(multiline: bool = False) -> ET.Element:
    widget = ET.Element("editWidget", {"type": "TextEdit"})
    widget.append(
        _option_map(
            [
                ("IsMultiline", "bool", "true" if multiline else "false"),
                ("UseHtml", "bool", "false"),
            ]
        )
    )
    return widget


def _tramo_layer(projectlayers: ET.Element, layer: KitLayer, base: str, geometry: str) -> None:
    _maplayer(
        projectlayers,
        layer.layer,
        LAYER_TITLE[layer.layer],
        layer_abstract(layer),
        base,
        geometry,
        rights=f"licencia {layer.license}; atribución: {' | '.join(layer.attribution)}",
    )


def _maplayer(
    projectlayers: ET.Element,
    table: str,
    title: str,
    abstract: str,
    base: str,
    geometry: str,
    rights: str,
) -> ET.Element:
    maplayer = ET.SubElement(projectlayers, "maplayer", {"type": "vector", "geometry": geometry})
    ET.SubElement(maplayer, "id").text = table
    ET.SubElement(maplayer, "datasource").text = f"./{base}.gpkg|layername={table}"
    ET.SubElement(maplayer, "layername").text = title
    ET.SubElement(maplayer, "title").text = title
    ET.SubElement(maplayer, "abstract").text = abstract
    ET.SubElement(maplayer, "provider").text = "ogr"
    srs = ET.SubElement(maplayer, "srs")
    ET.SubElement(ET.SubElement(srs, "spatialrefsys"), "authid").text = "EPSG:4326"
    metadata = ET.SubElement(maplayer, "resourceMetadata")
    ET.SubElement(metadata, "title").text = title
    ET.SubElement(metadata, "abstract").text = abstract
    ET.SubElement(metadata, "rights").text = rights
    return maplayer


def _geometry_of(layer: KitLayer) -> str:
    kinds = {geometry_kind(tramo.geometry) for tramo in layer.tramos}
    name = _GEOMETRY_NAMES[next(iter(kinds))] if len(kinds) == 1 else "GEOMETRY"
    return _QGIS_GEOMETRY[name]


def _form_html(text: str) -> str:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;")
    return f"<p><b>Antes de anotar:</b> {escaped}</p>"


def _incidences_layer(projectlayers: ET.Element, base: str) -> None:
    form = INCIDENCIA_FORM
    maplayer = _maplayer(
        projectlayers,
        INCIDENCES_TABLE,
        INCIDENCES_TITLE,
        form.warning,
        base,
        "Point",
        rights="Anotaciones tuyas: se quedan en tu dispositivo.",
    )
    configuration = ET.SubElement(maplayer, "fieldConfiguration")
    _field(configuration, "fid", _text_edit())
    _field(
        configuration,
        "tipo",
        _value_map([(o.label, o.value) for o in form.obstacle_types]),
    )
    _field(configuration, "estado", _value_map([(o.label, o.value) for o in form.states]))
    date_widget = ET.Element("editWidget", {"type": "DateTime"})
    date_widget.append(
        _option_map(
            [
                ("allow_null", "bool", "true"),
                ("calendar_popup", "bool", "true"),
                ("display_format", "QString", "yyyy-MM-dd"),
                ("field_format", "QString", "yyyy-MM-dd"),
                ("field_iso_format", "bool", "false"),
            ]
        )
    )
    _field(configuration, "fecha", date_widget)
    _field(configuration, "nota", _text_edit(multiline=True))
    attachment = ET.Element("editWidget", {"type": "ExternalResource"})
    attachment.append(
        _option_map(
            [
                ("DocumentViewer", "int", "1"),
                ("FileWidget", "bool", "true"),
                ("FileWidgetButton", "bool", "true"),
                ("RelativeStorage", "int", "1"),
                ("StorageMode", "int", "0"),
            ]
        )
    )
    _field(configuration, "foto", attachment)
    aliases = ET.SubElement(maplayer, "aliases")
    for index, (name, alias) in enumerate(
        [
            ("fid", ""),
            ("tipo", "Tipo de obstáculo"),
            ("estado", "Estado del camino"),
            ("fecha", "Fecha"),
            ("nota", form.note_label),
            ("foto", "Foto (opcional)"),
        ]
    ):
        ET.SubElement(aliases, "alias", {"field": name, "index": str(index), "name": alias})
    defaults = ET.SubElement(maplayer, "defaults")
    ET.SubElement(
        defaults,
        "default",
        {
            "field": "fecha",
            "expression": "format_date(now(), 'yyyy-MM-dd')",
            "applyOnUpdate": "0",
        },
    )
    editor = ET.SubElement(maplayer, "editorlayout")
    editor.text = "tablayout"
    form_element = ET.SubElement(maplayer, "attributeEditorForm")
    html = ET.SubElement(
        form_element,
        "attributeEditorHtmlElement",
        {"name": "advertencia", "showLabel": "0", "index": "-1"},
    )
    html.text = _form_html(form.warning)
    for index, name in enumerate(("tipo", "estado", "fecha", "nota", "foto")):
        ET.SubElement(
            form_element,
            "attributeEditorField",
            {"name": name, "index": str(index + 1), "showLabel": "1"},
        )


def build_qgs(kit: MunicipalKit) -> str:
    base = project_base(kit.municipality_code)
    title = f"Paso Común — kit de campo del municipio {kit.municipality_code}"
    root = ET.Element("qgis", {"version": "3.34.0", "projectname": title})
    ET.SubElement(root, "title").text = title
    crs = ET.SubElement(root, "projectCrs")
    ET.SubElement(ET.SubElement(crs, "spatialrefsys"), "authid").text = "EPSG:4326"
    projectlayers = ET.SubElement(root, "projectlayers")
    for layer in kit.layers:
        _tramo_layer(projectlayers, layer, base, _geometry_of(layer))
    _incidences_layer(projectlayers, base)
    tree = ET.SubElement(root, "layer-tree-group")
    for table, name in [(layer.layer, LAYER_TITLE[layer.layer]) for layer in kit.layers] + [
        (INCIDENCES_TABLE, INCIDENCES_TITLE)
    ]:
        ET.SubElement(
            tree, "layer-tree-layer", {"id": table, "name": name, "checked": "Qt::Checked"}
        )
    metadata = ET.SubElement(root, "projectMetadata")
    ET.SubElement(metadata, "title").text = title
    ET.SubElement(metadata, "abstract").text = INCIDENCIA_FORM.warning
    ET.SubElement(metadata, "rights").text = rights_text(kit)
    ET.indent(root, space=" ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


# --- LEEME y ZIP --------------------------------------------------------------------------


def build_readme(kit: MunicipalKit) -> str:
    lines = [
        f"Paso Común — kit de campo del municipio {kit.municipality_code}",
        f"Generado el {kit.generated_on.isoformat()}.",
        "",
        "ANTES DE ANOTAR",
        INCIDENCIA_FORM.warning,
        "",
        "CÓMO USARLO (sin cuenta y sin enviar nada)",
        f"1. Copia {project_base(kit.municipality_code)}.gpkg y "
        f"{project_base(kit.municipality_code)}.qgs a una misma carpeta del móvil "
        "(o importa este ZIP en QField).",
        "2. Abre el .qgs desde QField («Open local file»).",
        f"3. Anota en la capa «{INCIDENCES_TITLE}»; todo queda en tu dispositivo.",
        "",
        "CAPAS",
    ]
    for layer in kit.layers:
        lines.append(f"- {LAYER_TITLE[layer.layer]}: {layer_abstract(layer)}")
    if kit.missing:
        lines.append(f"Capas no publicadas para el municipio: {', '.join(kit.missing)}.")
    lines.append("")
    return "\n".join(lines)


def build_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3
            archive.writestr(info, files[name])
    return buffer.getvalue()
