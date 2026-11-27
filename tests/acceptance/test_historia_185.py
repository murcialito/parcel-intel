"""Historia #185: rediseño del visor (mapa de España, ficha en panel, aspecto).

Un test por criterio. Lo que depende del navegador (dibujo, panel, buscador) se prueba con los
tests de módulo de `tests/site/visor.test.mjs` (prefijo «H185»), con un Leaflet y un DOM
falsos; lo estático (HTML, CSS, config, datos publicados) se lee aquí. La verificación en un
navegador real queda en las capturas de `docs/diseno/capturas/` (agente diseñador).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.cli.main import build_publish_coverage_use_case
from parcel_intel.domain.public_card import BANNED_WORDS
from parcel_intel.domain.published_discrepancy import CADASTRAL_REFERENCE_RE
from tests.acceptance.test_historia_114 import _contraste, _temas
from tests.municipal_layer_fixtures import IGN_FIXTURE
from tests.site.nodo import assert_node_tests_pass

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
DATOS = SITE / "datos"
NOTICE = ROOT / "NOTICE"
REGISTRY = ROOT / "src" / "parcel_intel" / "sources" / "REGISTRY.md"
CAPTURAS = ROOT / "docs" / "diseno" / "capturas"


def _html() -> str:
    return (SITE / "index.html").read_text(encoding="utf-8")


def _css() -> str:
    return (SITE / "estilo.css").read_text(encoding="utf-8")


def _config() -> str:
    return (SITE / "config.js").read_text(encoding="utf-8")


def _texto_visible(html: str) -> str:
    sin_scripts = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", sin_scripts))


def test_ca1_espana_con_los_cubiertos_resaltados_y_el_resto_en_gris(tmp_path: Path) -> None:
    """CA1. Dado el visor recién abierto, cuando carga, entonces se ve el mapa de toda España;
    los municipios cubiertos se resaltan y el resto queda en gris, con la leyenda «aún sin
    cobertura»."""
    config = _config()
    espana = re.search(r"espana:\s*Object\.freeze\(\[([^\]]+)\]\)", config)
    assert espana is not None
    oeste, sur, este, norte = (float(x) for x in espana.group(1).split(","))
    # Península y Baleares: de Galicia a Menorca, de Tarifa a Estaca de Bares.
    assert oeste <= -9.3 and este >= 4.3 and sur <= 36.0 and norte >= 43.8
    assert re.search(r'fondoInicial:\s*"mapa"', config)
    assert "layer=IGNBase-gris" in config
    # Cobertura publicada: un contorno por municipio del índice, nada más.
    indice = json.loads((DATOS / "indice.json").read_text(encoding="utf-8"))
    cobertura = json.loads((DATOS / "cobertura.geojson").read_text(encoding="utf-8"))
    assert sorted(f["properties"]["ine"] for f in cobertura["features"]) == sorted(
        m["ine"] for m in indice["municipios"]
    )
    nombres = {m["ine"]: m["nombre"] for m in indice["municipios"]}
    for feature in cobertura["features"]:
        assert feature["properties"]["nombre"] == nombres[feature["properties"]["ine"]]
        assert feature["geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert "Aún sin cobertura" in _texto_visible(_html())
    assert re.search(r"\{n\} municipios con datos", config)
    assert_node_tests_pass("^H185 CA1:", tmp_path, minimum=2)


def test_ca2_elegir_municipio_por_buscador_o_mapa(tmp_path: Path) -> None:
    """CA2. Dado un municipio cubierto, cuando la persona lo elige (buscador o pulsando en el
    mapa), entonces el mapa se acerca a él y carga sus capas, con su estado (cargando, vacío,
    error)."""
    html = _html()
    entrada = re.search(r"<input[^>]*id=\"buscar\"[^>]*>", html)
    assert entrada is not None
    for atributo in (
        'type="search"',
        'role="combobox"',
        'aria-autocomplete="list"',
        'aria-expanded="false"',
        'aria-controls="sugerencias"',
    ):
        assert atributo in entrada.group(0), atributo
    assert re.search(r'<label for="buscar"[^>]*>Buscar municipio</label>', html)
    assert re.search(r'<ul id="sugerencias"[^>]*role="listbox"', html)
    for capa in ("vias_pecuarias", "camino_actual", "discrepancias", "candidatos"):
        assert f'id="estado-{capa}"' in html and f'id="recuento-{capa}"' in html
    assert_node_tests_pass("^H185 CA2:", tmp_path, minimum=4)
    # Los estados de capa siguen siendo los de #166 (cargando, vacío, error).
    assert_node_tests_pass("^H166 CA4:", tmp_path, minimum=3)


def test_ca3_ficha_en_panel_o_hoja_con_resumen_primero_y_detalle_plegable(
    tmp_path: Path,
) -> None:
    """CA3. Dado un trazado o un indicio, cuando se pulsa, entonces su ficha se abre en un panel
    lateral en escritorio y en una hoja inferior en móvil, nunca en un popup; muestra primero un
    resumen corto y el detalle (fuentes, imágenes de comparación) es desplegable."""
    for modulo in sorted(SITE.glob("*.js")):
        texto = modulo.read_text(encoding="utf-8")
        assert not re.search(r"bindPopup|openPopup|L\.popup", texto), modulo.name
    html = _html()
    ficha = re.search(r'<aside id="ficha"[^>]*>', html)
    assert ficha is not None
    assert "hidden" in ficha.group(0) and 'aria-labelledby="ficha-titulo"' in ficha.group(0)
    assert 'id="ficha-cerrar"' in html and 'id="ficha-ampliar"' in html
    css = _css()
    # Escritorio: panel a la derecha; móvil (< 900 px): hoja pegada abajo, ampliable.
    assert re.search(
        r"\n\.pc-ficha \{[^}]*right: var\(--hueco\)[^}]*width: var\(--ficha-ancho\)", css
    )
    movil = css[css.index("@media (max-width: 899px)") :]
    assert re.search(r"\.pc-cuerpo, \.pc-ficha \{[^}]*bottom: 0;", movil)
    assert '.pc-ficha[data-ampliada="true"]' in movil
    vista = (SITE / "vista.js").read_text(encoding="utf-8")
    assert 'crear("details"' in vista and 'crear("summary"' in vista
    assert_node_tests_pass("^H185 CA3:", tmp_path, minimum=3)


def test_ca4_enlace_con_municipio_y_tramo(tmp_path: Path) -> None:
    """CA4. Dado el estado del visor (municipio, tramo abierto), cuando se copia la URL,
    entonces al abrirla se restaura (`?municipio=…&tramo=…`)."""
    app = (SITE / "app.js").read_text(encoding="utf-8")
    assert "leerEnlace(location.search)" in app
    assert "history.replaceState" in app and "history.pushState" not in app
    # El id de un indicio publicado tiene la forma que acepta el enlace (16 hexadecimales).
    for fichero in sorted((DATOS / "discrepancias").glob("*.geojson")):
        for feature in json.loads(fichero.read_text(encoding="utf-8"))["features"]:
            assert re.fullmatch(r"[0-9a-f]{16}", str(feature["id"])), fichero.name
    assert_node_tests_pass("^H185 CA4:", tmp_path, minimum=3)


def test_ca5_invariantes(tmp_path: Path) -> None:
    """CA5. Las invariantes no cambian: aviso siempre visible, lenguaje de indicio (sin palabras
    vetadas), sin propietarios ni referencias catastrales ni geometría de parcela, atribución
    visible de cada capa, capas de indicios y tramos apagadas al cargar, sitio estático sin
    backend ni compilación, peso del sitio en verde."""
    html = _html()
    visible = _texto_visible(html)
    # Aviso del mapa y del panel, en el HTML estático.
    assert "Cartografía informativa, no es un deslinde." in visible
    assert "Indicios a verificar, no ilegalidades." in visible
    assert "cartografía de carácter informativo, no un deslinde" in visible
    # Lenguaje de indicio y nada catastral en lo que se ve y en los textos de config.js.
    textos = re.findall(r':\s*"([^"]+)"', _config())
    # Los principios del proyecto nombran lo que el mapa NO hace («nunca ilegalidades», «no
    # muestra datos de propietarios»): son la negación que exige la guía, no un hallazgo.
    principios = ("nunca ilegalidades", "no ilegalidades", "No muestra datos de propietarios")
    for frase in principios:
        assert frase in visible
        visible = visible.replace(frase, "")
    for texto in [visible, *textos]:
        minuscula = texto.lower()
        assert not [p for p in BANNED_WORDS if p in minuscula], texto[:80]
        assert CADASTRAL_REFERENCE_RE.search(texto) is None
    # Indicios y tramos nacen apagados; vías pecuarias y camino actual, encendidas.
    for capa, encendida in (
        ("vias_pecuarias", True),
        ("camino_actual", True),
        ("discrepancias", False),
        ("candidatos", False),
    ):
        casilla = re.search(rf'<input[^>]*id="capa-{capa}"[^>]*>', html)
        assert casilla is not None and ("checked" in casilla.group(0)) == encendida, capa
    # Atribución de cada fondo y de la cobertura, literal de NOTICE y en REGISTRY.md.
    notice = NOTICE.read_text(encoding="utf-8")
    assert "`IGNBase-gris CC BY 4.0 scne.es`" in notice
    assert "`CC BY 4.0 ign.es`" in notice
    assert "IGNBase-gris CC BY 4.0 scne.es" in REGISTRY.read_text(encoding="utf-8")
    assert 'atribucion: "CC BY 4.0 ign.es"' in _config()
    # Sitio estático: se construye con su procedencia y pesa lo que debe.
    destino = tmp_path / "_site"
    construir = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "construir_sitio.py"), str(SITE), str(destino)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert construir.returncode == 0, construir.stderr
    peso = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "comprobar_peso_sitio.py"), str(destino)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert peso.returncode == 0, peso.stdout + peso.stderr
    assert not (SITE / "package.json").exists()
    assert_node_tests_pass("^H185 CA5:", tmp_path)


def test_ca5_atribucion_por_encima_de_las_hojas_en_movil() -> None:
    """CA5 (atribución en móvil). La atribución de cada capa sigue visible con la ficha o la
    hoja de capas abiertas: en móvil sube por encima de la hoja (`--hoja-alto`, que publica
    app.js con lo que tapa la hoja), y la ficha ampliada le deja sitio (`--atribucion-alto`)."""
    movil = _css()[_css().index("@media (max-width: 899px)") :]
    assert ".leaflet-bottom { bottom: var(--hoja-alto, var(--asa-alto)); }" in movil
    for selector in (r'\.pc-ficha\[data-ampliada="true"\]', r"\.pc-cuerpo"):
        regla = re.search(selector + r" \{[^}]*max-height:[^;}]*var\(--atribucion-alto", movil)
        assert regla is not None, selector
    app = (SITE / "app.js").read_text(encoding="utf-8")
    assert 'setProperty("--hoja-alto", `${Math.round(relleno().abajo)}px`)' in app
    assert '"--atribucion-alto"' in app
    # Se recalcula al abrir o cerrar una hoja y al cambiar su tamaño o el de la atribución.
    assert 'attributeFilter: ["data-ficha", "data-panel"]' in app
    for selector in (".pc-ficha", ".pc-cuerpo", ".leaflet-control-attribution"):
        assert f'"{selector}"' in app, selector


def test_ca5_cobertura_publicada_desde_los_limites_del_ign(tmp_path: Path) -> None:
    """CA5 (cobertura). `publicar-cobertura` publica solo `ine` y `nombre` de cada municipio,
    con procedencia redistribuible y en EPSG:4326, a partir de la respuesta grabada del WFS de
    unidades administrativas del IGN (fixture real de los 7 municipios del ámbito)."""
    use_case = build_publish_coverage_use_case(
        tmp_path / "cache",
        tmp_path / "datos",
        offline=False,
        ign_http_get=lambda url, params: IGN_FIXTURE.read_bytes(),
        today=lambda: date(2026, 11, 27),
        sleep=lambda _: None,
    )
    codigos = ("28043", "28013", "28052", "28019", "28170", "28180", "28157")
    publicado = use_case.execute(codigos)
    assert publicado.municipality_codes == tuple(sorted(codigos))
    assert publicado.size_bytes < 60_000
    doc = json.loads((tmp_path / "datos" / "cobertura.geojson").read_text(encoding="utf-8"))
    assert doc["properties"]["procedencia"]["redistribucion"] == "publicable"
    assert doc["properties"]["procedencia"]["licencia"] == "CC BY 4.0 ign.es"
    for feature in doc["features"]:
        assert set(feature["properties"]) == {"ine", "nombre"}
        for anillo in (
            [feature["geometry"]["coordinates"][0]]
            if feature["geometry"]["type"] == "Polygon"
            else [p[0] for p in feature["geometry"]["coordinates"]]
        ):
            for lon, lat in anillo:
                assert -3.95 < lon < -3.1 and 39.8 < lat < 40.3
    # El fichero real de site/datos tiene la misma forma y su procedencia.
    sidecar = json.loads((DATOS / "cobertura.geojson.procedencia.json").read_text("utf-8"))
    assert sidecar["redistribucion"] == "publicable"
    assert sidecar["fuente"] == "ign_unidades_administrativas"


def test_ca6_accesibilidad_movil_y_temas() -> None:
    """CA6. Accesibilidad AA (contraste, teclado, foco visible, `prefers-reduced-motion`), móvil
    a 390 px y escritorio, tema claro y oscuro."""
    css = _css()
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "@media (max-width: 899px)" in css
    assert ":focus-visible { outline: 3px solid var(--color-focus)" in css
    # Nada quita el foco fuera de :focus-visible.
    for selector, cuerpo in re.findall(r"([^{}@]+)\{([^{}]*)\}", css):
        if re.search(r"outline:\s*(none|0)\b", cuerpo):
            assert ":focus-visible" in selector, selector
    # El borde de la cobertura y el foco cumplen 3:1 frente al fondo en los tres temas.
    for tema, variables in _temas().items():
        for token in ("--capa-cobertura", "--color-focus"):
            assert _contraste(variables[token], variables["--color-bg"]) >= 3.0, (tema, token)
    # Los tokens nuevos están en el sitio y en el sistema de diseño, idénticos.
    tokens = (SITE / "css" / "tokens.css").read_bytes()
    assert tokens == (ROOT / "docs" / "design-system" / "site" / "css" / "tokens.css").read_bytes()
    for token in ("--map-mapa-filter", "--capa-cobertura", "--capa-cobertura-velo"):
        assert tokens.decode("utf-8").count(token + ":") == 3, token
    # Botones con nombre accesible; el viewport permite ampliar.
    html = _html()
    for boton in re.findall(r"<button[^>]*>.*?</button>", html, re.DOTALL):
        assert 'type="button"' in boton
        assert "aria-label=" in boton or re.sub(r"<[^>]+>", "", boton).strip(), boton
    assert "user-scalable=no" not in html and "maximum-scale" not in html
    # Capturas finales en escritorio y móvil, claro y oscuro: como mucho 8 PNG de < 400 KB.
    capturas = sorted(CAPTURAS.glob("*.png"))
    assert 4 <= len(capturas) <= 8, capturas
    for png in capturas:
        assert png.stat().st_size < 400_000, png.name
    nombres = " ".join(p.name for p in capturas)
    for clave in ("escritorio", "movil", "claro", "oscuro"):
        assert clave in nombres, clave
