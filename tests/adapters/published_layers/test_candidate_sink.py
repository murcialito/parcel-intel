"""Sink de tramos a verificar (historias #170 y #172). Publicaciones sintéticas de la
fixture."""

import dataclasses
import json
from pathlib import Path

import pytest

from parcel_intel.adapters.comparison_files import JsonComparisonManifestReader
from parcel_intel.adapters.curated_candidates import CuratedCandidateReviewFiles
from parcel_intel.adapters.published_layers import (
    GeoJsonPublishedCandidateSink,
    JsonMeasurementReportReader,
    PublishedLayerError,
)
from parcel_intel.domain.candidate_review import reconcile
from parcel_intel.domain.published_candidate import (
    CandidateLayerPublication,
    build_candidate_layer,
    summarize_measurement,
)
from tests.fixtures.candidatos_publicar import generar
from tests.fixtures.candidatos_revision import generar as revision

URL = "https://example.invalid/repo"


def _publication() -> CandidateLayerPublication:
    reviews = CuratedCandidateReviewFiles(generar.DIRECTORY / "curated").reviews(generar.INE)
    state = reconcile(revision.report(), reviews)
    measurement = JsonMeasurementReportReader(generar.DIRECTORY / "medicion.json").get_measurement()
    summary = summarize_measurement(measurement, revision.report().method)
    manifest = JsonComparisonManifestReader(generar.DIRECTORY / "comparacion").get_manifest(
        generar.INE
    )
    assert manifest is not None
    return build_candidate_layer(state, summary, "Colmenar de Oreja", manifest).publication


def _snapshot(directory: Path) -> dict[str, bytes]:
    if not directory.exists():
        return {}
    return {
        str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob("*") if p.is_file()
    }


def _with_label(publication: CandidateLayerPublication, label: str) -> CandidateLayerPublication:
    first, *rest = publication.content.items
    item = dataclasses.replace(first, card=dataclasses.replace(first.card, label=label))
    content = dataclasses.replace(publication.content, items=(item, *rest))
    return dataclasses.replace(publication, content=content)


def test_los_ficheros_de_la_fixture_son_los_generados() -> None:
    for relative, text in generar.texts().items():
        assert (generar.DIRECTORY / relative).read_text(encoding="utf-8") == text, relative


def test_escribe_capa_procedencia_e_indice(tmp_path: Path) -> None:
    (published,) = GeoJsonPublishedCandidateSink(tmp_path, URL).publish([_publication()])
    assert published.path == "candidatos/28043.geojson"
    assert published.layer_id == "candidatos"
    assert not published.over_threshold
    document = json.loads((tmp_path / published.path).read_text(encoding="utf-8"))
    assert document["properties"]["procedencia"]["fuente"] == (
        "Paso Común, tramos a verificar revisados a mano"
    )
    assert document["properties"]["procedencia"]["licencia"] == "CC BY 4.0"
    sidecar = json.loads(
        (tmp_path / "candidatos" / "28043.geojson.procedencia.json").read_text(encoding="utf-8")
    )
    assert sidecar["medicion"] == {
        "fecha": "2026-11-27",
        "conjunto": "validacion-v1",
        "metodo": "candidato_corte v1",
    }
    assert [s["origen"] for s in sidecar["fuentes"]] == [
        "catastro_wfs_cp (sintético)",
        "idem_vias_pecuarias (sintético)",
        *["pnoa-historico"] * 4,  # un vuelo publicado por entrada (#172)
    ]
    index = json.loads((tmp_path / "indice.json").read_text(encoding="utf-8"))
    assert index["municipios"][0]["capas"] == {"candidatos": "candidatos/28043.geojson"}


def test_umbral_de_peso(tmp_path: Path) -> None:
    """#172 (ADR 0049 §7): por encima del umbral, falla sin escribir nada."""
    with pytest.raises(PublishedLayerError, match="por encima del umbral de 100"):
        GeoJsonPublishedCandidateSink(tmp_path, URL, 100).publish([_publication()])
    assert _snapshot(tmp_path) == {}


def test_imagenes_y_procedencia_de_los_vuelos(tmp_path: Path) -> None:
    GeoJsonPublishedCandidateSink(tmp_path, URL).publish([_publication()])
    document = json.loads((tmp_path / "candidatos" / "28043.geojson").read_text(encoding="utf-8"))
    for feature in document["features"]:
        for window in feature["properties"]["imagenes_comparacion"]:
            assert [i["franja"] for i in window["imagenes"]] == [
                "1997-2003",
                "2006-2011",
                "2014-2020",
                "reciente",
            ]
    sidecar = json.loads(
        (tmp_path / "candidatos" / "28043.geojson.procedencia.json").read_text(encoding="utf-8")
    )
    assert sidecar["imagenes_comparacion"]["alojadas_en_el_sitio"] is False
    assert [s["origen"] for s in sidecar["fuentes"]].count("pnoa-historico") == 4


def test_sin_publicaciones_no_escribe(tmp_path: Path) -> None:
    assert GeoJsonPublishedCandidateSink(tmp_path, URL).publish([]) == ()
    assert _snapshot(tmp_path) == {}


@pytest.mark.parametrize(
    "leak",
    [revision.CATASTRO_TRAIL_ID, "https://x.invalid/?refcat=1", "parece ilegal", "su propietario"],
)
def test_ultima_barrera_no_escribe_nada(tmp_path: Path, leak: str) -> None:
    with pytest.raises(PublishedLayerError):
        GeoJsonPublishedCandidateSink(tmp_path, URL).publish([_with_label(_publication(), leak)])
    assert _snapshot(tmp_path) == {}


def test_nombre_distinto_del_de_otras_capas_falla_sin_escribir(tmp_path: Path) -> None:
    sink = GeoJsonPublishedCandidateSink(tmp_path, URL)
    sink.publish([_publication()])
    before = _snapshot(tmp_path)
    (tmp_path / "discrepancias").mkdir()
    other = json.loads((tmp_path / "candidatos" / "28043.geojson").read_text(encoding="utf-8"))
    other["properties"]["nombre_municipio"] = "Otro nombre"
    (tmp_path / "discrepancias" / "28043.geojson").write_text(json.dumps(other), encoding="utf-8")
    with pytest.raises(PublishedLayerError):
        sink.publish([_publication()])
    after = _snapshot(tmp_path)
    after.pop("discrepancias/28043.geojson")
    assert after == before
