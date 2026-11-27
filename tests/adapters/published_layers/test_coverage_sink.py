"""Escritor de `cobertura.geojson` (historia #185, ADR 0051). Límites sintéticos en EPSG:25830
cerca de Colmenar de Oreja; no son datos reales."""

import json
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.published_layers import GeoJsonCoverageSink, PublishedLayerError
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.publication import PublishableLayer

_PROV = Provenance(
    source="límites sintéticos",
    url="https://example.invalid/limites",
    retrieved_at=date(2026, 11, 27),
    license="CC BY 4.0 ign.es",
    redistribution=Redistribution.PUBLIC,
)


def _cuadro(x: float, y: float, lado: float = 1000.0, puntos: int = 4) -> Geometry:
    """Cuadrado con `puntos` vértices por lado (los intermedios, alineados: se simplifican)."""
    paso = lado / puntos
    anillo: list[tuple[float, float]] = []
    for i in range(puntos):
        anillo.append((x + i * paso, y))
    for i in range(puntos):
        anillo.append((x + lado, y + i * paso))
    for i in range(puntos):
        anillo.append((x + lado - i * paso, y + lado))
    for i in range(puntos):
        anillo.append((x, y + lado - i * paso))
    anillo.append((x, y))
    return Geometry(rings=(tuple(anillo),), srid=25830)


def _capa(*limites: MunicipalBoundary) -> PublishableLayer[MunicipalBoundary]:
    return PublishableLayer[MunicipalBoundary](name="cobertura", items=limites)


def _limite(ine: str, geometria: Geometry, nombre: str | None = None) -> MunicipalBoundary:
    return MunicipalBoundary(ine, nombre if nombre is not None else f"M{ine}", geometria, _PROV)


def test_escribe_geojson_compacto_en_4326_con_lista_blanca_y_procedencia(tmp_path: Path) -> None:
    multi = Geometry(
        rings=(_cuadro(460000, 4435000).rings[0], _cuadro(463000, 4435000).rings[0]), srid=25830
    )
    resultado = GeoJsonCoverageSink(tmp_path).publish(
        _capa(_limite("28043", _cuadro(460000, 4436000, puntos=10)), _limite("28013", multi))
    )
    assert resultado.path == "cobertura.geojson"
    assert resultado.municipality_codes == ("28043", "28013")
    texto = (tmp_path / "cobertura.geojson").read_text(encoding="utf-8")
    assert resultado.size_bytes == len(texto.encode("utf-8"))
    doc = json.loads(texto)
    assert doc["properties"]["capa"] == "cobertura"
    assert doc["properties"]["atribucion"] == "CC BY 4.0 ign.es"
    assert doc["properties"]["procedencia"]["redistribucion"] == "publicable"
    a, b = doc["features"]
    assert a["id"] == "28043" and a["properties"] == {"ine": "28043", "nombre": "M28043"}
    assert a["geometry"]["type"] == "Polygon"
    # Simplificado: los vértices alineados sobran; el anillo sigue cerrado.
    anillo = a["geometry"]["coordinates"][0]
    assert len(anillo) == 5 and anillo[0] == anillo[-1]
    lon, lat = anillo[0]
    assert -3.6 < lon < -3.3 and 40.0 < lat < 40.2
    assert b["geometry"]["type"] == "MultiPolygon" and len(b["geometry"]["coordinates"]) == 2
    procedencia = json.loads(
        (tmp_path / "cobertura.geojson.procedencia.json").read_text(encoding="utf-8")
    )
    assert procedencia["fuente"] == _PROV.source
    assert procedencia["url"] == _PROV.url
    assert procedencia["fecha_descarga"] == "2026-11-27"
    assert procedencia["licencia"] == "CC BY 4.0 ign.es"
    assert procedencia["municipios"] == ["28043", "28013"]
    assert procedencia["transformacion"]["crs_destino"] == "EPSG:4326"


def test_es_determinista(tmp_path: Path) -> None:
    capa = _capa(_limite("28043", _cuadro(460000, 4436000)))
    GeoJsonCoverageSink(tmp_path / "a").publish(capa)
    GeoJsonCoverageSink(tmp_path / "b").publish(capa)
    for nombre in ("cobertura.geojson", "cobertura.geojson.procedencia.json"):
        assert (tmp_path / "a" / nombre).read_bytes() == (tmp_path / "b" / nombre).read_bytes()


@pytest.mark.parametrize(
    "limites",
    [
        (),
        (_limite("28043", _cuadro(0, 0)), _limite("28043", _cuadro(5000, 0))),
        (_limite("28043", _cuadro(0, 0), nombre=" "),),
        (_limite("28043", Geometry(rings=(), srid=25830)),),
    ],
    ids=["vacia", "repetido", "sin-nombre", "sin-geometria"],
)
def test_entradas_invalidas_no_escriben_nada(
    tmp_path: Path, limites: tuple[MunicipalBoundary, ...]
) -> None:
    with pytest.raises(PublishedLayerError):
        GeoJsonCoverageSink(tmp_path).publish(_capa(*limites))
    assert list(tmp_path.iterdir()) == []


def test_por_encima_del_limite_de_peso_no_escribe(tmp_path: Path) -> None:
    capa = _capa(_limite("28043", _cuadro(460000, 4436000)))
    with pytest.raises(PublishedLayerError, match="pesa"):
        GeoJsonCoverageSink(tmp_path, size_limit_bytes=100).publish(capa)
    assert list(tmp_path.iterdir()) == []
