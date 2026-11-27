"""Historia #115: marca Paso Común en el sitio (logo, favicon, manifest, imagen social).

Un test por criterio. Todo se lee con la stdlib, sin red.

Desviación de CA3 (escalada al fundador en la issue): la historia fija las URLs de Open Graph con
``murcialito.github.io/parcel-intel/``, pero el repositorio ya se llama ``paso-comun`` y el sitio
está en ``https://murcialito.github.io/paso-comun/`` (CLAUDE.md). Los tests usan esta última.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
DISENO = ROOT / "docs" / "design-system" / "site"
BUILD_SCRIPT = ROOT / "scripts" / "construir_sitio.py"

URL_PAGES = "https://murcialito.github.io/paso-comun/"

FICHEROS_MARCA = (
    "favicon.svg",
    "favicon-32.png",
    "apple-touch-icon.png",
    "icon-192.png",
    "icon-512.png",
    "og-image.png",
    "site.webmanifest",
    "img/logo/paso-comun-horizontal.svg",
    "img/logo/paso-comun-horizontal-oscuro.svg",
)


class _Html(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.texto: list[str] = []
        self._ignorar = 0
        self._pila: list[str] = []
        self.h1_texto: list[str] = []
        self.dentro_h1 = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))
        self._pila.append(tag)
        if tag in ("script", "style"):
            self._ignorar += 1
        if tag == "h1":
            self.dentro_h1 = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._ignorar:
            self._ignorar -= 1
        if tag == "h1":
            self.dentro_h1 = False

    def handle_data(self, data: str) -> None:
        if not self._ignorar:
            self.texto.append(data)


def _html() -> _Html:
    parser = _Html()
    parser.feed((SITE / "index.html").read_text(encoding="utf-8"))
    return parser


def _tags(html: _Html, nombre: str, **attrs: str) -> list[dict[str, str | None]]:
    return [
        a
        for t, a in html.tags
        if t == nombre and all(a.get(k) == v for k, v in attrs.items())
    ]


def _meta(html: _Html, clave: str, valor: str) -> str | None:
    for a in _tags(html, "meta"):
        if a.get(clave) == valor:
            return a.get("content")
    return None


def test_ca1_titulo_y_sin_parcel_intel() -> None:
    """CA1. Dado `site/index.html` cuando se lee entonces `<title>` contiene «Paso Común»,
    `<html lang="es">` se mantiene y no queda «Parcel Intel» en ningún texto visible ni metadato
    de la página."""
    crudo = (SITE / "index.html").read_text(encoding="utf-8")
    html = _html()
    titulo = re.search(r"<title>(.*?)</title>", crudo, re.DOTALL)
    assert titulo is not None and "Paso Común" in titulo.group(1)
    assert _tags(html, "html", lang="es")
    assert "parcel intel" not in crudo.lower()
    assert "parcel-intel" not in crudo.lower()


def test_ca2_logo_en_picture_y_h1() -> None:
    """CA2. Dado `index.html` cuando se lee entonces la cabecera muestra el logo horizontal
    dentro de un `<picture>`: `paso-comun-horizontal-oscuro.svg` con
    `media="(prefers-color-scheme: dark)"` y `paso-comun-horizontal.svg` como `<img>` por
    defecto, con `alt="Paso Común"`, ruta relativa y alto mínimo de 24 px en `estilo.css`. El
    `<h1>` conserva el texto «Paso Común» (accesible, sin duplicar el lema) y el aviso «indicios
    a verificar, nunca ilegalidades» sigue en la cabecera."""
    crudo = (SITE / "index.html").read_text(encoding="utf-8")
    cabecera = re.search(r"<header.*?</header>", crudo, re.DOTALL)
    assert cabecera is not None
    bloque = cabecera.group(0)
    assert re.search(r"<picture>.*</picture>", bloque, re.DOTALL)
    fuente = re.search(r"<source\s+([^>]*)>", bloque)
    assert fuente is not None
    assert 'srcset="img/logo/paso-comun-horizontal-oscuro.svg"' in fuente.group(1)
    assert 'media="(prefers-color-scheme: dark)"' in fuente.group(1)
    imagen = re.search(r"<img\s+([^>]*)>", bloque)
    assert imagen is not None
    assert 'src="img/logo/paso-comun-horizontal.svg"' in imagen.group(1)
    assert 'alt="Paso Común"' in imagen.group(1)
    assert "indicios a verificar</strong>, nunca ilegalidades" in bloque
    css = (SITE / "estilo.css").read_text(encoding="utf-8")
    regla = re.search(r"\.cabecera \.logo\s*\{([^}]*)\}", css)
    assert regla is not None
    minimo = re.search(r"min-height:\s*(\d+)px", regla.group(1))
    assert minimo is not None and int(minimo.group(1)) >= 24
    # El <h1> contiene el logo con alt «Paso Común»: su nombre accesible es «Paso Común».
    assert re.search(r"<h1>\s*<picture>", bloque)


def test_ca3_open_graph_y_description() -> None:
    """CA3. Dado `index.html` cuando se lee entonces declara `<meta name="description">` con el
    texto actual adaptado a la marca y `<meta property="og:*">` con `og:title`,
    `og:description`, `og:type=website`, `og:locale=es_ES`, `og:url` y `og:image` absolutas del
    sitio publicado (más `twitter:card=summary_large_image`); `og-image.png` existe en `site/`.
    (URL: la de Pages del repositorio actual, ver docstring del módulo.)"""
    html = _html()
    descripcion = _meta(html, "name", "description")
    assert descripcion and "Paso Común" in descripcion
    assert "indicios a verificar, nunca ilegalidades" in descripcion
    assert _meta(html, "property", "og:title")
    assert _meta(html, "property", "og:description")
    assert _meta(html, "property", "og:type") == "website"
    assert _meta(html, "property", "og:locale") == "es_ES"
    assert _meta(html, "property", "og:url") == URL_PAGES
    assert _meta(html, "property", "og:image") == URL_PAGES + "og-image.png"
    assert _meta(html, "name", "twitter:card") == "summary_large_image"
    assert (SITE / "og-image.png").is_file()


def test_ca4_favicons_manifest_y_copias_identicas() -> None:
    """CA4. Dado `index.html` cuando se lee entonces enlaza `favicon.svg`
    (`rel="icon" type="image/svg+xml"`), `favicon-32.png` (`rel="icon" sizes="32x32"`),
    `apple-touch-icon.png` (`rel="apple-touch-icon"`) y `site.webmanifest` (`rel="manifest"`),
    y añade `<meta name="theme-color">` con el valor del manifest; todos esos ficheros existen en
    `site/` y son idénticos byte a byte a los de `docs/design-system/site/`."""
    html = _html()
    assert _tags(html, "link", rel="icon", type="image/svg+xml", href="favicon.svg")
    assert _tags(html, "link", rel="icon", sizes="32x32", href="favicon-32.png")
    assert _tags(html, "link", rel="apple-touch-icon", href="apple-touch-icon.png")
    assert _tags(html, "link", rel="manifest", href="site.webmanifest")
    manifest = json.loads((SITE / "site.webmanifest").read_text(encoding="utf-8"))
    assert _meta(html, "name", "theme-color") == manifest["theme_color"]
    for nombre in (
        "favicon.svg",
        "favicon-32.png",
        "apple-touch-icon.png",
        "site.webmanifest",
    ):
        assert (SITE / nombre).read_bytes() == (DISENO / nombre).read_bytes(), nombre


def test_ca5_manifest_valido() -> None:
    """CA5. Dado `site/site.webmanifest` cuando se parsea entonces es JSON válido con `name`
    «Paso Común», `start_url` y `scope` relativos, y cada `src` de `icons` existe en `site/`
    (`favicon.svg`, `icon-192.png`, `icon-512.png`)."""
    manifest = json.loads((SITE / "site.webmanifest").read_text(encoding="utf-8"))
    assert manifest["name"] == "Paso Común"
    for clave in ("start_url", "scope"):
        valor = manifest[clave]
        assert not re.match(r"^([a-z]+:)?//|^/", valor), valor
    srcs = [icono["src"] for icono in manifest["icons"]]
    assert {"favicon.svg", "icon-192.png", "icon-512.png"} <= set(srcs)
    for src in srcs:
        assert (SITE / src).is_file(), src


def test_ca6_solo_ficheros_de_marca_usados() -> None:
    """CA6. Dado `site/` cuando se listan sus ficheros de marca entonces solo están los usados
    por `index.html` o el manifest (los dos logos horizontales, favicons, iconos, og-image,
    manifest); no se copian los logos de símbolo/monocromo, los de «Parcel Intel»,
    `componentes.html`, `css/`, `js/`, `fonts/` ni `img/iconos/` (los usan #114 y #116)."""
    for nombre in FICHEROS_MARCA:
        assert (SITE / nombre).is_file(), nombre
    logos = sorted(p.name for p in (SITE / "img" / "logo").iterdir())
    assert logos == [
        "paso-comun-horizontal-oscuro.svg",
        "paso-comun-horizontal.svg",
    ]
    assert not (SITE / "img" / "iconos").exists()
    # `css/` y `fonts/` los añadió #114 (tokens y tipografía, ya fusionada): esta historia no los
    # copia, pero ya no pueden exigirse ausentes.
    for ausente in ("componentes.html", "js"):
        assert not (SITE / ausente).exists(), ausente
    assert not list(SITE.rglob("parcel-intel-*"))


def test_ca7_construir_sitio_incluye_marca(tmp_path: Path) -> None:
    """CA7. Dado `scripts/construir_sitio.py origen destino` sobre el `site/` resultante cuando
    se ejecuta entonces termina con 0 y los recursos de marca llegan a `destino`. Los acceptance
    de #41, #84 y #85 siguen verdes (CA1 de #85: ningún recurso cargado apunta a host
    externo)."""
    destino = tmp_path / "_site"
    resultado = subprocess.run(
        [sys.executable, str(BUILD_SCRIPT), str(SITE), str(destino)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr
    for nombre in FICHEROS_MARCA:
        assert (destino / nombre).is_file(), nombre


def test_ca8_guia_de_marca_y_vision() -> None:
    """CA8. Dado `docs/` cuando se lee entonces `docs/marca/GUIA-DE-MARCA.md` es la guía de
    marca (copia de la del paquete) y `docs/vision.md` y `docs/design-system/README.md` la
    referencian si hablan del nombre; `docs/vision.md` usa «Paso Común» como nombre público del
    visor, sin renombrar el repositorio ni el paquete."""
    guia = ROOT / "docs" / "marca" / "GUIA-DE-MARCA.md"
    assert guia.read_bytes() == (DISENO / "GUIA-DE-MARCA.md").read_bytes()
    vision = (ROOT / "docs" / "vision.md").read_text(encoding="utf-8")
    assert "Paso Común" in vision
    assert "marca/GUIA-DE-MARCA.md" in vision
    readme = (ROOT / "docs" / "design-system" / "README.md").read_text(encoding="utf-8")
    assert "marca/GUIA-DE-MARCA.md" in readme
    assert (ROOT / "src" / "parcel_intel").is_dir()


def test_ca9_notice_recursos_de_diseno() -> None:
    """CA9. Dado `NOTICE` cuando se lee entonces tiene una sección «Recursos de diseño» que
    atribuye el logo, los iconos y la imagen social a Paso Común / sistema de diseño del
    proyecto bajo CC BY 4.0 (URL https://creativecommons.org/licenses/by/4.0/deed.es), con la
    ruta `docs/design-system/` como origen. Si la guía de marca no nombra autoría, se escribe la
    del proyecto («Parcel Intel / Paso Común») sin inventar nombres de personas."""
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    partes = re.split(r"^## ", notice, flags=re.MULTILINE)
    seccion = next((p for p in partes if p.startswith("Recursos de diseño")), None)
    assert seccion is not None
    assert "CC BY 4.0" in seccion
    assert "https://creativecommons.org/licenses/by/4.0/deed.es" in seccion
    assert "docs/design-system/" in seccion
    assert "Parcel Intel / Paso Común" in seccion
    for palabra in ("logo", "iconos", "imagen social"):
        assert palabra in seccion.lower()
