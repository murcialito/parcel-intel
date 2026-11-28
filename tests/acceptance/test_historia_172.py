"""Historia #172: imágenes de comparación en la ficha publicada del tramo a verificar
(ADR 0049).

Entradas SINTÉTICAS (`tests/fixtures/candidatos_publicar/`, ver su LEEME.md): los 5
candidatos de #168 con 3 aprobados (`aprobado`, `propuesto` de dos piezas y `caducado`) y
el manifiesto `comparacion/28043.json` escrito con el productor real de
`imagenes-comparacion` (#122) y un WMS falso: por ventana, `1956-1957` omitida y
`1997-2003` OLISTAT, `2006-2011` 2006, `2014-2020` 2017 y `reciente` 2023.

Política v2 (#208, CA14): la serie gana las franjas `1975` y `1991` de la IDEM. La fixture
se regeneró con `generar.py`, cuyo WMS falso responde a la IDEM con su PNG blanco real, así
que esas dos franjas quedan omitidas y los literales del IGN no cambian. Se actualizan al
literal nuevo, sin relajarlos: política `v2`, dos huecos (1958–1974 y 1976–1990), tres
omisiones por ventana, `servidores` en lugar de `servidor`, `periodo` en cada fuente de
imagen y el motivo «no es del servicio de su vuelo». Los docstrings conservan el criterio.

Oráculos del Bloque 0 (código de producción, `comparison_windows` y `stretch_pixels`):
- `aprobado` (`cb30d538bb5ea601`): ventana `(459940, 4435840, 460260, 4436160)` de 640 px,
  trazo `[[[120.0, 320.0], [520.0, 320.0]]]`.
- `propuesto` (`910f248ab773fae8`, dos piezas): ventana `(459935, 4436840, 460255,
  4437160)` de 640 px, trazo `[[[130.0, 320.0], [330.0, 320.0]], [[390.0, 320.0],
  [510.0, 320.0]]]`.
- `sin_revision` (`12b804770c6c38bd`, no aprobado): ventana `(459933, 4437888, 460157,
  4438112)` de 448 px y trazo `[[[134.0, 224.0], [314.0, 224.0]]]` (oráculo del diseño).
- Un tramo de 600 m (`460000,4438500 → 460600,4438500`, CA13): dos ventanas,
  `(459949, 4438244, 460461, 4438756)` de 1024 px y `(460364, 4438356, 460652, 4438644)`
  de 576 px.

Adaptación anotada (CA11): `12b804770c6c38bd` es el candidato `sin_revision` de la
fixture, que no está aprobado y por tanto no se publica. El test pide la URL de su
imagen `reciente` tal como la deja el manifiesto (es exactamente la que se publicaría,
`window_url`) y, además, la URL `reciente` realmente publicada del `aprobado`.
"""

import copy
import dataclasses
import json
import re
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

import tests.acceptance.test_historia_170 as historia_170
from parcel_intel.adapters.comparison_files import JsonComparisonManifestReader
from parcel_intel.adapters.curated_candidates import CuratedCandidateReviewFiles
from parcel_intel.adapters.cut_candidate_files import GeoJsonCutCandidateWriter
from parcel_intel.adapters.pnoa.window import window_url
from parcel_intel.adapters.published_layers import (
    GeoJsonPublishedCandidateSink,
    JsonMeasurementReportReader,
    PublishedLayerError,
)
from parcel_intel.cli import main
from parcel_intel.domain.candidate_review import candidate_fingerprint, reconcile
from parcel_intel.domain.comparison_image import FLIGHTS, attribution_for
from parcel_intel.domain.cut_candidate import CutCandidate
from parcel_intel.domain.orthophoto import OrthophotoWindow
from parcel_intel.domain.public_card import banned_words_in
from parcel_intel.domain.published_candidate import (
    CandidateLayerPublication,
    build_candidate_layer,
    summarize_measurement,
)
from parcel_intel.domain.published_comparison import SERVED_BY_TEXT
from parcel_intel.domain.published_discrepancy import CADASTRAL_REFERENCE_RE, PARCEL_LOCATOR_RE
from tests.fixtures.candidatos_publicar import generar
from tests.fixtures.candidatos_revision import generar as revision

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "candidatos_publicar"
CANDIDATES_DIR = FIXTURE / "candidatos"
CURATED_DIR = FIXTURE / "curated"
COMPARISON_DIR = FIXTURE / "comparacion"
MEASUREMENT = FIXTURE / "medicion.json"
MANIFEST = COMPARISON_DIR / "28043.json"
NOTICE = ROOT / "NOTICE"
INE = "28043"
RERUN = "vuelve a ejecutar imagenes-comparacion"

FOUND = revision.candidates()
APROBADO = FOUND["aprobado"].candidate_id  # cb30d538bb5ea601
PROPUESTO = FOUND["propuesto"].candidate_id  # 910f248ab773fae8
SIN_REVISION = "12b804770c6c38bd"
PUBLIC_IDS = historia_170.PUBLIC_IDS

APROBADO_WINDOW = OrthophotoWindow(459940, 4435840, 460260, 4436160, 25830, 640, 640)
APROBADO_RECIENTE_URL = (
    "https://www.ign.es/wms/pnoa-historico?bbox=459940%2C4435840%2C460260%2C4436160"
    "&crs=EPSG%3A25830&format=image%2Fjpeg&height=640&layers=PNOA2023&request=GetMap"
    "&service=WMS&styles=&version=1.3.0&width=640"
)
SIN_REVISION_RECIENTE_URL = (
    "https://www.ign.es/wms/pnoa-historico?bbox=459933%2C4437888%2C460157%2C4438112"
    "&crs=EPSG%3A25830&format=image%2Fjpeg&height=448&layers=PNOA2023&request=GetMap"
    "&service=WMS&styles=&version=1.3.0&width=448"
)
IMAGE_KEYS = {"url", "franja", "periodo", "resolucion_m", "atribucion", "texto_alternativo"}
WINDOW_KEYS = {"ancho_px", "alto_px", "trazo_px", "imagenes", "omitidas"}
SLOTS_WITH_IMAGE = ["1997-2003", "2006-2011", "2014-2020", "reciente"]
GAP_TEXTS = (
    "De 1958 a 1974: la serie no tiene ninguna ortofoto de esos años sobre el ámbito.",
    "De 1976 a 1990: la serie no tiene ninguna ortofoto de esos años sobre el ámbito (los "
    "vuelos Interministerial y Nacional del IGN no tienen imagen en él).",
)
OMITTED_SLOTS = ["1956-1957", "1975", "1991"]


# --- Utilidades -----------------------------------------------------------------------


def _run(args: list[str]) -> int:
    parsed = main._build_parser().parse_args(args)
    code: int = parsed.func(parsed)
    return code


def _publicar(
    salida: Path,
    comparacion: Path = COMPARISON_DIR,
    entrada: Path = CANDIDATES_DIR,
    curated: Path = CURATED_DIR,
) -> int:
    return _run(
        [
            "publicar-candidatos",
            "--municipio",
            INE,
            "--medicion",
            str(MEASUREMENT),
            "--entrada",
            str(entrada),
            "--curated",
            str(curated),
            "--comparacion",
            str(comparacion),
            "--salida",
            str(salida),
        ]
    )


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshot(directory: Path) -> dict[str, bytes]:
    if not directory.exists():
        return {}
    return {
        str(path.relative_to(directory)): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, str):
        yield value


def _written(site: Path) -> list[Path]:
    return [
        site / "candidatos" / f"{INE}.geojson",
        site / "candidatos" / f"{INE}.geojson.procedencia.json",
        site / "indice.json",
        site / "indice.json.procedencia.json",
    ]


def _stretch(document: dict[str, Any], stretch_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(s for s in document["tramos"] if s["id"] == stretch_id)
    return found


def _manifest_variant(base: Path, change: Callable[[dict[str, Any]], object]) -> Path:
    """Copia del manifiesto de la fixture con `change` aplicado, en `base`."""
    document = copy.deepcopy(_load(MANIFEST))
    change(document)
    base.mkdir(parents=True)
    (base / f"{INE}.json").write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return base


def _fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    comparacion: Path,
    *fragments: str,
    **inputs: Path,
) -> str:
    site = tmp_path / f"site-{comparacion.name}"
    assert _publicar(site, comparacion, **inputs) == 1
    err = capsys.readouterr().err
    for fragment in fragments:
        assert fragment in err, (fragment, err)
    assert f"No se ha escrito nada en {site}." in err
    assert _snapshot(site) == {}
    return err


def _review(candidate: CutCandidate) -> dict[str, object]:
    return {
        "candidate_id": candidate.candidate_id,
        "review": "aprobado",
        "reviewed_by": revision.REVIEWER,
        "reviewed_at": revision.REVIEWED_AT,
        "candidate_sha256": candidate_fingerprint(candidate),
    }


def _inputs(base: Path, candidates: list[CutCandidate], approve: list[CutCandidate]) -> Path:
    """Candidatos, revisión y manifiesto (productor real) en `base`."""
    report = dataclasses.replace(
        revision.report(), candidates=tuple(sorted(candidates, key=lambda c: c.candidate_id))
    )
    GeoJsonCutCandidateWriter(base / "candidatos").write(report)
    (base / "curated" / INE).mkdir(parents=True)
    (base / "curated" / INE / "revision.json").write_text(
        json.dumps({"municipio": INE, "revisiones": [_review(c) for c in approve]}),
        encoding="utf-8",
    )
    (base / "comparacion").mkdir()
    (base / "comparacion" / f"{INE}.json").write_text(
        generar.manifest_text_for(base / "candidatos" / f"{INE}.geojson"), encoding="utf-8"
    )
    return base


def _publication() -> CandidateLayerPublication:
    reviews = CuratedCandidateReviewFiles(CURATED_DIR).reviews(INE)
    state = reconcile(revision.report(), reviews)
    measurement = JsonMeasurementReportReader(MEASUREMENT).get_measurement()
    summary = summarize_measurement(measurement, revision.report().method)
    manifest = JsonComparisonManifestReader(COMPARISON_DIR).get_manifest(INE)
    assert manifest is not None
    return build_candidate_layer(state, summary, "Colmenar de Oreja", manifest).publication


@pytest.fixture
def published(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    site = tmp_path / "site" / "datos"
    code = _publicar(site)
    out = capsys.readouterr()
    assert code == 0, out.err
    document = _load(site / "candidatos" / f"{INE}.geojson")
    return {
        "site": site,
        "document": document,
        "by_id": {f["id"]: f for f in document["features"]},
        "sidecar": _load(site / "candidatos" / f"{INE}.geojson.procedencia.json"),
    }


# --- Criterios ------------------------------------------------------------------------


def test_ca1_feature_con_imagenes_en_orden_y_lista_blanca(published: dict[str, Any]) -> None:
    """CA1. Dado un candidato aprobado con `estado: generada` en el manifiesto, cuando se
    publica el municipio, entonces su feature lleva `imagenes_comparacion`: una entrada por
    ventana, en el orden del manifiesto, con `ancho_px`, `alto_px`, `trazo_px` (todas las
    partes), `imagenes` y `omitidas`; las imágenes van en orden cronológico (el de
    `COMPARISON_SLOTS`), cada una con `url` (la URL canónica del `GetMap` del manifiesto),
    `franja`, `periodo`, `resolucion_m`, `atribucion` con el texto «Obra derivada de
    <atribución SCNE>» (ADR 0042 §5) y `texto_alternativo` («Ortofoto de <periodo> con el
    tramo a verificar marcado»), y nada más: ni `sha256`, ni `bytes`, ni `vuelo`, ni
    procedencia interna, ni `bbox`, ni `srid`."""
    manifest = _load(MANIFEST)
    (window,) = published["by_id"][PUBLIC_IDS["aprobado"]]["properties"]["imagenes_comparacion"]
    assert set(window) == WINDOW_KEYS
    assert (window["ancho_px"], window["alto_px"]) == (640, 640)
    assert window["trazo_px"] == [[[120.0, 320.0], [520.0, 320.0]]]
    assert [image["franja"] for image in window["imagenes"]] == SLOTS_WITH_IMAGE
    for image in window["imagenes"]:
        assert set(image) == IMAGE_KEYS
        assert image["atribucion"].startswith("Obra derivada de ")
        assert image["texto_alternativo"] == (
            f"Ortofoto de {image['periodo']} con el tramo a verificar marcado"
        )
    recent = window["imagenes"][-1]
    assert recent == {
        "url": APROBADO_RECIENTE_URL,
        "franja": "reciente",
        "periodo": "2023",
        "resolucion_m": 0.25,
        "atribucion": "Obra derivada de PNOA 2023 CC-BY 4.0 scne.es",
        "texto_alternativo": "Ortofoto de 2023 con el tramo a verificar marcado",
    }
    assert recent["url"] == window_url(APROBADO_WINDOW, 2023)
    olistat = window["imagenes"][0]
    assert (olistat["periodo"], olistat["resolucion_m"]) == ("1997-1999", 1.0)
    assert olistat["atribucion"] == "Obra derivada de Orto-OLISTAT 1997-1999 CC-BY 4.0 scne.es"

    # Cada feature, ventana a ventana, con las URL del manifiesto en el mismo orden.
    for role in generar.APPROVED_ROLES:
        candidate_id = FOUND[role].candidate_id
        feature = published["by_id"][PUBLIC_IDS[role]]
        windows = feature["properties"]["imagenes_comparacion"]
        expected = _stretch(manifest, candidate_id)["ventanas"]
        assert len(windows) == len(expected)
        for got, want in zip(windows, expected, strict=True):
            assert got["trazo_px"] == want["trazo_px"]
            assert [i["url"] for i in got["imagenes"]] == [
                i["procedencia"]["url"] for i in want["imagenes"]
            ]
        for key in ("sha256", "bytes", "vuelo", "procedencia", "bbox", "srid", "probados"):
            assert key not in set(_strings(windows)), key


def test_ca2_bloque_comparacion_y_omitidas_en_lenguaje_llano(published: dict[str, Any]) -> None:
    """CA2. Dado el fichero publicado, cuando se lee, entonces la colección lleva el bloque
    `comparacion` con la política (`imagenes_comparacion v1`), los `huecos` declarados
    (`desde` 1957, `hasta` 1997 y su `texto` ya redactado), la nota de que las imágenes las
    sirve el IGN y el texto de «imagen no disponible»; y, por ventana, las franjas omitidas
    con `franja` y un `texto` fijo en lenguaje llano («sin cobertura de ese vuelo»), sin
    tipo de error ni lista de vuelos probados."""
    assert published["document"]["properties"]["comparacion"] == {
        "politica": "imagenes_comparacion v2",
        "huecos": [
            {"desde": 1958, "hasta": 1974, "texto": GAP_TEXTS[0]},
            {"desde": 1976, "hasta": 1990, "texto": GAP_TEXTS[1]},
        ],
        "servidas_por": SERVED_BY_TEXT,
        "no_disponible": "Imagen no disponible",
    }
    assert "Instituto Geográfico Nacional" in SERVED_BY_TEXT
    for feature in published["document"]["features"]:
        for window in feature["properties"]["imagenes_comparacion"]:
            assert window["omitidas"] == [
                {"franja": slot, "texto": "sin cobertura de ese vuelo"} for slot in OMITTED_SLOTS
            ]
    text = (published["site"] / "candidatos" / f"{INE}.geojson").read_text(encoding="utf-8")
    for leaked in (
        "tipo_error",
        "probados",
        "sin_cobertura",
        "AMS_1956-1957",
        "CM_1975",
        "CM_1991",
        "motivo",
    ):
        assert leaked not in text, leaked


def test_ca3_sin_manifiesto_falla_con_motivo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA3. Dado un municipio sin fichero de manifiesto, cuando se publica, entonces falla
    con 1, con motivo («sin manifiesto de imágenes de comparación; ejecuta
    imagenes-comparacion») y no se escribe nada."""
    _fails(
        tmp_path,
        capsys,
        tmp_path / "sin-manifiesto",
        "ERROR 28043: sin manifiesto de imágenes de comparación; ejecuta imagenes-comparacion",
    )


def _drop_aprobado(document: dict[str, Any]) -> None:
    document["tramos"] = [s for s in document["tramos"] if s["id"] != APROBADO]


def _too_long(document: dict[str, Any]) -> None:
    stretch = _stretch(document, APROBADO)
    stretch["estado"] = "tramo_demasiado_largo"
    stretch["ventanas"] = []


def _no_images(document: dict[str, Any]) -> None:
    for window in _stretch(document, APROBADO)["ventanas"]:
        for image in window["imagenes"]:
            window["omitidas"].append(
                {
                    "franja": image["franja"],
                    "motivo": "sin_cobertura",
                    "probados": [image["vuelo"]],
                    "tipo_error": None,
                }
            )
        window["imagenes"] = []


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (
            _drop_aprobado,
            "no está en el manifiesto de imágenes de comparación; ejecuta imagenes-comparacion",
        ),
        (_too_long, "tramo demasiado largo para las imágenes de comparación"),
        (_no_images, "sin imágenes de comparación"),
    ],
    ids=["ausente", "demasiado-largo", "sin-imagenes"],
)
def test_ca4_aprobado_sin_imagenes_publicables_falla_el_municipio(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    change: Callable[[dict[str, Any]], None],
    reason: str,
) -> None:
    """CA4. Dado un candidato aprobado que no está en el manifiesto, o está con
    `tramo_demasiado_largo`, o sin ninguna imagen en ninguna ventana, cuando se publica,
    entonces falla el municipio nombrando su `candidate_id` y el motivo, sin escribir nada
    (mismo criterio que ADR 0048 §6: un aprobado no publicable es un error de revisión que
    debe verse; la revisión de #168 ya muestra la disponibilidad antes de aprobar)."""
    comparacion = _manifest_variant(tmp_path / "comparacion", change)
    _fails(tmp_path, capsys, comparacion, f"el candidato {APROBADO}: {reason}")


@pytest.mark.parametrize(
    ("dx", "dy"), [(0.0, 1.0), (0.2, 0.0)], ids=["1m-norte-otra-ventana", "20cm-otro-trazo"]
)
def test_ca5_manifiesto_de_otro_trazado_falla(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], dx: float, dy: float
) -> None:
    """CA5. Dado un manifiesto generado con un trazado distinto del actual del candidato (el
    candidato se regeneró y el manifiesto es anterior; caso de prueba: tramo desplazado 1 m),
    cuando se publica, entonces falla: el dominio recalcula `comparison_windows(tramo)` y
    `stretch_pixels` y exige que ventanas (esquinas y píxeles) y trazo coincidan
    **exactamente** con el manifiesto; el motivo nombra el `candidate_id` y pide volver a
    ejecutar `imagenes-comparacion`.

    Con el productor real: se desplaza el tramo del `aprobado` en una copia del fichero de
    candidatos (con su mismo id) y se genera el manifiesto desde ella. 1 m al norte mueve la
    ventana; 0,2 m al este deja la misma ventana (el centro redondea igual) y solo cambia
    el trazo en píxeles."""
    document = _load(CANDIDATES_DIR / f"{INE}.geojson")
    feature = next(f for f in document["features"] if f["id"] == APROBADO)
    feature["geometry"]["coordinates"] = [
        [[x + dx, y + dy] for x, y in line] for line in feature["geometry"]["coordinates"]
    ]
    moved = tmp_path / "movido" / f"{INE}.geojson"
    moved.parent.mkdir()
    moved.write_text(json.dumps(document), encoding="utf-8")
    comparacion = tmp_path / "comparacion"
    comparacion.mkdir()
    (comparacion / f"{INE}.json").write_text(generar.manifest_text_for(moved), encoding="utf-8")
    _fails(
        tmp_path,
        capsys,
        comparacion,
        f"el candidato {APROBADO}: el manifiesto no corresponde al tramo actual; {RERUN}",
    )


def _recent_of_aprobado(document: dict[str, Any]) -> dict[str, Any]:
    image: dict[str, Any] = _stretch(document, APROBADO)["ventanas"][0]["imagenes"][-1]
    assert image["franja"] == "reciente"
    return image


def _set_provenance(key: str, value: str) -> Callable[[dict[str, Any]], None]:
    def change(document: dict[str, Any]) -> None:
        _recent_of_aprobado(document)["procedencia"][key] = value

    return change


def _set_image(key: str, value: object) -> Callable[[dict[str, Any]], None]:
    def change(document: dict[str, Any]) -> None:
        _recent_of_aprobado(document)[key] = value

    return change


def _replace_in_url(old: str, new: str) -> Callable[[dict[str, Any]], None]:
    def change(document: dict[str, Any]) -> None:
        provenance = _recent_of_aprobado(document)["procedencia"]
        assert old in provenance["url"]
        provenance["url"] = provenance["url"].replace(old, new)

    return change


def _swap_slots(document: dict[str, Any]) -> None:
    images = _stretch(document, APROBADO)["ventanas"][0]["imagenes"]
    images[-1]["franja"], images[-2]["franja"] = images[-2]["franja"], images[-1]["franja"]


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        (_set_provenance("redistribucion", "solo_uso_interno"), "no está marcada como publicable"),
        (_set_provenance("licencia", "CC BY-SA 4.0"), "no lleva la licencia CC BY 4.0"),
        (_set_provenance("fuente", "pnoa-ma"), "no es del servicio de su vuelo"),
        (_replace_in_url("www.ign.es/wms/pnoa-historico", "example.org/wms"), "URL canónica"),
        (_replace_in_url("layers=PNOA2023", "layers=PNOA2020"), "URL canónica"),
        (_replace_in_url("bbox=459940", "bbox=459941"), "URL canónica"),
        (_replace_in_url("&width=640", "&width=640&extra=1"), "URL canónica"),
        (_set_image("atribucion", "PNOA 2023 CC-BY 4.0 scne.es"), "no lleva la atribución"),
        (_set_image("periodo", "2022"), "no lleva el periodo de su vuelo"),
        (_set_image("resolucion_m", 0.5), "no lleva la resolución de su vuelo"),
        (_swap_slots, "es de un vuelo de otra franja"),
    ],
    ids=[
        "redistribucion",
        "licencia",
        "fuente",
        "otro-servidor",
        "otra-capa",
        "otro-bbox",
        "otro-parametro",
        "atribucion",
        "periodo",
        "resolucion",
        "franja",
    ],
)
def test_ca6_imagen_fuera_de_la_lista_blanca_falla(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    change: Callable[[dict[str, Any]], None],
    fragment: str,
) -> None:
    """CA6. Dado un manifiesto cuya imagen tiene `redistribucion` distinta de `publicable`,
    licencia distinta de `CC BY 4.0`, fuente distinta de `pnoa-historico`, una URL distinta
    de la URL canónica de su ventana y su vuelo en el WMS histórico del IGN (lista blanca
    cerrada: servidor, capa y parámetros), o una franja, periodo, resolución o atribución
    distintos de los de ADR 0042 §3 para su vuelo, cuando se publica, entonces falla sin
    escribir nada."""
    comparacion = _manifest_variant(tmp_path / "comparacion", change)
    _fails(tmp_path, capsys, comparacion, fragment)


def _set_top(key: str, value: object) -> Callable[[dict[str, Any]], None]:
    def change(document: dict[str, Any]) -> None:
        document[key] = value

    return change


def _set_first_id(value: str) -> Callable[[dict[str, Any]], None]:
    def change(document: dict[str, Any]) -> None:
        document["tramos"][0]["id"] = value

    return change


def _repeat_stretch(document: dict[str, Any]) -> None:
    document["tramos"].append(copy.deepcopy(document["tramos"][0]))


def _float_bbox(document: dict[str, Any]) -> None:
    window = _stretch(document, APROBADO)["ventanas"][0]
    window["bbox"] = [float(value) + 0.5 for value in window["bbox"]]


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        (_set_top("municipio", "28013"), "el manifiesto es del municipio 28013"),
        (_set_first_id("NO-ES-UN-ID"), "tramos.0.id"),
        (_repeat_stretch, "id de tramo repetido"),
        (_set_top("clave_desconocida", 1), "clave_desconocida"),
        (_set_top("tramos", {"no": "es una lista"}), "tramos"),
        (_float_bbox, "bbox"),
    ],
    ids=["otro-municipio", "id-no-valido", "id-repetido", "clave-desconocida", "formato", "bbox"],
)
def test_ca7_manifiesto_no_valido_falla_con_mensaje_claro(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    change: Callable[[dict[str, Any]], None],
    fragment: str,
) -> None:
    """CA7. Dado un manifiesto ilegible, de otro municipio, con ids no válidos o repetidos,
    con claves desconocidas o con formato distinto, cuando se publica, entonces falla con un
    mensaje claro y sin escribir."""
    comparacion = _manifest_variant(tmp_path / "comparacion", change)
    _fails(
        tmp_path,
        capsys,
        comparacion,
        "Manifiesto de imágenes de comparación no válido",
        str(comparacion / f"{INE}.json"),
        fragment,
    )


def test_ca7_manifiesto_ilegible(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CA7 (ilegible): un fichero que no es JSON falla con su ruta."""
    comparacion = tmp_path / "comparacion"
    comparacion.mkdir()
    (comparacion / f"{INE}.json").write_text("{no es json", encoding="utf-8")
    _fails(tmp_path, capsys, comparacion, str(comparacion / f"{INE}.json"), "JSON ilegible")


def _with_url(publication: CandidateLayerPublication, url: str) -> CandidateLayerPublication:
    first, *rest = publication.content.items
    window, *other_windows = first.comparison.windows
    image, *other_images = window.images
    window = dataclasses.replace(
        window, images=(dataclasses.replace(image, url=url), *other_images)
    )
    comparison = dataclasses.replace(first.comparison, windows=(window, *other_windows))
    items = (dataclasses.replace(first, comparison=comparison), *rest)
    return dataclasses.replace(
        publication, content=dataclasses.replace(publication.content, items=items)
    )


def _with_omission(publication: CandidateLayerPublication, text: str) -> CandidateLayerPublication:
    first, *rest = publication.content.items
    window, *other_windows = first.comparison.windows
    omitted, *other_omitted = window.omitted
    window = dataclasses.replace(
        window, omitted=(dataclasses.replace(omitted, text=text), *other_omitted)
    )
    comparison = dataclasses.replace(first.comparison, windows=(window, *other_windows))
    items = (dataclasses.replace(first, comparison=comparison), *rest)
    return dataclasses.replace(
        publication, content=dataclasses.replace(publication.content, items=items)
    )


def _with_gap(publication: CandidateLayerPublication, text: str) -> CandidateLayerPublication:
    notes = publication.comparison_notes
    gap = dataclasses.replace(notes.gaps[0], text=text)
    return dataclasses.replace(
        publication, comparison_notes=dataclasses.replace(notes, gaps=(gap,))
    )


def test_ca8_barrera_sobre_url_y_textos_y_sin_falsos_positivos(
    published: dict[str, Any], tmp_path: Path
) -> None:
    """CA8. Dado un fichero publicado con imágenes, cuando casa con `CADASTRAL_REFERENCE_RE`,
    `PARCEL_LOCATOR_RE` o `BANNED_WORDS` (incluidas las URL y los textos de omisión y
    huecos), entonces no se escribe nada (la última barrera de #170 se extiende a las
    imágenes). Y las URL reales de la fixture pasan la barrera (no hay falso positivo)."""
    urls = [
        image["url"]
        for feature in published["document"]["features"]
        for window in feature["properties"]["imagenes_comparacion"]
        for image in window["imagenes"]
    ]
    assert len(urls) == 12
    for path in _written(published["site"]):
        for value in _strings(_load(path)):
            assert CADASTRAL_REFERENCE_RE.search(value) is None, (path.name, value)
            assert PARCEL_LOCATOR_RE.search(value) is None, (path.name, value)
            assert banned_words_in(value) == (), (path.name, value)

    publication = _publication()
    site = tmp_path / "barrera"
    GeoJsonPublishedCandidateSink(site, main.REPOSITORY_URL).publish([publication])
    before = _snapshot(site)
    reference = f"https://www.ign.es/wms/pnoa-historico?x={revision.CATASTRO_TRAIL_ID}"
    tampered = [
        _with_url(publication, reference),
        _with_url(publication, "https://www.ign.es/wms/pnoa-historico?parcela=1"),
        _with_omission(publication, "sin cobertura; su propietario lo cerró"),
        _with_gap(publication, f"hueco {revision.CATASTRO_TRAIL_ID}"),
        _with_gap(publication, "De 1957 a 1997: delito"),
    ]
    for variant in tampered:
        with pytest.raises(PublishedLayerError):
            GeoJsonPublishedCandidateSink(site, main.REPOSITORY_URL).publish([variant])
        assert _snapshot(site) == before


def test_ca9_por_encima_del_umbral_falla_sin_escribir(
    published: dict[str, Any], tmp_path: Path
) -> None:
    """CA9. Dado el fichero de un municipio, cuando su tamaño serializado supera
    `DEFAULT_SIZE_THRESHOLD_BYTES` (3.000.000 bytes, umbral por fichero de #86), entonces la
    publicación **falla** (no solo marca `over_threshold`) y no escribe nada; el presupuesto
    esperado es ~0,2 MB por municipio (ADR 0042 §5)."""
    from parcel_intel.adapters.published_layers.geojson_sink import DEFAULT_SIZE_THRESHOLD_BYTES

    assert DEFAULT_SIZE_THRESHOLD_BYTES == 3_000_000
    size = (published["site"] / "candidatos" / f"{INE}.geojson").stat().st_size
    assert size < 200_000

    site = tmp_path / "umbral"
    use_case = main.build_publish_candidates_use_case(
        MEASUREMENT,
        CANDIDATES_DIR,
        CURATED_DIR,
        COMPARISON_DIR,
        site,
        size_threshold_bytes=size - 1,
    )
    with pytest.raises(PublishedLayerError) as error:
        use_case.execute([INE])
    assert f"pesa {size} bytes, por encima del umbral de {size - 1}" in str(error.value)
    assert _snapshot(site) == {}
    sink = GeoJsonPublishedCandidateSink(site, main.REPOSITORY_URL, size_threshold_bytes=size)
    (file,) = sink.publish([_publication()])
    assert file.size_bytes == size and not file.over_threshold


def test_ca10_procedencia_atribucion_notice_e_indice(published: dict[str, Any]) -> None:
    """CA10. Dado `site/datos/indice.json` y la procedencia, cuando se publica, entonces el
    `.procedencia.json` de la capa lleva el bloque `imagenes_comparacion` (servidor, que no se
    alojan en el sitio, política y atribuciones) y una entrada en `fuentes` por vuelo
    publicado; la `atribucion` de la colección incluye las de las ortofotos; `NOTICE` recoge
    las cadenas «Obra derivada de …» de cada vuelo de ADR 0042 §3 y que las imágenes se
    sirven desde el IGN; y el índice sigue siendo válido."""
    flights = [
        "Obra derivada de Orto-OLISTAT 1997-1999 CC-BY 4.0 scne.es",
        "Obra derivada de PNOA 2006 CC-BY 4.0 scne.es",
        "Obra derivada de PNOA 2017 CC-BY 4.0 scne.es",
        "Obra derivada de PNOA 2023 CC-BY 4.0 scne.es",
    ]
    sidecar = published["sidecar"]
    assert sidecar["imagenes_comparacion"] == {
        "servidores": ["https://www.ign.es/wms/pnoa-historico"],
        "alojadas_en_el_sitio": False,
        "politica": "imagenes_comparacion v2",
        "atribucion": flights,
    }
    image_sources = [s for s in sidecar["fuentes"] if s["origen"] == "pnoa-historico"]
    periods = ["1997-1999", "2006", "2017", "2023"]
    assert image_sources == [
        {
            "origen": "pnoa-historico",
            "url": "https://www.ign.es/wms/pnoa-historico",
            "periodo": period,
            "fecha_descarga": "2026-11-27",
            "licencia": "CC BY 4.0",
            "atribucion": attribution,
        }
        for period, attribution in zip(periods, flights, strict=True)
    ]
    assert not [s for s in sidecar["fuentes"] if s["origen"] == "idem-vuelos-historicos"]
    for attribution in flights:
        assert attribution in published["document"]["properties"]["atribucion"]
        assert attribution in sidecar["atribucion"]
    assert published["document"]["properties"]["procedencia"]["fecha_descarga"] == "2026-11-27"

    notice = NOTICE.read_text(encoding="utf-8")
    section = notice.split("### IGN/CNIG — imágenes de comparación de los tramos a verificar")[1]
    section = section.split("\n### ")[0]
    for vintage, flight in FLIGHTS.items():
        if flight.source == "pnoa-historico":
            assert f"`{attribution_for(vintage)}`" in section, vintage
    assert "se sirven desde el WMS histórico del" in section
    assert "nunca aloja las imágenes" in section.replace("\n  ", " ")

    index = _load(published["site"] / "indice.json")
    (entry,) = index["municipios"]
    assert entry["capas"] == {"candidatos": f"candidatos/{INE}.geojson"}
    assert len(entry["bbox"]) == 4


@pytest.mark.integration
@pytest.mark.red
def test_ca11_el_wms_del_ign_sirve_la_imagen_reciente(published: dict[str, Any]) -> None:
    """CA11. [integración] Dada la URL publicada de la imagen `reciente` del tramo
    `12b804770c6c38bd` de la fixture (Colmenar de Oreja), cuando se pide al WMS del IGN,
    entonces responde con un JPEG de más de 0,02 bytes por píxel (no la blanca de «sin
    cobertura») (marcador `red` e `integration`, job `red-externa`: no bloquea el merge).

    Adaptación (ver el docstring del módulo): `12b804770c6c38bd` no está aprobado, así que
    su URL sale del manifiesto; se pide también la `reciente` publicada del `aprobado`."""
    manifest = _load(MANIFEST)
    window = _stretch(manifest, SIN_REVISION)["ventanas"][0]
    assert window["imagenes"][-1]["procedencia"]["url"] == SIN_REVISION_RECIENTE_URL
    (published_window,) = published["by_id"][PUBLIC_IDS["aprobado"]]["properties"][
        "imagenes_comparacion"
    ]
    assert published_window["imagenes"][-1]["url"] == APROBADO_RECIENTE_URL
    for url, pixels in ((SIN_REVISION_RECIENTE_URL, 448 * 448), (APROBADO_RECIENTE_URL, 640 * 640)):
        request = urllib.request.Request(url, headers={"User-Agent": "paso-comun-tests"})
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (URL fija)
            content_type = response.headers.get_content_type()
            body = response.read()
        assert content_type == "image/jpeg", url
        assert body.startswith(b"\xff\xd8"), url
        assert len(body) / pixels > 0.02, (url, len(body))


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        (lambda d: d["politica"].update(version=1), "otra versión de la política"),
        (lambda d: d["huecos"][0].update(hasta=1998), "otros huecos"),
        (lambda d: d.update(huecos=[]), "otros huecos"),
        (
            lambda d: _stretch(d, APROBADO)["ventanas"][0]["omitidas"].append(
                {
                    "franja": "reciente",
                    "motivo": "sin_cobertura",
                    "probados": [2023],
                    "tipo_error": None,
                }
            ),
            "no cubre exactamente las franjas de la política una vez",
        ),
        (
            lambda d: _stretch(d, APROBADO)["ventanas"][0].update(omitidas=[]),
            "no cubre exactamente las franjas de la política una vez",
        ),
        (
            lambda d: _stretch(d, APROBADO)["ventanas"][0]["omitidas"][0].update(
                motivo="fallo", tipo_error="TimeoutError"
            ),
            "se omitió por un fallo de descarga",
        ),
    ],
    ids=[
        "politica-v1",
        "huecos-cambiados",
        "sin-huecos",
        "franja-repetida",
        "franja-ausente",
        "fallo",
    ],
)
def test_ca12_politica_huecos_y_franjas_incoherentes_fallan(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    change: Callable[[dict[str, Any]], object],
    fragment: str,
) -> None:
    """CA12. Dado un manifiesto de otra versión de la política (`politica` distinta de
    `COMPARISON_POLICY`), con `huecos` distintos de `DECLARED_GAPS`, con una ventana que no
    cubre exactamente las cinco franjas (cada una una vez, como imagen u omitida) o con una
    franja omitida por `fallo` (`imagenes-comparacion` nunca escribe un manifiesto con
    fallos), cuando se publica, entonces falla el municipio sin escribir y el motivo pide
    volver a ejecutar `imagenes-comparacion`."""
    comparacion = _manifest_variant(tmp_path / "comparacion", change)
    _fails(tmp_path, capsys, comparacion, fragment, RERUN)


def test_ca13_multiparte_y_varias_ventanas(
    published: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA13. Dado un aprobado con el tramo en dos piezas (fixture de #170) y otro con varias
    ventanas, cuando se publica, entonces `trazo_px` lleva todas las partes en cada ventana y
    las ventanas salen en el orden de `comparison_windows` (lección de la historia 0002: el
    caso multiparte)."""
    (window,) = published["by_id"][PUBLIC_IDS["propuesto"]]["properties"]["imagenes_comparacion"]
    assert window["trazo_px"] == [
        [[130.0, 320.0], [330.0, 320.0]],
        [[390.0, 320.0], [510.0, 320.0]],
    ]
    assert "bbox=459935%2C4436840%2C460255%2C4437160&" in window["imagenes"][0]["url"]

    long_one = revision.make_candidate(
        "via_pecuaria_oficial",
        "VP-SINT-LARGO",
        (((460000.0, 4438500.0), (460600.0, 4438500.0)),),
        0.8,
        0.5,
    )
    two_pieces = FOUND["propuesto"]
    base = _inputs(tmp_path / "entradas", [long_one, two_pieces], [long_one, two_pieces])
    site = tmp_path / "site"
    code = _publicar(site, base / "comparacion", base / "candidatos", base / "curated")
    assert code == 0, capsys.readouterr().err
    document = _load(site / "candidatos" / f"{INE}.geojson")
    by_id = {f["id"]: f for f in document["features"]}
    from parcel_intel.domain.published_candidate import public_candidate_id

    windows = by_id[public_candidate_id(long_one)]["properties"]["imagenes_comparacion"]
    assert [(w["ancho_px"], w["alto_px"]) for w in windows] == [(1024, 1024), (576, 576)]
    assert "bbox=459949%2C4438244%2C460461%2C4438756&" in windows[0]["imagenes"][0]["url"]
    assert "bbox=460364%2C4438356%2C460652%2C4438644&" in windows[1]["imagenes"][0]["url"]
    assert windows[0]["trazo_px"] == [[[102.0, 512.0], [1302.0, 512.0]]]
    assert windows[1]["trazo_px"] == [[[-728.0, 288.0], [472.0, 288.0]]]
    multi = by_id[PUBLIC_IDS["propuesto"]]["properties"]["imagenes_comparacion"]
    assert [len(w["trazo_px"]) for w in multi] == [2]


def test_ca14_nada_de_los_no_aprobados(published: dict[str, Any]) -> None:
    """CA14. Dado el manifiesto con tramos no aprobados (propuestos, rechazados), cuando se
    publica, entonces ninguna URL, trazo ni ventana suya aparece en el fichero ni en su
    procedencia."""
    manifest = _load(MANIFEST)
    not_approved = {FOUND["rechazado"].candidate_id, SIN_REVISION}
    assert {s["id"] for s in manifest["tramos"]} >= not_approved
    forbidden: list[str] = []
    traces: list[object] = []
    for stretch_id in not_approved:
        for window in _stretch(manifest, stretch_id)["ventanas"]:
            min_x, min_y, max_x, max_y = window["bbox"]
            forbidden.append(f"bbox={min_x}%2C{min_y}%2C{max_x}%2C{max_y}")
            forbidden += [image["procedencia"]["url"] for image in window["imagenes"]]
            traces.append(window["trazo_px"])
        forbidden.append(stretch_id)
    published_traces = [
        window["trazo_px"]
        for feature in published["document"]["features"]
        for window in feature["properties"]["imagenes_comparacion"]
    ]
    for trace in traces:
        assert trace not in published_traces
    for path in _written(published["site"]):
        text = path.read_text(encoding="utf-8")
        for value in forbidden:
            assert value not in text, (path.name, value)


def test_ca15_los_tests_de_170_usan_la_forma_nueva() -> None:
    """CA15. Dados los tests de #170, cuando entra esta historia, entonces se actualizan a la
    forma nueva sin relajarlos: `FEATURE_KEYS` y las claves de la colección ganan
    `imagenes_comparacion` y `comparacion` (literal nuevo), el helper `_publicar` pasa
    `--comparacion` con la fixture, CA15 de #170 se salta también si falta
    `data/derived/comparacion/28043.json`, y el test del sink que esperaba `over_threshold`
    pasa a esperar el fallo."""
    assert "imagenes_comparacion" in historia_170.FEATURE_KEYS
    assert "comparacion" in historia_170.COLLECTION_KEYS
    assert historia_170.COMPARISON_DIR == COMPARISON_DIR
    source = Path(historia_170.__file__).read_text(encoding="utf-8")
    helper = source.split("def _publicar(")[1].split("\ndef ")[0]
    assert '"--comparacion"' in helper and "comparacion: Path = COMPARISON_DIR" in helper
    ca15 = source.split("def test_ca15_flujo_real_en_local")[1].split("\ndef ")[0]
    assert '"comparacion"' in ca15 and "falta data/derived/comparacion/28043.json" in ca15
    sink_tests = ROOT / "tests" / "adapters" / "published_layers" / "test_candidate_sink.py"
    sink_source = sink_tests.read_text(encoding="utf-8")
    threshold = sink_source.split("def test_umbral_de_peso")[1].split("\ndef ")[0]
    assert "pytest.raises(PublishedLayerError" in threshold
    assert "assert published.over_threshold" not in sink_source
    assert re.search(r"assert not published\.over_threshold", sink_source)
