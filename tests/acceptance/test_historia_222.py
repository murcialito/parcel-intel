"""Historia #222: `publicar-kit-campo-qfield` genera un proyecto de QField por municipio.

Entradas SINTÉTICAS de #213 en `tests/fixtures/kit_campo/datos/` (vías pecuarias y discrepancias
de 28043; sin candidatos). Los docstrings copian el criterio de la issue.
"""

import json
import shutil
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from parcel_intel.cli import main as cli
from parcel_intel.domain.kit_campo import MAX_KIT_FILE_BYTES, QFIELD_WARNING

pytestmark = pytest.mark.acceptance

FIXTURES = Path(__file__).parent.parent / "fixtures" / "kit_campo" / "datos"
BASE = "paso_comun_28043"
GPKG_REQUIRED = {"gpkg_spatial_ref_sys", "gpkg_contents", "gpkg_geometry_columns"}


@pytest.fixture
def entrada(tmp_path: Path) -> Path:
    target = tmp_path / "entrada"
    shutil.copytree(FIXTURES, target)
    return target


def run(entrada: Path, salida: Path, *municipios: str, extra: tuple[str, ...] = ()) -> int:
    args = ["--entrada", str(entrada), "--salida", str(salida), *extra]
    for code in municipios:
        args += ["--municipio", code]
    namespace = cli._build_parser().parse_args(["publicar-kit-campo-qfield", *args])
    exit_code: int = namespace.func(namespace)
    return exit_code


def edit_geojson(entrada: Path, layer: str, mutate: Callable[[Any], object]) -> None:
    path = entrada / layer / "28043.geojson"
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(json.dumps(document), encoding="utf-8")


def project_dir(salida: Path) -> Path:
    return salida / "kit" / "28043" / "qfield"


def written(salida: Path) -> list[Path]:
    return sorted(p for p in salida.rglob("*") if p.is_file()) if salida.exists() else []


def qgs_root(salida: Path) -> ET.Element:
    return ET.parse(project_dir(salida) / f"{BASE}.qgs").getroot()


def layer_element(root: ET.Element, layer_id: str) -> ET.Element:
    for maplayer in root.iter("maplayer"):
        if maplayer.findtext("id") == layer_id:
            return maplayer
    raise AssertionError(layer_id)


def test_ca1_escribe_gpkg_valido_qgs_bien_formado_y_zip(entrada: Path, tmp_path: Path) -> None:
    """Dado un municipio con capas publicadas cuando se ejecuta
    `publicar-kit-campo-qfield --municipio <ine>` entonces escribe `site/datos/kit/<ine>/qfield/`
    con un `.gpkg` válido (leído con `sqlite3`: tablas OGC obligatorias, `application_id` GPKG) y
    un `.qgs` XML bien formado, y un ZIP de ambos."""
    salida = tmp_path / "salida"
    assert run(entrada, salida, "28043") == 0
    directory = project_dir(salida)
    connection = sqlite3.connect(directory / f"{BASE}.gpkg")
    try:
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master")}
        assert GPKG_REQUIRED <= tables
        assert connection.execute("PRAGMA application_id").fetchone()[0] == 0x47504B47
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        connection.close()
    assert ET.parse(directory / f"{BASE}.qgs").getroot().tag == "qgis"
    with zipfile.ZipFile(directory / f"{BASE}.zip") as archive:
        assert archive.testzip() is None
        assert {f"{BASE}.gpkg", f"{BASE}.qgs", "LEEME.txt"} == set(archive.namelist())
        assert archive.read(f"{BASE}.gpkg") == (directory / f"{BASE}.gpkg").read_bytes()
        assert archive.read(f"{BASE}.qgs") == (directory / f"{BASE}.qgs").read_bytes()


def test_ca2_una_capa_por_capa_publicada_e_incidencias_vacia(entrada: Path, tmp_path: Path) -> None:
    """Dado el GeoPackage cuando se lee entonces contiene una capa por cada capa publicada
    (EPSG:4326, solo propiedades de la lista blanca de #213, con el aviso de cada tramo) y una
    capa editable vacía `incidencias` (puntos) con los campos tipo, estado, fecha, nota (corta,
    «Nota corta (sin nombres de personas)») y foto opcional."""
    salida = tmp_path / "salida"
    assert run(entrada, salida, "28043") == 0
    connection = sqlite3.connect(project_dir(salida) / f"{BASE}.gpkg")
    try:
        contents = {
            r[0]: r[1] for r in connection.execute("SELECT table_name, srs_id FROM gpkg_contents")
        }
        assert contents == {
            "vias_pecuarias": 4326,
            "discrepancias": 4326,
            "incidencias": 4326,
        }
        columns = [r[1] for r in connection.execute("PRAGMA table_info(vias_pecuarias)")]
        assert columns == ["fid", "geom", "nombre", "descripcion"]
        descriptions = [r[0] for r in connection.execute("SELECT descripcion FROM discrepancias")]
        assert descriptions and all("Esto no es un dictamen" in d for d in descriptions)
        assert connection.execute("SELECT COUNT(*) FROM incidencias").fetchone()[0] == 0
        fields = [r[1] for r in connection.execute("PRAGMA table_info(incidencias)")]
        assert fields == ["fid", "geom", "tipo", "estado", "fecha", "nota", "foto"]
        kind = connection.execute(
            "SELECT geometry_type_name FROM gpkg_geometry_columns WHERE table_name='incidencias'"
        ).fetchone()[0]
        assert kind == "POINT"
        blob = connection.execute("SELECT geom FROM vias_pecuarias").fetchone()[0]
        assert blob[:2] == b"GP" and int.from_bytes(blob[4:8], "little") == 4326
    finally:
        connection.close()
    aliases = {
        a.get("field"): a.get("name")
        for a in layer_element(qgs_root(salida), "incidencias").iter("alias")
    }
    assert aliases["nota"] == "Nota corta (sin nombres de personas)"


def test_ca3_tipo_y_estado_son_valuemap_foto_opcional_fecha_del_dia(
    entrada: Path, tmp_path: Path
) -> None:
    """Dado el `.qgs` cuando se lee entonces `tipo` y `estado` son `ValueMap` con exactamente los
    valores listados arriba; la foto es de tipo adjunto opcional; la fecha por defecto es la del
    día."""
    salida = tmp_path / "salida"
    assert run(entrada, salida, "28043") == 0
    layer = layer_element(qgs_root(salida), "incidencias")
    widgets = {f.get("name"): f.find("editWidget") for f in layer.iter("field")}

    def values(name: str) -> list[str]:
        widget = widgets[name]
        assert widget is not None and widget.get("type") == "ValueMap"
        return [o.get("value", "") for o in widget.iter("Option") if o.get("type") == "QString"]

    assert values("tipo") == [
        "cancela",
        "valla",
        "cadena",
        "zanja",
        "bloques",
        "cartel_prohibido",
        "arado",
        "vegetacion",
    ]
    assert values("estado") == [
        "practicable",
        "tapado_vegetacion",
        "con_obstaculo",
        "deteriorado_maquinas",
    ]
    foto = widgets["foto"]
    assert foto is not None and foto.get("type") == "ExternalResource"
    assert layer.find(".//constraints") is None  # ninguna restricción: la foto es opcional
    default = next(d for d in layer.iter("default") if d.get("field") == "fecha")
    assert "now()" in (default.get("expression") or "")


def test_ca4_advertencia_literal_en_qgs_y_leeme_y_aviso_en_cada_tramo(
    entrada: Path, tmp_path: Path
) -> None:
    """Dado el proyecto cuando se abre entonces el texto de advertencia aprobado (ver arriba,
    literal) consta en el `.qgs` como ayuda/cabecera del formulario y en un `LEEME.txt` del ZIP,
    y el aviso de cada tramo («Indicio a verificar…») consta en su descripción."""
    salida = tmp_path / "salida"
    assert run(entrada, salida, "28043") == 0
    layer = layer_element(qgs_root(salida), "incidencias")
    header = layer.find(".//attributeEditorHtmlElement")
    assert header is not None and QFIELD_WARNING in (header.text or "")
    with zipfile.ZipFile(project_dir(salida) / f"{BASE}.zip") as archive:
        assert QFIELD_WARNING in archive.read("LEEME.txt").decode("utf-8")
    connection = sqlite3.connect(project_dir(salida) / f"{BASE}.gpkg")
    try:
        for table in ("vias_pecuarias", "discrepancias"):
            rows = [r[0] for r in connection.execute(f"SELECT descripcion FROM {table}")]
            assert rows and all(
                "no deslinde" in d or "no es un dictamen" in d.lower() for d in rows
            )
    finally:
        connection.close()


def test_ca5_procedencia_en_rights_y_sin_servidor(entrada: Path, tmp_path: Path) -> None:
    """Dado el proyecto cuando se examina entonces la fuente, licencia y atribución de cada capa
    (de su `.procedencia.json`) constan en `projectMetadata/rights` y en la descripción de cada
    capa, y no hay ninguna URL, servidor ni configuración de envío (sin QFieldCloud)."""
    salida = tmp_path / "salida"
    assert run(entrada, salida, "28043") == 0
    root = qgs_root(salida)
    rights = root.findtext("projectMetadata/rights") or ""
    assert "CC BY 4.0 Comunidad de Madrid" in rights
    assert "Instituto Geográfico Nacional" in rights
    for layer_id, source in (("vias_pecuarias", "idem"), ("discrepancias", "Parcel Intel")):
        abstract = layer_element(root, layer_id).findtext("abstract") or ""
        assert f"Fuente {source}" in abstract[:60] or source in abstract
        assert "licencia" in abstract and "atribución" in abstract
    text = (project_dir(salida) / f"{BASE}.qgs").read_text(encoding="utf-8").lower()
    assert "http" not in text and "qfieldcloud" not in text and "cloud" not in text
    assert {m.findtext("provider") for m in root.iter("maplayer")} == {"ogr"}


def test_ca6_entrada_invalida_falla_sin_escribir(
    entrada: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dado un fichero de entrada con aviso ausente, propiedad fuera de la lista blanca o
    propiedad de titularidad/referencia catastral cuando se genera entonces falla (todo o nada,
    sale con 1, no escribe), igual que #213."""
    mutations: list[tuple[str, Callable[[Any], object]]] = [
        ("discrepancias", lambda d: d["features"][0]["properties"].pop("aviso")),
        ("vias_pecuarias", lambda d: d["features"][0]["properties"].update(extra="x")),
        ("discrepancias", lambda d: d["features"][0]["properties"].update(propietario="x")),
        (
            "discrepancias",
            lambda d: d["features"][0]["properties"].update(referencia_catastral="x"),
        ),
    ]
    for number, (layer, mutate) in enumerate(mutations):
        shutil.rmtree(entrada)
        shutil.copytree(FIXTURES, entrada)
        edit_geojson(entrada, layer, mutate)
        salida = tmp_path / f"salida{number}"
        assert run(entrada, salida, "28043") == 1
        assert written(salida) == []
    assert "titularidad o referencia catastral" in capsys.readouterr().err


def test_ca7_sin_capas_sale_con_1_y_dice_cuales_faltaban(
    entrada: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dado un municipio sin ninguna capa publicada cuando se ejecuta entonces sale con 1 sin
    escribir; si falta alguna capa (p. ej. `candidatos`) el resumen dice cuáles incluyó y cuáles
    faltaban."""
    salida = tmp_path / "salida"
    assert run(entrada, salida, "28043") == 0
    out = capsys.readouterr().out
    assert "capas incluidas: vias_pecuarias, discrepancias" in out
    assert "capas que faltaban: camino_actual, candidatos" in out
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    sin_nada = tmp_path / "sin_nada"
    assert run(vacio, sin_nada, "28043") == 1
    assert written(sin_nada) == []


def test_ca8_reproducible_limite_de_tamano_e_indice_sin_tocar(
    entrada: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dado el mismo municipio y las mismas entradas cuando se ejecuta dos veces entonces el
    resultado es idéntico byte a byte (el ZIP con fechas fijas, la fecha de generación es la del
    día como en #213); ningún fichero pasa de 3.000.000 bytes y, si pasa, falla sin escribir. El
    `.procedencia.json` del proyecto lo describe. No se añade el proyecto a
    `site/datos/kit/indice.json` ni se despliega en el sitio hasta anotar la apertura real en
    QField (decisión 2)."""
    a, b = tmp_path / "a", tmp_path / "b"
    assert run(entrada, a, "28043") == 0
    assert run(entrada, b, "28043") == 0
    names = [p.relative_to(a) for p in written(a)]
    assert names == [p.relative_to(b) for p in written(b)]
    assert all((a / n).read_bytes() == (b / n).read_bytes() for n in names)
    assert all(p.stat().st_size <= MAX_KIT_FILE_BYTES for p in written(a))
    provenance = json.loads(
        (project_dir(a) / f"{BASE}.zip.procedencia.json").read_text(encoding="utf-8")
    )
    assert (
        provenance["municipio"] == "28043"
        and QFIELD_WARNING == provenance["advertencia_formulario"]
    )
    assert not (a / "kit" / "indice.json").exists()  # índice público sin tocar por defecto
    # con el indicador explícito sí entra
    c = tmp_path / "c"
    assert run(entrada, c, "28043", extra=("--incluir-en-indice",)) == 0
    index = json.loads((c / "kit" / "indice.json").read_text(encoding="utf-8"))
    assert index["municipios"][0]["qfield"]["ruta"] == f"28043/qfield/{BASE}.zip"
    # límite de tamaño: todo o nada
    monkeypatch.setattr("parcel_intel.adapters.kit_campo.qfield_sink.MAX_KIT_FILE_BYTES", 100)
    d = tmp_path / "d"
    assert run(entrada, d, "28043") == 1
    assert written(d) == []


def test_ca8_indice_existente_no_se_toca_por_defecto(entrada: Path, tmp_path: Path) -> None:
    """(CA8) El índice público existente queda byte a byte igual si no se pide incluirlo."""
    salida = tmp_path / "salida"
    (salida / "kit").mkdir(parents=True)
    index = salida / "kit" / "indice.json"
    index.write_text('{"municipios": []}\n', encoding="utf-8")
    assert run(entrada, salida, "28043") == 0
    assert index.read_text(encoding="utf-8") == '{"municipios": []}\n'


def test_ca9_se_verifica_con_fixtures_sin_red_ni_qgis(
    entrada: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dado el entorno de CI cuando se prueba entonces todo se verifica con fixtures, sin red,
    sin QGIS ni GDAL. [integración manual, fuera de CI] la apertura real en QField la anota en
    REGISTRY.md quien tenga el móvil (reserva de #219), sin bloquear la fusión."""
    import socket
    import sys

    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("el comando no debe usar la red")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    assert run(entrada, tmp_path / "salida", "28043") == 0
    assert "osgeo" not in sys.modules and "qgis" not in sys.modules
