"""Tests de aceptación de la historia #37: capa interna de caminos de Catastro por municipio.

Todo sobre las fixtures SINTÉTICAS de #46 y su generador (sin red). El criterio
`[integración]` (CA7) usa el Catastro real y no guarda ni nombra ninguna referencia real.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from dataclasses import replace
from pathlib import Path

import pytest

from parcel_intel.adapters.catastro.area_adapter import (
    CATASTRO_INSPIRE_LICENSE,
    CATASTRO_WFS_TILE_SIDE_M,
    CatastroAreaAdapter,
)
from parcel_intel.adapters.catastro.client import DNPPP_URL, WFS_PARCEL_URL
from parcel_intel.adapters.catastro.parsing import (
    geometry_from_rings,
    parse_dnppp,
    parse_wfs_parcels,
)
from parcel_intel.adapters.raw_cache import CachedRawFetcher
from parcel_intel.application.build_cadastral_road_layer import BuildCadastralRoadLayerUseCase
from parcel_intel.cli.main import build_cadastral_road_layer
from parcel_intel.domain.cadastral_road import (
    CadastralRoad,
    CadastralRoadLayer,
    RuralCadastralReference,
    parse_rural_reference,
)
from parcel_intel.domain.geometry import tile_bbox
from parcel_intel.domain.parcel import Parcel
from parcel_intel.domain.provenance import Redistribution
from parcel_intel.domain.publication import NotRedistributableError, PublishableLayer
from parcel_intel.ports.errors import (
    AreaQueryLimitExceededError,
    ParcelNotFoundError,
    TruncatedAreaQueryError,
)
from tests.caminos_catastro_support import (
    CONTROL_REF,
    HG_DESCRIPTION,
    ROAD_REFS,
    TODAY,
    WFS_FIXTURE,
    WINDOW,
    FixtureCatastroHttp,
    FixtureLandUsePort,
    FixtureParcelsPort,
    TableParcelsPort,
    dnppp_bytes,
    fixture_parcels,
    provenance,
    table_parcel,
)
from tests.fixtures import generate_caminos
from tests.fixtures.generate_catastro import SyntheticParcel, SyntheticSurface, wfs_cp_collection

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).parents[2]
REGISTRY = ROOT / "src" / "parcel_intel" / "sources" / "REGISTRY.md"
MUNICIPALITY = "28043"

# Bbox del término de Colmenar de Oreja (IGN, WFS de unidades administrativas, EPSG:25830,
# ejes E,N), redondeado hacia fuera al metro. Petición y resultado en REGISTRY.md.
COLMENAR_BBOX = (449341.0, 4431623.0, 470702.0, 4442906.0)


def _use_case(
    parcels: FixtureParcelsPort | TableParcelsPort, land_use: FixtureLandUsePort, side: float
) -> BuildCadastralRoadLayerUseCase:
    return BuildCadastralRoadLayerUseCase(parcels, land_use, tile_side_m=side)


def _layer_from_fixtures(tmp_path: Path) -> tuple[FixtureCatastroHttp, CadastralRoadLayer]:
    http = FixtureCatastroHttp()
    layer = build_cadastral_road_layer(
        "MADRID",
        "COLMENAR DE OREJA",
        MUNICIPALITY,
        WINDOW,
        tmp_path / "cache",
        offline=False,
        http_get=http,
        today=lambda: TODAY,
        sleep=lambda _s: None,
    )
    return http, layer


def test_ca1_solo_se_consultan_las_candidatas_con_numero_9000_o_mas() -> None:
    """CA1. Dada la fixture `catastro_wfsCP_sintetica_rustica_bbox600m.xml` como única tesela
    (bbox (469000, 4439000, 469600, 4439600), `tile_side_m=900`) y el código `28043`, cuando se
    ejecuta el caso de uso con un port de parcelas que devuelve esa fixture y un port de uso que
    lee las DNPPP sintéticas, entonces `tiles == 1`, `parcels_seen == 20`,
    `road_number_candidates == 4` y el port de uso se llama exactamente 4 veces, con
    `28043A99109101`, `28043A99109102`, `28043A99209201` y `28043A99209202` (en ese orden).
    """
    land_use = FixtureLandUsePort()
    layer = _use_case(FixtureParcelsPort(fixture_parcels()), land_use, 900.0).execute(
        MUNICIPALITY, WINDOW
    )
    assert layer.tiles == 1
    assert layer.parcels_seen == 20
    assert layer.road_number_candidates == 4
    assert land_use.calls == list(ROAD_REFS)


def test_ca2_la_clase_vt_es_camino_y_hg_o_cultivo_no() -> None:
    """CA2. Dadas las DNPPP sintéticas y una novena respuesta `HG`
    (`render_dnppp("28043A99109103", "HG", "HIDROGRAFÍA NATURAL (RÍO,LAGUNA,ARROYO.)", 500)`
    añadida a la lista de candidatas en el test), cuando se filtra por clase `VT`, entonces
    `28043A99109101`, `28043A99109102`, `28043A99209201` y `28043A99209202` quedan como camino,
    la `28043A99100001` (`C-`, no es candidata por su número) no se consulta, y
    `28043A99109103` queda en `excluded` con sus clases `("HG",)`.
    """
    hg_ref = "28043A99109103"
    hg_tile = generate_caminos.Tile(hg_ref, 0, 10, 0, 10)
    parcels = [*fixture_parcels(), table_parcel(hg_tile)]
    hg_response = generate_caminos.render_dnppp(hg_ref, "HG", HG_DESCRIPTION, 500)
    land_use = FixtureLandUsePort(extra={hg_ref: hg_response})
    layer = _use_case(FixtureParcelsPort(parcels), land_use, 900.0).execute(MUNICIPALITY, WINDOW)
    assert tuple(road.cadastral_reference for road in layer.roads) == ROAD_REFS
    assert CONTROL_REF not in land_use.calls
    assert hg_ref in land_use.calls
    assert layer.excluded == ((hg_ref, ("HG",)),)


def test_ca3_teselas_contiguas_deduplican_parcelas_repetidas() -> None:
    """CA3. Dado un port de parcelas de prueba que, para cada bbox pedido, devuelve **con su
    geometría completa** (sin recortar) las parcelas de la tabla sintética cuyo rectángulo
    interseca el interior del bbox, cuando se ejecuta el caso de uso sobre
    (469000, 4439000, 469600, 4439600) con `tile_side_m=300`, entonces se piden exactamente 4
    teselas (469000/469300 × 4439000/4439300, en orden fila a fila desde la esquina SO),
    `28043A99109101` (cruza el borde y=300 entre dos teselas) y `28043A99209202` (también)
    llegan en dos respuestas y aparecen **una sola vez** en `roads` con la geometría de la
    primera tesela, `parcels_seen == 20` y `roads` tiene 4 elementos. Además, `tile_bbox` tiene
    tests unitarios para un bbox múltiplo exacto del lado, uno que no lo es (última fila y
    columna recortadas), uno menor que una tesela, y `side_m <= 0` o bbox degenerado
    (`ValueError`).
    """
    port = TableParcelsPort()
    layer = _use_case(port, FixtureLandUsePort(), 300.0).execute(MUNICIPALITY, WINDOW)
    assert port.calls == [
        (469000.0, 4439000.0, 469300.0, 4439300.0),
        (469300.0, 4439000.0, 469600.0, 4439300.0),
        (469000.0, 4439300.0, 469300.0, 4439600.0),
        (469300.0, 4439300.0, 469600.0, 4439600.0),
    ]
    for ref in ("28043A99109101", "28043A99209202"):
        assert sum(ref in response for response in port.responses) == 2
    refs = [road.cadastral_reference for road in layer.roads]
    assert refs == list(ROAD_REFS)
    assert layer.parcels_seen == 20
    assert len(layer.roads) == 4
    primera_tesela = TableParcelsPort._intersecting(port.calls[0])
    first = next(p for p in primera_tesela if p.cadastral_reference == "28043A99109101")
    assert layer.roads[0].geometry == first.geometry
    # tile_bbox: múltiplo exacto, no múltiplo (recortes), menor que una tesela, errores.
    assert len(tile_bbox(WINDOW, 300.0)) == 4
    recortadas = tile_bbox((0.0, 0.0, 250.0, 130.0), 100.0)
    assert len(recortadas) == 6 and recortadas[-1] == (200.0, 100.0, 250.0, 130.0)
    assert tile_bbox((0.0, 0.0, 50.0, 20.0), 100.0) == ((0.0, 0.0, 50.0, 20.0),)
    for bbox, side in (
        (WINDOW, 0.0),
        (WINDOW, -5.0),
        ((1.0, 0.0, 1.0, 5.0), 10.0),
        ((0.0, 5.0, 4.0, 5.0), 10.0),
    ):
        with pytest.raises(ValueError):
            tile_bbox(bbox, side)


def test_ca4_el_camino_lleva_geometria_superficie_y_procedencia_internas(tmp_path: Path) -> None:
    """CA4. Dado el camino `28043A99109101` de CA1, cuando se inspecciona, entonces
    `geometry.srid == 25830`, `area_m2 == 6000.0` (el `areaValue` del WFS, no los 6011 de
    DNPPP), `land_use_classes == ("VT",)`, `cadastral_reference == "28043A99109101"`,
    `polygon == 991`, `parcel == 9101`, y `provenance` y `land_use_provenance` llevan fuente,
    URL completa de la petición, fecha de descarga, `license == CATASTRO_INSPIRE_LICENSE` y
    `redistribution == Redistribution.INTERNAL_ONLY`. La capa devuelve
    `redistribution == INTERNAL_ONLY`. Lo mismo con `28043A99209201` (`area_m2 == 3000.0` frente
    a 3024 de DNPPP).
    """
    _http, layer = _layer_from_fixtures(tmp_path)
    roads = {road.cadastral_reference: road for road in layer.roads}
    for ref, area, ssp in (("28043A99109101", 6000.0, 6011.0), ("28043A99209201", 3000.0, 3024.0)):
        road = roads[ref]
        assert road.geometry.srid == 25830
        assert road.area_m2 == area
        assert road.land_use_classes == ("VT",)
        assert road.cadastral_reference == ref
        assert (road.polygon, road.parcel) == (int(ref[6:9]), int(ref[9:14]))
        assert parse_dnppp(dnppp_bytes(ref), ref)["subparcels"][0]["area_m2"] == ssp
        for prov, base in (
            (road.provenance, WFS_PARCEL_URL),
            (road.land_use_provenance, DNPPP_URL),
        ):
            assert prov.source and prov.url.startswith(base + "?")
            assert prov.retrieved_at == TODAY
            assert prov.license == CATASTRO_INSPIRE_LICENSE
            assert prov.redistribution is Redistribution.INTERNAL_ONLY
    first = roads["28043A99109101"]
    assert "bbox=469000.0%2C4439000.0%2C469600.0%2C4439600.0" in first.provenance.url
    assert "Poligono=991" in first.land_use_provenance.url
    assert "Parcela=9101" in first.land_use_provenance.url
    assert layer.redistribution is Redistribution.INTERNAL_ONLY


def test_ca5_la_capa_interna_no_pasa_a_una_serializacion_publica(tmp_path: Path) -> None:
    """CA5. Dada la capa de CA1, cuando se construye `PublishableLayer` con sus `roads`,
    entonces lanza `NotRedistributableError`. Y construir un `CadastralRoad` con cualquiera de
    sus dos `Provenance` en `PUBLIC`, o con `srid` distinto de 25830, lanza `ValueError`.
    """
    _http, layer = _layer_from_fixtures(tmp_path)
    roads: tuple[CadastralRoad, ...] = layer.roads
    with pytest.raises(NotRedistributableError):
        PublishableLayer("caminos", roads)
    road = roads[0]
    publica = replace(road.provenance, redistribution=Redistribution.PUBLIC)
    with pytest.raises(ValueError):
        replace(road, provenance=publica)
    with pytest.raises(ValueError):
        replace(road, land_use_provenance=publica)
    with pytest.raises(ValueError):
        replace(road, geometry=replace(road.geometry, srid=4326))


def test_ca6_ningun_campo_es_de_titularidad() -> None:
    """CA6. Dado `CadastralRoad`, cuando se listan sus campos (`dataclasses.fields`), entonces
    son exactamente los del diseño, ninguno más. Y el parser de DNPPP devuelve solo las claves
    `class_code`, `description` y `area_m2` por subparcela, sin datos de titularidad.
    """
    assert [f.name for f in dataclasses.fields(CadastralRoad)] == [
        "cadastral_reference",
        "municipality_code",
        "polygon",
        "parcel",
        "land_use_classes",
        "area_m2",
        "geometry",
        "provenance",
        "land_use_provenance",
    ]
    cuerpo = generate_caminos.render_dnppp("28043A99109101", "VT", "VÍA", 10).decode("utf-8")
    con_titular = cuerpo.replace(
        "</bi>", "<ctt><nif>00000000T</nif><nom>TITULAR INVENTADO</nom></ctt></bi>"
    )
    subparcelas = parse_dnppp(con_titular.encode("utf-8"), "28043A99109101")["subparcels"]
    assert all(set(s) == {"class_code", "description", "area_m2"} for s in subparcelas)
    assert "TITULAR" not in repr(subparcelas)


@pytest.mark.integration
def test_ca7_catastro_real_de_colmenar_se_cachea_y_se_repite_sin_red(tmp_path: Path) -> None:
    """CA7. [integración] Dado Colmenar de Oreja (código de Catastro `28043`) y el bbox de su
    término, obtenido del WFS de unidades administrativas del IGN con el orden de ejes E,N en
    EPSG:25830 y registrado en `REGISTRY.md` con su petición, cuando se ejecuta
    `catastro-caminos` contra el Catastro real, entonces la capa tiene al menos un camino,
    todos con referencia que empieza por `28043`, número ≥9000 y `"VT" in land_use_classes`.
    Al repetir con `--sin-red`, la capa es igual (`==`) a la primera y los ficheros de
    `data/raw/catastro/` no cambian (mismo número y mismo sha256). `REGISTRY.md` anota solo
    **números agregados** (teselas, peticiones, caminos, excluidas por clase, sin clasificar,
    duración); **ninguna referencia catastral real** ni coordenada de parcela.
    """
    cache = tmp_path / "catastro"
    args = ("MADRID", "COLMENAR DE OREJA", MUNICIPALITY, COLMENAR_BBOX, cache)
    primera = build_cadastral_road_layer(*args, offline=False)

    assert primera.roads
    for road in primera.roads:
        assert road.cadastral_reference.startswith(MUNICIPALITY)
        assert road.parcel >= 9000
        assert "VT" in road.land_use_classes

    def huellas() -> dict[str, str]:
        return {
            str(p.relative_to(cache)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(cache.rglob("*"))
            if p.is_file()
        }

    antes = huellas()
    segunda = build_cadastral_road_layer(*args, offline=True)
    assert segunda == primera
    assert huellas() == antes

    texto = REGISTRY.read_text(encoding="utf-8")
    seccion = texto[texto.index("#### Capa interna de caminos de Catastro") :]
    seccion = seccion[: seccion.index("\n### ")]
    assert "449341" in seccion and "4442906" in seccion
    assert not re.search(r"\b\d{5}[A-Z]\d{8}", seccion)


def _fetcher(tmp_path: Path, wfs: bytes) -> tuple[CatastroAreaAdapter, Path]:
    cache = tmp_path / "cache"
    http = FixtureCatastroHttp(wfs=wfs)
    fetcher = CachedRawFetcher(http, cache, lambda: TODAY, sleep=lambda _s: None)
    return CatastroAreaAdapter("MADRID", "COLMENAR DE OREJA", fetcher), cache


def test_ca8_un_exception_report_de_area_no_se_cachea(tmp_path: Path) -> None:
    """CA8. Dada una respuesta WFS **sintética** (nombrada como tal en el test;
    `ExceptionReport` con el texto `Area of extension out of limits` que `REGISTRY.md` registra
    del servicio real), cuando el adapter la recibe, entonces lanza
    `AreaQueryLimitExceededError` y la caché no guarda nada.
    """
    respuesta_sintetica = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows/1.1" version="2.0.0">'
        b'<ows:Exception exceptionCode="OperationProcessingFailed">'
        b"<ows:ExceptionText>Area of extension out of limits (SINTETICA)</ows:ExceptionText>"
        b"</ows:Exception></ows:ExceptionReport>"
    )
    adapter, cache = _fetcher(tmp_path, respuesta_sintetica)
    with pytest.raises(AreaQueryLimitExceededError):
        adapter.get_parcels_in_bbox(WINDOW)
    assert not cache.exists() or not any(p.is_file() for p in cache.rglob("*"))


def test_ca9_una_respuesta_truncada_no_se_cachea(tmp_path: Path) -> None:
    """CA9. Dada una respuesta sintética con `numberMatched="20" numberReturned="10"` (la
    fixture de caminos con la mitad de los miembros), cuando el adapter la recibe, entonces
    lanza `TruncatedAreaQueryError(bbox, 20, 10)` y la caché no guarda nada.
    """
    mitad = [
        SyntheticParcel(
            tile.ref,
            tile.area,
            (SyntheticSurface(exterior=generate_caminos.clockwise_ring(tile)),),
        )
        for tile in generate_caminos.TILES[:10]
    ]
    cuerpo = wfs_cp_collection(mitad).replace(b'numberMatched="10"', b'numberMatched="20"')
    assert b'numberReturned="10"' in cuerpo and b'numberMatched="20"' in cuerpo
    adapter, cache = _fetcher(tmp_path, cuerpo)
    with pytest.raises(TruncatedAreaQueryError) as error:
        adapter.get_parcels_in_bbox(WINDOW)
    assert (error.value.bbox, error.value.matched, error.value.returned) == (WINDOW, 20, 10)
    assert not cache.exists() or not any(p.is_file() for p in cache.rglob("*"))


def test_ca10_las_parcelas_de_otro_municipio_no_cuentan() -> None:
    """CA10. Dada la fixture de CA1 y el código `28170` (Villaconejos), cuando se ejecuta el
    caso de uso, entonces `parcels_seen == 0`, `roads == ()` y el port de uso no se llama.
    """
    land_use = FixtureLandUsePort()
    layer = _use_case(FixtureParcelsPort(fixture_parcels()), land_use, 900.0).execute(
        "28170", WINDOW
    )
    assert layer.parcels_seen == 0
    assert layer.roads == ()
    assert land_use.calls == []


def test_ca11_solo_se_conservan_los_anillos_exteriores() -> None:
    """CA11. Dada una parcela sintética con `MultiSurface` de dos polígonos, uno de ellos con un
    `gml:interior` (construida en el test con `SyntheticSurface`), cuando se parsea, entonces la
    geometría tiene exactamente 2 anillos, los dos exteriores. Los tests existentes del informe
    por parcela siguen en verde.
    """
    ext_a = ((0.0, 0.0), (0.0, 100.0), (100.0, 100.0), (100.0, 0.0), (0.0, 0.0))
    hueco = ((40.0, 40.0), (60.0, 40.0), (60.0, 60.0), (40.0, 60.0), (40.0, 40.0))
    ext_b = ((200.0, 0.0), (200.0, 50.0), (250.0, 50.0), (250.0, 0.0), (200.0, 0.0))
    parcela = SyntheticParcel(
        "28043A99109199",
        12500,
        (SyntheticSurface(exterior=ext_a, interiors=(hueco,)), SyntheticSurface(exterior=ext_b)),
    )
    cuerpo = wfs_cp_collection([parcela])
    assert cuerpo.count(b"<gml:interior>") == 1
    (raw,) = parse_wfs_parcels(cuerpo)
    assert len(geometry_from_rings(raw["rings"]).rings) == 2
    assert raw["rings"] == (ext_a, ext_b)


def test_ca12_una_dnppp_sin_datos_no_aborta_el_lote() -> None:
    """CA12. Dadas tres candidatas ≥9000 (`28043A99109101`, `28043A99109102`,
    `28043A99209201`) en las que `get_land_use` lanza `ParcelNotFoundError` para la segunda,
    cuando se ejecuta el caso de uso, entonces `28043A99109102` queda en `unclassified` y las
    otras dos se clasifican como camino.
    """
    tres = [t for t in generate_caminos.TILES if t.ref in ROAD_REFS[:3]]
    port = FixtureParcelsPort([table_parcel(t) for t in tres])
    land_use = FixtureLandUsePort(missing=frozenset({"28043A99109102"}))
    layer = _use_case(port, land_use, 900.0).execute(MUNICIPALITY, WINDOW)
    assert layer.unclassified == ("28043A99109102",)
    assert [r.cadastral_reference for r in layer.roads] == ["28043A99109101", "28043A99209201"]
    with pytest.raises(ParcelNotFoundError):
        land_use.get_land_use(_ref("28043A99109102"))


def _ref(compact: str) -> RuralCadastralReference:
    reference = parse_rural_reference(compact)
    assert reference is not None
    return reference


def test_la_tesela_de_catastro_deja_margen_bajo_el_limite_del_wfs() -> None:
    """Soporte de CA3/CA8: el lado inyectado es el del adapter (900 m < 1000 m del servicio)."""
    assert CATASTRO_WFS_TILE_SIDE_M == 900.0
    assert WFS_FIXTURE.exists()
    assert provenance().redistribution is Redistribution.INTERNAL_ONLY
    assert isinstance(table_parcel(generate_caminos.TILES[0]), Parcel)
