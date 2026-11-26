"""Historia #83: vias-pecuarias-municipios escribe data/derived/vias_pecuarias/<ine>.geojson."""

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from parcel_intel.adapters.road_layer_files import GeoJsonLivestockTrailLayerWriter
from parcel_intel.adapters.trail_layers import GeoJsonTrailLayerReader
from parcel_intel.cli import main as cli
from parcel_intel.cli.main import AMBITO_HITO_INE, build_municipal_layers
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.livestock_trail import LIVESTOCK_TRAIL_CHARACTER
from parcel_intel.domain.municipal_livestock_trails import MunicipalLivestockTrailLayer
from parcel_intel.ports.errors import TrailLayerUnavailableError
from tests.municipal_layer_fixtures import NoNetwork, prepare_cache

pytestmark = pytest.mark.acceptance

D1 = date(2026, 11, 26)
D2 = date(2027, 1, 15)
LICENSE = "CC BY 4.0 Comunidad de Madrid"

Prepared = tuple[Path, tuple[MunicipalLivestockTrailLayer, ...]]


@pytest.fixture(scope="module")
def prepared(tmp_path_factory: pytest.TempPathFactory) -> Prepared:
    cache_dir = tmp_path_factory.mktemp("raw")
    return cache_dir, prepare_cache(cache_dir, D1)


def _layer(
    layers: tuple[MunicipalLivestockTrailLayer, ...], ine: str
) -> MunicipalLivestockTrailLayer:
    return next(layer for layer in layers if layer.municipality.ine_code == ine)


def _write(layer: MunicipalLivestockTrailLayer, directory: Path) -> dict[str, Any]:
    path = GeoJsonLivestockTrailLayerWriter(directory).write(layer)
    assert path == directory / f"{layer.municipality.ine_code}.geojson"
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def test_ca1_fichero_con_coleccion_en_25830_y_propiedades_de_coleccion(
    prepared: Prepared, tmp_path: Path
) -> None:
    """Dada la capa de un municipio con tramos (fixture real de Colmenar 28043), cuando se
    escribe, entonces existe `<salida>/28043.geojson`, una `FeatureCollection` con `crs`
    EPSG:25830 y `properties` de colección `fuente="via_pecuaria_oficial"`,
    `municipio="28043"`, `nombre_municipio`, `procedencia`, `procedencia_limite` y `aviso`."""
    _, layers = prepared
    layer = _layer(layers, "28043")

    collection = _write(layer, tmp_path)

    assert collection["type"] == "FeatureCollection"
    assert collection["crs"] == {
        "type": "name",
        "properties": {"name": "urn:ogc:def:crs:EPSG::25830"},
    }
    properties = collection["properties"]
    assert properties["fuente"] == "via_pecuaria_oficial"
    assert properties["municipio"] == "28043"
    assert properties["nombre_municipio"] == "Colmenar de Oreja"
    assert properties["procedencia"]["fuente"] == "idem"
    assert properties["procedencia"]["licencia"] == LICENSE
    assert properties["procedencia_limite"]["fuente"] == layer.municipality.provenance.source
    assert properties["procedencia_limite"]["url"] == layer.municipality.provenance.url
    assert properties["aviso"]
    assert collection["features"]


def test_ca2_el_lector_real_lee_el_fichero_sin_perder_piezas_ni_partes(
    prepared: Prepared, tmp_path: Path
) -> None:
    """Dado ese fichero, cuando se pasa por `GeoJsonTrailLayerReader.get_layer(
    "via_pecuaria_oficial", "28043")`, entonces se lee sin error, con el mismo número de
    trazados que piezas tenía la capa, y cada uno con geometría (`Polygon` o `MultiPolygon` si
    la pieza tiene varias partes, sin perder ninguna) y `role="via"`."""
    _, layers = prepared
    layer = _layer(layers, "28043")
    _write(layer, tmp_path)

    read = GeoJsonTrailLayerReader({"via_pecuaria_oficial": tmp_path}).get_layer(
        "via_pecuaria_oficial", "28043"
    )

    assert len(read.trails) == len(layer.trails) == 19
    assert any(len(p.geometry.rings) > 1 for p in layer.trails)  # multiparte real
    for piece, trail in zip(layer.trails, read.trails, strict=True):
        assert isinstance(trail.geometry, Geometry)
        assert len(trail.geometry.rings) == len(piece.geometry.rings)
        assert trail.role == "via"


def test_ca3_cada_feature_lleva_id_estable_propiedades_y_procedencia_propia(
    prepared: Prepared, tmp_path: Path
) -> None:
    """Dado cada feature, entonces lleva `id` estable y único, `nombre`, `tipo`, `area_m2` de
    la pieza, `parte_del_tramo` (`share_of_source`), `fecha_dato` y una `procedencia` propia
    (fuente, URL, `fecha_descarga`, licencia) igual a la del tramo de IDEM. Ninguna propiedad
    de titularidad."""
    _, layers = prepared
    for layer in layers:
        features = _write(layer, tmp_path)["features"]
        ids = [f["id"] for f in features]
        assert len(set(ids)) == len(ids) == len(layer.trails)
        for feature, piece in zip(features, layer.trails, strict=True):
            props = feature["properties"]
            assert props["nombre"] == piece.source.name
            assert props["tipo"] == piece.source.trail_type
            assert props["area_m2"] == round(piece.area_m2, 2)
            assert props["parte_del_tramo"] == round(piece.share_of_source, 4)
            assert "fecha_dato" in props
            assert props["procedencia"] == {
                "fuente": piece.provenance.source,
                "url": piece.provenance.url,
                "fecha_descarga": piece.provenance.retrieved_at.isoformat(),
                "licencia": piece.provenance.license,
                # Historia #84 (ADR 0036): la marca de redistribución viaja con el dato.
                "redistribucion": "publicable",
            }
            assert not any(
                word in key for key in props for word in ("propiet", "titular", "owner")
            )
    # (La colisión de un mismo `trail_code` con varias piezas, que en los datos reales del
    # ámbito no ocurre, la cubre el test unitario sintético del escritor.)


def test_ca4_el_aviso_es_el_literal_y_aparece_en_la_coleccion(
    prepared: Prepared, tmp_path: Path
) -> None:
    """Dado el aviso de la capa, entonces el texto de `aviso` es `LIVESTOCK_TRAIL_CHARACTER`
    ("cartografía informativa, no deslinde") y aparece también en la colección."""
    _, layers = prepared
    layer = _layer(layers, "28043")

    collection = _write(layer, tmp_path)
    read = GeoJsonTrailLayerReader({"via_pecuaria_oficial": tmp_path}).get_layer(
        "via_pecuaria_oficial", "28043"
    )

    assert LIVESTOCK_TRAIL_CHARACTER == "cartografía informativa, no deslinde"
    assert layer.notice == LIVESTOCK_TRAIL_CHARACTER
    assert collection["properties"]["aviso"] == LIVESTOCK_TRAIL_CHARACTER
    assert {t.character for t in read.trails} == {LIVESTOCK_TRAIL_CHARACTER}


def test_ca5_municipio_sin_tramos_es_capa_vacia_no_ausente(
    prepared: Prepared, tmp_path: Path
) -> None:
    """Dado un municipio sin tramos (Belmonte de Tajo 28019 o Valdelaguna 28157), cuando se
    escribe, entonces el fichero existe con `features: []` y el lector lo devuelve como capa
    vacía (distinta de capa ausente). (Con los datos reales solo Belmonte 28019 está vacío:
    Valdelaguna 28157 recibe una astilla de 0,25 m² y el umbral de astillas queda fuera de
    alcance, ADR 0032.)"""
    ine = "28019"
    _, layers = prepared
    layer = _layer(layers, ine)
    assert layer.trails == ()

    collection = _write(layer, tmp_path)
    reader = GeoJsonTrailLayerReader({"via_pecuaria_oficial": tmp_path})

    assert collection["features"] == []
    assert reader.get_layer("via_pecuaria_oficial", ine).trails == ()
    with pytest.raises(TrailLayerUnavailableError):
        reader.get_layer("via_pecuaria_oficial", "28043")


def test_ca6_dos_escrituras_con_today_distinto_y_sin_red_son_identicas_byte_a_byte(
    prepared: Prepared, tmp_path: Path
) -> None:
    """Dadas dos escrituras de la misma capa con `today` distinto y sin red, cuando se
    comparan los ficheros, entonces son idénticos byte a byte (claves ordenadas, redondeo solo
    al escribir, sin fecha de generación, `fecha_descarga` la de la caché)."""
    cache_dir, first = prepared
    second = build_municipal_layers(
        cache_dir,
        offline=True,
        ign_http_get=NoNetwork(),
        idem_http_get=NoNetwork(),
        today=lambda: D2,
        sleep=lambda _: None,
    )
    for layer in first:
        GeoJsonLivestockTrailLayerWriter(tmp_path / "a").write(layer)
    for layer in second:
        GeoJsonLivestockTrailLayerWriter(tmp_path / "b").write(layer)

    names = sorted(p.name for p in (tmp_path / "a").iterdir())
    assert names == sorted(f"{ine}.geojson" for ine in AMBITO_HITO_INE)
    for name in names:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
    assert D2.isoformat() not in (tmp_path / "b" / "28043.geojson").read_text(encoding="utf-8")


def test_ca7_el_comando_escribe_un_fichero_por_municipio_e_imprime_ruta(
    prepared: Prepared,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dado el subcomando `vias-pecuarias-municipios --sin-red --cache <dir> --salida <dir>`
    con la caché preparada desde fixtures, cuando se ejecuta, entonces escribe un fichero por
    cada uno de los 7 municipios del ámbito, imprime por municipio el INE, el número de piezas
    y la ruta, mantiene el detalle actual por pieza y sale con 0. El valor por defecto de
    `--salida` es `data/derived/vias_pecuarias`."""
    cache_dir, layers = prepared
    out_dir = tmp_path / "derived"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "vias-pecuarias-municipios",
            "--sin-red",
            "--cache",
            str(cache_dir),
            "--salida",
            str(out_dir),
        ],
    )

    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    assert sorted(p.name for p in out_dir.iterdir()) == sorted(
        f"{ine}.geojson" for ine in AMBITO_HITO_INE
    )
    for layer in layers:
        ine = layer.municipality.ine_code
        assert f"{ine} {layer.municipality.name}" in out
        assert f"piezas: {len(layer.trails)}" in out
        assert str(out_dir / f"{ine}.geojson") in out
        for piece in layer.trails:
            assert f"trail_code={piece.source.trail_code}" in out
            assert piece.provenance.url in out
    parser = cli._build_parser()
    assert parser.parse_args(["vias-pecuarias-municipios"]).salida == Path(
        "data/derived/vias_pecuarias"
    )


def test_ca8_fallo_de_escritura_se_informa_sin_fichero_a_medias_y_sale_con_1(
    prepared: Prepared,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dado un fallo de escritura o de datos de un municipio, entonces el comando lo informa en
    stderr, no deja un fichero a medias (escritura atómica con `os.replace`) y sale con 1; el
    error de capa de la fuente (`RawCacheMissError`, etc.) conserva su mensaje y código 1."""
    cache_dir, _ = prepared
    out_dir = tmp_path / "derived"
    real_replace = os.replace

    def replace(src: Any, dst: Any) -> None:
        if str(dst).endswith("28052.geojson"):
            raise OSError("disco lleno simulado")
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(
        sys,
        "argv",
        ["prog", "vias-pecuarias-municipios", "--sin-red", "--cache", str(cache_dir),
         "--salida", str(out_dir)],
    )

    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert exit_info.value.code == 1
    assert "FALLO 28052 Chinchón: disco lleno simulado" in capsys.readouterr().err
    names = sorted(p.name for p in out_dir.iterdir())
    assert names == sorted(f"{ine}.geojson" for ine in AMBITO_HITO_INE if ine != "28052")
    assert not any(name.endswith(".tmp") for name in names)

    # El error de la capa de la fuente conserva su mensaje y su código.
    monkeypatch.setattr(
        sys,
        "argv",
        ["prog", "vias-pecuarias-municipios", "--sin-red", "--cache", str(tmp_path / "vacia"),
         "--salida", str(out_dir)],
    )
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == 1
    assert "Sin red y no cacheado" in capsys.readouterr().err


@pytest.mark.integration
def test_ca9_integracion_con_red_y_luego_sin_red_da_ficheros_identicos(tmp_path: Path) -> None:
    """[integración] Dado el IDEM real, cuando se ejecuta con red una vez y luego `--sin-red`,
    entonces los ficheros de la segunda ejecución son idénticos a los de la primera."""
    cache_dir = tmp_path / "raw"
    online = build_municipal_layers(cache_dir, offline=False, sleep=lambda _: None)
    offline = build_municipal_layers(cache_dir, offline=True, today=lambda: D2)
    for layer in online:
        GeoJsonLivestockTrailLayerWriter(tmp_path / "a").write(layer)
    for layer in offline:
        GeoJsonLivestockTrailLayerWriter(tmp_path / "b").write(layer)

    names = sorted(p.name for p in (tmp_path / "a").iterdir())
    assert names == sorted(f"{ine}.geojson" for ine in AMBITO_HITO_INE)
    for name in names:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
