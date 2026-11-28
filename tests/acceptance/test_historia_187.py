"""Historia #187: catálogo cerrado y versionado de citas normativas (entidad, carga y ADR).

Un test por criterio. Las fixtures de `tests/fixtures/normativa/` son SINTÉTICAS
(`BOE-A-9999-1`, «Texto sintético de prueba…»): ninguna es texto legal real. Las variantes
mutadas se construyen con `tests/fixtures/normativa/generar.py`, que recalcula las huellas con
`hashlib` sin pasar por el código de producción. Sin red.
"""

import copy
import json
import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from parcel_intel.adapters.curated_normative import CuratedNormativeCatalogFile
from parcel_intel.domain.normative_citation import (
    BOE_INFORMATIVE_NOTICE,
    BOE_REUSE_LICENSE,
    BOE_SOURCE_NOTICE,
    InvalidNormativeCitationError,
    NormativeCitation,
    citation_attribution,
    text_fingerprint,
)
from parcel_intel.domain.trail import SourceKind
from parcel_intel.ports.errors import NormativeCatalogFileError
from tests.acceptance import test_historia_43 as h43
from tests.fixtures.normativa import generar

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "src" / "parcel_intel" / "sources" / "REGISTRY.md"
NOTICE = REPO / "NOTICE"
SENTINEL = "valor-secreto-rechazado"
# Referencia catastral sintética con forma válida (municipio inexistente 99999, lección de #95).
FAKE_REFERENCE = "99999A00109101"
HEX64 = re.compile(r"\b[0-9a-f]{64}\b")

Doc = dict[str, Any]


def _citation(**overrides: Any) -> NormativeCitation:
    text = overrides.pop("text", "Texto sintético de prueba (historia #187).")
    fields: dict[str, Any] = {
        "citation_id": "sintetica-art-01",
        "norm_title": "Ley sintética 9/2090, de prueba",
        "boe_id": "BOE-A-9999-1",
        "article": "Artículo 1",
        "norm_date": date(2090, 3, 23),
        "last_updated": date(2095, 12, 23),
        "text": text,
        "url": "https://www.boe.es/buscar/act.php?id=BOE-A-9999-1#a1",
        "retrieved_at": date(2099, 1, 1),
        "license": BOE_REUSE_LICENSE,
        "catalog_version": 1,
        "text_sha256": text_fingerprint(text),
        "source_kinds": ("via_pecuaria_oficial",),
    }
    fields.update(overrides)
    return NormativeCitation(**fields)


def _load(tmp_path: Path, doc: Doc | str) -> CuratedNormativeCatalogFile:
    root = tmp_path / "normativa"
    root.mkdir(exist_ok=True)
    text = doc if isinstance(doc, str) else generar.render(doc)
    (root / "catalogo.json").write_text(text, encoding="utf-8")
    return CuratedNormativeCatalogFile(root)


def _mutated(mutate: Callable[[list[Doc]], None], version: int = 1) -> Doc:
    """Documento con las citas mutadas y la huella del catálogo recalculada."""
    cites = generar.citations(version)
    mutate(cites)
    return generar.document(cites, version)


def _reject(tmp_path: Path, doc: Doc | str) -> str:
    with pytest.raises(NormativeCatalogFileError) as info:
        _load(tmp_path, doc).catalog()
    return str(info.value)


def test_ca1_cita_completa_es_entidad_congelada_con_huella_del_texto() -> None:
    """Dado una cita con todos los campos obligatorios (norma, identificador BOE, artículo,
    fecha de la norma, fecha de última actualización, texto literal, URL oficial, fecha de
    consulta, licencia, versión del catálogo, huella) cuando se construye `NormativeCitation`
    entonces es una entidad congelada válida y la huella sha256 coincide con la del texto
    literal."""
    citation = _citation()
    assert citation.text_sha256 == generar.sha256_text(citation.text)
    with pytest.raises(AttributeError):
        citation.text = "otro"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"text": ""}, "texto"),
        ({"norm_title": ""}, "norma"),
        ({"article": "   "}, "articulo"),
        ({"url": "https://www.bocm.es/boletin/CM_Orden_BOCM/2090/03/23/BOCM-1.PDF"}, "url"),
        ({"url": "http://www.boe.es/buscar/act.php?id=BOE-A-9999-1"}, "url"),
        ({"url": "https://www.boe.es/buscar/doc.php?id=BOE-A-9999-1"}, "url"),
        ({"url": "https://www.boe.es/buscar/act.php?id=BOE-A-9999-2"}, "url"),
        ({"url": "https://www.boe.es/buscar/act.php?id=BOE-A-9999-1#a1&x=1"}, "url"),
        ({"retrieved_at": date(2090, 3, 22)}, "consultado"),
        ({"retrieved_at": date(2095, 12, 22)}, "consultado"),
        ({"text_sha256": "0" * 64}, "texto_sha256"),
        ({"license": "CC BY 4.0"}, "licencia"),
        ({"boe_id": "BOCM-20900323-1"}, "identificador"),
    ],
)
def test_ca2_cita_mal_formada_se_rechaza_nombrando_cita_y_campo(
    overrides: dict[str, Any], field: str, tmp_path: Path
) -> None:
    """Dado una cita a la que le falta un campo obligatorio, con texto vacío, con una URL que
    no sea `https://www.boe.es/buscar/act.php?id=<su identificador>` (con ancla opcional;
    también se rechaza `bocm.es`), con la fecha de consulta anterior a la fecha de la norma o a
    la última actualización, o con una huella que no coincide con el texto, cuando se valida
    entonces se rechaza con un error que nombra la cita y el campo."""
    if "text" in overrides and "text_sha256" not in overrides:
        overrides["text_sha256"] = generar.sha256_text(overrides["text"])
    with pytest.raises(InvalidNormativeCitationError) as info:
        _citation(**overrides)
    assert str(info.value).startswith(f"sintetica-art-01: {field}: ")


@pytest.mark.parametrize("missing", sorted(generar.citation("sintetica-art-01")))
def test_ca2_falta_un_campo_obligatorio(missing: str, tmp_path: Path) -> None:
    """Dado una cita a la que le falta un campo obligatorio […] cuando se valida entonces se
    rechaza con un error que nombra la cita y el campo."""

    def drop(cites: list[Doc]) -> None:
        del cites[1][missing]

    message = _reject(tmp_path, _mutated(drop))
    if missing == "id":
        assert "cita 2: faltan id" in message
    else:
        assert f"sintetica-art-01: faltan {missing}" in message


def test_ca3_carga_por_tipo_de_fuente_ordenada_y_sin_lugar() -> None:
    """Dado un catálogo en `curated/normativa/` con citas asociadas a valores de `SourceKind`
    cuando se carga entonces devuelve las citas por tipo de fuente, ordenadas de forma
    determinista (por identificador de cita), sin asociación a ninguna finca, tramo ni
    municipio."""
    catalog = CuratedNormativeCatalogFile(generar.VALID_DIR).catalog()
    ids = [c.citation_id for c in catalog.citations]
    assert ids == ["sintetica-art-01", "sintetica-art-02", "sintetica-art-10"]
    by_source = catalog.by_source()
    assert list(by_source) == sorted(by_source)
    assert len(by_source) == 5
    vp: SourceKind = "via_pecuaria_oficial"
    vt: SourceKind = "catastro_vt"
    assert [c.citation_id for c in by_source[vp]] == ["sintetica-art-01", "sintetica-art-02"]
    assert [c.citation_id for c in by_source[vt]] == ["sintetica-art-02", "sintetica-art-10"]
    assert by_source["ign_red_transporte"] == ()
    fields = set(NormativeCitation.__dataclass_fields__)
    for forbidden in ("finca", "tramo", "municipio", "municipality", "parcel", "trail"):
        assert not any(forbidden in name for name in fields), forbidden


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda c: c[0].update(tipos_fuente=["vereda"]), id="no-sourcekind"),
        pytest.param(lambda c: c[0].update(finca="x"), id="finca"),
        pytest.param(lambda c: c[0].update(tramo="x"), id="tramo"),
        pytest.param(lambda c: c[0].update(municipio="28043"), id="municipio"),
        pytest.param(lambda c: c[0].update(referencia_catastral="x"), id="referencia_catastral"),
        pytest.param(lambda c: c[0].update(nombre="x"), id="nombre"),
        pytest.param(
            lambda c: c[0].update(nota=f"Véase {FAKE_REFERENCE}"), id="referencia-en-nota"
        ),
        pytest.param(
            lambda c: c[0].update(
                texto=f"Texto {FAKE_REFERENCE}",
                texto_sha256=generar.sha256_text(f"Texto {FAKE_REFERENCE}"),
            ),
            id="referencia-en-texto",
        ),
    ],
)
def test_ca4_tipo_desconocido_campo_de_lugar_o_referencia_rechaza_el_catalogo(
    mutate: Callable[[list[Doc]], None], tmp_path: Path
) -> None:
    """Dado una cita asociada a un valor que no es un `SourceKind`, o con un campo de finca,
    tramo, municipio, referencia catastral o nombre de persona (claves `finca`, `tramo`,
    `municipio`, `referencia_catastral`, `nombre`), o con una referencia catastral en
    cualquier texto, cuando se carga entonces el catálogo se rechaza."""
    message = _reject(tmp_path, _mutated(mutate))
    assert FAKE_REFERENCE not in message


@pytest.mark.parametrize(
    ("key", "field"), [("norma", "norma"), ("articulo", "articulo"), ("nota", "nota")]
)
def test_ca5_palabra_vetada_fuera_del_literal_se_rechaza(
    key: str, field: str, tmp_path: Path
) -> None:
    """Dado un campo que no es el texto literal (norma, artículo, licencia, nota) que contiene
    una palabra de `BANNED_WORDS` cuando se valida entonces se rechaza; dado el texto literal
    con esa palabra, se acepta."""

    def mutate(cites: list[Doc]) -> None:
        cites[1][key] = "Artículo del titular"

    message = _reject(tmp_path, _mutated(mutate))
    assert f"sintetica-art-01: {field}: contiene palabras vetadas" in message
    with pytest.raises(InvalidNormativeCitationError, match="licencia"):
        _citation(license=BOE_REUSE_LICENSE + " del titular")
    # El literal con «titular» (fixture sintética) se acepta.
    catalog = CuratedNormativeCatalogFile(generar.VALID_DIR).catalog()
    assert "titular" in catalog.citations[0].text


def _duplicated(cites: list[Doc]) -> None:
    cites.append(copy.deepcopy(cites[0]))


def _other_version(cites: list[Doc]) -> None:
    cites[0]["version_catalogo"] = 2


@pytest.mark.parametrize(
    ("doc", "expected"),
    [
        pytest.param(lambda: _mutated(_duplicated), "sintetica-art-10: id: repetido", id="dup"),
        pytest.param(
            lambda: _mutated(_other_version),
            "sintetica-art-10: version_catalogo: no coincide",
            id="version-entre-citas",
        ),
        pytest.param(
            lambda: generar.document(generar.citations(2), 2) | {"version": 1},
            "version_catalogo: no coincide con la version del documento",
            id="version-del-documento",
        ),
        pytest.param(lambda: '{"version": 1, "citas": [', "no es JSON válido", id="json"),
    ],
)
def test_ca6_ids_repetidos_versiones_distintas_o_json_mal_formado_fallan_todo_o_nada(
    doc: Callable[[], Doc | str], expected: str, tmp_path: Path
) -> None:
    """Dado un catálogo con dos citas con el mismo identificador de cita, una versión de
    catálogo distinta entre citas (o distinta de la del documento) o un fichero con JSON mal
    formado cuando se carga entonces falla con un error claro y no carga nada (todo o nada)."""
    source = _load(tmp_path, doc())
    result: list[object] = []
    with pytest.raises(NormativeCatalogFileError) as info:
        result.append(source.catalog())
    assert expected in str(info.value)
    assert result == []


def test_ca7_catalogo_vacio_valido_no_es_fallo() -> None:
    """Dado un catálogo válido vacío (sin contenido legal todavía) cuando se carga entonces
    devuelve un catálogo vacío y no es un fallo."""
    catalog = CuratedNormativeCatalogFile(generar.EMPTY_DIR).catalog()
    assert catalog.citations == ()
    assert all(value == () for value in catalog.by_source().values())


def test_ca8_el_catalogo_real_del_repositorio_carga() -> None:
    """Dado el catálogo real del repositorio cuando corre el test entonces carga sin errores
    (guarda contra editar mal `curated/normativa/`)."""
    catalog = CuratedNormativeCatalogFile(REPO / "curated" / "normativa").catalog()
    assert catalog.version >= 1


def test_ca9_atribucion_de_una_cita_cargada() -> None:
    """Dado una cita cargada cuando se consulta su atribución entonces incluye el texto de
    cita del BOE, el enlace oficial, la fecha de consulta, la fecha de última actualización y
    el aviso de que el texto es informativo y no oficial."""
    citation = CuratedNormativeCatalogFile(generar.VALID_DIR).catalog().citations[0]
    attribution = citation_attribution(citation)
    assert attribution.source_notice == BOE_SOURCE_NOTICE
    assert BOE_SOURCE_NOTICE == "Fuente de los datos: Agencia Estatal Boletín Oficial del Estado"
    assert attribution.url == "https://www.boe.es/buscar/act.php?id=BOE-A-9999-1#a1"
    assert attribution.retrieved_at == date(2099, 1, 1)
    assert attribution.last_updated == date(2095, 12, 23)
    assert attribution.informative_notice == BOE_INFORMATIVE_NOTICE
    assert "meramente informativo" in BOE_INFORMATIVE_NOTICE
    assert "oficiales y auténticos" in BOE_INFORMATIVE_NOTICE


def test_ca10_texto_no_nfc_con_espacios_o_cambiado_se_rechaza(tmp_path: Path) -> None:
    """Dado un texto literal que no está en forma Unicode NFC o que empieza o acaba en espacio
    en blanco cuando se valida entonces se rechaza; dado un texto que difiere del original en
    un solo carácter interior con la huella del original, se rechaza, y el mensaje da la huella
    calculada (64 hex) para que quien edita la copie tras comprobar el texto. La huella se
    calcula sin normalizar nada."""
    nfd = "Texto sintético"
    for text, reason in ((nfd, "NFC"), (" Texto", "espacio"), ("Texto\n", "espacio")):
        with pytest.raises(InvalidNormativeCitationError, match=reason):
            _citation(text=text, text_sha256=generar.sha256_text(text))
    original = generar.citation("sintetica-art-01")
    changed = original["texto"].replace("vía", "via", 1)
    assert changed != original["texto"] and len(changed) == len(original["texto"])

    def mutate(cites: list[Doc]) -> None:
        cites[1]["texto"] = changed

    message = _reject(tmp_path, _mutated(mutate))
    assert "sintetica-art-01: texto_sha256: no coincide con el texto" in message
    assert re.search(rf"huella calculada: {generar.sha256_text(changed)}\b", message)
    assert original["texto_sha256"] not in message
    # Sin normalizar: dos formas Unicode del mismo texto dan huellas distintas.
    assert text_fingerprint(nfd) != text_fingerprint("Texto sintético")


def test_ca11_huella_del_catalogo(tmp_path: Path) -> None:
    """Dado un catálogo cuya `huella_catalogo` no coincide con la calculada cuando se carga
    entonces se rechaza y el mensaje da la huella calculada; dado un catálogo válido,
    `huella_catalogo` cambia si cambia cualquier campo de cualquier cita o la versión, y no
    cambia si solo se reordenan las citas en el fichero."""
    good = generar.document()
    bad = good | {"huella_catalogo": "0" * 64}
    message = _reject(tmp_path, bad)
    assert f"huella calculada: {good['huella_catalogo']}" in message
    assert "0" * 64 not in message

    base = CuratedNormativeCatalogFile(generar.VALID_DIR).catalog().fingerprint
    assert base == good["huella_catalogo"]
    reordered = generar.citations()[::-1]
    loaded = _load(tmp_path, generar.document(reordered)).catalog()
    assert loaded.fingerprint == base

    seen = {base}
    changes: dict[str, Any] = {
        "norma": "Ley sintética otra",
        "articulo": "Artículo 9",
        "fecha_norma": "2090-03-24",
        "ultima_actualizacion": "2096-01-01",
        "url": "https://www.boe.es/buscar/act.php?id=BOE-A-9999-1",
        "consultado": "2099-01-02",
        "tipos_fuente": ["mtn50_historico"],
        "nota": "Otra nota sintética.",
    }
    for key, value in changes.items():
        cites = generar.citations()
        cites[2][key] = value
        fingerprint = _load(tmp_path, generar.document(cites)).catalog().fingerprint
        assert fingerprint not in seen, key
        seen.add(fingerprint)
    cites = generar.citations()
    cites[0]["texto"] = "Texto sintético cambiado."
    cites[0]["texto_sha256"] = generar.sha256_text(cites[0]["texto"])
    seen_text = _load(tmp_path, generar.document(cites)).catalog().fingerprint
    assert seen_text not in seen
    seen.add(seen_text)
    v2 = _load(tmp_path, generar.document(generar.citations(2), 2)).catalog().fingerprint
    assert v2 not in seen


def _set(index: int, key: str, value: Any) -> Callable[[list[Doc]], None]:
    def mutate(cites: list[Doc]) -> None:
        cites[index][key] = value

    return mutate


_SENTINEL_CASES: list[Any] = [
    pytest.param(_set(1, "id", SENTINEL.upper()), id="ca2-id"),
    pytest.param(_set(1, "url", f"https://www.boe.es/{SENTINEL}"), id="ca2-url"),
    pytest.param(_set(1, "url", f"https://www.bocm.es/{SENTINEL}"), id="ca2-bocm"),
    pytest.param(_set(1, "identificador", SENTINEL), id="ca2-identificador"),
    pytest.param(_set(1, "fecha_norma", SENTINEL), id="ca2-fecha"),
    pytest.param(_set(1, "licencia", SENTINEL), id="ca2-licencia"),
    pytest.param(_set(1, "texto_sha256", SENTINEL), id="ca2-huella"),
    pytest.param(_set(1, "version_catalogo", SENTINEL), id="ca2-version"),
    pytest.param(_set(1, "tipos_fuente", [SENTINEL]), id="ca4-tipo"),
    pytest.param(_set(1, SENTINEL, "x"), id="ca4-clave"),
    pytest.param(_set(1, "municipio", SENTINEL), id="ca4-municipio"),
    pytest.param(_set(1, "nota", f"{SENTINEL} {FAKE_REFERENCE}"), id="ca4-referencia"),
    pytest.param(_set(1, "norma", f"{SENTINEL} titular"), id="ca5-norma"),
    pytest.param(_set(1, "articulo", f"{SENTINEL} propietario"), id="ca5-articulo"),
    pytest.param(_set(1, "nota", f"{SENTINEL} dueño"), id="ca5-nota"),
    pytest.param(_set(1, "texto", f" {SENTINEL}"), id="ca10-espacio"),
    pytest.param(_set(1, "texto", f"{SENTINEL} sintético"), id="ca10-nfc"),
    pytest.param(_set(1, "texto", f"{SENTINEL} cambiado"), id="ca10-huella"),
]


@pytest.mark.parametrize("mutate", _SENTINEL_CASES)
def test_ca12_ningun_mensaje_repite_el_valor_rechazado(
    mutate: Callable[[list[Doc]], None], tmp_path: Path
) -> None:
    """Dado cualquier rechazo de CA2, CA4, CA5, CA6, CA10 y CA11 provocado con un valor
    centinela (`valor-secreto-rechazado`, o una referencia catastral sintética) cuando se lee
    el mensaje de error entonces no contiene el valor rechazado (lección de #168); nombra solo
    el fichero, el identificador de cita ya validado o la posición («cita 3») y el campo."""
    message = _reject(tmp_path, _mutated(mutate))
    assert SENTINEL not in message
    assert SENTINEL.upper() not in message
    assert FAKE_REFERENCE not in message
    # Nombra el id ya validado, la posición o (antes de leer el JSON) el fichero entero.
    file_level = "contiene una referencia catastral o un localizador de parcela" in message
    assert "sintetica-art-01" in message or "cita 2: " in message or file_level


@pytest.mark.parametrize(
    "doc",
    [
        pytest.param(lambda: f'{{"version": 1, "citas": ["{SENTINEL}"', id="ca6-json"),
        pytest.param(
            lambda: generar.document() | {"huella_catalogo": SENTINEL}, id="ca11-huella"
        ),
        pytest.param(lambda: generar.document() | {SENTINEL: 1}, id="ca4-clave-documento"),
        pytest.param(
            lambda: _mutated(_set(1, "id", "sintetica-art-10")), id="ca6-repetido"
        ),
    ],
)
def test_ca12_documento_sin_valor_rechazado(doc: Callable[[], Doc | str], tmp_path: Path) -> None:
    """Dado cualquier rechazo de CA2, CA4, CA5, CA6, CA10 y CA11 provocado con un valor
    centinela […] cuando se lee el mensaje de error entonces no contiene el valor rechazado."""
    message = _reject(tmp_path, doc())
    assert SENTINEL not in message


def test_ca13_fichero_ausente_no_es_vacio(tmp_path: Path) -> None:
    """Dado que no existe `curated/normativa/catalogo.json` cuando se carga entonces falla con
    `NormativeCatalogFileError` (ausente no es vacío: el vacío es un fichero válido sin
    citas)."""
    with pytest.raises(NormativeCatalogFileError, match="no existe"):
        CuratedNormativeCatalogFile(tmp_path / "normativa").catalog()


def _registry_boe_section() -> str:
    text = REGISTRY.read_text(encoding="utf-8")
    start = text.index("\n## BOE\n")
    end = text.index("\n## ", start + 5)
    return text[start:end]


def test_ca14_registry_y_notice_recogen_la_licencia_del_boe() -> None:
    """Dado el repositorio cuando se leen `REGISTRY.md` y `NOTICE` entonces el BOE consta con
    la URL del aviso legal, la fecha de lectura (2026-11-27), las citas literales de sus
    condiciones y la conclusión **Publicar** (texto literal de artículos con atribución); y el
    test de coherencia de #43 (CA6) mapea la fila nueva, sin relajar ninguna aserción."""
    aviso = "https://www.boe.es/informacion/aviso_legal/index.php"
    literals = (
        "para fines comerciales y no comerciales",
        "Fuente de los datos: Agencia Estatal Boletín Oficial del Estado",
        "Basado en datos de la Agencia Estatal Boletín Oficial del Estado",
        "Está prohibido desnaturalizar el sentido de la información",
        "texto consolidado de carácter meramente informativo",
        "Debe mencionarse la fecha de la última actualización",
    )
    section = _registry_boe_section()
    assert aviso in section
    assert "2026-11-27" in section
    assert "no verificada explícitamente" not in section
    for literal in literals:
        assert literal in section, literal
    assert "https://www.bocm.es/aviso-legal" in section

    rows = [
        line
        for line in REGISTRY.read_text(encoding="utf-8").splitlines()
        if line.startswith("| BOE — texto consolidado de la legislación citada")
    ]
    assert len(rows) == 1
    assert "**Publicar**" in rows[0]

    notice = NOTICE.read_text(encoding="utf-8")
    publishable = notice[
        notice.index("## Fuentes que pueden publicarse") : notice.index(
            "## Información derivada de fuentes que no se publican"
        )
    ]
    boe = publishable[
        publishable.index("### Agencia Estatal Boletín Oficial del Estado — texto de la") :
    ]
    assert aviso in boe
    assert "Fuente de los datos: Agencia Estatal Boletín Oficial del Estado" in boe
    assert "última actualización" in boe
    assert "meramente informativo" in boe

    assert h43.FUENTES_PUBLICABLES["BOE"] == "Boletín Oficial del Estado"
    h43.test_ca6_coherencia_registry_publicar_frente_a_notice()


def test_fixtures_versionadas_coinciden_con_el_generador() -> None:
    """Guarda: las fixtures sintéticas son exactamente lo que da `generar.py` (las huellas se
    calculan, no se copian a mano)."""
    for path, text in generar.expected_files().items():
        assert path.read_text(encoding="utf-8") == text, path
    assert json.loads((generar.VALID_DIR / "catalogo.json").read_text())["citas"]
