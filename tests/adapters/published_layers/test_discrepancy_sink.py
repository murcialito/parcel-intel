"""Sink de indicios publicados (historia #94): lista blanca, barrera de referencias e índice
compartido. Datos SINTÉTICOS."""

import dataclasses
import json
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.published_layers import (
    GeoJsonPublishedDiscrepancySink,
    PublishedLayerError,
)
from parcel_intel.domain.discrepancy import Discrepancy, Measurement, SourceRef, TrailRef
from parcel_intel.domain.discrepancy_criterion import CRITERION
from parcel_intel.domain.discrepancy_report import DiscrepancyRecord, MunicipalDiscrepancyReport
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.published_discrepancy import (
    DiscrepancyLayerPublication,
    build_discrepancy_layer,
)

REPO = "https://example.invalid/repo"


def _publication(url: str = "https://example.invalid/vias") -> DiscrepancyLayerPublication:
    prov = Provenance("SINTÉTICO vías", url, date(2026, 11, 20), "SINT", Redistribution.PUBLIC)
    other = Provenance(
        "SINTÉTICO ign",
        "https://example.invalid/ign",
        date(2026, 11, 22),
        "SINT",
        Redistribution.PUBLIC,
    )
    discrepancy = Discrepancy(
        kind="AUSENTE_EN_FUENTE",
        zone=Geometry(
            rings=(
                ((465000.0, 4440300.0), (465100.0, 4440300.0), (465100.0, 4440310.0)),
                ((465200.0, 4440300.0), (465300.0, 4440300.0), (465300.0, 4440310.0)),
            ),
            srid=25830,
        ),
        subject=TrailRef("VP-2", SourceRef("via_pecuaria_oficial", prov, date(2014, 1, 1))),
        counterpart_source=SourceRef("ign_red_transporte", other, date(2025, 3, 15)),
        counterpart_trails=(),
        confidence=0.7,
        evidence=(Measurement("radio_busqueda_m", 33.541, "m"),),
        criterion=CRITERION,
    )
    report = MunicipalDiscrepancyReport(
        "28043",
        "discrepancia_trazados@1",
        (),
        (DiscrepancyRecord("r", discrepancy, (), False),),
        True,
        "Colmenar de Oreja",
    )
    publication = build_discrepancy_layer(report).publication
    assert publication is not None
    return publication


def _load(path: Path) -> dict[str, object]:
    loaded: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def test_publica_la_lista_blanca_con_anillos_cerrados_y_procedencia(tmp_path: Path) -> None:
    (published,) = GeoJsonPublishedDiscrepancySink(tmp_path, REPO).publish([_publication()])
    assert published.path == "discrepancias/28043.geojson"
    assert published.layer_id == "discrepancias"
    assert not published.over_threshold and published.simplification is None
    document = _load(tmp_path / published.path)
    assert "crs" not in document
    props = document["properties"]
    assert isinstance(props, dict)
    assert props["procedencia"] == {
        "fuente": "Parcel Intel, indicios de discrepancia entre trazados",
        "url": REPO,
        "fecha_descarga": "2026-11-22",
        "licencia": "CC BY 4.0",
        "redistribucion": "publicable",
    }
    assert props["criterio"] == "discrepancia_trazados v1"
    features = document["features"]
    assert isinstance(features, list)
    (feature,) = features
    geometry = feature["geometry"]
    assert geometry["type"] == "MultiPolygon" and len(geometry["coordinates"]) == 2
    for polygon in geometry["coordinates"]:
        assert polygon[0][0] == polygon[0][-1]  # anillo cerrado
    assert set(feature["properties"]) == {
        "tipo",
        "etiqueta",
        "texto",
        "aviso",
        "confianza",
        "evidencia",
        "criterio",
        "descripcion_criterio",
        "aviso_omision",
    }
    text = (tmp_path / published.path).read_text(encoding="utf-8")
    assert "VP-2" not in text and "33.541" not in text and "0.7" not in text
    sidecar = _load(tmp_path / "discrepancias" / "28043.geojson.procedencia.json")
    assert sidecar["redistribucion"] == "publicable"
    assert len(sidecar["fuentes"]) == 2  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "url",
    [
        "https://example.invalid/x?ref=99043A00109001",
        "https://example.invalid/x?Poligono=1&Parcela=9001",
    ],
)
def test_barrera_de_referencias_no_escribe_nada(tmp_path: Path, url: str) -> None:
    with pytest.raises(PublishedLayerError, match="referencia o localizador de parcela"):
        GeoJsonPublishedDiscrepancySink(tmp_path, REPO).publish([_publication(url)])
    assert list(tmp_path.iterdir()) == []


def test_sin_publicaciones_no_escribe(tmp_path: Path) -> None:
    assert GeoJsonPublishedDiscrepancySink(tmp_path, REPO).publish([]) == ()
    assert list(tmp_path.iterdir()) == []


def test_el_indice_conserva_las_capas_de_trazados(tmp_path: Path) -> None:
    existing = {
        "type": "FeatureCollection",
        "properties": {
            "nombre_municipio": "Colmenar de Oreja",
            "procedencia": {"fecha_descarga": "2026-11-26"},
        },
        "features": [
            {"geometry": {"type": "LineString", "coordinates": [[-3.5, 40.1], [-3.4, 40.2]]}}
        ],
    }
    for layer in ("vias_pecuarias", "camino_actual"):
        (tmp_path / layer).mkdir()
        (tmp_path / layer / "28043.geojson").write_text(json.dumps(existing), encoding="utf-8")
    GeoJsonPublishedDiscrepancySink(tmp_path, REPO).publish([_publication()])
    index = json.loads((tmp_path / "indice.json").read_text(encoding="utf-8"))
    (entry,) = index["municipios"]
    assert set(entry["capas"]) == {"camino_actual", "discrepancias", "vias_pecuarias"}


def test_fichero_publicado_ilegible_de_otra_capa_no_escribe_nada(tmp_path: Path) -> None:
    (tmp_path / "vias_pecuarias").mkdir()
    (tmp_path / "vias_pecuarias" / "28045.geojson").write_text("{", encoding="utf-8")
    with pytest.raises(PublishedLayerError, match="ilegible"):
        GeoJsonPublishedDiscrepancySink(tmp_path, REPO).publish([_publication()])
    assert not (tmp_path / "discrepancias").exists()


def test_umbral_marca_over_threshold(tmp_path: Path) -> None:
    (published,) = GeoJsonPublishedDiscrepancySink(tmp_path, REPO, size_threshold_bytes=10).publish(
        [dataclasses.replace(_publication())]
    )
    assert published.over_threshold
