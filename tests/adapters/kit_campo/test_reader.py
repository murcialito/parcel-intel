import json
import shutil
from pathlib import Path

import pytest

from parcel_intel.adapters.kit_campo import PublishedLayerFileReader
from parcel_intel.ports.kit_campo import PublishedLayerFileError

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "kit_campo" / "datos"


def test_lee_capa_publicada_con_su_procedencia() -> None:
    file = PublishedLayerFileReader(FIXTURES).read("discrepancias", "28043")
    assert file is not None
    assert len(file.features) == 2
    assert len(file.attribution) == 2
    assert file.features[0].geometry.lines and file.features[1].geometry.polygons


def test_capa_no_publicada_es_none() -> None:
    assert PublishedLayerFileReader(FIXTURES).read("candidatos", "28043") is None


def test_fichero_sin_procedencia_falla(tmp_path: Path) -> None:
    shutil.copytree(FIXTURES, tmp_path / "d")
    (tmp_path / "d/discrepancias/28043.geojson.procedencia.json").unlink()
    with pytest.raises(PublishedLayerFileError, match="falta"):
        PublishedLayerFileReader(tmp_path / "d").read("discrepancias", "28043")


def test_geometria_no_admitida_falla(tmp_path: Path) -> None:
    shutil.copytree(FIXTURES, tmp_path / "d")
    path = tmp_path / "d/vias_pecuarias/28043.geojson"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["features"][0]["geometry"] = {"type": "Point", "coordinates": [-3.5, 40.0]}
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(PublishedLayerFileError, match="no admitido"):
        PublishedLayerFileReader(tmp_path / "d").read("vias_pecuarias", "28043")


def test_json_corrupto_falla(tmp_path: Path) -> None:
    shutil.copytree(FIXTURES, tmp_path / "d")
    (tmp_path / "d/vias_pecuarias/28043.geojson").write_text("{", encoding="utf-8")
    with pytest.raises(PublishedLayerFileError):
        PublishedLayerFileReader(tmp_path / "d").read("vias_pecuarias", "28043")
