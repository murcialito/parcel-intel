"""Historia #315: publicar la tabla de convergencia en los tramos a verificar
(`publicar-candidatos`, ADR 0057 §1, §4, §5, §6 y §8). Los docstrings copian el criterio.

Entradas SINTÉTICAS (`tests/fixtures/candidatos_publicar/`, ver su LEEME.md): los candidatos
de #168 con 3 aprobados (`aprobado`, `propuesto` y `caducado`), su manifiesto de imágenes y
las capas derivadas de `capas/` (vía pecuaria, camino actual que solapa el 60 % del tramo de
`aprobado`, carretera lejana y un polígono VT de Catastro con id `99999A00109102` alrededor
del tramo de `caducado`). Las unidades históricas son la fixture sintética `280075-w1` de
#137 y copias suyas en `tmp_path` (como en #313). Sin red ni PostGIS, salvo CA11.

Adaptaciones anotadas (CA12 manda sobre CA3, como dice el diseño):
- CA3 «manifiesto inutilizable» y «aprobado con una franja `fallo`» se siguen informando
  primero con el mensaje de #170/#172, sin la tabla de por medio; el formato
  `el candidato <id>: tabla de convergencia: <motivo>` se prueba con un fallo de tabla que
  #172 no filtra (la tabla no encuentra su manifiesto).
"""

import copy
import dataclasses
import json
import math
import shutil
import typing
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest

import tests.acceptance.test_historia_172 as historia_172
import tests.acceptance.test_historia_313 as historia_313
from parcel_intel.adapters.comparison_files import JsonComparisonManifestReader
from parcel_intel.adapters.published_layers import PublishedLayerError
from parcel_intel.adapters.published_layers.convergence import (
    ROW_KEYS,
    SIDECAR_KEYS,
    TABLE_KEYS,
    convergence_document,
)
from parcel_intel.adapters.published_layers.geojson_sink import dump_compact
from parcel_intel.application.build_convergence_tables import NO_MANIFEST
from parcel_intel.cli import main
from parcel_intel.domain.candidate_review import reconcile
from parcel_intel.domain.comparison_image import COMPARISON_SLOTS
from parcel_intel.domain.convergence import (
    CONVERGENCE_METHOD,
    CONVERGENCE_ROW_SOURCES,
    CONVERGENCE_TEXT_VALIDATION,
    CONVERGENCE_TITLE,
    CONVERGENCE_WARNING,
    LAYER_ROW_LABEL,
    ORTHOPHOTO_ROW_LABEL,
    VALUE_TEXT,
    ConvergenceRow,
    InvalidConvergenceTableError,
    StretchNotComputableError,
    YearSpan,
    build_convergence_table,
    compute_convergence_text_hash,
    stretch_from_candidate,
    vetoed_terms_in,
)
from parcel_intel.domain.discrepancy import SourceRef, TrailRef
from parcel_intel.domain.discrepancy_criterion import CriterionRef
from parcel_intel.domain.geometry import Geometry, LineGeometry, MultiLineGeometry
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.public_card import CATASTRO_ATTRIBUTION, banned_words_in
from parcel_intel.domain.published_candidate import public_candidate_id
from parcel_intel.domain.published_comparison import NOT_IN_MANIFEST, TOO_LONG
from parcel_intel.domain.published_convergence import (
    ROW_SOURCE_KEYS,
    PublishedConvergence,
    publish_convergence,
)
from parcel_intel.domain.published_discrepancy import CADASTRAL_REFERENCE_RE, PARCEL_LOCATOR_RE
from parcel_intel.domain.trail import SourceKind
from parcel_intel.ports.errors import TrailLayerFileError
from tests.convergence_support import comparison_for, empty_coverages, line, manifest, stretch
from tests.fixtures.candidatos_publicar import generar
from tests.fixtures.candidatos_revision import generar as revision

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "candidatos_publicar"
CANDIDATES_DIR = FIXTURE / "candidatos"
CURATED_DIR = FIXTURE / "curated"
COMPARISON_DIR = FIXTURE / "comparacion"
MEASUREMENT = FIXTURE / "medicion.json"
CAPAS_DIR = FIXTURE / "capas"
KIT_FIXTURES = ROOT / "tests" / "fixtures" / "kit_campo" / "datos"
INE = "28043"

FOUND = revision.candidates()
APPROVED = {role: FOUND[role] for role in ("aprobado", "propuesto", "caducado")}
PUBLIC_IDS = {role: public_candidate_id(c) for role, c in APPROVED.items()}
FEATURE_KEYS_BEFORE = {
    "etiqueta",
    "texto",
    "aviso",
    "confianza",
    "evidencia",
    "aviso_omision",
    "imagenes_comparacion",
}
# Lista blanca del ADR 0057 §8, literal.
ADR_TABLE_KEYS = ["titulo", "filas", "imagenes", "aviso", "metodo", "criterio"]
ADR_ROW_KEYS = [
    "fuente",
    "rotulo",
    "tipo_evidencia",
    "valor",
    "texto",
    "anio",
    "fecha_consulta",
    "enlaces",
    "atribucion",
]
LAYER_TRAIL_IDS = ("VP-SINT-1", "VP-SINT-2", "VP-SINT-3", "IGN-SINT-1", "IGN-SINT-ASF-1")
UMBRAL_ERROR = "ERROR --umbral-aparece: debe estar en (0, 1]"


# --- Utilidades -----------------------------------------------------------------------


def _run(args: list[str]) -> int:
    parsed = main._build_parser().parse_args(args)
    code: int = parsed.func(parsed)
    return code


def _publicar(
    salida: Path,
    *,
    capas: Path = CAPAS_DIR,
    curated_historico: Path | None = None,
    cache_historico: Path | None = None,
    entrada: Path = CANDIDATES_DIR,
    curated: Path = CURATED_DIR,
    comparacion: Path = COMPARISON_DIR,
    medicion: Path = MEASUREMENT,
    extra: tuple[str, ...] = (),
) -> int:
    return _run(
        [
            "publicar-candidatos",
            "--municipio",
            INE,
            "--medicion",
            str(medicion),
            "--entrada",
            str(entrada),
            "--curated",
            str(curated),
            "--comparacion",
            str(comparacion),
            "--salida",
            str(salida),
            "--capas",
            str(capas),
            "--curated-historico",
            str(curated_historico or salida.parent / "sin_curated_historico"),
            "--cache-historico",
            str(cache_historico or salida.parent / "sin_cache_historico"),
            *extra,
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


def _files(site: Path) -> tuple[Path, Path]:
    return (
        site / "candidatos" / f"{INE}.geojson",
        site / "candidatos" / f"{INE}.geojson.procedencia.json",
    )


def _by_role(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_id = {feature["id"]: feature for feature in document["features"]}
    return {role: by_id[public_id] for role, public_id in PUBLIC_IDS.items()}


def _row(feature: dict[str, Any], source: str) -> dict[str, Any]:
    found: dict[str, Any] = next(
        row for row in feature["properties"]["convergencia"]["filas"] if row["fuente"] == source
    )
    return found


def _copy_capas(base: Path, *only: str) -> Path:
    target = base / "capas"
    for directory in only or generar.CAPAS_DIRECTORIES:
        shutil.copytree(CAPAS_DIR / directory, target / directory)
    return target


def _fails(site: Path, capsys: pytest.CaptureFixture[str], expected: str, **options: Any) -> str:
    assert _publicar(site, **options) == 1
    err = capsys.readouterr().err
    assert expected in err.splitlines(), (expected, err)
    assert f"No se ha escrito nada en {site}." in err
    assert _snapshot(site) == {}
    return err


@pytest.fixture
def published(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    site = tmp_path / "site"
    code = _publicar(site)
    out = capsys.readouterr()
    assert code == 0, out.err
    layer, sidecar = _files(site)
    return {
        "site": site,
        "out": out.out,
        "document": _load(layer),
        "sidecar": _load(sidecar),
        "text": layer.read_text(encoding="utf-8"),
        "sidecar_text": sidecar.read_text(encoding="utf-8"),
    }


# --- CA1 ------------------------------------------------------------------------------


def test_ca1_cada_aprobado_lleva_su_tabla_y_la_lista_blanca_crece_solo_en_convergencia(
    published: dict[str, Any],
) -> None:
    """CA1 (CA2 de #246). Dado un tramo a verificar aprobado, cuando se ejecuta
    `publicar-candidatos`, entonces su feature lleva `convergencia` con la tabla de
    `stretch_from_candidate`. Las filas siguen el orden de `CONVERGENCE_ROW_SOURCES`. La lista
    blanca de la feature solo crece en `convergencia`, y la de `convergencia` es exactamente la
    del ADR 0057 §8."""
    assert list(TABLE_KEYS) == ADR_TABLE_KEYS and list(ROW_KEYS) == ADR_ROW_KEYS
    reader = main._trail_layer_reader(CAPAS_DIR)
    use_case = main.BuildConvergenceTablesUseCase(
        layers=reader,
        historic=main.build_historic_coverage_source(
            published["site"] / "nada", published["site"] / "nada"
        ),
        comparisons=JsonComparisonManifestReader(COMPARISON_DIR),
    )
    result = use_case.execute(INE, [stretch_from_candidate(c) for c in APPROVED.values()])
    tables = {r.stretch_id: r.table for r in result.results}
    for role, feature in _by_role(published["document"]).items():
        properties = feature["properties"]
        assert set(properties) == FEATURE_KEYS_BEFORE | {"convergencia"}
        table = properties["convergencia"]
        assert set(table) == set(ADR_TABLE_KEYS)  # el JSON publicado ordena las claves
        for row in table["filas"]:
            assert set(row) == set(ADR_ROW_KEYS)
        assert [row["fuente"] for row in table["filas"]] == list(ROW_SOURCE_KEYS)
        assert len(ROW_SOURCE_KEYS) == len(CONVERGENCE_ROW_SOURCES)
        expected = tables[APPROVED[role].candidate_id]
        assert expected is not None
        assert table == convergence_document(publish_convergence(expected))
    aprobado = _by_role(published["document"])["aprobado"]
    assert _row(aprobado, "via_pecuaria_oficial")["valor"] == "aparece"
    assert _row(aprobado, "ign_red_transporte")["valor"] == "aparece"  # 60 % >= 0,5
    assert _row(aprobado, "catastro_vt")["valor"] == "no_aparece"
    caducado = _by_role(published["document"])["caducado"]
    assert _row(caducado, "catastro_vt")["valor"] == "aparece"


# --- CA2 ------------------------------------------------------------------------------


_ALLOWED_TYPES = {
    bool,
    str,
    int,
    float,
    date,
    type(None),
    YearSpan,
    ConvergenceRow,
    PublishedConvergence,
}
_FORBIDDEN_TYPES = (
    Geometry,
    MultiLineGeometry,
    LineGeometry,
    Provenance,
    TrailRef,
    SourceRef,
)


def _walk_types(tp: object, seen: set[object]) -> None:
    """Recorre las anotaciones (también anidadas) hasta los tipos hoja (lección de #240)."""
    origin = typing.get_origin(tp)
    if origin is not None:
        for arg in typing.get_args(tp):
            if arg is not Ellipsis:
                _walk_types(arg, seen)
        return
    if isinstance(tp, str):
        return  # valores de un Literal
    if isinstance(tp, type) and issubclass(tp, _FORBIDDEN_TYPES):
        raise AssertionError(f"tipo prohibido en la tabla publicada: {tp}")
    assert tp in _ALLOWED_TYPES, f"tipo fuera de la lista blanca: {tp!r}"
    if dataclasses.is_dataclass(tp) and tp not in seen:
        seen.add(tp)
        for name, hint in typing.get_type_hints(tp).items():
            assert name != "stretch_id", f"campo stretch_id en {tp}"
            _walk_types(hint, seen)


def test_ca2_sin_catastro_ni_ids_ni_textos_ajenos(published: dict[str, Any]) -> None:
    """CA2 (CA4 de #246, candidatos). Un test falla si el fichero publicado o su
    `.procedencia.json` contienen: geometría o atributos de Catastro; algo que case con
    `CADASTRAL_REFERENCE_RE` o `PARCEL_LOCATOR_RE`; un `candidate_id` o `trail_id` dentro de
    `convergencia`; una palabra vetada; un texto de la tabla que no esté entre los validados
    (huella `CONVERGENCE_TEXT_VALIDATION`) ni entre los rótulos de `LAYER_ROW_LABEL` y
    `ORTHOPHOTO_ROW_LABEL`. La fila de Catastro, cuando no está «Sin cobertura», lleva
    `atribucion == [CATASTRO_ATTRIBUTION]` y `fecha_consulta`. Un test recorre las anotaciones
    de `PublishedConvergence` (lección de #240) y falla si alcanza `Geometry`, `Provenance`,
    `TrailRef` o un campo `stretch_id`."""
    document, sidecar = published["document"], published["sidecar"]
    # Geometría y atributos de Catastro: ni su polígono, ni su id, ni sus atributos.
    for feature in document["features"]:
        assert feature["geometry"]["type"] in {"LineString", "MultiLineString"}
    for text in (published["text"], published["sidecar_text"]):
        for leaked in (generar.CATASTRO_LAYER_TRAIL_ID, '"area_m2"', '"clases"', "(VT)"):
            assert leaked not in text, leaked
        assert "example.invalid/capas" not in text  # ninguna procedencia de capa
    for value in [*_strings(document), *_strings(sidecar)]:
        assert CADASTRAL_REFERENCE_RE.search(value) is None, value
        assert PARCEL_LOCATOR_RE.search(value) is None, value
        assert banned_words_in(value) == (), value
    # Ningún id interno ni de trazado dentro de `convergencia` (ni en su procedencia).
    ids = [c.candidate_id for c in FOUND.values()]
    ids += [c.subject.trail_id for c in FOUND.values()]
    ids += [*LAYER_TRAIL_IDS, generar.CATASTRO_LAYER_TRAIL_ID]
    blocks = [f["properties"]["convergencia"] for f in document["features"]]
    blocks.append(sidecar["convergencia"])
    for block in blocks:
        text = json.dumps(block, ensure_ascii=False)
        for identifier in ids:
            assert identifier not in text, identifier
    assert set(sidecar["convergencia"]) == set(SIDECAR_KEYS)
    # Textos validados por su huella y rótulos aprobados.
    assert compute_convergence_text_hash() == CONVERGENCE_TEXT_VALIDATION.text_hash
    labels = set(LAYER_ROW_LABEL.values()) | {
        ORTHOPHOTO_ROW_LABEL.format(franja=slot.name) for slot in COMPARISON_SLOTS
    }
    for table in blocks[:-1]:
        assert table["titulo"] == CONVERGENCE_TITLE
        assert table["aviso"] == CONVERGENCE_WARNING
        assert table["imagenes"] is None
        for row in table["filas"]:
            assert row["rotulo"] in labels
            assert row["texto"] == VALUE_TEXT[row["valor"]]
            for text in (row["rotulo"], row["texto"], *row["atribucion"]):
                assert vetoed_terms_in(text) == (), text
            if row["fuente"] == "catastro_vt" and row["valor"] != "sin_cobertura":
                assert row["atribucion"] == [CATASTRO_ATTRIBUTION]
                assert row["fecha_consulta"] == "2026-11-26"
    # Las anotaciones de la entidad publicada no alcanzan nada prohibido.
    _walk_types(PublishedConvergence, set())
    assert "stretch_id" not in {f.name for f in dataclasses.fields(PublishedConvergence)}


# --- CA3 ------------------------------------------------------------------------------


def test_ca3_todo_o_nada_por_cada_motivo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """CA3 (CA6 de #246, candidatos). Todo o nada: sale con 1, informa y no escribe nada en
    estos casos: una capa derivada ilegible; el manifiesto inutilizable; un aprobado sin tabla
    (por ejemplo, con una franja `fallo`); una `HistoricCoverageError`; una fila inválida. El
    mensaje es `ERROR <ine>: el candidato <candidate_id>: tabla de convergencia: <motivo fijo>`,
    o `ERROR <ine>: tabla de convergencia: <motivo fijo>` si el fallo es de todo el
    municipio."""
    # Capa derivada ilegible.
    capas = _copy_capas(tmp_path / "ilegible")
    (capas / "vias_pecuarias" / f"{INE}.geojson").write_text("{no es json", encoding="utf-8")
    _fails(
        tmp_path / "s1",
        capsys,
        f"ERROR {INE}: tabla de convergencia: capa via_pecuaria_oficial no válida; "
        "regenera las capas derivadas",
        capas=capas,
    )
    # Manifiesto inutilizable: el mensaje de #172 va primero (CA12).
    comparacion = historia_172._manifest_variant(
        tmp_path / "otra_politica", lambda d: d["politica"].update(version=1)
    )
    _fails(
        tmp_path / "s2",
        capsys,
        f"ERROR {INE}: manifiesto de imágenes no utilizable: el manifiesto es de otra versión "
        "de la política de imágenes; vuelve a ejecutar imagenes-comparacion",
        comparacion=comparacion,
    )
    # Un aprobado con una franja `fallo`: el motivo de #172 va primero (CA12).
    aprobado = APPROVED["aprobado"].candidate_id

    def with_failure(document: dict[str, Any]) -> None:
        tramo = next(t for t in document["tramos"] if t["id"] == aprobado)
        omitted = tramo["ventanas"][0]["omitidas"][0]
        omitted.update(motivo="fallo", tipo_error="ConnectionError")

    _fails(
        tmp_path / "s3",
        capsys,
        f"ERROR {INE}: no publicable: el candidato {aprobado}: una franja se omitió por un "
        "fallo de descarga; vuelve a ejecutar imagenes-comparacion",
        comparacion=historia_172._manifest_variant(tmp_path / "fallo", with_failure),
    )
    # Un aprobado sin tabla por un motivo que #172 no filtra: la tabla no ve el manifiesto.
    real = main.BuildConvergenceTablesUseCase

    def blind(**kwargs: Any) -> Any:
        kwargs["comparisons"] = JsonComparisonManifestReader(tmp_path / "sin_manifiesto")
        return real(**kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(main, "BuildConvergenceTablesUseCase", blind)
        first = sorted(c.candidate_id for c in APPROVED.values())[0]
        _fails(
            tmp_path / "s4",
            capsys,
            f"ERROR {INE}: el candidato {first}: tabla de convergencia: {NO_MANIFEST}",
        )
    # HistoricCoverageError: aprobación caducada en una unidad aceptada.
    curated, cache = tmp_path / "historico", tmp_path / "cache"
    curated.mkdir()
    historia_313._add_unit(curated, cache, historia_313.UNIT_ID)
    historia_313._edit_csv(curated, historia_313.UNIT_ID, "Plaza en el centro", "Plaza central")
    _fails(
        tmp_path / "s5",
        capsys,
        f"ERROR {INE}: tabla de convergencia: cobertura histórica: la unidad "
        f"{historia_313.UNIT_ID} no es utilizable: aprobaciones caducadas: T001, T002; "
        "vuelve a revisar la unidad",
        curated_historico=curated,
        cache_historico=cache,
    )
    # Fila inválida: un año fuera de rango en la capa del camino actual.
    capas = _copy_capas(tmp_path / "anio")
    path = capas / "camino_actual" / f"{INE}.geojson"
    document = _load(path)
    document["features"][0]["properties"]["fecha_dato"] = "1700-01-01"
    path.write_text(json.dumps(document), encoding="utf-8")
    _fails(
        tmp_path / "s6", capsys, f"ERROR {INE}: tabla de convergencia: fila no válida", capas=capas
    )


# --- CA4 ------------------------------------------------------------------------------


def test_ca4_sin_historico_ni_catastro_salen_sin_cobertura(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA4 (CA7 de #246). Sin `curated/historico/` ni capas de Catastro, las filas de
    planimetría, MTN50 y Catastro salen «Sin cobertura» y no es fallo."""
    capas = _copy_capas(tmp_path, "vias_pecuarias", "camino_actual", "camino_asfaltado")
    site = tmp_path / "site"
    assert _publicar(site, capas=capas) == 0, capsys.readouterr().err
    for feature in _load(_files(site)[0])["features"]:
        for source in ("planimetria_historica", "mtn50_historico", "catastro_vt"):
            row = _row(feature, source)
            assert row["valor"] == "sin_cobertura" and row["texto"] == "Sin cobertura"
            assert (row["anio"], row["fecha_consulta"], row["atribucion"]) == (None, None, [])


# --- CA5 ------------------------------------------------------------------------------


def test_ca5_umbral_de_aparece_configurable_y_registrado(
    tmp_path: Path, published: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """CA5 (CA8 de #246). Con `--umbral-aparece 0.8`, el cálculo usa 0,8: en la fixture, un
    solape del 60 % pasa de «Aparece» a «No aparece». El `.procedencia.json` registra
    `convergencia.umbral_aparece: 0.8`; sin la opción, registra 0,5. Con `0`, `1.5` o `nan`,
    sale con 1 antes de leer nada."""
    aprobado = _by_role(published["document"])["aprobado"]
    assert _row(aprobado, "ign_red_transporte")["valor"] == "aparece"
    assert published["sidecar"]["convergencia"]["umbral_aparece"] == 0.5

    site = tmp_path / "umbral"
    code = _publicar(site, extra=("--umbral-aparece", "0.8"))
    assert code == 0, capsys.readouterr().err
    capsys.readouterr()
    layer, sidecar = _files(site)
    aprobado = _by_role(_load(layer))["aprobado"]
    assert _row(aprobado, "ign_red_transporte")["valor"] == "no_aparece"
    assert _load(sidecar)["convergencia"]["umbral_aparece"] == 0.8

    def no_debe_leerse(*args: object, **kwargs: object) -> object:
        raise AssertionError("no debe leer nada")

    for value in ("0", "1.5", "nan"):
        bad = tmp_path / f"malo-{value}"
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(main, "build_historic_coverage_source", no_debe_leerse)
            patch.setattr(main, "build_publish_candidates_use_case", no_debe_leerse)
            code = _publicar(
                bad, medicion=tmp_path / "no_existe.json", extra=("--umbral-aparece", value)
            )
        out = capsys.readouterr()
        assert code == 1
        assert out.err.splitlines() == [UMBRAL_ERROR]
        assert out.out == ""
        assert not bad.exists()
    assert math.isnan(float("nan"))


# --- CA6 ------------------------------------------------------------------------------


def test_ca6_la_tabla_que_pasa_del_umbral_de_peso_no_se_escribe(
    tmp_path: Path, published: dict[str, Any]
) -> None:
    """CA6 (CA9 de #246). Si la tabla hace pasar el fichero de 3.000.000 bytes, sale con 1 y
    no escribe. Se prueba inyectando un umbral bajo en el sink."""
    size = len(published["text"].encode("utf-8"))
    without = copy.deepcopy(published["document"])
    for feature in without["features"]:
        del feature["properties"]["convergencia"]
    size_without = len(dump_compact(without).encode("utf-8"))
    assert size_without < size - 1  # sin la tabla cabría: es la tabla la que lo pasa
    site = tmp_path / "pesado"
    use_case = main.build_publish_candidates_use_case(
        MEASUREMENT,
        CANDIDATES_DIR,
        CURATED_DIR,
        COMPARISON_DIR,
        site,
        CAPAS_DIR,
        main.build_historic_coverage_source(tmp_path / "nada", tmp_path / "nada"),
        size_threshold_bytes=size - 1,
    )
    with pytest.raises(PublishedLayerError) as error:
        use_case.execute([INE])
    assert f"pesa {size} bytes, por encima del umbral de {size - 1}" in str(error.value)
    assert _snapshot(site) == {}


def test_ca6_por_la_cli_sale_con_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA6, por la CLI: el error del sink sale con 1 sin escribir nada."""
    real = main.build_publish_candidates_use_case

    def small(*args: Any, **kwargs: Any) -> Any:
        kwargs["size_threshold_bytes"] = 1000
        return real(*args, **kwargs)

    monkeypatch.setattr(main, "build_publish_candidates_use_case", small)
    site = tmp_path / "site"
    assert _publicar(site) == 1
    assert "por encima del umbral de 1000" in capsys.readouterr().err
    assert _snapshot(site) == {}


# --- CA7 ------------------------------------------------------------------------------


def test_ca7_dos_publicaciones_dan_los_mismos_bytes(tmp_path: Path) -> None:
    """CA7 (CA10 de #246). Dos publicaciones con las mismas entradas dan ficheros idénticos
    byte a byte."""
    first, second = tmp_path / "a" / "site", tmp_path / "b" / "site"
    assert _publicar(first) == 0
    assert _publicar(second) == 0
    assert _snapshot(first) == _snapshot(second)
    assert _snapshot(first)


# --- CA8 ------------------------------------------------------------------------------


def test_ca8_tramo_demasiado_largo_sin_filas_de_imagen() -> None:
    """CA8. `build_convergence_table(..., without_images_if_too_long=True)` con un tramo
    `tramo_demasiado_largo` da una tabla sin filas de imagen y con `images_unavailable=True`.
    Con `False` (por defecto), sigue dando `StretchNotComputableError(TOO_LONG)`.
    `CONVERGENCE_METHOD == ("convergencia_fuentes", 2)`. No se puede construir una
    `ConvergenceTable` con `images_unavailable=True` y filas de imagen."""
    axis = line((0, 0), (200, 0))
    too_long = dataclasses.replace(comparison_for(axis), status="tramo_demasiado_largo", windows=())
    tramo = stretch(axis)
    with pytest.raises(StretchNotComputableError) as error:
        build_convergence_table(tramo, CONVERGENCE_ROW_SOURCES, {}, empty_coverages(), too_long)
    assert error.value.reason == TOO_LONG
    table = build_convergence_table(
        tramo,
        CONVERGENCE_ROW_SOURCES,
        {},
        empty_coverages(),
        too_long,
        without_images_if_too_long=True,
    )
    assert table.images_unavailable is True
    assert all(row.evidence_kind == "trazado" for row in table.rows)
    assert [row.source_key for row in table.rows] == list(ROW_SOURCE_KEYS[:5])
    assert publish_convergence(table).images_note == "Imagen no disponible"
    # Otro motivo se sigue propagando con la opción activa.
    with pytest.raises(StretchNotComputableError) as error:
        build_convergence_table(
            tramo,
            CONVERGENCE_ROW_SOURCES,
            {},
            empty_coverages(),
            manifest().stretch(tramo.stretch_id),
            without_images_if_too_long=True,
        )
    assert error.value.reason == NOT_IN_MANIFEST
    assert CONVERGENCE_METHOD == CriterionRef("convergencia_fuentes", 2)
    with_images = build_convergence_table(
        tramo, CONVERGENCE_ROW_SOURCES, {}, empty_coverages(), comparison_for(axis)
    )
    with pytest.raises(InvalidConvergenceTableError, match="filas de imagen"):
        dataclasses.replace(with_images, images_unavailable=True)


# --- CA9 ------------------------------------------------------------------------------


def test_ca9_el_kit_de_campo_admite_convergencia_y_no_la_exporta(
    tmp_path: Path, published: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """CA9. `publicar-kit-campo` y `publicar-kit-campo-qfield` siguen funcionando con un
    `candidatos/<ine>.geojson` y un `discrepancias/<ine>.geojson` que llevan `convergencia`, y
    no la exportan."""
    entrada = tmp_path / "entrada"
    shutil.copytree(KIT_FIXTURES, entrada)
    shutil.copytree(published["site"] / "candidatos", entrada / "candidatos")
    table = published["document"]["features"][0]["properties"]["convergencia"]
    path = entrada / "discrepancias" / f"{INE}.geojson"
    document = _load(path)
    for feature in document["features"]:
        feature["properties"]["convergencia"] = table
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    capsys.readouterr()

    salida = tmp_path / "salida"
    common = ["--municipio", INE, "--entrada", str(entrada), "--salida", str(salida)]
    assert _run(["publicar-kit-campo", *common]) == 0, capsys.readouterr().err
    assert _run(["publicar-kit-campo-qfield", *common]) == 0, capsys.readouterr().err
    written = [p for p in (salida / "kit").rglob("*") if p.is_file()]
    assert any(p.suffix == ".gpx" for p in written)
    assert any(p.suffix == ".gpkg" for p in written)
    markers = ["convergencia", CONVERGENCE_TITLE, "Sin cobertura", "Imagen disponible"]
    for file in written:
        if file.suffix == ".zip":
            continue  # comprimido: su contenido es el .gpkg/.qgs ya comprobados
        content = file.read_bytes()
        for marker in markers:
            assert marker.encode("utf-8") not in content, (file.name, marker)


# --- CA10 -----------------------------------------------------------------------------


def test_ca10_los_tests_de_otras_historias_usan_la_forma_nueva() -> None:
    """CA10. Los tests de #170, #172, #208 y #240 se actualizan a la forma nueva sin
    relajarlos. Las búsquedas de fugas que antes recorrían el fichero entero se acotan al
    bloque que protegían, y `convergencia` se cubre con su propia lista blanca (lección de
    #172)."""
    acceptance = ROOT / "tests" / "acceptance"
    source_170 = (acceptance / "test_historia_170.py").read_text(encoding="utf-8")
    assert '"convergencia",  # #315' in source_170
    helper_170 = source_170.split("def _publicar(")[1].split("\ndef ")[0]
    assert '"--capas"' in helper_170 and '"--curated-historico"' in helper_170
    ca7 = source_170.split("def test_ca7_")[1].split("\ndef ")[0]
    assert 'pop("convergencia")' in ca7 and "TABLE_KEYS" in ca7 and "ROW_KEYS" in ca7
    for leak in ('"0.8"', '"0.5"', '"candidate"', '"huella"'):
        assert leak in ca7, leak  # la búsqueda de fugas sigue entera
    source_172 = (acceptance / "test_historia_172.py").read_text(encoding="utf-8")
    helper_172 = source_172.split("def _publicar(")[1].split("\ndef ")[0]
    assert '"--capas"' in helper_172 and '"--curated-historico"' in helper_172
    ca2 = source_172.split("def test_ca2_")[1].split("\ndef ")[0]
    assert 'del feature["properties"]["convergencia"]' in ca2 and '"sin_cobertura"' in ca2
    source_208 = (FIXTURE / "generar_idem.py").read_text(encoding="utf-8")
    assert '"--capas"' in source_208
    site_fixture = (
        ROOT / "tests" / "fixtures" / "site" / "candidatos_comparacion_idem_28043.geojson"
    )
    (feature,) = _load(site_fixture)["features"]
    assert set(feature["properties"]["convergencia"]) == set(ADR_TABLE_KEYS)
    source_240 = (acceptance / "test_historia_240.py").read_text(encoding="utf-8")
    assert '"images_unavailable",  # #315' in source_240
    assert 'CriterionRef("convergencia_fuentes", 2)' in source_240


# --- CA11 -----------------------------------------------------------------------------


@pytest.mark.integration
def test_ca11_datos_reales_de_28043(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CA11 (CA11 de #246) [integración]. Con la caché cruda real y las capas derivadas reales
    de 28043, `publicar-candidatos` publica los aprobados con tabla y el fichero pasa el test
    de CA2. Sin red: si faltan los datos reales en local (`data/`, `curated/candidatos/`), se
    salta."""
    medicion = ROOT / "data" / "derived" / "validacion" / "medicion.json"
    entrada = ROOT / "data" / "derived" / "candidatos" / "interno"
    curated = ROOT / "curated" / "candidatos"
    comparacion = ROOT / "data" / "derived" / "comparacion"
    capas = ROOT / "data" / "derived"
    needed = [
        medicion,
        entrada / f"{INE}.geojson",
        curated / INE / "revision.json",
        comparacion / f"{INE}.json",
        capas / "vias_pecuarias" / f"{INE}.geojson",
    ]
    missing = [str(path.relative_to(ROOT)) for path in needed if not path.is_file()]
    if missing:
        pytest.skip(f"faltan datos reales: {', '.join(missing)}")
    site = tmp_path / "site"
    code = _publicar(
        site,
        medicion=medicion,
        entrada=entrada,
        curated=curated,
        comparacion=comparacion,
        capas=capas,
        curated_historico=ROOT / "curated" / "historico",
        cache_historico=ROOT / "data" / "raw" / "ign_planimetrias",
    )
    out = capsys.readouterr()
    assert code == 0, out.err
    layer, sidecar = _files(site)
    document = _load(layer)
    for feature in document["features"]:
        assert set(feature["properties"]["convergencia"]) == set(ADR_TABLE_KEYS)
    for value in [*_strings(document), *_strings(_load(sidecar))]:
        assert CADASTRAL_REFERENCE_RE.search(value) is None, value
        assert PARCEL_LOCATOR_RE.search(value) is None, value
        assert banned_words_in(value) == (), value


# --- CA12 -----------------------------------------------------------------------------


class _NoLayers:
    """Lector de capas que falla si se llama (CA12)."""

    def __init__(self) -> None:
        self.calls = 0

    def get_layer(self, source: SourceKind, municipality_code: str) -> Any:
        self.calls += 1
        raise AssertionError("no se debe leer ninguna capa derivada")


class _NoHistoric:
    """Cobertura histórica que falla si se lee (CA12)."""

    def __init__(self) -> None:
        self.calls = 0

    def get_coverage(self, document_kind: str) -> Any:
        self.calls += 1
        raise AssertionError("no se debe leer curated/historico")

    def skipped_units(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        return ()


def _review_document(*entries: dict[str, object]) -> dict[str, object]:
    return {"municipio": INE, "revisiones": list(entries)}


def _curated_with(base: Path, document: dict[str, object]) -> Path:
    (base / INE).mkdir(parents=True)
    (base / INE / "revision.json").write_text(json.dumps(document), encoding="utf-8")
    return base


def test_ca12_los_fallos_de_antes_van_primero_y_sin_leer_capas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """CA12 (arquitecto). Los fallos que ya existían se siguen informando primero y con el
    mismo mensaje de #170 y #172, sin la tabla de por medio: aprobaciones caducadas u
    huérfanas; manifiesto inutilizable (`manifiesto de imágenes no utilizable: …`); ningún
    aprobado; fuente no redistribuible; un aprobado `tramo_demasiado_largo` o con una franja
    `fallo` (`no publicable: el candidato <id>: <motivo de #172>`). En estos casos no se lee
    ninguna capa derivada ni `curated/historico/`: un test usa un lector de capas que falla si
    se llama."""
    layers, historic = _NoLayers(), _NoHistoric()
    monkeypatch.setattr(main, "_trail_layer_reader", lambda derived: layers)
    monkeypatch.setattr(main, "build_historic_coverage_source", lambda *a, **k: historic)
    aprobado, rechazado = FOUND["aprobado"], FOUND["rechazado"]
    stale = dict(historia_172._review(aprobado), candidate_sha256="0" * 64)
    cases: list[tuple[str, dict[str, Any]]] = [
        (
            f"ERROR {INE}: revisiones no vigentes; caducadas: {aprobado.candidate_id}; "
            f"huérfanas: ninguna; corrígelas en curated/candidatos/{INE}/revision.json",
            {"curated": _curated_with(tmp_path / "caducada", _review_document(stale))},
        ),
        (
            f"ERROR {INE}: no publicable: ningún candidato aprobado",
            {"curated": _curated_with(tmp_path / "ninguno", _review_document())},
        ),
        (
            f"ERROR {INE}: no publicable: el candidato {rechazado.candidate_id} tiene un "
            "trazado de una fuente no redistribuible",
            {
                "curated": _curated_with(
                    tmp_path / "catastro", _review_document(historia_172._review(rechazado))
                )
            },
        ),
        (
            f"ERROR {INE}: manifiesto de imágenes no utilizable: el manifiesto es de otra "
            "versión de la política de imágenes; vuelve a ejecutar imagenes-comparacion",
            {
                "comparacion": historia_172._manifest_variant(
                    tmp_path / "politica", lambda d: d["politica"].update(version=1)
                )
            },
        ),
    ]

    def with_failure(document: dict[str, Any]) -> None:
        tramo = next(t for t in document["tramos"] if t["id"] == aprobado.candidate_id)
        tramo["ventanas"][0]["omitidas"][0].update(motivo="fallo", tipo_error="ConnectionError")

    cases.append(
        (
            f"ERROR {INE}: no publicable: el candidato {aprobado.candidate_id}: una franja se "
            "omitió por un fallo de descarga; vuelve a ejecutar imagenes-comparacion",
            {"comparacion": historia_172._manifest_variant(tmp_path / "fallo", with_failure)},
        )
    )
    long = revision.make_candidate(
        "via_pecuaria_oficial",
        "VP-SINT-LARGO",
        (((460000.0, 4440000.0), (462500.0, 4440000.0)),),
        0.8,
        0.5,
    )
    base = historia_172._inputs(tmp_path / "largo", [long], [long])
    cases.append(
        (
            f"ERROR {INE}: no publicable: el candidato {long.candidate_id}: {TOO_LONG}",
            {
                "entrada": base / "candidatos",
                "curated": base / "curated",
                "comparacion": base / "comparacion",
            },
        )
    )
    for index, (expected, options) in enumerate(cases):
        _fails(tmp_path / f"site-{index}", capsys, expected, **options)
    assert layers.calls == 0 and historic.calls == 0


# --- CA13 -----------------------------------------------------------------------------


def test_ca13_capa_corrupta_o_incompleta_con_motivo_fijo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA13 (arquitecto). Una capa derivada corrupta (JSON ilegible) o incompleta
    (`camino_actual` sin `camino_asfaltado`) se informa como `ERROR 28043: tabla de
    convergencia: capa <fuente> no válida; regenera las capas derivadas`. El motivo es fijo: no
    cita la ruta ni el mensaje de pydantic. Una capa ausente no es fallo: su fila sale «Sin
    cobertura»."""
    corrupt = _copy_capas(tmp_path / "corrupta")
    (corrupt / "catastro_caminos" / f"{INE}.geojson").write_text("[1, 2", encoding="utf-8")
    err = _fails(
        tmp_path / "s1",
        capsys,
        f"ERROR {INE}: tabla de convergencia: capa catastro_vt no válida; regenera las capas "
        "derivadas",
        capas=corrupt,
    )
    assert str(corrupt) not in err and "JSON" not in err

    invalid = _copy_capas(tmp_path / "pydantic")
    path = invalid / "vias_pecuarias" / f"{INE}.geojson"
    document = _load(path)
    document["features"][0]["geometry"] = {"type": "Punto", "coordinates": "valor-secreto"}
    path.write_text(json.dumps(document), encoding="utf-8")
    _fails(
        tmp_path / "s2",
        capsys,
        f"ERROR {INE}: tabla de convergencia: capa via_pecuaria_oficial no válida; regenera "
        "las capas derivadas",
        capas=invalid,
    )
    for leaked in (str(invalid), "valor-secreto", "input_value", "discriminator", "Punto"):
        assert leaked not in err, leaked

    incomplete = _copy_capas(tmp_path / "incompleta", "vias_pecuarias", "camino_actual")
    err = _fails(
        tmp_path / "s3",
        capsys,
        f"ERROR {INE}: tabla de convergencia: capa ign_red_transporte no válida; regenera las "
        "capas derivadas",
        capas=incomplete,
    )
    assert "camino_asfaltado" not in err
    assert issubclass(main.TrailLayerFormatError, TrailLayerFileError)

    absent = _copy_capas(tmp_path / "ausente", "camino_actual", "camino_asfaltado")
    site = tmp_path / "s4"
    assert _publicar(site, capas=absent) == 0, capsys.readouterr().err
    for feature in _load(_files(site)[0])["features"]:
        assert _row(feature, "via_pecuaria_oficial")["valor"] == "sin_cobertura"


# --- CA14 -----------------------------------------------------------------------------


def test_ca14_unidad_con_veredicto_negativo_se_omite_y_se_informa(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA14 (arquitecto). Con una unidad de `curated/historico/` de veredicto negativo, la
    publicación termina con 0. La unidad no cuenta y stdout dice `unidad histórica omitida
    <unit_id>: <motivos>`. Con una aprobación caducada en una unidad aceptada, sale con 1 con
    `ERROR 28043: tabla de convergencia: cobertura histórica: la unidad <unit_id> no es
    utilizable: <motivo>`."""
    curated, cache = tmp_path / "historico", tmp_path / "cache"
    curated.mkdir()
    historia_313._add_unit(curated, cache, historia_313.UNIT_ID)
    historia_313._add_unit(curated, cache, "280075-w2")
    # P05 +100 m en X: el LOO de la unidad pasa de los 15 m (veredicto negativo, #313 CA3).
    historia_313._edit_csv(curated, "280075-w2", "467082.0", "467182.0")
    source = main.build_historic_coverage_source(curated, cache)
    coverage = source.get_coverage("planimetria")
    assert [unit.unit_id for unit in coverage.units] == [historia_313.UNIT_ID]
    ((unit_id, reasons),) = source.skipped_units()
    assert unit_id == "280075-w2" and reasons

    site = tmp_path / "site"
    code = _publicar(site, curated_historico=curated, cache_historico=cache)
    out = capsys.readouterr()
    assert code == 0, out.err
    assert f"unidad histórica omitida 280075-w2: {'; '.join(reasons)}" in out.out.splitlines()
    assert _files(site)[0].is_file()

    historia_313._edit_csv(curated, historia_313.UNIT_ID, "Plaza en el centro", "Plaza central")
    _fails(
        tmp_path / "caducada",
        capsys,
        f"ERROR {INE}: tabla de convergencia: cobertura histórica: la unidad "
        f"{historia_313.UNIT_ID} no es utilizable: aprobaciones caducadas: T001, T002; "
        "vuelve a revisar la unidad",
        curated_historico=curated,
        cache_historico=cache,
    )


def test_ca14_reconcile_de_la_fixture_tiene_tres_aprobados() -> None:
    """Comprobación de la fixture que usan los criterios: 3 aprobados vigentes."""
    from parcel_intel.adapters.curated_candidates import CuratedCandidateReviewFiles

    state = reconcile(revision.report(), CuratedCandidateReviewFiles(CURATED_DIR).reviews(INE))
    assert {c.candidate_id for c in state.approved()} == {c.candidate_id for c in APPROVED.values()}
