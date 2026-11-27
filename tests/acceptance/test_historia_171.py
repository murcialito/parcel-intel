"""Historia #171: el visor muestra los tramos a verificar (ficha, resumen, «revisado a mano»).

Un test por criterio. La lógica se prueba en Node (`tests/site/visor.test.mjs`, casos
`H171 CA<n>:`) con `L` falso y documento falso, sobre la fixture sintética
`tests/fixtures/site/candidatos_28043.geojson` (generada con el sink de #170); aquí van las
comprobaciones estáticas y el lanzamiento de esos casos. Ninguna prueba toca la red.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from parcel_intel.domain.public_candidate_card import CANDIDATE_LAYER_NAME
from parcel_intel.domain.public_card import BANNED_WORDS, WARNING
from parcel_intel.domain.published_discrepancy import CADASTRAL_REFERENCE_RE
from tests.site.nodo import CANDIDATOS, SITE, assert_node_tests_pass

pytestmark = pytest.mark.acceptance


def _html() -> str:
    return (SITE / "index.html").read_text(encoding="utf-8")


def test_ca1_capa_en_el_panel_apagada_y_con_atribucion_condicionada(tmp_path: Path) -> None:
    """CA1. Dado un índice con la capa `candidatos` en un municipio, cuando se abre el visor,
    entonces la capa aparece en el panel con el título «Tramos a verificar (no son un
    dictamen)», **apagada**, y su atribución solo se muestra en el mapa cuando se activa y está
    cargada."""
    html = _html()
    casilla = re.search(r'<input[^>]*id="capa-candidatos"[^>]*>', html)
    assert casilla is not None and "checked" not in casilla.group(0)
    assert re.search(
        r'<label for="capa-candidatos"[^>]*>.*?'
        r"Tramos a verificar \(no son un dictamen\)</span>",
        html,
        re.DOTALL,
    )
    assert 'id="estado-candidatos"' in html and 'id="resumen-candidatos"' in html
    assert_node_tests_pass("^H171 CA1:", tmp_path)


def test_ca2_ficha_con_lista_blanca_y_fuentes(tmp_path: Path) -> None:
    """CA2. Dado el fichero publicado de fixtures, cuando se activa la capa y se pulsa un tramo,
    entonces la ficha muestra etiqueta, texto, aviso (el del feature; si falta, el fijo de
    `config.js`), confianza en palabras, y cada fuente con papel, fuente, año o «año no
    declarado», fecha de descarga, licencia, atribución y enlace solo si es `https://`. La ficha
    no muestra el id público, la geometría ni ninguna propiedad fuera de la lista blanca."""
    assert_node_tests_pass("^H171 CA2:", tmp_path)


def test_ca3_resumen_de_la_medicion_tal_cual(tmp_path: Path) -> None:
    """CA3. Dado el mismo fichero, cuando se carga la capa, entonces el panel muestra bajo ella,
    con `textContent`, las cuatro frases de `medicion.texto` tal cual, en su orden, y el texto
    de `revisado_a_mano` tal cual. El visor no calcula ni reformula cifras (test: una fixture
    con frases distintas se ve igual)."""
    assert_node_tests_pass("^H171 CA3:", tmp_path)


def test_ca4_fichero_roto_o_sin_medicion_da_error_sin_tramos(tmp_path: Path) -> None:
    """CA4. Dada una capa `candidatos` cuyo fichero falta, no es JSON, no es un
    `FeatureCollection`, o no trae `medicion.texto` (cuatro cadenas no vacías) y
    `revisado_a_mano` (cadena no vacía), cuando se carga, entonces la capa pasa a estado error
    con el mensaje del patrón de #95, el resumen no se muestra, y las demás capas se cargan y
    funcionan igual. Sin medición no se enseña ningún tramo."""
    assert_node_tests_pass("^H171 CA4:", tmp_path)


def test_ca5_sin_la_capa_en_el_indice_dice_sin_tramos_publicados(tmp_path: Path) -> None:
    """CA5. Dado un municipio cuyo índice no lista `candidatos`, cuando se elige, entonces la
    capa muestra «sin tramos a verificar publicados» (no error) y no se pide ningún fichero."""
    assert "sin tramos a verificar publicados" in (SITE / "config.js").read_text(encoding="utf-8")
    assert_node_tests_pass("^H171 CA5:|^H171: al cambiar", tmp_path, minimum=2)


def test_ca6_fichero_sin_tramos_muestra_el_estado_vacio(tmp_path: Path) -> None:
    """CA6. Dado un fichero con cero features, cuando se carga, entonces la capa muestra el
    mismo estado vacío y el resumen sigue sin mostrarse."""
    assert_node_tests_pass("^H171 CA6:", tmp_path)


def test_ca7_estilo_propio_distinguible_con_tema_oscuro_halo_y_orden(tmp_path: Path) -> None:
    """CA7. Estilo propio: la clave de estilo de la capa en `estilos-capas.js` es distinguible
    de `viasPecuarias`, `caminoActual` y `indicio*` (color o patrón distinto; un test lo
    comprueba como los de #165), con variante de tema oscuro y halo, y su muestra en el panel
    usa el mismo patrón. El orden de dibujo la deja por encima de los indicios."""
    css = (SITE / "estilo.css").read_text(encoding="utf-8")
    assert re.search(r"\.pc-muestra--candidato \.l\s*\{[^}]*var\(--capa-candidato\)", css)
    assert re.search(r"\.pc-muestra--candidato \.h\s*\{[^}]*var\(--capa-candidato-halo\)", css)
    estilos = (SITE / "estilos-capas.js").read_text(encoding="utf-8")
    claro = re.search(r'candidato: \{ color: "(#\w+)".*?dashArray: "([^"]+)"', estilos)
    assert claro is not None
    color, patron = claro.groups()
    # Los colores viven en tokens.css (copia fiel de docs/design-system, que también se actualiza).
    tokens = (SITE / "css" / "tokens.css").read_text(encoding="utf-8")
    fuente = SITE.parent / "docs" / "design-system" / "site" / "css" / "tokens.css"
    assert tokens == fuente.read_text(encoding="utf-8")
    assert re.search(rf"--capa-candidato:\s*{color};", tokens)
    halo = re.search(r'candidato: \{.*?halo: \{ color: "(#\w+)"', estilos)
    assert halo is not None and f"--capa-candidato-halo: {halo.group(1)};" in tokens
    oscuro = re.search(r'oscuro\.candidato\.color = "(#\w+)"', estilos)
    assert oscuro is not None
    assert tokens.count(f"--capa-candidato: {oscuro.group(1)};") == 2  # preferencia y forzado
    muestra = re.search(r"\.pc-muestra--candidato \.h, [^{]*\{\s*stroke-dasharray:\s*([^;]+);", css)
    assert muestra is not None and muestra.group(1) == patron
    assert_node_tests_pass("^H171 CA7:", tmp_path, minimum=2)


def test_ca8_textos_visibles_sin_palabras_vetadas_ni_referencias_catastrales(
    tmp_path: Path,
) -> None:
    """CA8. Dado cualquier texto visible nuevo de `config.js` o `index.html` y el fichero
    publicado de fixtures (colección y features), cuando se comprueba, entonces ninguno
    contiene una palabra de `BANNED_WORDS` ni coincide con `CADASTRAL_REFERENCE_RE`; el título
    y el aviso de la capa se comparan con los de `domain/public_candidate_card.py` y
    `public_card.WARNING`."""
    config = (SITE / "config.js").read_text(encoding="utf-8")
    titulo = re.search(r'id: "candidatos",\s*titulo: "([^"]+)"', config)
    assert titulo is not None and titulo.group(1) == CANDIDATE_LAYER_NAME
    assert CANDIDATE_LAYER_NAME in _html()
    publicado = json.loads(CANDIDATOS.read_text(encoding="utf-8"))
    assert publicado["properties"]["nombre_capa"] == CANDIDATE_LAYER_NAME
    assert publicado["properties"]["aviso"] == WARNING
    assert WARNING in config  # el aviso fijo de `config.js` (avisoIndicio) es el de la ficha
    for feature in publicado["features"]:
        assert feature["properties"]["aviso"].startswith(WARNING)
    de_capa = config.split('"candidatos"')[1]
    nuevos = [
        titulo.group(1),
        *re.findall(r'(?:fuente|atribucion|sinCandidatos):\s*"([^"]+)"', de_capa),
        _html().split('id="capa-candidatos"')[0].rsplit('<li class="pc-capa">', 1)[1],
    ]
    textos = [*nuevos, json.dumps(publicado, ensure_ascii=False)]
    for texto in textos:
        minuscula = texto.lower()
        assert not [p for p in BANNED_WORDS if p in minuscula], texto
        assert CADASTRAL_REFERENCE_RE.search(texto) is None, texto
    assert_node_tests_pass("^H171 CA8:", tmp_path)


def test_ca9_extension_de_95_sin_innerhtml_ni_ficha_duplicada(tmp_path: Path) -> None:
    """CA9. Los cambios son una extensión de #95: sus tests siguen en verde sin modificarse
    (salvo los que cuentan las capas de `CONFIG.capas`, que se actualizan) y no hay `innerHTML`
    ni código duplicado de la ficha (se reutiliza `fichaIndicio`/`nodoFichaIndicio`)."""
    for modulo in sorted(SITE.glob("*.js")):
        texto = modulo.read_text(encoding="utf-8")
        assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML", texto), modulo.name
    controlador = (SITE / "controlador.js").read_text(encoding="utf-8")
    vista = (SITE / "vista.js").read_text(encoding="utf-8")
    assert controlador.count("export function fichaIndicio") == 1
    assert vista.count("function nodoFichaIndicio") == 1
    assert "fichaCandidato" not in controlador + vista
    assert_node_tests_pass("^H95 CA", tmp_path, minimum=10)
