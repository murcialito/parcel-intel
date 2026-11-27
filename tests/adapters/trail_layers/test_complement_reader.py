"""Lector con fichero complementario (historia #183, ADR 0050): `camino_actual` ∪
`camino_asfaltado` en una sola capa de `ign_red_transporte`. Capas SINTÉTICAS en `tmp_path`."""

import json
from pathlib import Path

import pytest

from parcel_intel.adapters.trail_layers import (
    GeoJsonTrailLayerReader,
    IncompleteTrailLayerError,
    TrailLayerFormatError,
)
from parcel_intel.domain.trail import SourceKind
from parcel_intel.ports.errors import TrailLayerUnavailableError

IGN: SourceKind = "ign_red_transporte"
_LINE = {"type": "LineString", "coordinates": [[0, 0], [10, 0]]}


def _provenance(tag: str) -> dict[str, str]:
    return {
        "fuente": f"SINTÉTICO {tag}",
        "url": f"https://example.invalid/{tag}",
        "fecha_descarga": "2026-11-27",
        "licencia": "SINTÉTICA",
    }


def _write(
    directory: Path,
    ids: list[str],
    surface: str | None,
    feature_surface: str | None = None,
    name: str | None = None,
) -> Path:
    properties: dict[str, object] = {
        "fuente": IGN,
        "municipio": "28043",
        "procedencia": _provenance(directory.name),
        "procedencia_limite": _provenance("limite"),
    }
    if surface is not None:
        properties["superficie"] = surface
    if name is not None:
        properties["nombre_municipio"] = name
    features = []
    for identifier in ids:
        feature_properties: dict[str, object] = {"procedencia": _provenance(identifier)}
        if feature_surface is not None:
            feature_properties["superficie"] = feature_surface
        features.append(
            {"type": "Feature", "id": identifier, "geometry": _LINE, "properties": feature_properties}
        )
    document = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "EPSG:25830"}},
        "properties": properties,
        "features": features,
    }
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "28043.geojson"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _reader(tmp_path: Path) -> GeoJsonTrailLayerReader:
    return GeoJsonTrailLayerReader(
        {IGN: tmp_path / "camino_actual"}, complements={IGN: tmp_path / "camino_asfaltado"}
    )


def test_une_los_dos_ficheros_y_marca_solo_los_asfaltados(tmp_path: Path) -> None:
    _write(tmp_path / "camino_actual", ["1", "2"], "unpaved", name="Colmenar de Oreja")
    _write(tmp_path / "camino_asfaltado", ["3"], "paved", "paved", name="Colmenar de Oreja")

    layer = _reader(tmp_path).get_layer(IGN, "28043")

    assert [(t.identifier, t.counterpart_only) for t in layer.trails] == [
        ("1", False),
        ("2", False),
        ("3", True),
    ]
    # Procedencia, nombre y límite de la capa: los del principal.
    assert layer.provenance.source == "SINTÉTICO camino_actual"
    assert layer.municipality_name == "Colmenar de Oreja"
    assert layer.boundary_provenance is not None
    # Cada tramo asfaltado conserva su procedencia propia.
    assert layer.trails[2].provenance.source == "SINTÉTICO 3"


def test_el_principal_de_la_historia_27_sin_superficie_se_acepta(tmp_path: Path) -> None:
    _write(tmp_path / "camino_actual", ["1"], None)
    _write(tmp_path / "camino_asfaltado", [], "paved")

    layer = _reader(tmp_path).get_layer(IGN, "28043")

    assert [t.identifier for t in layer.trails] == ["1"]


def test_sin_ninguno_de_los_dos_la_fuente_esta_ausente(tmp_path: Path) -> None:
    with pytest.raises(TrailLayerUnavailableError):
        _reader(tmp_path).get_layer(IGN, "28043")


def test_sin_el_asfaltado_falla_y_pide_regenerar(tmp_path: Path) -> None:
    _write(tmp_path / "camino_actual", ["1"], None)

    with pytest.raises(IncompleteTrailLayerError) as error:
        _reader(tmp_path).get_layer(IGN, "28043")

    assert isinstance(error.value, TrailLayerFormatError)
    assert error.value.path == tmp_path / "camino_asfaltado" / "28043.geojson"
    assert "camino-actual-municipios" in error.value.detail
    assert "regenera" in error.value.detail


def test_el_asfaltado_sin_el_principal_falla(tmp_path: Path) -> None:
    _write(tmp_path / "camino_asfaltado", ["3"], "paved")

    with pytest.raises(IncompleteTrailLayerError) as error:
        _reader(tmp_path).get_layer(IGN, "28043")

    assert error.value.path == tmp_path / "camino_actual" / "28043.geojson"


@pytest.mark.parametrize(
    ("principal", "complement", "feature_principal", "feature_complement", "bad"),
    [
        ("paved", "paved", None, None, "camino_actual"),
        ("unpaved", "unpaved", None, None, "camino_asfaltado"),
        ("unpaved", None, None, None, "camino_asfaltado"),
        ("unpaved", "paved", "paved", None, "camino_actual"),
        ("unpaved", "paved", None, "unpaved", "camino_asfaltado"),
    ],
)
def test_superficie_cruzada_nombra_el_fichero(
    tmp_path: Path,
    principal: str | None,
    complement: str | None,
    feature_principal: str | None,
    feature_complement: str | None,
    bad: str,
) -> None:
    _write(tmp_path / "camino_actual", ["1"], principal, feature_principal)
    _write(tmp_path / "camino_asfaltado", ["3"], complement, feature_complement)

    with pytest.raises(TrailLayerFormatError, match="superficie") as error:
        _reader(tmp_path).get_layer(IGN, "28043")

    assert error.value.path == tmp_path / bad / "28043.geojson"


def test_un_identificador_en_los_dos_ficheros_es_error(tmp_path: Path) -> None:
    _write(tmp_path / "camino_actual", ["1", "2"], "unpaved")
    _write(tmp_path / "camino_asfaltado", ["2"], "paved")

    with pytest.raises(TrailLayerFormatError, match="'2'") as error:
        _reader(tmp_path).get_layer(IGN, "28043")

    assert error.value.path == tmp_path / "camino_asfaltado" / "28043.geojson"


def test_nombres_de_municipio_distintos_son_error(tmp_path: Path) -> None:
    _write(tmp_path / "camino_actual", ["1"], "unpaved", name="Colmenar de Oreja")
    _write(tmp_path / "camino_asfaltado", ["3"], "paved", name="Chinchón")

    with pytest.raises(TrailLayerFormatError, match="municipio"):
        _reader(tmp_path).get_layer(IGN, "28043")


def test_sin_complementos_el_lector_ignora_el_asfaltado(tmp_path: Path) -> None:
    """Así lo usa `publicar-capas`: nada de `camino_asfaltado/` entra (CA5)."""
    _write(tmp_path / "camino_actual", ["1"], "unpaved")
    _write(tmp_path / "camino_asfaltado", ["3"], "paved")

    layer = GeoJsonTrailLayerReader({IGN: tmp_path / "camino_actual"}).get_layer(IGN, "28043")

    assert [(t.identifier, t.counterpart_only) for t in layer.trails] == [("1", False)]


def test_otras_fuentes_no_se_ven_afectadas_por_el_complemento(tmp_path: Path) -> None:
    via: SourceKind = "via_pecuaria_oficial"
    directory = tmp_path / "vias"
    _write(tmp_path / "camino_actual", ["1"], "unpaved")
    _write(tmp_path / "camino_asfaltado", [], "paved")
    document = json.loads((tmp_path / "camino_actual" / "28043.geojson").read_text("utf-8"))
    document["properties"]["fuente"] = via
    del document["properties"]["superficie"]
    directory.mkdir()
    (directory / "28043.geojson").write_text(json.dumps(document), encoding="utf-8")
    reader = GeoJsonTrailLayerReader(
        {IGN: tmp_path / "camino_actual", via: directory},
        complements={IGN: tmp_path / "camino_asfaltado"},
    )

    assert [t.counterpart_only for t in reader.get_layer(via, "28043").trails] == [False]
