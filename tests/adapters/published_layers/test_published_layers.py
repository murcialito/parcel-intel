"""Adapter de salida `published_layers`. Datos SINTÉTICOS en EPSG:25830 dentro del ámbito."""

import json
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.published_layers import GeoJsonPublishedLayerSink, PublishedLayerError
from parcel_intel.adapters.published_layers.index import IndexEntry, build_index
from parcel_intel.adapters.published_layers.projection import to_lonlat
from parcel_intel.adapters.published_layers.simplification import simplify_shape
from parcel_intel.domain.geometry import Geometry, MultiLineGeometry, TrailShape
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.publication import PublishableLayer
from parcel_intel.domain.published_layers import PUBLISHED_LAYERS, TrailLayerPublication
from parcel_intel.domain.trail import SourceKind, Trail

PUBLIC = Provenance(
    "sintética",
    "https://example.invalid",
    date(2026, 11, 26),
    "CC BY 4.0",
    Redistribution.PUBLIC,
)
X, Y = 455_000.0, 4_436_000.0


def _trail(geometry: TrailShape, identifier: str = "T1") -> Trail:
    source: SourceKind = (
        "via_pecuaria_oficial" if isinstance(geometry, Geometry) else "ign_red_transporte"
    )
    return Trail(
        identifier=identifier,
        source=source,
        role="via",
        name="Vereda sintética" if isinstance(geometry, Geometry) else None,
        trail_type="Vereda" if isinstance(geometry, Geometry) else None,
        municipality_code="28997",
        geometry=geometry,
        provenance=PUBLIC,
        data_date=None,
        character="sintética",
    )


def _publication(
    layer_id: str, trails: tuple[Trail, ...], code: str = "28997", name: str = "Sintético"
) -> TrailLayerPublication:
    spec = PUBLISHED_LAYERS["vias_pecuarias" if layer_id == "vias_pecuarias" else "camino_actual"]
    return TrailLayerPublication(
        spec=spec,
        municipality_code=code,
        municipality_name=name,
        content=PublishableLayer[Trail](
            name=f"{layer_id}/{code}", items=trails, layer_provenance=PUBLIC
        ),
        boundary_provenance=None,
    )


def _square(dx: float = 0.0) -> tuple[tuple[float, float], ...]:
    return ((X + dx, Y), (X + dx + 20, Y), (X + dx + 20, Y + 20), (X + dx, Y + 20))


def _dense_line(dy: float, n: int = 500) -> tuple[tuple[float, float], ...]:
    return tuple((X + i, Y + dy + (0.3 if i % 2 else -0.3)) for i in range(n))


def test_proyeccion_lon_lat_en_el_ambito_con_6_decimales() -> None:
    [[lon, lat]] = to_lonlat(((X, Y),))

    assert -3.62 < lon < -3.15
    assert 39.98 < lat < 40.22
    assert round(lon, 6) == lon
    assert to_lonlat(()) == []


def test_simplificar_conserva_partes_y_tipo() -> None:
    lines = MultiLineGeometry(lines=(_dense_line(0), ((X, Y), (X + 1, Y))), srid=25830)

    simplified = simplify_shape(lines, 2.0)

    assert isinstance(simplified, MultiLineGeometry)
    assert len(simplified.lines) == 2
    assert len(simplified.lines[0]) < 10
    assert simplified.lines[1] == ((X, Y), (X + 1, Y))


def test_simplificar_no_pierde_un_anillo_diminuto() -> None:
    tiny = ((X, Y), (X + 0.5, Y), (X + 0.5, Y + 0.5), (X, Y + 0.5), (X, Y))
    polygon = Geometry(rings=(_square(), tiny), srid=25830)

    simplified = simplify_shape(polygon, 2.0)

    assert isinstance(simplified, Geometry)
    assert len(simplified.rings) == 2
    # La parte diminuta puede simplificarse, pero nunca desaparece ni se abre.
    assert len(simplified.rings[1]) >= 4
    assert simplified.rings[1][0] == simplified.rings[1][-1]


def test_indice_ordenado_por_nombre_y_codigo() -> None:
    entries = [
        IndexEntry("camino_actual", "28002", "B", (-3.5, 40.0, -3.4, 40.1), "2026-11-01"),
        IndexEntry("vias_pecuarias", "28001", "B", (-3.6, 40.0, -3.4, 40.1), "2026-11-20"),
        IndexEntry("camino_actual", "28003", "A", (-3.5, 40.0, -3.4, 40.1), "2026-10-01"),
    ]

    index, provenance = build_index(entries, "https://example.invalid/repo")

    municipios = index["municipios"]
    assert isinstance(municipios, list)
    assert [m["ine"] for m in municipios] == ["28003", "28001", "28002"]
    assert provenance["fecha_descarga"] == "2026-11-20"
    assert provenance["url"] == "https://example.invalid/repo"


def test_indice_ordena_nombres_con_tilde_junto_a_su_letra() -> None:
    bbox = (-3.5, 40.0, -3.4, 40.1)
    entries = [
        IndexEntry("camino_actual", "28001", "Zarzalejo", bbox, "2026-11-01"),
        IndexEntry("camino_actual", "28002", "Álamo", bbox, "2026-11-01"),
        IndexEntry("camino_actual", "28003", "Belmonte", bbox, "2026-11-01"),
        IndexEntry("camino_actual", "28004", "Alameda", bbox, "2026-11-01"),
    ]

    index, _ = build_index(entries, "u")

    municipios = index["municipios"]
    assert isinstance(municipios, list)
    assert [m["nombre"] for m in municipios] == ["Alameda", "Álamo", "Belmonte", "Zarzalejo"]


def test_indice_falla_si_un_municipio_tiene_dos_nombres() -> None:
    entries = [
        IndexEntry("camino_actual", "28001", "A", (0, 0, 1, 1), "2026-11-01"),
        IndexEntry("vias_pecuarias", "28001", "B", (0, 0, 1, 1), "2026-11-01"),
    ]

    with pytest.raises(PublishedLayerError, match="nombres distintos"):
        build_index(entries, "u")


def test_sink_escribe_capa_procedencia_e_indice(tmp_path: Path) -> None:
    sink = GeoJsonPublishedLayerSink(tmp_path, "https://example.invalid/repo")

    files = sink.publish(
        [_publication("vias_pecuarias", (_trail(Geometry(rings=(_square(),), srid=25830)),))]
    )

    assert [f.path for f in files] == ["vias_pecuarias/28997.geojson"]
    path = tmp_path / "vias_pecuarias" / "28997.geojson"
    assert files[0].size_bytes == path.stat().st_size
    assert files[0].simplification is None
    assert not files[0].over_threshold
    ring = json.loads(path.read_text(encoding="utf-8"))["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1]
    assert len(ring) == 5
    assert (tmp_path / "vias_pecuarias" / "28997.geojson.procedencia.json").is_file()
    assert (tmp_path / "indice.json").is_file()
    assert (tmp_path / "indice.json.procedencia.json").is_file()


def test_sink_sin_publicaciones_no_escribe_nada(tmp_path: Path) -> None:
    assert GeoJsonPublishedLayerSink(tmp_path, "u").publish([]) == ()
    assert list(tmp_path.iterdir()) == []


def test_sink_avisa_si_sigue_por_encima_del_umbral(tmp_path: Path) -> None:
    sink = GeoJsonPublishedLayerSink(tmp_path, "u", size_threshold_bytes=100)
    lines = MultiLineGeometry(lines=(_dense_line(0),), srid=25830)

    [published] = sink.publish([_publication("camino_actual", (_trail(lines),))])

    assert published.simplification is not None
    assert published.simplification.tolerance_m == 2.0
    assert published.simplification.bytes_before > published.size_bytes
    assert published.over_threshold


def test_sink_con_un_fichero_publicado_ilegible_no_escribe_nada(tmp_path: Path) -> None:
    broken = tmp_path / "camino_actual" / "28001.geojson"
    broken.parent.mkdir(parents=True)
    broken.write_text("{roto", encoding="utf-8")
    sink = GeoJsonPublishedLayerSink(tmp_path, "u")

    with pytest.raises(PublishedLayerError, match="28001.geojson"):
        sink.publish(
            [_publication("vias_pecuarias", (_trail(Geometry(rings=(_square(),), srid=25830)),))]
        )

    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == ["28001.geojson"]


def test_sink_repara_un_fichero_ilegible_al_republicarlo(tmp_path: Path) -> None:
    # Diseño de #84, §2: el índice sale de los ficheros que NO se van a reemplazar;
    # el que se reemplaza no se lee, así que estar corrupto no bloquea su reparación.
    broken = tmp_path / "vias_pecuarias" / "28001.geojson"
    broken.parent.mkdir(parents=True)
    broken.write_text("{roto", encoding="utf-8")
    sink = GeoJsonPublishedLayerSink(tmp_path, "u")

    sink.publish(
        [
            _publication(
                "vias_pecuarias",
                (_trail(Geometry(rings=(_square(),), srid=25830)),),
                code="28001",
                name="Uno",
            )
        ]
    )

    document = json.loads(broken.read_text(encoding="utf-8"))
    assert document["properties"]["municipio"] == "28001"
    assert len(document["features"]) == 1
    index = json.loads((tmp_path / "indice.json").read_text(encoding="utf-8"))
    assert "28001" in json.dumps(index)


def test_sink_rechaza_un_trazado_sin_geometria_sin_escribir(tmp_path: Path) -> None:
    sink = GeoJsonPublishedLayerSink(tmp_path, "u")
    empty = _trail(MultiLineGeometry(lines=(), srid=25830))

    with pytest.raises(PublishedLayerError, match="sin geometría"):
        sink.publish([_publication("camino_actual", (empty,))])
    assert list(tmp_path.iterdir()) == []


def test_sink_reemplaza_la_capa_del_mismo_municipio_y_conserva_las_demas(tmp_path: Path) -> None:
    sink = GeoJsonPublishedLayerSink(tmp_path, "u")
    square = Geometry(rings=(_square(),), srid=25830)
    sink.publish([_publication("vias_pecuarias", (_trail(square),), code="28001", name="Uno")])
    sink.publish([_publication("vias_pecuarias", (_trail(square),), code="28002", name="Dos")])
    sink.publish(
        [_publication("vias_pecuarias", (_trail(square, "T2"),), code="28001", name="Uno")]
    )

    index = json.loads((tmp_path / "indice.json").read_text(encoding="utf-8"))
    assert [m["nombre"] for m in index["municipios"]] == ["Dos", "Uno"]
    layer = json.loads((tmp_path / "vias_pecuarias" / "28001.geojson").read_text("utf-8"))
    assert [f["id"] for f in layer["features"]] == ["T2"]
