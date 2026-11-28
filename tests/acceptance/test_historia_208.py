"""Historia #208: vuelos históricos de la Comunidad de Madrid (1975 y 1991) en la serie de
imágenes de comparación (ADR 0052).

Datos SINTÉTICOS salvo las teselas reales de la IDEM de #206/#207
(`tests/fixtures/idem_vuelos/`): la no blanca de 1975 sirve como imagen de los dos vuelos
de Madrid y la blanca (fuera de cobertura) como respuesta «sin cobertura».

Oráculo del diseño (lección 0017: se compara con el literal, no solo con `window_url`): el
tramo `LINESTRING(463700 4437250, 463800 4437250)` da una ventana
`463638, 4437138, 463862, 4437362` de 448 px, trazo `[[[124.0, 224.0], [324.0, 224.0]]]`, y
las URL de `ORACLE_URL_1975`/`ORACLE_URL_1991`.

El caso de dos ventanas de CA13 (`tests/fixtures/candidatos_publicar/generar_idem.py`)
encadena los productores reales: `imagenes-comparacion` → `publicar-candidatos`.

Actualizado por #315 (CA10, ADR 0057): `publicar-candidatos` lee también las capas
derivadas y `curated/historico/`; `generar_idem.py` le pasa las capas sintéticas de la
fixture y una cobertura histórica vacía, y la fixture del visor
(`tests/fixtures/site/candidatos_comparacion_idem_28043.geojson`) se regeneró con la
propiedad `convergencia`. Las comprobaciones de CA13 sobre las imágenes no cambian.
"""

import copy
import hashlib
import json
import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from parcel_intel.adapters.comparison_files import read_stretches
from parcel_intel.adapters.comparison_files.manifest_reader import parse_manifest
from parcel_intel.adapters.comparison_windows.router import (
    FlightRoutedWindowAdapter,
    comparison_window_url,
)
from parcel_intel.adapters.idem_vuelos.window import WMS_URL as IDEM_WMS_URL
from parcel_intel.adapters.idem_vuelos.window import IdemVuelosWindowAdapter
from parcel_intel.adapters.pnoa.window import PnoaWindowAdapter
from parcel_intel.adapters.raw_cache import CachedRawFetcher
from parcel_intel.application.build_comparison_images import BuildComparisonImagesUseCase
from parcel_intel.cli import main
from parcel_intel.domain.comparison_image import (
    COMPARISON_POLICY,
    COMPARISON_SLOTS,
    DECLARED_GAPS,
    FLIGHTS,
    IDEM_ATTRIBUTION,
    IDEM_NOTICE,
    StretchRequest,
    attribution_for,
)
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.orthophoto import HistoricalVintage, Orthophoto, OrthophotoWindow
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.published_comparison import SERVED_BY_TEXT
from tests.fixtures.candidatos_publicar import generar, generar_idem
from tests.site.nodo import assert_node_tests_pass

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).resolve().parents[2]
NOTICE = ROOT / "NOTICE"
INE = "28043"
DAY = date(2026, 11, 27)
RERUN = "vuelve a ejecutar imagenes-comparacion"
ORACLE_ID = "0123456789abcdef"
ORACLE_WINDOW = OrthophotoWindow(463638, 4437138, 463862, 4437362, 25830, 448, 448)
ORACLE_URL_1975 = (
    "https://idem.comunidad.madrid/srvimagenes2/ogc/wms/visorcartografia2?bbox=463638%2C4437138"
    "%2C463862%2C4437362&crs=EPSG%3A25830&format=image%2Fpng&height=448"
    "&layers=fotosAereasHistoricas_1970-1979_orto-1975-ed50&request=GetMap&service=WMS"
    "&styles=&version=1.3.0&width=448"
)
ORACLE_URL_1991 = ORACLE_URL_1975.replace(
    "fotosAereasHistoricas_1970-1979_orto-1975-ed50",
    "fotosAereasHistoricas_1990-1999_orto-1991-ed50",
)
IDEM_DERIVED = "Obra derivada de " + IDEM_ATTRIBUTION
SLOT_ORDER = ["1956-1957", "1975", "1991", "1997-2003", "2006-2011", "2014-2020", "reciente"]
XML_ERROR = (
    b'<?xml version="1.0"?><ServiceExceptionReport><ServiceException/></ServiceExceptionReport>'
)


# --- Utilidades -----------------------------------------------------------------------


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshot(directory: Path) -> dict[str, bytes]:
    if not directory.exists():
        return {}
    return {
        str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob("*") if p.is_file()
    }


def _run(args: list[str]) -> int:
    parsed = main._build_parser().parse_args(args)
    code: int = parsed.func(parsed)
    return code


def _oracle_stretches(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25830"}},
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"id": ORACLE_ID},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[463700, 4437250], [463800, 4437250]],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


class Servers:
    """`http_get` falso: IGN con contenido; IDEM según `idem(params)`."""

    def __init__(self, idem: Callable[[dict[str, str]], bytes] | None = None) -> None:
        self.idem = idem or (lambda params: generar_idem.IDEM_REAL_PNG)
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls.append((url, dict(params)))
        if url == IDEM_WMS_URL:
            return self.idem(params)
        return generar_idem.FakeServers()(url, params)


def _comparison(
    tmp_path: Path,
    http: Servers,
    *,
    offline: bool = False,
    sleep: Callable[[float], None] = lambda s: None,
) -> int:
    tmp_path.mkdir(parents=True, exist_ok=True)
    tramos = _oracle_stretches(tmp_path / "tramos.geojson")
    use_case = main.build_comparison_use_case(
        tmp_path / "raw",
        tmp_path / "comparacion",
        offline=offline,
        http_get=http,
        today=lambda: DAY,
        sleep=sleep,
    )
    try:
        use_case.execute(INE, read_stretches(tramos, INE))
    except Exception:
        return 1
    return 0


def _oracle_window(tmp_path: Path) -> Any:
    (stretch,) = _load(tmp_path / "comparacion" / f"{INE}.json")["tramos"]
    (window,) = stretch["ventanas"]
    return window


@pytest.fixture
def case(tmp_path: Path) -> dict[str, Any]:
    """El caso de dos ventanas de CA13 con sus entradas y su publicación."""
    base = generar_idem.write_inputs(tmp_path / "entradas")
    site = tmp_path / "site"
    assert _run(generar_idem.publish_args(base, site)) == 0
    return {
        "base": base,
        "site": site,
        "manifest": _load(base / "comparacion" / f"{INE}.json"),
        "document": _load(site / "candidatos" / f"{INE}.geojson"),
        "sidecar": _load(site / "candidatos" / f"{INE}.geojson.procedencia.json"),
    }


def _variant(
    case: dict[str, Any], tmp_path: Path, change: Callable[[dict[str, Any]], object]
) -> Path:
    """Copia de las entradas del caso con el manifiesto cambiado."""
    document = copy.deepcopy(case["manifest"])
    change(document)
    directory = tmp_path / "variante"
    directory.mkdir()
    (directory / f"{INE}.json").write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8"
    )
    return directory


def _publish_fails(
    case: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    comparacion: Path,
    *fragments: str,
) -> None:
    args = generar_idem.publish_args(case["base"], tmp_path / "site-fallo")
    args[args.index("--comparacion") + 1] = str(comparacion)
    capsys.readouterr()
    assert _run(args) == 1
    err = capsys.readouterr().err
    for fragment in fragments:
        assert fragment in err, (fragment, err)
    assert _snapshot(tmp_path / "site-fallo") == {}


def _idem_image(document: dict[str, Any], window: int, slot: str) -> dict[str, Any]:
    (stretch,) = document["tramos"]
    images = stretch["ventanas"][window]["imagenes"]
    found: dict[str, Any] = next(i for i in images if i["franja"] == slot)
    return found


# --- Criterios ------------------------------------------------------------------------


def test_ca1_cada_ventana_trae_1975_y_1991_con_atribucion_y_procedencia(tmp_path: Path) -> None:
    """CA1. Dado un tramo con cobertura en los vuelos de Madrid, cuando se ejecuta
    `imagenes-comparacion`, entonces cada ventana trae también las imágenes de 1975 y 1991 de
    la IDEM, con atribución literal de `NOTICE` precedida de «Obra derivada de», periodo,
    resolución 0,5 m, procedencia (fuente `idem-vuelos-historicos`, URL canónica, fecha,
    CC BY 4.0, publicable) y sha256, en orden cronológico entre las franjas del IGN."""
    assert _comparison(tmp_path, Servers()) == 0
    window = _oracle_window(tmp_path)
    assert window["bbox"] == [463638, 4437138, 463862, 4437362]
    assert (window["ancho_px"], window["alto_px"]) == (448, 448)
    assert window["trazo_px"] == [[[124.0, 224.0], [324.0, 224.0]]]
    assert [i["franja"] for i in window["imagenes"]] == SLOT_ORDER
    assert window["omitidas"] == []
    notice = NOTICE.read_text(encoding="utf-8")
    assert f"`{IDEM_ATTRIBUTION}`" in notice
    cases: tuple[tuple[str, HistoricalVintage, str], ...] = (
        ("1975", "CM_1975", ORACLE_URL_1975),
        ("1991", "CM_1991", ORACLE_URL_1991),
    )
    for slot, vintage, url in cases:
        image = next(i for i in window["imagenes"] if i["franja"] == slot)
        assert image == {
            "franja": slot,
            "vuelo": vintage,
            "periodo": slot,
            "resolucion_m": 0.5,
            "atribucion": IDEM_DERIVED,
            "sha256": hashlib.sha256(generar_idem.IDEM_REAL_PNG).hexdigest(),
            "bytes": len(generar_idem.IDEM_REAL_PNG),
            "procedencia": {
                "fuente": "idem-vuelos-historicos",
                "url": url,
                "fecha_descarga": "2026-11-27",
                "licencia": "CC BY 4.0",
                "redistribucion": "publicable",
            },
        }
        assert comparison_window_url(ORACLE_WINDOW, vintage) == url


def test_ca2_blanco_de_madrid_es_sin_cobertura_y_se_publica_como_tal(
    tmp_path: Path, case: dict[str, Any]
) -> None:
    """CA2. Dado un vuelo de Madrid que responde en blanco en una ventana, cuando se
    construye la comparación, entonces la franja queda omitida como `sin_cobertura` (no como
    fallo) y la publicación dice «sin cobertura de ese vuelo»."""
    blank = Servers(idem=lambda params: generar_idem.IDEM_BLANK_PNG)
    assert _comparison(tmp_path, blank) == 0
    window = _oracle_window(tmp_path)
    assert window["omitidas"] == [
        {"franja": "1975", "motivo": "sin_cobertura", "probados": ["CM_1975"], "tipo_error": None},
        {"franja": "1991", "motivo": "sin_cobertura", "probados": ["CM_1991"], "tipo_error": None},
    ]
    (feature,) = case["document"]["features"]
    second = feature["properties"]["imagenes_comparacion"][1]
    assert second["omitidas"] == [{"franja": "1991", "texto": "sin cobertura de ese vuelo"}]


def _network_down(params: dict[str, str]) -> bytes:
    raise ConnectionError("secreto")


@pytest.mark.parametrize(
    ("idem", "error_type"),
    [
        (lambda params: XML_ERROR, "NotPngResponseError"),
        (_network_down, "ConnectionError"),
    ],
    ids=["no-png", "red"],
)
def test_ca3_fallo_de_madrid_es_fallo_y_la_publicacion_lo_rechaza(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    case: dict[str, Any],
    idem: Callable[[dict[str, str]], bytes],
    error_type: str,
) -> None:
    """CA3. Dado un fallo de red o una respuesta que no es PNG en un vuelo de Madrid, cuando
    se construye la comparación, entonces la franja queda como `fallo` y la publicación del
    tramo se rechaza con «vuelve a ejecutar imagenes-comparacion» (comportamiento de #172),
    sin tragarse el error."""
    http = Servers(idem=idem)
    fetcher = _fetcher(http, tmp_path / "raw-a")
    windows = FlightRoutedWindowAdapter(
        ign=PnoaWindowAdapter(fetcher), idem=IdemVuelosWindowAdapter(fetcher)
    )
    stretch = MultiLineGeometry((((463700.0, 4437250.0), (463800.0, 4437250.0)),), 25830)
    result = BuildComparisonImagesUseCase(windows).execute(StretchRequest(ORACLE_ID, INE, stretch))
    (window,) = result.windows
    assert [(o.slot, o.reason, o.error_type) for o in window.omitted] == [
        ("1975", "fallo", error_type),
        ("1991", "fallo", error_type),
    ]
    assert "secreto" not in repr(result)
    # El comando sale con 1 y no escribe el manifiesto.
    tramos = _oracle_stretches(tmp_path / "t.geojson")
    out = tmp_path / "salida"
    use_case = main.build_comparison_use_case(
        tmp_path / "raw-b",
        out,
        offline=False,
        http_get=http,
        today=lambda: DAY,
        sleep=lambda s: None,
    )
    with pytest.raises(Exception, match="franjas omitidas por fallo"):
        use_case.execute(INE, read_stretches(tramos, INE))
    assert not (out / f"{INE}.json").exists()  # el comando real, en CA12 con --sin-red

    # Un manifiesto con la franja de Madrid en `fallo` no se publica.
    def failed(document: dict[str, Any]) -> None:
        (stretch_doc,) = document["tramos"]
        first = stretch_doc["ventanas"][0]
        first["imagenes"] = [i for i in first["imagenes"] if i["franja"] != "1975"]
        first["omitidas"].append(
            {"franja": "1975", "motivo": "fallo", "probados": ["CM_1975"], "tipo_error": error_type}
        )

    comparacion = _variant(case, tmp_path, failed)
    _publish_fails(case, tmp_path, capsys, comparacion, "se omitió por un fallo de descarga", RERUN)


def _fetcher(http: Servers, cache: Path, *, offline: bool = False) -> CachedRawFetcher:
    return CachedRawFetcher(http, cache, clock=lambda: DAY, sleep=lambda s: None, offline=offline)


def test_ca4_manifiesto_v1_no_se_publica(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], case: dict[str, Any]
) -> None:
    """CA4. Dada la política nueva, cuando se publica con un manifiesto de la política
    anterior (v1), entonces `publicar-candidatos` falla con el motivo fijo de «otra versión
    de la política» y no escribe nada."""
    assert (COMPARISON_POLICY.identifier, COMPARISON_POLICY.version) == ("imagenes_comparacion", 2)
    comparacion = _variant(case, tmp_path, lambda d: d["politica"].update(version=1))
    _publish_fails(
        case,
        tmp_path,
        capsys,
        comparacion,
        f"el manifiesto es de otra versión de la política de imágenes; {RERUN}",
    )


def test_ca5_huecos_de_la_v2_en_el_manifiesto_y_la_ficha(
    tmp_path: Path, case: dict[str, Any]
) -> None:
    """CA5. Dados los huecos declarados, cuando se genera el manifiesto y la ficha, entonces
    los huecos reflejan los vuelos añadidos (el hueco sin imagen pasa a ser solo el que de
    verdad queda entre franjas) y el texto de la ficha lo cuenta en castellano llano."""
    assert [(g.from_year, g.to_year) for g in DECLARED_GAPS] == [(1958, 1974), (1976, 1990)]
    assert [(h["desde"], h["hasta"]) for h in case["manifest"]["huecos"]] == [
        (1958, 1974),
        (1976, 1990),
    ]
    # Regla del ADR 0052: todo intervalo de más de 10 años sin vuelo de la serie.
    years: set[int] = set()
    for flight in FLIGHTS.values():
        first, _, last = flight.period.partition("-")
        years |= set(range(int(first), int(last or first) + 1))
    gaps: list[tuple[int, int]] = []
    start = None
    for year in range(min(years), max(years) + 2):
        if year not in years and start is None:
            start = year
        elif year in years and start is not None:
            if year - start > 10:
                gaps.append((start, year - 1))
            start = None
    assert gaps == [(g.from_year, g.to_year) for g in DECLARED_GAPS]
    assert case["document"]["properties"]["comparacion"]["huecos"] == [
        {
            "desde": 1958,
            "hasta": 1974,
            "texto": "De 1958 a 1974: la serie no tiene ninguna ortofoto de esos años sobre el "
            "ámbito.",
        },
        {
            "desde": 1976,
            "hasta": 1990,
            "texto": "De 1976 a 1990: la serie no tiene ninguna ortofoto de esos años sobre el "
            "ámbito (los vuelos Interministerial y Nacional del IGN no tienen imagen en él).",
        },
    ]
    assert_node_tests_pass("^H208 CA5:", tmp_path)
    assert 'test("H208 CA5: ' in (ROOT / "tests" / "site" / "visor.test.mjs").read_text("utf-8")


def _set_url(slot: str, old: str, new: str) -> Callable[[dict[str, Any]], None]:
    def change(document: dict[str, Any]) -> None:
        provenance = _idem_image(document, 0, slot)["procedencia"]
        assert old in provenance["url"], provenance["url"]
        provenance["url"] = provenance["url"].replace(old, new)

    return change


def _set_field(slot: str, path: tuple[str, ...], value: object) -> Callable[[dict[str, Any]], None]:
    def change(document: dict[str, Any]) -> None:
        target = _idem_image(document, 0, slot)
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return change


def _as_1991_in_1975(document: dict[str, Any]) -> None:
    """La imagen de la franja 1975 pasa a ser de 1991, con su URL canónica de 1991."""
    image = _idem_image(document, 0, "1975")
    image["vuelo"] = "CM_1991"
    image["procedencia"]["url"] = image["procedencia"]["url"].replace(
        "fotosAereasHistoricas_1970-1979_orto-1975-ed50",
        "fotosAereasHistoricas_1990-1999_orto-1991-ed50",
    )


def _as_1956(document: dict[str, Any]) -> None:
    image = _idem_image(document, 0, "1975")
    image["vuelo"] = "CM_1956"
    image["procedencia"]["url"] = image["procedencia"]["url"].replace(
        "fotosAereasHistoricas_1970-1979_orto-1975-ed50",
        "fotosAereasHistoricas_1950-1959_1956-CT-50cm-mosaico",
    )


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        (_set_url("1975", "https://idem.comunidad.madrid", "https://example.org"), "URL canónica"),
        (
            _set_url(
                "1975",
                "https://idem.comunidad.madrid/srvimagenes2/ogc/wms/visorcartografia2",
                "http://idem.comunidad.madrid/erdas-iws/ogc/wms/visorcartografia2",
            ),
            "URL canónica",
        ),
        (_set_url("1975", "orto-1975-ed50", "1956-CT-50cm-mosaico"), "URL canónica"),
        (_set_url("1975", "1970-1979_orto-1975", "1990-1999_orto-1991"), "URL canónica"),
        (_set_url("1991", "&width=1024", "&width=1024&extra=1"), "URL canónica"),
        (_as_1956, "vuelo"),
        (_as_1991_in_1975, "es de un vuelo de otra franja"),
        (
            _set_field("1975", ("procedencia", "licencia"), "CC BY-SA 4.0"),
            "no lleva la licencia CC BY 4.0",
        ),
        (
            _set_field("1975", ("procedencia", "fuente"), "pnoa-historico"),
            "no es del servicio de su vuelo",
        ),
        (
            _set_field(
                "1991", ("atribucion",), "Obra derivada de " + IDEM_ATTRIBUTION.rstrip(" .")
            ),
            "no lleva la atribución",
        ),
        (_set_field("1975", ("procedencia", "redistribucion"), "solo_uso_interno"), "publicable"),
    ],
    ids=[
        "otro-servidor",
        "getmap-del-getcapabilities",
        "capa-1956",
        "capa-de-1991",
        "otro-parametro",
        "vuelo-1956",
        "vuelo-de-otra-franja",
        "licencia",
        "fuente",
        "atribucion",
        "redistribucion",
    ],
)
def test_ca6_imagen_de_la_idem_fuera_de_la_lista_blanca_falla(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    case: dict[str, Any],
    change: Callable[[dict[str, Any]], None],
    fragment: str,
) -> None:
    """CA6. Dada la publicación de candidatos, cuando una imagen es de la IDEM, entonces su
    URL pasa la lista blanca solo si es la URL canónica `GetMap` de `idem.comunidad.madrid`
    para su ventana y su vuelo (1975 o 1991), con licencia CC BY 4.0 y la atribución exacta;
    cualquier otro servidor, capa (incluida `CM_1956`), licencia o atribución hace fallar
    todo (todo o nada) y no se aloja ninguna imagen en `site/`."""
    comparacion = _variant(case, tmp_path, change)
    _publish_fails(case, tmp_path, capsys, comparacion, fragment)
    # Lo que sí pasa: la URL publicada es la canónica, del servidor de la IDEM.
    (feature,) = case["document"]["features"]
    for window in feature["properties"]["imagenes_comparacion"]:
        for image in window["imagenes"]:
            if image["franja"] in ("1975", "1991"):
                assert image["url"].startswith(IDEM_WMS_URL + "?")
    assert not [p for p in case["site"].rglob("*") if p.suffix in (".png", ".jpg", ".jpeg")]


def test_ca7_procedencia_con_una_fuente_por_vuelo_de_madrid(case: dict[str, Any]) -> None:
    """CA7. Dado el fichero publicado, cuando se genera `site/datos/candidatos/<ine>.geojson`,
    entonces su `.procedencia.json` lista una fuente por vuelo de Madrid usado, con su
    servidor, fecha, licencia y atribución, y el fichero no pasa de 3.000.000 bytes."""
    sidecar = case["sidecar"]
    idem = [s for s in sidecar["fuentes"] if s["origen"] == "idem-vuelos-historicos"]
    assert idem == [
        {
            "origen": "idem-vuelos-historicos",
            "url": IDEM_WMS_URL,
            "periodo": period,
            "fecha_descarga": "2026-11-27",
            "licencia": "CC BY 4.0",
            "atribucion": IDEM_DERIVED,
        }
        for period in ("1975", "1991")
    ]
    block = sidecar["imagenes_comparacion"]
    assert block["servidores"] == sorted(["https://www.ign.es/wms/pnoa-historico", IDEM_WMS_URL])
    assert block["alojadas_en_el_sitio"] is False
    assert block["politica"] == "imagenes_comparacion v2"
    assert IDEM_DERIVED in block["atribucion"]
    assert IDEM_DERIVED in sidecar["atribucion"]
    assert IDEM_DERIVED in case["document"]["properties"]["atribucion"]
    size = (case["site"] / "candidatos" / f"{INE}.geojson").stat().st_size
    assert size < 3_000_000


def test_ca8_la_ficha_muestra_las_de_madrid_con_ano_atribucion_y_aviso(tmp_path: Path) -> None:
    """CA8. Dada la ficha del visor, cuando se abre un tramo con imágenes de Madrid, entonces
    muestra cada una con su año, su atribución literal y el aviso de «cartografía de carácter
    informativo, sin valor vinculante en procedimientos administrativos» (del aviso legal de
    la IDEM), con el trazo superpuesto en píxeles y el texto «Imagen no disponible» si el
    servidor no responde; y la ficha dice que las sirve la Comunidad de Madrid y no este sitio
    (ampliando `SERVED_BY_TEXT`)."""
    assert_node_tests_pass("^H208 CA8:", tmp_path, minimum=3)
    notice = " ".join(NOTICE.read_text(encoding="utf-8").split())
    assert IDEM_NOTICE[0].lower() + IDEM_NOTICE[1:] in notice
    assert "Comunidad de Madrid" in SERVED_BY_TEXT
    assert "Instituto Geográfico Nacional" in SERVED_BY_TEXT
    assert "este sitio no aloja ninguna" in SERVED_BY_TEXT
    published = _load(generar_idem.SITE_FIXTURE)
    assert published["properties"]["comparacion"]["servidas_por"] == SERVED_BY_TEXT
    # La URL del visor no se escribe en el JS: viene del fichero publicado.
    for name in ("vista.js", "controlador.js"):
        assert "idem.comunidad.madrid" not in (ROOT / "site" / name).read_text(encoding="utf-8")


def _manifest_document() -> dict[str, Any]:
    document: dict[str, Any] = _load(generar.DIRECTORY / "comparacion" / f"{INE}.json")
    return document


def test_ca9_el_lector_acepta_1975_y_1991_y_rechaza_otras(case: dict[str, Any]) -> None:
    """CA9. Dado el manifiesto, cuando el lector lo carga, entonces acepta los vuelos de
    Madrid 1975 y 1991 y rechaza una imagen de la IDEM cuya URL no sea la canónica de su
    ventana y vuelo, o que sea de `CM_1956`."""
    manifest = parse_manifest(case["manifest"], INE)
    (stretch,) = manifest.stretches
    vintages = {image.vintage for window in stretch.windows for image in window.images}
    assert {"CM_1975", "CM_1991"} <= vintages

    def rejects(change: Callable[[dict[str, Any]], None], fragment: str) -> None:
        document = copy.deepcopy(case["manifest"])
        change(document)
        with pytest.raises(ValueError, match=fragment):
            parse_manifest(document, INE)

    canonical = "no es la URL canónica de su ventana y su vuelo en el servidor de ese vuelo"
    rejects(_set_url("1975", "orto-1975-ed50", "1956-CT-50cm-mosaico"), canonical)
    rejects(_set_url("1991", "bbox=459949", "bbox=459950"), canonical)
    ign_url = comparison_window_url(stretch.windows[0].window, 2023)
    rejects(_set_field("1975", ("procedencia", "url"), ign_url), canonical)
    rejects(_as_1956, "vuelo")
    # El literal del oráculo es el que el lector acepta para esa ventana.
    assert comparison_window_url(ORACLE_WINDOW, "CM_1975") == ORACLE_URL_1975
    assert comparison_window_url(ORACLE_WINDOW, "CM_1991") == ORACLE_URL_1991


@pytest.mark.integration
@pytest.mark.red
def test_ca10_integracion_colmenar_contra_la_idem(tmp_path: Path) -> None:
    """CA10. [integración, marcador `red`: corre en `red-externa`, no bloquea] Dado un tramo
    real de Colmenar de Oreja con cobertura, cuando se ejecuta `imagenes-comparacion
    --municipio 28043` contra la IDEM, entonces el manifiesto trae las imágenes de Madrid y
    `NOTICE` recoge la atribución usada."""
    tramos = _oracle_stretches(tmp_path / "tramos.geojson")
    out = tmp_path / "comparacion"
    code = _run(
        [
            "imagenes-comparacion",
            "--municipio",
            INE,
            "--tramos",
            str(tramos),
            "--cache",
            str(tmp_path / "raw"),
            "--salida",
            str(out),
        ]
    )
    assert code == 0
    (stretch,) = _load(out / f"{INE}.json")["tramos"]
    (window,) = stretch["ventanas"]
    madrid = {i["franja"]: i for i in window["imagenes"] if i["vuelo"] in ("CM_1975", "CM_1991")}
    assert set(madrid) == {"1975", "1991"}
    assert madrid["1975"]["procedencia"]["url"] == ORACLE_URL_1975
    assert madrid["1991"]["procedencia"]["url"] == ORACLE_URL_1991
    notice = NOTICE.read_text(encoding="utf-8")
    for image in madrid.values():
        assert image["atribucion"].removeprefix("Obra derivada de ") in notice


class _Recorder:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[HistoricalVintage] = []

    def get_orthophoto_window(
        self, window: OrthophotoWindow, vintage: HistoricalVintage
    ) -> Orthophoto:
        self.calls.append(vintage)
        return Orthophoto(
            b"x", vintage, Provenance(self.name, "u", DAY, "CC BY 4.0", Redistribution.PUBLIC)
        )


def test_ca11_serie_y_fuentes_coherentes_con_los_adapters(tmp_path: Path) -> None:
    """CA11. Dada la serie, cuando se recorre, entonces cada vuelo de `COMPARISON_SLOTS` está
    en `FLIGHTS` y cada vuelo de `FLIGHTS` está en exactamente una franja; `CM_1956` no está
    en ninguno de los dos; y la fuente que declara `FLIGHTS` para un vuelo del IGN y para uno
    de Madrid es la misma cadena que pone en la procedencia el adapter real
    (`PnoaWindowAdapter` e `IdemVuelosWindowAdapter` sobre fixtures), para que dominio y
    adapter no diverjan."""
    in_slots = [v for slot in COMPARISON_SLOTS for v in slot.vintages]
    assert set(in_slots) <= set(FLIGHTS)
    assert sorted(map(str, in_slots)) == sorted(map(str, FLIGHTS))
    assert len(in_slots) == len(set(in_slots))
    assert "CM_1956" not in FLIGHTS and "CM_1956" not in in_slots
    assert [s.name for s in COMPARISON_SLOTS] == SLOT_ORDER
    window = OrthophotoWindow(463700, 4437200, 463828, 4437328, 25830, 256, 256)
    http = Servers()
    ign = PnoaWindowAdapter(_fetcher(http, tmp_path)).get_orthophoto_window(window, 2023)
    idem = IdemVuelosWindowAdapter(_fetcher(http, tmp_path)).get_orthophoto_window(
        window, "CM_1975"
    )
    assert ign.provenance.source == FLIGHTS[2023].source == "pnoa-historico"
    assert idem.provenance.source == FLIGHTS["CM_1975"].source == "idem-vuelos-historicos"
    assert idem.provenance.license == ign.provenance.license == "CC BY 4.0"
    for vintage, flight in FLIGHTS.items():
        expected = "idem-vuelos-historicos" if str(vintage).startswith("CM_") else "pnoa-historico"
        assert flight.source == expected, vintage
        assert (flight.notice is not None) == str(vintage).startswith("CM_"), vintage
    assert attribution_for("CM_1975") == attribution_for("CM_1991") == IDEM_DERIVED


def test_ca12_despacho_por_vuelo_y_un_solo_fetcher(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA12. Dado el despachador de ventanas, cuando se piden `CM_1975` y `CM_1991`,
    entonces van al adapter de la IDEM, y cualquier otro vuelo de la serie va al del IGN; los
    dos comparten un único `CachedRawFetcher` (misma caché `data/raw`, misma pausa). Con
    `--sin-red` y la imagen de Madrid ausente de la caché, la franja queda `fallo`
    (`RawCacheMissError`) y `imagenes-comparacion` sale con 1 sin escribir el manifiesto."""
    ign, idem = _Recorder("ign"), _Recorder("idem")
    router = FlightRoutedWindowAdapter(ign=ign, idem=idem)
    for vintage in FLIGHTS:
        router.get_orthophoto_window(ORACLE_WINDOW, vintage)
    assert idem.calls == ["CM_1975", "CM_1991"]
    assert sorted(map(str, ign.calls)) == sorted(
        str(v) for v in FLIGHTS if v not in ("CM_1975", "CM_1991")
    )

    # Un único fetcher: una sola caché y una pausa antes de cada petición salvo la primera,
    # también al pasar del IGN a la IDEM y al revés.
    pauses: list[float] = []
    http = Servers()
    assert _comparison(tmp_path / "a", http, sleep=pauses.append) == 0
    assert {url for url, _ in http.calls} == {"https://www.ign.es/wms/pnoa-historico", IDEM_WMS_URL}
    assert len(pauses) == len(http.calls) - 1
    bodies = list((tmp_path / "a" / "raw").rglob("*.body"))
    assert len(bodies) == len(http.calls)

    # Caché con el IGN y sin Madrid (la IDEM falló al poblarla) + --sin-red.
    failing = Servers(idem=lambda params: XML_ERROR)
    assert _comparison(tmp_path / "b", failing) == 1
    out = tmp_path / "b" / "salida"
    tramos = _oracle_stretches(tmp_path / "b" / "t.geojson")
    capsys.readouterr()
    code = _run(
        [
            "imagenes-comparacion",
            "--municipio",
            INE,
            "--tramos",
            str(tramos),
            "--cache",
            str(tmp_path / "b" / "raw"),
            "--salida",
            str(out),
            "--sin-red",
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert f"FALLO {ORACLE_ID} franja 1975: RawCacheMissError" in err
    assert f"FALLO {ORACLE_ID} franja 1991: RawCacheMissError" in err
    assert not re.search(r"franja (1956-1957|1997-2003|2006-2011|2014-2020|reciente)", err)
    assert not (out / f"{INE}.json").exists()


def test_ca13_dos_ventanas_con_cobertura_distinta(case: dict[str, Any]) -> None:
    """CA13. [caso no trivial, lección 0002] Dado un tramo de **dos ventanas** donde 1975
    cubre las dos y 1991 solo la primera (blanca en la segunda), cuando se ejecuta
    `imagenes-comparacion` y después `publicar-candidatos` (productor real encadenado,
    lecciones de #170 y #172), entonces la primera ventana publica siete imágenes en el orden
    `1956-1957, 1975, 1991, 1997-2003, 2006-2011, 2014-2020, reciente` y la segunda seis, con
    `1991` en `omitidas` con «sin cobertura de ese vuelo»; el `.procedencia.json` tiene
    **una** fuente por vuelo de Madrid (1975 y 1991, distinguidas por `periodo` aunque
    compartan atribución)."""
    (feature,) = case["document"]["features"]
    first, second = feature["properties"]["imagenes_comparacion"]
    assert (first["ancho_px"], second["ancho_px"]) == (1024, 576)
    assert [i["franja"] for i in first["imagenes"]] == SLOT_ORDER
    assert first["omitidas"] == []
    assert [i["franja"] for i in second["imagenes"]] == [s for s in SLOT_ORDER if s != "1991"]
    assert second["omitidas"] == [{"franja": "1991", "texto": "sin cobertura de ese vuelo"}]
    for window in (first, second):
        for image in window["imagenes"]:
            if image["franja"] in ("1975", "1991"):
                assert image["aviso_fuente"] == IDEM_NOTICE
                assert image["atribucion"] == IDEM_DERIVED
            else:
                assert "aviso_fuente" not in image
    assert "bbox=460364%2C4438356%2C460652%2C4438644&" in second["imagenes"][1]["url"]
    idem_sources = [
        s for s in case["sidecar"]["fuentes"] if s["origen"] == "idem-vuelos-historicos"
    ]
    assert [s["periodo"] for s in idem_sources] == ["1975", "1991"]
    assert len({s["atribucion"] for s in idem_sources}) == 1
    # La fixture del visor es este mismo fichero publicado (lección de #178).
    assert generar_idem.SITE_FIXTURE.read_text(encoding="utf-8") == (
        case["site"] / "candidatos" / f"{INE}.geojson"
    ).read_text(encoding="utf-8")


def test_ca14_tests_de_la_serie_v1_actualizados_y_fixture_regenerada() -> None:
    """CA14. Dados los tests de #121, #122, #168, #170, #172 y #178 que fijan la serie v1
    (cinco franjas, hueco 1957–1997, `servidor` único, política v1), cuando se pasa a v2,
    entonces se actualizan al literal nuevo **sin relajarlos** (lección de #172), y la fixture
    `tests/fixtures/candidatos_publicar/` se regenera con su `generar.py`."""
    for relative, text in generar.texts().items():
        assert (generar.DIRECTORY / relative).read_text(encoding="utf-8") == text, relative
    manifest = _manifest_document()
    assert manifest["politica"] == {"id": "imagenes_comparacion", "version": 2}
    assert [(h["desde"], h["hasta"]) for h in manifest["huecos"]] == [(1958, 1974), (1976, 1990)]
    for stretch in manifest["tramos"]:
        for window in stretch["ventanas"]:
            slots = [i["franja"] for i in window["imagenes"]] + [
                o["franja"] for o in window["omitidas"]
            ]
            assert sorted(slots) == sorted(SLOT_ORDER)
    stale = (
        '"imagenes_comparacion v1"',
        "(1957, 1997)",
        "cinco franjas una vez",
        '"servidor": "https://www.ign.es/wms/pnoa-historico"',
        "no es del WMS histórico del IGN",
    )
    tests = ROOT / "tests"
    for name in (
        "acceptance/test_historia_121.py",
        "acceptance/test_historia_122.py",
        "acceptance/test_historia_168.py",
        "acceptance/test_historia_170.py",
        "acceptance/test_historia_172.py",
        "acceptance/test_historia_178.py",
        "domain/test_published_comparison.py",
        "domain/test_published_candidate.py",
        "adapters/comparison_files/test_manifest_writer.py",
        "adapters/published_layers/test_candidate_sink.py",
    ):
        text = (tests / name).read_text(encoding="utf-8")
        for value in stale:
            assert value not in text, (name, value)
