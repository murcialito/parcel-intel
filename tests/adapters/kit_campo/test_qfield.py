import sqlite3
import struct
import zipfile
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.kit_campo.qfield import (
    build_geopackage,
    build_qgs,
    build_zip,
    gpkg_geometry,
)
from parcel_intel.domain.kit_campo import KitGeometry, KitLayer, KitTramo, MunicipalKit

LINE = ((-3.5, 40.0), (-3.4, 40.1))
RING = ((-3.5, 40.0), (-3.4, 40.0), (-3.4, 40.1), (-3.5, 40.0))


def _layer(name: str, geometry: KitGeometry) -> KitLayer:
    return KitLayer(
        layer="vias_pecuarias" if name == "v" else "discrepancias",
        source="fuente",
        license="CC BY 4.0",
        attribution=("atrib",),
        notice="aviso",
        tramos=(KitTramo("t", "d", geometry, "vias_pecuarias"),),
    )


def test_geometria_multilinea_y_multipoligono_con_huecos() -> None:
    blob = gpkg_geometry(KitGeometry(lines=(LINE, LINE)))
    assert blob[:2] == b"GP"
    assert struct.unpack("<BII", blob[8:17]) == (1, 5, 2)
    hole = ((-3.48, 40.02), (-3.46, 40.02), (-3.46, 40.04), (-3.48, 40.02))
    polygon = gpkg_geometry(KitGeometry(polygons=((RING, hole), (RING,))))
    assert struct.unpack("<BII", polygon[8:17]) == (1, 6, 2)  # dos polígonos, uno con hueco


def test_geometria_vacia_falla() -> None:
    with pytest.raises(ValueError):
        gpkg_geometry(KitGeometry())


def test_capa_con_lineas_y_poligonos_mezclados_es_geometry() -> None:
    kit = MunicipalKit(
        "28043",
        date(2026, 11, 27),
        (
            KitLayer(
                "discrepancias",
                "f",
                "l",
                ("a",),
                "aviso",
                (
                    KitTramo("a", "d", KitGeometry(lines=(LINE,)), "discrepancias"),
                    KitTramo("b", "d", KitGeometry(polygons=((RING,),)), "discrepancias"),
                ),
            ),
        ),
        (),
    )
    connection = sqlite3.connect(":memory:")
    connection.deserialize(build_geopackage(kit))
    row = connection.execute(
        "SELECT geometry_type_name FROM gpkg_geometry_columns WHERE table_name='discrepancias'"
    ).fetchone()
    assert row[0] == "GEOMETRY"
    assert connection.execute("SELECT COUNT(*) FROM discrepancias").fetchone()[0] == 2
    connection.close()


def test_capa_sin_tramos_se_escribe_y_el_qgs_la_declara() -> None:
    kit = MunicipalKit(
        "28043",
        date(2026, 11, 27),
        (KitLayer("vias_pecuarias", "f", "l", ("a",), "aviso", ()),),
        (),
    )
    connection = sqlite3.connect(":memory:")
    connection.deserialize(build_geopackage(kit))
    assert connection.execute("SELECT COUNT(*) FROM vias_pecuarias").fetchone()[0] == 0
    connection.close()
    assert "vias_pecuarias" in build_qgs(kit)


def test_zip_determinista_y_ordenado(tmp_path: Path) -> None:
    files = {"b.txt": b"2", "a.txt": b"1"}
    first, second = build_zip(files), build_zip(dict(reversed(files.items())))
    assert first == second
    path = tmp_path / "x.zip"
    path.write_bytes(first)
    with zipfile.ZipFile(path) as archive:
        assert archive.namelist() == ["a.txt", "b.txt"]
        assert archive.getinfo("a.txt").date_time == (1980, 1, 1, 0, 0, 0)
