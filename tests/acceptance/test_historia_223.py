"""Historia #223: kit de campo, enlaces de descarga en el visor.

Lo que depende del DOM y del controlador se prueba con los tests de módulo de
`tests/site/visor.test.mjs` (prefijo «H223 CAn»), con un documento falso que prohíbe `innerHTML`;
lo estático (HTML, CSS, config) se lee aquí. El índice del kit de los tests es sintético.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from parcel_intel.cli import main as cli
from tests.site.nodo import MODULOS, SITE, assert_node_tests_pass

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).resolve().parents[2]


def _css() -> str:
    return (SITE / "estilo.css").read_text(encoding="utf-8")


def _html() -> str:
    return (SITE / "index.html").read_text(encoding="utf-8")


def _kit_css() -> str:
    return "\n".join(line for line in _css().splitlines() if "pc-kit" in line)


def test_ca1_enlaces_de_descarga_por_fichero_del_indice(tmp_path: Path) -> None:
    """CA1. Dado `datos/kit/indice.json` con kit para 28043 cuando se selecciona Colmenar de
    Oreja entonces el panel muestra una sección «Kit de campo» con un enlace de descarga por
    cada fichero del índice (GPX, KML), con atributo `download`, ruta `datos/kit/<ruta>` y el
    tamaño legible en el texto del enlace, con los rótulos aprobados."""
    assert_node_tests_pass("H223 CA1", tmp_path)
    assert 'id="kit-campo"' in _html()
    assert ">Kit de campo<" in _html()
    config = (SITE / "config.js").read_text(encoding="utf-8")
    assert '"Descargar GPX ({tamano})"' in config
    assert '"Descargar KML ({tamano})"' in config


def test_ca2_municipio_sin_kit_no_muestra_seccion(tmp_path: Path) -> None:
    """CA2. Dado un municipio sin entrada en el índice del kit cuando se selecciona entonces no
    aparece la sección ni enlace alguno y no se muestra ningún error."""
    assert_node_tests_pass("H223 CA2", tmp_path)
    # La sección nace oculta en el HTML: sin kit no hay nada que ver.
    assert re.search(r'<div[^>]*id="kit-campo"[^>]*\bhidden\b', _html())


def test_ca3_sin_indice_del_kit_el_visor_funciona_igual(tmp_path: Path) -> None:
    """CA3. Dado que `datos/kit/indice.json` no existe (404) o no es válido cuando arranca el
    visor entonces el resto del visor funciona igual, no hay enlaces del kit y no se muestra
    error al usuario (solo `console`)."""
    assert_node_tests_pass("H223 CA3", tmp_path)


def test_ca4_rutas_no_seguras_y_claves_fuera_de_lista_se_descartan(tmp_path: Path) -> None:
    """CA4. Dado un índice del kit con rutas no seguras (absolutas, `..`, con `:` o `\\`), una
    clave fuera de la lista blanca o un `ine` repetido cuando se valida entonces esa
    entrada/clave se descarta y nunca se genera un enlace con ella."""
    assert_node_tests_pass("H223 CA4", tmp_path)


def test_ca5_enlace_qfield_solo_si_el_indice_trae_la_clave(tmp_path: Path) -> None:
    """CA5. Dado un índice con la clave `qfield` para un municipio cuando se muestra la sección
    entonces aparece además el enlace «Descargar proyecto de campo (QField)»; sin esa clave no
    aparece."""
    assert_node_tests_pass("H223 CA5", tmp_path)


def test_ca6_aviso_de_uso_aviso_de_indicio_y_capas(tmp_path: Path) -> None:
    """CA6. Dada la sección del kit visible cuando se lee entonces lleva, junto a los enlaces,
    el aviso de uso aprobado (texto literal de arriba, en `config.js::textos`) y el aviso de
    «indicio a verificar» (`textos.avisoIndicio`), y los enlaces nombran las capas incluidas y
    las `capas_no_publicadas` solo como «sin publicar» (sin dar a entender que faltan por una
    causa concreta)."""
    assert_node_tests_pass("H223 CA6", tmp_path)
    config = (SITE / "config.js").read_text(encoding="utf-8")
    assert "kitAvisoTitulo:" in config and "kitAvisoCuerpo:" in config


def test_ca7_la_seccion_refleja_solo_el_municipio_actual(tmp_path: Path) -> None:
    """CA7. Dado cambiar de municipio, o a «España», cuando se actualiza el panel entonces la
    sección refleja solo el municipio actual y desaparece al salir."""
    assert_node_tests_pass("H223 CA7", tmp_path)


def test_ca8_sistema_de_diseno_teclado_y_sin_peticiones_externas(tmp_path: Path) -> None:
    """CA8. Dados los textos nuevos cuando se comparan con el sistema de diseño entonces usan
    las clases y tokens existentes (`pc-*`, sin colores literales en `estilo.css`), los enlaces
    son alcanzables por teclado con foco visible y el contraste pasa los tests de #166; no se
    añade ninguna biblioteca ni petición a dominios externos (test de #85 CA1)."""
    assert_node_tests_pass("H223 CA8", tmp_path)
    css = _kit_css()
    assert css, "faltan las reglas pc-kit"
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(", css), "color literal"
    assert "var(--" in css
    # Los enlaces son <a href> (alcanzables por teclado) con la clase de botón del sistema y el
    # foco visible global de `:focus-visible`; nada de tabindex negativo ni outline: none.
    vista = (SITE / "vista.js").read_text(encoding="utf-8")
    assert 'crear("a", "pc-boton"' in vista and 'setAttribute("href"' in vista
    assert ":focus-visible { outline: 3px solid var(--color-focus)" in _css()
    assert "outline: none" not in css and "outline:none" not in css
    # Sin bibliotecas nuevas ni dominios externos en el kit.
    for nombre in ("config.js", "controlador.js", "vista.js"):
        codigo = (SITE / nombre).read_text(encoding="utf-8")
        assert "kit" not in "".join(re.findall(r"https?://\S+", codigo))
    assert [p.name for p in (SITE / "vendor").iterdir()] == ["leaflet"]
    # Los tests de #166 y #85 (contraste, recursos externos) se ejecutan en CA9.


def test_ca9_los_tests_de_otras_historias_siguen_en_verde(tmp_path: Path) -> None:
    """CA9. Dados los tests de otras historias que fijan `index.html` o `config.js` cuando se
    ejecuta la suite entonces siguen en verde sin relajarlos."""
    # La suite de módulos completa (incluye #85, #95, #165, #166, #171, #178 y #185) y los
    # tests de aceptación de esas historias, que se ejecutan con `pytest -m acceptance`.
    assert_node_tests_pass(".*", tmp_path, minimum=100)
    resultado = subprocess.run(
        [
            "uv", "run", "pytest", "-q", "-m", "acceptance", "-p", "no:cacheprovider",
            "tests/acceptance/test_historia_85.py",
            "tests/acceptance/test_historia_95.py",
            "tests/acceptance/test_historia_166.py",
            "tests/acceptance/test_historia_171.py",
            "tests/acceptance/test_historia_185.py",
        ],
        capture_output=True, text=True, cwd=ROOT, check=False, timeout=600,
    )
    assert resultado.returncode == 0, resultado.stdout[-3000:]


@pytest.mark.integration
def test_ca10_los_enlaces_descargan_ficheros_gpx_y_kml_validos(tmp_path: Path) -> None:
    """CA10 [integración, local]. Dado `publicar-kit-campo --municipio 28043` y el visor servido
    en local cuando se abre Colmenar entonces los enlaces descargan ficheros GPX/KML válidos.
    Se comprueba en navegador real (`scripts/capturar_visor.mjs`); la captura con datos
    sintéticos no se sube a `docs/`. Aquí: el kit real de lo publicado en `site/datos/`, y los
    enlaces que el visor construye a partir de su índice."""
    salida = tmp_path / "datos"
    parser = cli._build_parser()
    namespace = parser.parse_args(
        ["publicar-kit-campo", "--municipio", "28043", "--entrada", str(SITE / "datos"),
         "--salida", str(salida)]
    )
    assert namespace.func(namespace) == 0
    indice = json.loads((salida / "kit" / "indice.json").read_text(encoding="utf-8"))

    node = shutil.which("node")
    assert node is not None
    copia = tmp_path / "visor"
    copia.mkdir()
    for nombre in MODULOS:
        shutil.copyfile(SITE / nombre, copia / nombre)
    (copia / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (copia / "enlaces.mjs").write_text(
        'import { readFileSync } from "node:fs";'
        'import { CONFIG } from "./config.js";'
        'import { validarIndiceKit, modeloKit } from "./controlador.js";'
        "const kit = validarIndiceKit(JSON.parse(readFileSync(process.argv[2], 'utf8')), CONFIG);"
        'const municipio = { nombre: "Colmenar de Oreja" };'
        'console.log(JSON.stringify(modeloKit(kit.get("28043"), municipio, CONFIG)));',
        encoding="utf-8",
    )
    proceso = subprocess.run(
        [node, str(copia / "enlaces.mjs"), str(salida / "kit" / "indice.json")],
        capture_output=True, text=True, cwd=copia, check=False, timeout=60,
    )
    assert proceso.returncode == 0, proceso.stderr
    modelo = json.loads(proceso.stdout)
    assert [e["clave"] for e in modelo["enlaces"]] == list(indice["municipios"][0]["ficheros"])
    for enlace in modelo["enlaces"]:
        fichero = salida / enlace["href"].removeprefix("datos/")
        assert fichero.is_file()
        raiz = ET.parse(fichero).getroot()  # XML bien formado
        assert raiz.tag.endswith("gpx" if enlace["clave"] == "gpx" else "kml")
        assert str(fichero.stat().st_size) in json.dumps(indice)
