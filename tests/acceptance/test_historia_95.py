"""Historia #95: el visor dibuja los indicios de discrepancia y muestra su ficha de evidencia.

Un test por criterio. La lógica se prueba en Node (`tests/site/visor.test.mjs`, casos
`H95 CA<n>:`) con `L` falso y documento falso; aquí van las comprobaciones estáticas y el
lanzamiento de esos casos. Ninguna prueba toca la red.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.site.nodo import SITE, assert_node_tests_pass

pytestmark = pytest.mark.acceptance

NOTICE = SITE.parent / "NOTICE"
VENDOR = SITE / "vendor"
PROPIOS = sorted(SITE.glob("*.js"))


def _html() -> str:
    return (SITE / "index.html").read_text(encoding="utf-8")


def test_ca1_capa_dibujada_con_estilo_distinto_y_casilla_rotulada(tmp_path: Path) -> None:
    """CA1. Dado el `indice.json` de un municipio con la capa `discrepancias` cuando se elige ese
    municipio entonces el visor carga `datos/<ruta del índice>`, la dibuja sobre el mapa con un
    estilo distinto del de las otras capas y su casilla aparece en «Capas» con el rótulo
    «Indicios a verificar (no son un dictamen)»."""
    html = _html()
    assert 'id="capa-discrepancias"' in html
    assert re.search(
        r'<label for="capa-discrepancias">.*?Indicios a verificar \(no son un dictamen\)</label>',
        html,
    )
    assert_node_tests_pass("^H95 CA1:", tmp_path)


def test_ca2_la_capa_nace_apagada_y_su_atribucion_va_con_la_casilla(tmp_path: Path) -> None:
    """CA2. Dado un municipio recién elegido cuando termina la carga entonces la capa de indicios
    está apagada (casilla sin marcar, nada dibujado) y no aporta su atribución; al marcar la
    casilla se dibuja y aparece su atribución, y al desmarcarla desaparecen ambas. Las otras dos
    capas conservan su comportamiento actual (encendidas por defecto)."""
    casilla = re.search(r'<input[^>]*id="capa-discrepancias"[^>]*>', _html())
    assert casilla is not None
    assert "checked" not in casilla.group(0)
    for capa in ("vias_pecuarias", "camino_actual"):
        assert re.search(rf'<input[^>]*id="capa-{capa}"[^>]*checked', _html())
    assert_node_tests_pass("^H95 CA2:|^unidad: visibleInicial", tmp_path, minimum=2)


def test_ca3_sin_capa_en_el_indice_dice_sin_indicios_publicados(tmp_path: Path) -> None:
    """CA3. Dado un municipio cuyo `indice.json` no lista la capa `discrepancias` (o cuyo fichero
    no existe en el índice) cuando se elige entonces el estado de la capa dice «sin indicios
    publicados», sin mensaje de error y sin afectar a las demás capas."""
    assert "sin indicios publicados" in (SITE / "config.js").read_text(encoding="utf-8")
    assert_node_tests_pass("^H95 CA3:", tmp_path)


def test_ca4_fichero_roto_da_error_de_esa_capa_sin_afectar_a_las_otras(tmp_path: Path) -> None:
    """CA4. Dado un fichero de discrepancias que falla al cargar o que no es un FeatureCollection
    cuando se elige el municipio entonces aparece el error de esa capa («no se pudo cargar») sin
    impedir que se dibujen las otras dos."""
    assert_node_tests_pass("^H95 CA4:", tmp_path)


def test_ca5_ficha_en_orden(tmp_path: Path) -> None:
    """CA5. Dado un indicio dibujado cuando se pulsa entonces se abre una ficha con, por este
    orden: etiqueta, `texto` del indicio, confianza en palabras («confianza alta/media/baja»), el
    `aviso` de #16 y la lista de fuentes."""
    assert_node_tests_pass("^H95 CA5:", tmp_path)


def test_ca6_fuentes_con_todos_sus_campos_y_enlace_solo_https(tmp_path: Path) -> None:
    """CA6. Dado un indicio con evidencia cuando se muestra su ficha entonces cada fuente aparece
    con su papel (sujeto/contraparte), nombre, año (o «año no declarado»), fecha de descarga,
    licencia, atribución y URL como enlace; el enlace se crea con `href` asignado como propiedad
    solo si empieza por `https://`, con `rel="noopener noreferrer"`, y en otro caso se muestra
    como texto."""
    vista = (SITE / "vista.js").read_text(encoding="utf-8")
    assert r"/^https:\/\/\S/" in vista
    assert_node_tests_pass("^H95 CA6:", tmp_path)


def test_ca7_criterio_descripcion_y_aviso_de_omision(tmp_path: Path) -> None:
    """CA7. Dado un indicio cuando se muestra su ficha entonces aparecen también el criterio con
    su versión (`criterio`), su `descripcion_criterio` y, si no es `null`, el `aviso_omision`."""
    assert_node_tests_pass("^H95 CA7:", tmp_path)


def test_ca8_el_aviso_siempre_esta_y_coincide_con_el_publicado(tmp_path: Path) -> None:
    """CA8. Dado cualquier ficha de indicio cuando se muestra entonces el aviso («Esto no es un
    dictamen…») está siempre en ella, aunque falte el resto de campos: si la feature no trae
    `aviso`, la ficha usa el aviso fijo de `config.js` (copia literal del de #16/NOTICE,
    comparado por test con el fichero publicado). Una feature sin la forma esperada (sin `texto`
    o `evidencia` que no sea lista) muestra solo el aviso y «ficha no disponible», sin lanzar."""
    config = (SITE / "config.js").read_text(encoding="utf-8")
    match = re.search(r'avisoIndicio:\s*"([^"]+)"', config)
    assert match is not None
    aviso = match.group(1)
    assert f"`{aviso}`" in NOTICE.read_text(encoding="utf-8")
    datos = SITE / "datos" / "discrepancias"
    for sidecar in datos.glob("*.geojson.procedencia.json"):
        assert json.loads(sidecar.read_text(encoding="utf-8"))["aviso"] == aviso, sidecar.name
    for fichero in datos.glob("*.geojson"):
        for feature in json.loads(fichero.read_text(encoding="utf-8"))["features"]:
            assert feature["properties"]["aviso"] == aviso, fichero.name
    assert_node_tests_pass("^H95 CA8:", tmp_path)


def test_ca9_el_marcado_html_se_ve_como_texto() -> None:
    """CA9. Dado un indicio cuyo texto, etiqueta, fuente o atribución contiene marcado HTML
    (`<img onerror=…>`) cuando se muestra la ficha entonces se ve como texto literal: todo se
    inserta con `textContent`, el módulo de la vista no usa `innerHTML`, `outerHTML` ni
    `insertAdjacentHTML` y un documento falso que los prohíbe pasa la prueba."""
    for modulo in PROPIOS:
        texto = modulo.read_text(encoding="utf-8")
        assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML", texto), modulo.name


def test_ca9_node(tmp_path: Path) -> None:
    """CA9 (parte dinámica): documento falso que lanza si se toca HTML."""
    assert_node_tests_pass("^H95 CA9:", tmp_path)


def test_ca10_fichas_reales_sin_refcat_ni_propiedades_fuera_de_la_lista_blanca(
    tmp_path: Path,
) -> None:
    """CA10. Dado `site/datos/discrepancias/28043.geojson` real cuando se pasa por la ficha de
    cada una de sus features entonces ninguna ficha contiene referencias catastrales ni nombres
    de personas (reutiliza `CADASTRAL_REFERENCE_RE` de #94 en un test pytest sobre el DOM falso)
    y ninguna ficha supera las propiedades de la lista blanca del ADR 0044 §2: cualquier otra
    propiedad del GeoJSON se ignora."""
    assert (SITE / "datos" / "discrepancias" / "28043.geojson").is_file()
    assert_node_tests_pass("^H95 CA10:", tmp_path)


def test_ca11_sitio_completo_leaflet_solo_en_mapa_js_y_nada_de_innerhtml() -> None:
    """CA11. Dado el sitio completo cuando se revisan los ficheros de `site/` entonces `L` solo
    aparece en `mapa.js`, no hay `innerHTML` fuera de comentarios, y `index.html` lista la nueva
    capa con su casilla y su estado (`estado-discrepancias`). `mapa.js` no cambia salvo que la
    interfaz lo necesite; si cambia, sigue sin importar nada."""
    patron = re.compile(r"\bL\s*[.\[]|window\.L\b|globalThis\.L\b")
    for fichero in sorted(SITE.rglob("*")):
        if (
            fichero.is_file()
            and fichero.suffix in {".html", ".js", ".mjs", ".css"}
            and VENDOR not in fichero.parents
            and fichero.name != "mapa.js"
        ):
            texto = fichero.read_text(encoding="utf-8")
            assert not patron.search(texto), fichero.name
            sin_comentarios = re.sub(r"^\s*//.*$", "", texto, flags=re.MULTILINE)
            assert "innerHTML" not in sin_comentarios, fichero.name
    html = _html()
    assert 'id="capa-discrepancias"' in html
    assert 'id="estado-discrepancias"' in html
    # Historia #165: mapa.js importa solo el módulo puro de estilos, nunca otro del visor.
    importados = re.findall(
        r"^\s*import\b.*?from\s+[\"']([^\"']+)[\"']",
        (SITE / "mapa.js").read_text("utf-8"),
        re.MULTILINE,
    )
    assert importados == ["./estilos-capas.js"]


def test_ca12_cambiar_de_municipio_quita_los_indicios_y_manda_la_ultima_peticion(
    tmp_path: Path,
) -> None:
    """CA12. Dado el municipio elegido cuando se cambia a otro entonces los indicios del anterior
    se quitan del mapa y no se mezclan; si el cambio es rápido, manda la última petición (como
    ya ocurre con las otras capas)."""
    assert_node_tests_pass("^H95 CA12:", tmp_path)


def test_ca13_atribuciones_del_sidecar_visibles_en_ficha_o_capa(tmp_path: Path) -> None:
    """CA13. Dado el `.procedencia.json` de `discrepancias/28043.geojson` cuando se comparan sus
    atribuciones con las que el visor muestra en la ficha y en el control de atribución de la
    capa activa entonces cada atribución del sidecar aparece literal en alguna ficha o en la
    atribución de la capa (ADR 0035 y 0044)."""
    assert_node_tests_pass("^H95 CA13:", tmp_path)
