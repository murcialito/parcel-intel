"""Tests de aceptación de la historia #46: fixtures sintéticas de caminos de Catastro."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from parcel_intel.adapters.catastro.parsing import parse_wfs_parcels
from tests.fixtures import generate_caminos, generate_catastro
from tests.fixtures.catastro_fingerprints import (
    reference_fingerprints,
    ring_fingerprints,
    vertex_fingerprints,
)
from tests.network_guard import no_network

pytestmark = pytest.mark.acceptance

TESTS_DIR = Path(__file__).parents[1]
ROOT = TESTS_DIR.parent
CAMINOS_DIR = TESTS_DIR / "fixtures" / "caminos"
HUELLAS = TESTS_DIR / "fixtures" / "catastro_huellas_reales.json"
REGISTRY = ROOT / "src" / "parcel_intel" / "sources" / "REGISTRY.md"

_CATASTRO = "{http://www.catastro.meh.es/}"
_GML = "{http://www.opengis.net/gml/3.2}"
_WFS = "{http://www.opengis.net/wfs/2.0}"
_CP = "{http://inspire.ec.europa.eu/schemas/cp/4.0}"

NUEVOS = (
    "catastro_wfsCP_sintetica_rustica_bbox600m.xml",
    "catastro_dnppp_sintetica_pol991_parc1.xml",
    "catastro_dnppp_sintetica_pol991_parc9101.xml",
    "catastro_dnppp_sintetica_pol991_parc9102.xml",
    "catastro_dnppp_sintetica_pol992_parc9201.xml",
    "catastro_dnppp_sintetica_pol992_parc9202.xml",
)
ANTIGUOS = (
    "catastro_wfsCP_colmenar_rustica_bbox600m.xml",
    "catastro_dnppp_colmenar_pol1_parc1.xml",
    "catastro_dnppp_colmenar_pol1_parc9001.xml",
    "catastro_dnppp_colmenar_pol1_parc9007.xml",
    "catastro_dnppp_colmenar_pol2_parc9003.xml",
    "catastro_dnppp_colmenar_pol2_parc9004.xml",
)
CAMINOS_9XXX = (
    "28043A99109101",
    "28043A99109102",
    "28043A99209201",
    "28043A99209202",
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _wfs() -> bytes:
    return (CAMINOS_DIR / "catastro_wfsCP_sintetica_rustica_bbox600m.xml").read_bytes()


def _huellas() -> dict[str, object]:
    data: dict[str, object] = json.loads(HUELLAS.read_text(encoding="utf-8"))
    return data


def _huellas_set(clave: str) -> set[str]:
    valor = _huellas()[clave]
    assert isinstance(valor, list)
    return {str(item) for item in valor}


def _dnppp(name: str) -> tuple[str, int]:
    root = ET.fromstring((CAMINOS_DIR / name).read_bytes())
    ccc = root.findtext(f".//{_CATASTRO}lspr/{_CATASTRO}spr/{_CATASTRO}dspr/{_CATASTRO}ccc")
    ssp = root.findtext(f".//{_CATASTRO}lspr/{_CATASTRO}spr/{_CATASTRO}dspr/{_CATASTRO}ssp")
    assert ccc is not None and ssp is not None
    return ccc, int(ssp)


def _shoelace(ring: tuple[tuple[float, float], ...]) -> float:
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False)) / 2


def test_ca1_el_generador_produce_los_seis_ficheros_de_forma_determinista_y_sin_red(
    tmp_path: Path,
) -> None:
    """CA1. Dado el generador cuando se ejecuta entonces produce también los seis ficheros de
    `caminos/` de forma determinista y sin red."""
    primera, segunda = tmp_path / "primera", tmp_path / "segunda"

    with no_network():
        rutas = generate_caminos.generate(primera)
        generate_caminos.generate(segunda)
        assert generate_catastro.main(["--check"]) == 0  # el punto de entrada de #45 las incluye

    assert [p.name for p in rutas] == sorted(NUEVOS)
    for nombre in NUEVOS:
        assert (primera / nombre).read_bytes() == (segunda / nombre).read_bytes()
        assert (primera / nombre).read_bytes() == (CAMINOS_DIR / nombre).read_bytes()
    assert generate_caminos.differences(CAMINOS_DIR) == []


def test_ca2_el_esquema_es_el_real_y_los_tests_de_caminos_pasan_sin_red() -> None:
    """CA2. Dadas las fixtures nuevas cuando las consumen los tests de caminos entonces el
    esquema es el real y los tests pasan sin red."""
    body = _wfs()
    assert body.startswith(b'<?xml version="1.0" encoding="ISO-8859-1"?>')
    root = ET.fromstring(body)
    assert root.tag == f"{_WFS}FeatureCollection"
    assert root.get("numberMatched") == root.get("numberReturned") == "20"
    for feature in root.iter(f"{_CP}CadastralParcel"):
        assert [child.tag for child in feature] == [
            f"{_CP}{tag}"
            for tag in (
                "areaValue",
                "beginLifespanVersion",
                "endLifespanVersion",
                "geometry",
                "inspireId",
                "label",
                "nationalCadastralReference",
                "referencePoint",
            )
        ]
    for element in root.iter():
        if element.tag in (f"{_GML}MultiSurface", f"{_GML}Surface", f"{_GML}Point"):
            assert element.get("srsName") == "http://www.opengis.net/def/crs/EPSG/0/25830"

    for nombre in NUEVOS[1:]:
        dnppp = (CAMINOS_DIR / nombre).read_bytes()
        assert dnppp.startswith(b'<?xml version="1.0" encoding="utf-8"?>')
        droot = ET.fromstring(dnppp)
        assert droot.tag == f"{_CATASTRO}consulta_dnp"
        assert droot.findtext(f"{_CATASTRO}control/{_CATASTRO}cudnp") == "1"

    with no_network():
        assert len(parse_wfs_parcels(body)) == 20


def test_ca3_ninguna_referencia_ni_geometria_coincide_con_las_reales() -> None:
    """CA3. Dado el test de huellas de la historia hermana cuando se amplía a estas fixtures
    entonces ninguna referencia ni geometría coincide con las reales."""
    referencias = _huellas_set("referencias")
    anillos = _huellas_set("anillos")
    vertices = _huellas_set("vertices")
    hexa = re.compile(r"^[0-9a-f]{64}$")
    assert len(vertices) > 1000  # los 1.287 vértices distintos de las 51 parcelas originales
    assert all(hexa.match(h) for h in referencias | anillos | vertices)

    for nombre in NUEVOS:
        body = (CAMINOS_DIR / nombre).read_bytes()
        assert not reference_fingerprints(body) & referencias, nombre
        assert not ring_fingerprints(body) & anillos, nombre
        assert not vertex_fingerprints(body) & vertices, nombre
    assert len(vertex_fingerprints(_wfs())) > 30  # la huella de vértices ve de verdad los datos


def test_ca4_solo_quedan_versiones_sinteticas() -> None:
    """CA4. Dado el árbol de trabajo cuando se busca `tests/fixtures/caminos/catastro_*`
    entonces solo quedan versiones sintéticas (cabecera XML con comentario "sintético")."""
    en_disco = sorted(p.name for p in CAMINOS_DIR.glob("catastro_*"))
    assert en_disco == sorted(NUEVOS)
    for nombre in ANTIGUOS:
        assert not (CAMINOS_DIR / nombre).exists()
    for nombre in en_disco:
        assert "sintetica" in nombre
        codificacion = "latin-1" if "wfsCP" in nombre else "utf-8"
        cabecera = (CAMINOS_DIR / nombre).read_bytes()[:300].decode(codificacion)
        assert generate_catastro.HEADER_COMMENT in cabecera
        assert "sintétic" in cabecera.lower()


def test_ca5_el_generador_y_el_entorno_son_coherentes() -> None:
    """CA5. Dado `pytest`, `pytest -m acceptance`, `mypy`, `ruff` y `lint-imports` cuando se
    ejecutan entonces todo pasa.

    Los cinco comandos se ejecutan en la PR y en CI. Aquí se fija la parte observable: el
    generador no usa nada de `parcel_intel` ni de red (así `lint-imports` y los tests sin red
    siguen en verde) y lo versionado coincide con lo generado."""
    fuente = (TESTS_DIR / "fixtures" / "generate_caminos.py").read_text(encoding="utf-8")
    importados: set[str] = set()
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Import):
            importados |= {alias.name.split(".")[0] for alias in nodo.names}
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            importados.add(nodo.module.split(".")[0])
    prohibidos = {"parcel_intel", "random", "secrets", "time", "datetime", "socket", "requests"}
    assert not importados & prohibidos
    assert generate_caminos.main(["--check"]) == 0


def test_ca6_registry_recoge_las_fixtures_como_sinteticas() -> None:
    """CA6. Dado `REGISTRY.md` cuando se lee entonces recoge también estas fixtures como
    sintéticas."""
    registry = REGISTRY.read_text(encoding="utf-8")
    inicio = registry.index("Fixtures sintéticas de caminos (historia #46")
    seccion = registry[inicio : registry.index("\n### ", inicio)]

    for nombre in NUEVOS:
        assert nombre in seccion or nombre.replace("catastro_dnppp_sintetica_", "…_") in seccion
    assert "sintétic" in seccion
    assert "uv run python -m tests.fixtures.generate_catastro" in seccion
    for nombre in ANTIGUOS:
        assert nombre not in registry


_REF = re.compile(r"(?<![0-9A-Za-z])(?:\d{5}[A-Z]\d{8}|[0-9A-Z]{14})")
_PAR = re.compile(r"(?<![\d.])\d{6}(?:\.\d+)? \d{7}(?:\.\d+)?(?![\d.])")


def test_ca7_ninguna_huella_de_las_respuestas_originales_en_tests_docs_ni_src() -> None:
    """CA7. Dado el repo completo cuando se buscan las huellas de respuestas originales entonces
    no hay ninguna en `tests/`, `docs/` ni `src/`."""
    referencias = _huellas_set("referencias")
    vertices = _huellas_set("vertices")
    ficheros = subprocess.run(
        ["git", "ls-files", "tests", "docs", "src"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    leidos = 0
    encontrados: dict[str, int] = {}  # ruta -> nº de coincidencias (huellas, nunca datos)
    for ruta in ficheros:
        try:
            texto = (ROOT / ruta).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        leidos += 1
        if ruta == "tests/fixtures/catastro_huellas_reales.json":
            continue
        for candidato in _REF.findall(texto):
            if _sha(candidato) in referencias:
                encontrados[ruta] = encontrados.get(ruta, 0) + 1
        for par in _PAR.findall(texto):
            x, y = par.split(" ")
            if _sha(f"{float(x):.2f} {float(y):.2f}") in vertices:
                encontrados[ruta] = encontrados.get(ruta, 0) + 1
    assert leidos > 200  # el escaneo recorre de verdad el árbol versionado
    assert encontrados == {}


def test_ca8_la_wfs_sintetica_da_el_oraculo_exacto() -> None:
    """CA8. Dada la WFS sintética cuando la parsea `parse_wfs_parcels` (sin red) entonces
    devuelve exactamente **20** parcelas, exactamente **4** con número ≥9000 (`28043A99109101`,
    `28043A99109102`, `28043A99209201`, `28043A99209202`), la `28043A99109101` con
    `area_m2 == 6000` y la `28043A99100001` con `area_m2 == 21025`; cada parcela tiene un único
    anillo de 5 vértices en sentido horario y ninguna se solapa con otra (suma de áreas =
    360 000 m²)."""
    with no_network():
        parcelas = parse_wfs_parcels(_wfs())

    assert len(parcelas) == 20
    caminos = [p["reference"] for p in parcelas if int(p["reference"][9:14]) >= 9000]
    assert sorted(caminos) == list(CAMINOS_9XXX)
    por_ref = {p["reference"]: p for p in parcelas}
    assert por_ref["28043A99109101"]["area_m2"] == 6000
    assert por_ref["28043A99100001"]["area_m2"] == 21025

    limites: list[tuple[float, float, float, float]] = []
    total = 0.0
    for parcela in parcelas:
        assert len(parcela["rings"]) == 1
        anillo = parcela["rings"][0]
        assert len(anillo) == 5 and anillo[0] == anillo[-1]
        area_con_signo = _shoelace(anillo)
        assert area_con_signo < 0  # sentido horario
        total += -area_con_signo
        xs, ys = [x for x, _ in anillo], [y for _, y in anillo]
        limites.append((min(xs), min(ys), max(xs), max(ys)))
        assert parcela["area_m2"] == pytest.approx(-area_con_signo)
    assert total == pytest.approx(360_000.0)
    for i, (ax0, ay0, ax1, ay1) in enumerate(limites):
        for bx0, by0, bx1, by1 in limites[i + 1 :]:
            solapa = min(ax1, bx1) > max(ax0, bx0) and min(ay1, by1) > max(ay0, by0)
            assert not solapa


def test_ca9_las_dnppp_sinteticas_dan_vt_y_ssp_distinto_del_areavalue() -> None:
    """CA9. Dadas las cinco DNPPP sintéticas cuando se leen `lspr/spr/dspr/{ccc,ssp}` entonces
    las cuatro ≥9000 dan `VT` y la `991/1` da `C-`, y `ssp` de `9101` (6011) y de `9201` (3024)
    **difiere** del `areaValue` de la WFS (6000 y 3000), como en el dato real."""
    assert _dnppp("catastro_dnppp_sintetica_pol991_parc1.xml") == ("C-", 21025)
    esperado = {
        "catastro_dnppp_sintetica_pol991_parc9101.xml": 6011,
        "catastro_dnppp_sintetica_pol991_parc9102.xml": 2900,
        "catastro_dnppp_sintetica_pol992_parc9201.xml": 3024,
        "catastro_dnppp_sintetica_pol992_parc9202.xml": 1950,
    }
    for nombre, ssp in esperado.items():
        assert _dnppp(nombre) == ("VT", ssp)

    areas = {p["reference"]: p["area_m2"] for p in parse_wfs_parcels(_wfs())}
    ssp_9101 = esperado["catastro_dnppp_sintetica_pol991_parc9101.xml"]
    ssp_9201 = esperado["catastro_dnppp_sintetica_pol992_parc9201.xml"]
    assert areas["28043A99109101"] == 6000 != ssp_9101
    assert areas["28043A99209201"] == 3000 != ssp_9201
    # Ningún campo de titularidad en la plantilla.
    for nombre in NUEVOS[1:]:
        raiz = ET.fromstring((CAMINOS_DIR / nombre).read_bytes())
        etiquetas = {e.tag.rsplit("}", 1)[-1] for e in raiz.iter()}
        assert not etiquetas & {"nif", "nom", "np2", "titular", "ldp"}
