"""Tests de aceptación de la historia #45: fixtures sintéticas de Catastro."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from parcel_intel.adapters.catastro.adapter import CatastroAdapter
from parcel_intel.adapters.catastro.parsing import (
    parse_cpmrc_centroid,
    parse_wfs_buildings,
    parse_wfs_parcels,
)
from parcel_intel.adapters.hydrography.parsing import parse_watercourse_features
from parcel_intel.adapters.protected_areas.parsing import parse_wfs_protected_areas
from parcel_intel.domain.geometry import (
    Geometry,
    LineGeometry,
    bbox_with_margin,
    distance_polygon_to_line,
    geometries_overlap,
)
from parcel_intel.domain.protected_area import ProtectedArea
from parcel_intel.domain.report import EnrichedParcelReport, ParcelReport
from parcel_intel.domain.rule import evaluate_rules
from parcel_intel.ports.errors import ParcelNotFoundError
from tests.adapters.catastro.helpers import (
    FIXTURES_DIR,
    VILLACONEJOS_BARRANCO_DEL_MONTERO_M,
    SequenceHttpGetter,
)
from tests.adapters.hydrography.helpers import FIXTURES_DIR as DPH_FIXTURES_DIR
from tests.adapters.protected_areas.helpers import FIXTURES_DIR as PROTECTED_AREAS_FIXTURES_DIR
from tests.domain.test_rule import (
    _land_classification,
    _red_natura_rule,
    _report,
    _rule,
    _watercourse,
)
from tests.factories import make_parcel, make_provenance
from tests.fixtures import generate_catastro
from tests.fixtures.catastro_fingerprints import reference_fingerprints, ring_fingerprints
from tests.network_guard import NetworkBlockedError, no_network

pytestmark = pytest.mark.acceptance

TESTS_DIR = Path(__file__).parents[1]
HUELLAS = TESTS_DIR / "fixtures" / "catastro_huellas_reales.json"
GENERATOR = TESTS_DIR / "fixtures" / "generate_catastro.py"

_GML = "{http://www.opengis.net/gml/3.2}"
_WFS = "{http://www.opengis.net/wfs/2.0}"
_CP = "{http://inspire.ec.europa.eu/schemas/cp/4.0}"
_BU_EXT = "{http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0}"
_CATASTRO = "{http://www.catastro.meh.es/}"
_OWS = "{http://www.opengis.net/ows/1.1}"

_CP_FILES = (
    "wfsCP_colmenar_rustica_por_centroide.xml",
    "wfsCP_villaconejos_rustica_por_centroide.xml",
    "wfsCP_colmenar_bbox_denso.xml",
    "wfsCP_colmenar_parcela_con_edificios.xml",
)
_BU_FILES = ("wfsBU_colmenar_dense_bbox.xml", "wfsBU_colmenar_urbano_por_centroide.xml")
_CPMRC_FILES = (
    "cpmrc_colmenar_14char.xml",
    "cpmrc_villaconejos_14char.xml",
    "cpmrc_colmenar_urbano_14char.xml",
    "cpmrc_colmenar_edificio.xml",
    "cpmrc_no_encontrada.xml",
)


def _adapter(*fixtures: str) -> tuple[CatastroAdapter, SequenceHttpGetter]:
    http_get = SequenceHttpGetter([FIXTURES_DIR / name for name in fixtures])
    return CatastroAdapter(provincia="MADRID", municipio="X", http_get=http_get), http_get


def _generator_imports() -> set[str]:
    """Paquetes de primer nivel que importa el generador."""
    modules: set[str] = set()
    for node in ast.walk(ast.parse(GENERATOR.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def _parcel_geometry(fixture: str, reference: str) -> Geometry:
    parcels = parse_wfs_parcels((FIXTURES_DIR / fixture).read_bytes())
    target = next(p for p in parcels if p["reference"] == reference)
    return Geometry(rings=target["rings"], srid=25830)


def test_ca1_generador_determinista_y_sin_red(tmp_path: Path) -> None:
    """CA1. Dado el script generador versionado (p. ej. `tests/fixtures/generate_catastro.py`)
    cuando se ejecuta dos veces entonces produce ficheros idénticos byte a byte (determinista,
    semilla fija) y sin red."""
    primera, segunda = tmp_path / "primera", tmp_path / "segunda"

    with no_network():
        assert generate_catastro.main(["--destino", str(primera)]) == 0
        assert generate_catastro.main(["--destino", str(segunda)]) == 0
        assert generate_catastro.main(["--check"]) == 0  # lo versionado es lo que genera

    nombres = sorted(p.name for p in primera.iterdir())
    assert nombres == sorted(generate_catastro.FIXTURES)
    assert nombres == sorted(p.name for p in segunda.iterdir())
    for nombre in nombres:
        assert (primera / nombre).read_bytes() == (segunda / nombre).read_bytes()

    # "Semilla fija" se cumple con cero aleatoriedad: ni azar, ni reloj, ni red.
    forbidden = {"random", "secrets", "time", "datetime", "socket", "requests", "urllib", "uuid"}
    assert not _generator_imports() & forbidden

    # El bloqueo de red funciona de verdad: una conexión dentro del bloque falla.
    import socket

    with no_network(), pytest.raises(NetworkBlockedError):
        socket.create_connection(("example.invalid", 80))


def test_ca2_esquema_del_servicio_y_adapter_sin_red() -> None:
    """CA2. Dadas las fixtures generadas cuando las parsea el adapter de Catastro entonces el
    esquema GML/XML es el real (namespaces, elementos, CRS EPSG:25830) y los tests del adapter
    pasan sin red."""
    for name in _CP_FILES:
        body = (FIXTURES_DIR / name).read_bytes()
        assert body.startswith(b'<?xml version="1.0" encoding="ISO-8859-1"?>')
        root = ET.fromstring(body)
        assert root.tag == f"{_WFS}FeatureCollection"
        features = list(root.iter(f"{_CP}CadastralParcel"))
        assert features and root.get("numberReturned") == str(len(features))
        for feature in features:
            children = [child.tag for child in feature]
            assert children == [
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
    for name in _BU_FILES:
        body = (FIXTURES_DIR / name).read_bytes()
        assert body.startswith(b'<?xml version="1.0" encoding="ISO-8859-1"?>')
        root = ET.fromstring(body)
        assert root.tag == f"{_GML}FeatureCollection"
        assert root.get(f"{_GML}id") == "ES.SDGC.BU"
        for element in root.iter():
            if element.tag in (f"{_GML}Surface", f"{_GML}Envelope"):
                assert element.get("srsName") == "urn:ogc:def:crs:EPSG::25830"
    buildings_root = ET.fromstring((FIXTURES_DIR / _BU_FILES[0]).read_bytes())
    assert len(list(buildings_root.iter(f"{_BU_EXT}Building"))) == 11
    for name in _CPMRC_FILES:
        body = (FIXTURES_DIR / name).read_bytes()
        assert body.startswith(b'<?xml version="1.0" encoding="utf-8"?>')
        root = ET.fromstring(body)
        assert root.tag == f"{_CATASTRO}consulta_coordenadas"
        srs = root.find(f".//{_CATASTRO}srs")
        assert srs is None or srs.text == "EPSG:25830"

    # El generador no usa el parser que comprueba sus datos (ni nada de parcel_intel).
    assert "parcel_intel" not in _generator_imports()

    with no_network():
        adapter, _ = _adapter(
            "cpmrc_colmenar_14char.xml", "wfsCP_colmenar_rustica_por_centroide.xml"
        )
        assert adapter.get_parcel("99043A90100001").area_m2 == 844.0
        adapter, _ = _adapter(
            "cpmrc_colmenar_edificio.xml",
            "wfsCP_colmenar_parcela_con_edificios.xml",
            "wfsBU_colmenar_dense_bbox.xml",
        )
        assert [b.cadastral_reference for b in adapter.get_buildings("9900105ZZ0000S")] == [
            "9900105ZZ0000S"
        ]


def test_ca3_ninguna_referencia_ni_anillo_coincide_con_los_originales() -> None:
    """CA3. Dadas las geometrías y referencias catastrales cuando se comparan con las
    originales entonces ninguna coincide: referencias inventadas o desplazadas, geometrías
    simplificadas o transformadas (ni copias ni recortes). Un test lo comprueba contra una
    lista de huellas (hash) de las referencias reales, sin incluir datos reales."""
    huellas = json.loads(HUELLAS.read_text(encoding="utf-8"))
    assert huellas["algoritmo"] == "sha256"
    originales_ref = set(huellas["referencias"])
    originales_anillos = set(huellas["anillos"])
    assert len(originales_ref) > 100 and len(originales_anillos) > 100
    # Solo huellas: 64 caracteres hexadecimales, ningún dato real en claro.
    hexa = re.compile(r"^[0-9a-f]{64}$")
    assert all(hexa.match(h) for h in originales_ref | originales_anillos)

    referencias_sinteticas: set[str] = set()
    for name, body in generate_catastro.build_all().items():
        assert not reference_fingerprints(body) & originales_ref, name
        assert not ring_fingerprints(body) & originales_anillos, name
        text = body.decode("latin-1")
        assert "D.G. del Catastro" not in text and "sedecatastro" not in text, name
        root = ET.fromstring(body)
        for element in root.iter():
            local = element.tag.rsplit("}", 1)[-1]
            if local in ("nationalCadastralReference", "localId") and element.text:
                referencias_sinteticas.add(element.text)
            if local in ("CadastralParcel", "Building"):
                referencias_sinteticas.add((element.get(f"{_GML}id") or "").rsplit(".", 1)[-1])
            if local == "pc":
                referencias_sinteticas.add("".join(child.text or "" for child in element))
    assert len(referencias_sinteticas) > 100
    assert all(ref.startswith("99") for ref in referencias_sinteticas)


def test_ca4_no_queda_ninguna_respuesta_original() -> None:
    """CA4. Dado el árbol de trabajo cuando se lista `tests/fixtures/catastro/` entonces no
    queda ninguna respuesta cruda original; los GetCapabilities se sustituyen por versiones
    mínimas sintéticas con el mismo esquema."""
    en_disco = {p.name for p in FIXTURES_DIR.iterdir() if p.name != generate_catastro.README_NAME}
    assert en_disco == set(generate_catastro.build_all())
    for name in en_disco:
        assert (FIXTURES_DIR / name).read_bytes() == generate_catastro.build_all()[name]

    for name, feature_type, default_crs in (
        ("wfsCP_getcapabilities.xml", "cp:CadastralParcel", "urn:ogc:def:crs:EPSG::4326"),
        ("wfsBU_getcapabilities.xml", "bu:Building", "urn:ogc:def:crs:EPSG::25830"),
    ):
        root = ET.fromstring((FIXTURES_DIR / name).read_bytes())
        assert root.tag == f"{_WFS}WFS_Capabilities" and root.get("version") == "2.0.0"
        title = root.find(f"{_OWS}ServiceIdentification/{_OWS}Title")
        assert title is not None and title.text == "Servicio WFS sintético para tests"
        operations = {op.get("name") for op in root.iter(f"{_OWS}Operation")}
        assert operations == {"GetCapabilities", "DescribeFeatureType", "GetFeature"}
        types = root.findall(f"{_WFS}FeatureTypeList/{_WFS}FeatureType")
        assert [t.findtext(f"{_WFS}Name") for t in types] == [feature_type]
        assert types[0].findtext(f"{_WFS}DefaultCRS") == default_crs
        tags = {element.tag.rsplit("}", 1)[-1] for element in root.iter()}
        assert not tags & {"Abstract", "Keywords", "ServiceProvider"}
    cp_types = ET.fromstring((FIXTURES_DIR / "wfsCP_getcapabilities.xml").read_bytes())
    assert [e.text for e in cp_types.iter(f"{_WFS}OtherCRS")] == ["urn:ogc:def:crs:EPSG::25830"]


def test_ca5_los_tests_que_dependian_de_valores_concretos_usan_los_sinteticos() -> None:
    """CA5. Dado `pytest`, `pytest -m acceptance`, `mypy`, `ruff` y `lint-imports` cuando se
    ejecutan entonces todo pasa; los tests que dependían de valores concretos (superficies,
    nº de edificios, refcats) se adaptan a los sintéticos manteniendo la intención de la
    prueba.

    Los cinco comandos se ejecutan en la PR y en CI. Aquí se fija la parte observable: los
    valores concretos de las fixtures (superficies, edificios, referencias) son los sintéticos
    y ningún test que lee fixtures de Catastro filtra ya por una referencia de las originales."""
    adapter, _ = _adapter(
        "cpmrc_villaconejos_14char.xml", "wfsCP_villaconejos_rustica_por_centroide.xml"
    )
    assert adapter.get_parcel("99170A901000010000ZZ").area_m2 == 25290.0
    adapter, _ = _adapter("cpmrc_colmenar_urbano_14char.xml", "wfsCP_colmenar_bbox_denso.xml")
    assert adapter.get_parcel("99043A93700001").area_m2 == 320.0
    adapter, _ = _adapter(
        "cpmrc_colmenar_edificio.xml",
        "wfsCP_colmenar_parcela_con_edificios.xml",
        "wfsBU_colmenar_dense_bbox.xml",
    )
    (edificio,) = adapter.get_buildings("9900105ZZ0000S")
    assert (edificio.area_m2, edificio.construction_year, len(edificio.geometry.rings)) == (
        96.0,
        1975,
        3,
    )

    # Referencias de las respuestas originales: solo se comparan sus huellas, sin citarlas.
    originales = set(json.loads(HUELLAS.read_text(encoding="utf-8"))["referencias"])
    for path in TESTS_DIR.rglob("*.py"):
        module = ast.parse(path.read_text(encoding="utf-8"))
        if not _functions_reading_catastro(module):
            continue
        for literal in _code_strings(module):
            for candidato in re.findall(r"(?<![0-9A-Za-z])[0-9A-Z]{14}(?![0-9A-Za-z])", literal):
                huella = hashlib.sha256(candidato.encode("utf-8")).hexdigest()
                assert huella not in originales, f"{path}: {literal}"


def test_ca6_registry_documenta_fixtures_sinteticas() -> None:
    """CA6. Dado `src/parcel_intel/sources/REGISTRY.md` cuando se lee la sección de Catastro
    entonces indica que las fixtures son sintéticas, cómo regenerarlas y que la verificación
    real se hizo contra el servicio (con fecha)."""
    registry = (TESTS_DIR.parent / "src" / "parcel_intel" / "sources" / "REGISTRY.md").read_text(
        encoding="utf-8"
    )
    start = registry.index("## Catastro (INSPIRE)")
    section = registry[start : registry.index("\n## ", start + 1)]

    assert "sintéticas" in section
    assert "uv run python -m tests.fixtures.generate_catastro" in section
    assert "uv run python -m tests.fixtures.generate_catastro --check" in section
    assert "verificación real contra el servicio" in section
    assert "2026-10-15" in section and "2026-11-25" in section
    # Cada fixture original citada en la sección se marca como retirada.
    for cited in set(re.findall(r"`(?:tests/fixtures/catastro/)?(\w+\.xml)`", section)):
        for match in re.finditer(re.escape(cited) + r"`", section):
            following = section[match.end() : match.end() + 60]
            assert "respuesta original retirada en la historia #45" in following, cited


@pytest.mark.parametrize(
    ("fixture", "reference", "margin_m", "expected"),
    [
        (
            "wfsCP_colmenar_rustica_por_centroide.xml",
            "99043A90100001",
            2.0,
            (467548.15, 4442009.35, 467616.92, 4442039.4),
        ),
        (
            "wfsCP_villaconejos_rustica_por_centroide.xml",
            "99170A90100001",
            2.0,
            (454553.78, 4441392.86, 454827.45, 4441584.42),
        ),
        (
            "wfsCP_colmenar_parcela_con_edificios.xml",
            "9900105ZZ0000S",
            10.0,
            (457143.87, 4436008.27, 457193.48, 4436065.23),
        ),
        (
            "wfsCP_colmenar_parcela_con_edificios.xml",
            "9900105ZZ0000S",
            20.0,
            (457133.87, 4435998.27, 457203.48, 4436075.23),
        ),
    ],
)
def test_ca7_bbox_de_las_tres_parcelas_cruzadas_no_cambia(
    fixture: str, reference: str, margin_m: float, expected: tuple[float, float, float, float]
) -> None:
    """CA7 (añadido por el arquitecto). Dadas las tres parcelas sintéticas que otros tests
    cruzan con respuestas reales de otras fuentes (rústica de Colmenar, rústica de Villaconejos
    y urbana con edificio) cuando se calcula `bbox_with_margin` entonces da exactamente los
    mismos bbox que ya afirman los tests de IDEM, DPH, vías pecuarias, Red Natura, PNOA y
    Sentinel-2. Esos tests pasan **sin cambiar ningún valor numérico de bbox**; solo cambian la
    referencia que filtran."""
    bbox = bbox_with_margin(_parcel_geometry(fixture, reference), margin_m)

    assert bbox == pytest.approx(expected, abs=1e-6)


def test_ca8_distancia_no_trivial_al_barranco_del_montero() -> None:
    """CA8 (añadido por el arquitecto). Dada la parcela sintética de Villaconejos y el cauce
    real "Barranco del Montero" cuando se calcula `distance_polygon_to_line` entonces el
    resultado es **mayor que 0**, coincide con el valor de control calculado con `shapely`
    antes de escribir el test (estimación a mano del arquitecto: ≈ 3,69 m) y la regla
    `dph_cauce` de 100 m produce el hallazgo con ese `measured_value`. La misma parcela sigue
    sin solapar con Red Natura 2000."""
    raw_parcel = next(
        p
        for p in parse_wfs_parcels(
            (FIXTURES_DIR / "wfsCP_villaconejos_rustica_por_centroide.xml").read_bytes()
        )
        if p["reference"] == "99170A90100001"
    )
    geometry = Geometry(rings=raw_parcel["rings"], srid=25830)
    raw_watercourse = parse_watercourse_features(
        (
            DPH_FIXTURES_DIR
            / "features_watercourse_villaconejos_rustica_margin2m_barranco_montero.json"
        ).read_bytes()
    )[0]
    assert raw_watercourse["name"] == "Barranco del Montero"

    distance = distance_polygon_to_line(
        geometry, LineGeometry(points=raw_watercourse["points"], srid=25830)
    )

    assert distance > 0
    assert distance == pytest.approx(VILLACONEJOS_BARRANCO_DEL_MONTERO_M, abs=1e-9)
    assert abs(VILLACONEJOS_BARRANCO_DEL_MONTERO_M - 3.686) < 0.05  # estimación del arquitecto

    parcel = make_parcel(
        cadastral_reference=raw_parcel["reference"],
        rings=raw_parcel["rings"],
        area_m2=raw_parcel["area_m2"],
    )
    report = EnrichedParcelReport(
        report=ParcelReport(parcel=parcel, buildings=()),
        orthophoto=None,
        ndvi_summary=None,
        boe_notices=None,
        bocm_notices=None,
        land_classifications=(_land_classification("Suelo No Urbanizable Común"),),
        watercourses=(_watercourse(raw_watercourse["points"], name="Barranco del Montero"),),
        flood_hazard=None,
        livestock_trails=None,
        protected_areas=None,
    )
    (finding,) = evaluate_rules(report, (_rule(meters=100.0),))
    assert finding.rule.spatial.layer == "dph_cauce"
    assert finding.evidence[0].measured_value == pytest.approx(
        VILLACONEJOS_BARRANCO_DEL_MONTERO_M, abs=1e-9
    )

    raw_area = parse_wfs_protected_areas(
        (
            PROTECTED_AREAS_FIXTURES_DIR / "wfs_getfeature_bbox_villaconejos_rustica_margin2m.xml"
        ).read_bytes()
    )[0]
    zona = Geometry(rings=raw_area["rings"], srid=25830)
    assert not geometries_overlap(geometry, zona)
    area = ProtectedArea(
        plan_code=raw_area["plan_code"],
        plan_name=raw_area["plan_name"],
        zone_code=raw_area["zone_code"],
        zone_name=raw_area["zone_name"],
        geometry=zona,
        provenance=make_provenance(source="idem"),
    )
    red_natura = _report(protected_areas=(area,), parcel_rings=raw_parcel["rings"])
    assert evaluate_rules(red_natura, (_red_natura_rule(),)) == ()


def test_ca9_casos_limite_del_adapter() -> None:
    """CA9 (añadido por el arquitecto). Dadas las fixtures sintéticas cuando se ejecutan los
    tests del adapter entonces cubren estos casos límite: (a) edificio de 3 cuerpos dentro de la
    parcela, devuelto como 1 edificio con 3 anillos; (b) edificio vecino con el centroide
    **dentro de la envolvente** de la parcela pero **fuera del polígono**, que no se devuelve;
    (c) parcela objetivo `MultiSurface` de 2 superficies dentro de un bbox denso de 121
    parcelas; (d) parcela vecina con un `gml:interior`; (e) referencia no encontrada
    (`cuerr=1`); (f) referencia de 20 caracteres normalizada a 14."""
    # (a) y (b)
    adapter, _ = _adapter(
        "cpmrc_colmenar_edificio.xml",
        "wfsCP_colmenar_parcela_con_edificios.xml",
        "wfsBU_colmenar_dense_bbox.xml",
    )
    buildings = adapter.get_buildings("9900105ZZ0000S")
    assert len(buildings) == 1 and len(buildings[0].geometry.rings) == 3
    vecino = next(
        b
        for b in parse_wfs_buildings((FIXTURES_DIR / "wfsBU_colmenar_dense_bbox.xml").read_bytes())
        if b["reference"] == "9900108ZZ0000S"
    )
    ring = vecino["rings"][0][:-1]
    cx = sum(x for x, _ in ring) / len(ring)
    cy = sum(y for _, y in ring) / len(ring)
    minx, miny, maxx, maxy = (457153.87, 4436018.27, 457183.48, 4436055.23)
    assert minx <= cx <= maxx and miny <= cy <= maxy
    assert abs(cx - 457168.675) / 14.805 + abs(cy - 4436036.75) / 18.48 > 1  # fuera del rombo

    # (c)
    denso = parse_wfs_parcels((FIXTURES_DIR / "wfsCP_colmenar_bbox_denso.xml").read_bytes())
    assert len(denso) == 121
    adapter, _ = _adapter("cpmrc_colmenar_urbano_14char.xml", "wfsCP_colmenar_bbox_denso.xml")
    assert len(adapter.get_parcel("99043A93700001").geometry.rings) == 2

    # (d)
    villaconejos = (FIXTURES_DIR / "wfsCP_villaconejos_rustica_por_centroide.xml").read_bytes()
    root = ET.fromstring(villaconejos)
    con_hueco = [
        feature.get(f"{_GML}id")
        for feature in root.iter(f"{_CP}CadastralParcel")
        if feature.find(f".//{_GML}interior") is not None
    ]
    assert con_hueco == ["ES.SDGC.CP.99170A90100002"]

    # (e)
    adapter, _ = _adapter("cpmrc_no_encontrada.xml")
    with pytest.raises(ParcelNotFoundError):
        adapter.get_parcel("99043A99999999")
    with pytest.raises(ParcelNotFoundError):
        parse_cpmrc_centroid((FIXTURES_DIR / "cpmrc_no_encontrada.xml").read_bytes(), "x")

    # (f)
    adapter, http_get = _adapter(
        "cpmrc_colmenar_14char.xml", "wfsCP_colmenar_rustica_por_centroide.xml"
    )
    parcel = adapter.get_parcel("99043A901000010000ZZ")
    assert parcel.cadastral_reference == "99043A90100001"
    assert http_get.calls[0][1]["RC"] == "99043A90100001"


def _catastro_dir_names(module: ast.Module) -> set[str]:
    """Nombres con los que un módulo de tests se refiere a `tests/fixtures/catastro/`."""
    names: set[str] = set()
    for node in module.body:
        if isinstance(node, ast.ImportFrom) and node.module == "tests.adapters.catastro.helpers":
            names |= {a.asname or a.name for a in node.names if a.name == "FIXTURES_DIR"}
        if isinstance(node, ast.Assign):
            names |= {
                t.id
                for t in node.targets
                if isinstance(t, ast.Name) and "CATASTRO_FIXTURES" in t.id
            }
    return names


def _functions_reading_catastro(module: ast.Module) -> list[ast.FunctionDef]:
    dirs = _catastro_dir_names(module)
    return [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.FunctionDef)
        and any(isinstance(n, ast.Name) and n.id in dirs for n in ast.walk(node))
    ]


def _code_strings(module: ast.Module) -> set[str]:
    """Literales de texto del módulo, sin contar los docstrings (que citan criterios)."""
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(module)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return {
        node.value
        for node in ast.walk(module)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def test_ca10_ningun_nombre_presenta_lo_sintetico_como_captura_de_red() -> None:
    """CA10 (añadido por el arquitecto, lección de la historia 0012). Dado el árbol de tests
    cuando se buscan nombres de fixture, de test o de helper que usen datos de Catastro
    entonces ninguno dice "real". Cada fichero generado lleva tras la declaración XML el
    comentario `FIXTURE SINTÉTICA` y ninguno conserva el comentario de origen de la D.G. del
    Catastro."""
    for path in FIXTURES_DIR.iterdir():
        assert "real" not in path.name.lower(), path.name

    # Funciones (tests y helpers) que leen directamente una fixture de Catastro. Las que solo
    # llaman a un helper y dicen "real" se refieren a la otra fuente (PNOA, IDEM...), que sí
    # lo es; por eso se renombran los helpers y no esos tests.
    offenders: list[str] = []
    readers = 0
    for path in TESTS_DIR.rglob("*.py"):
        for function in _functions_reading_catastro(ast.parse(path.read_text(encoding="utf-8"))):
            readers += 1
            if "real" in function.name.lower():
                offenders.append(f"{path.relative_to(TESTS_DIR)}::{function.name}")
    assert readers > 20  # la detección encuentra de verdad los tests y helpers afectados
    assert offenders == []

    for name, body in generate_catastro.build_all().items():
        lines = body.split(b"\n")
        assert lines[0].startswith(b"<?xml "), name
        encoding = "utf-8" if b'encoding="utf-8"' in lines[0].lower() else "latin-1"
        assert lines[1].decode(encoding) == generate_catastro.HEADER_COMMENT, name
        assert "FIXTURE SINTÉTICA" in generate_catastro.HEADER_COMMENT
        assert b"D.G. del Catastro" not in body, name
