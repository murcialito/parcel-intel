"""Historia #114: tokens de diseño y tipografía Atkinson Hyperlegible en el visor.

Sin red: ficheros del repo, parseo con stdlib y contraste WCAG calculado en Python puro.
"""

from __future__ import annotations

import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

RAIZ = Path(__file__).resolve().parents[2]
SITE = RAIZ / "site"
FONTS = SITE / "fonts"
TOKENS = SITE / "css" / "tokens.css"
ESTILO = SITE / "estilo.css"
INDEX = SITE / "index.html"

WOFF2 = {
    "next-400": FONTS / "atkinson-hyperlegible-next-400.woff2",
    "next-700": FONTS / "atkinson-hyperlegible-next-700.woff2",
    "mono-400": FONTS / "atkinson-hyperlegible-mono-400.woff2",
}


def _volcado(nombre: str) -> set[int]:
    texto = (FONTS / f"cmap-{nombre}.txt").read_text(encoding="utf-8")
    return {int(linea.strip()[2:], 16) for linea in texto.splitlines() if linea.strip()}


def _rango(desde: int, hasta: int) -> set[int]:
    return set(range(desde, hasta + 1))


def test_ca1_ficheros_woff2_validos_y_ligeros() -> None:
    """CA1. Dado el repo, cuando se listan los ficheros de `site/fonts/`, entonces existen
    `atkinson-hyperlegible-next-400.woff2`, `atkinson-hyperlegible-next-700.woff2` y
    `atkinson-hyperlegible-mono-400.woff2`, cada uno con cabecera WOFF2 válida (`wOF2`) y un
    tamaño inferior a 60 KB."""
    nombres = {p.name for p in FONTS.iterdir()}
    for ruta in WOFF2.values():
        assert ruta.name in nombres, ruta.name
        datos = ruta.read_bytes()
        assert datos[:4] == b"wOF2", ruta.name
        assert len(datos) < 60 * 1024, (ruta.name, len(datos))


def test_ca2_cobertura_del_subconjunto_latino() -> None:
    """CA2. Dado el subconjunto latino indicado en `LEEME.md`, cuando se compara con el volcado de
    codepoints (`cmap-*.txt`) guardado en `site/fonts/`, entonces las dos Next cubren `ñ`, `Ñ`,
    vocales con tilde y diéresis (`áéíóúü`), `¿`, `¡`, `€`, `–`, `—`, y la
    Mono cubre al menos U+0000–00FF y la puntuación general de su `unicode-range`."""
    # Decisión del fundador (#114): la fuente oficial 2.001 NO trae las flechas U+2190-2193 ni
    # U+00AD ni U+00B5 (site/fonts/PROCEDENCIA.md); no se exigen y caen a `system-ui`.
    obligatorios = {ord(c) for c in "ñÑáéíóúüÁÉÍÓÚÜ¿¡€–—"}
    for nombre in ("next-400", "next-700"):
        faltan = obligatorios - _volcado(nombre)
        assert not faltan, (nombre, sorted(hex(c) for c in faltan))
    # La Mono: Latin-1 imprimible y la puntuación general de su unicode-range.
    mono = _volcado("mono-400")
    esperado = (
        _rango(0x20, 0x7E)
        | _rango(0xA0, 0xFF)
        | {0x2013, 0x2014, 0x2022, 0x2026}
        | _rango(0x2018, 0x201E)
    ) - {0xAD, 0xB5, 0x201B}  # la Mono oficial 2.001 no trae estos tres; caen a system-ui
    faltan_mono = esperado - mono
    assert not faltan_mono, sorted(hex(c) for c in faltan_mono)


def _rangos_font_face() -> dict[str, set[int]]:
    """`unicode-range` de cada `@font-face` de tokens.css, expandido a codepoints, por volcado."""
    resultado: dict[str, set[int]] = {}
    for bloque in re.findall(r"@font-face\s*\{[^}]*\}", TOKENS.read_text(encoding="utf-8")):
        fichero = re.search(r"fonts/atkinson-hyperlegible-([a-z]+-\d+)\.woff2", bloque)
        rango = re.search(r"unicode-range:\s*([^;]+);", bloque)
        assert fichero and rango, bloque
        cps: set[int] = set()
        for parte in rango.group(1).split(","):
            m = re.fullmatch(r"U\+([0-9A-Fa-f]+)(?:-([0-9A-Fa-f]+))?", parte.strip())
            assert m, parte
            desde = int(m.group(1), 16)
            cps |= _rango(desde, int(m.group(2), 16) if m.group(2) else desde)
        resultado[fichero.group(1)] = cps
    return resultado


def test_ca2_unicode_range_sin_flechas_ni_ad_ni_b5() -> None:
    """CA2 (segunda mitad). Las flechas U+2190–2193, U+00AD y U+00B5 no aparecen en ningún
    `unicode-range` de `site/css/tokens.css`, y el rango de cada fuente es subconjunto de su
    volcado `cmap-*` (salvo la excepción documentada U+201B)."""
    rangos = _rangos_font_face()
    assert set(rangos) == set(WOFF2)
    excluidos = _rango(0x2190, 0x2193) | {0xAD, 0xB5}
    for nombre, cps in rangos.items():
        assert not (cps & excluidos), (nombre, sorted(hex(c) for c in cps & excluidos))
        controles = _rango(0, 0x1F) | _rango(0x7F, 0x9F)  # sin glifo, no están en el cmap
        fuera = cps - _volcado(nombre) - {0x201B} - controles
        assert not fuera, (nombre, sorted(hex(c) for c in fuera))


def test_ca3_licencia_y_procedencia() -> None:
    """CA3. Dado `site/fonts/`, cuando se leen `OFL.txt` y `PROCEDENCIA.md`, entonces `OFL.txt`
    contiene el texto de la SIL Open Font License 1.1 y la procedencia indica fuente (Braille
    Institute o paquete OFL de Google Fonts), URL de descarga, fecha de descarga, licencia
    "SIL OFL 1.1" y el comando de subconjunto usado."""
    ofl = (FONTS / "OFL.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE Version 1.1" in ofl
    assert "PERMISSION & CONDITIONS" in ofl
    procedencia = (FONTS / "PROCEDENCIA.md").read_text(encoding="utf-8")
    assert "Braille Institute" in procedencia
    assert re.search(r"https://github\.com/googlefonts/atkinson-hyperlegible", procedencia)
    assert re.search(r"Fecha de descarga\*\*: \d{4}-\d{2}-\d{2}", procedencia)
    assert "SIL OFL 1.1" in procedencia
    assert "pyftsubset" in procedencia and "--unicodes" in procedencia


class _Etiquetas(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.etiquetas: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.etiquetas.append((tag, dict(attrs)))


def _html() -> list[tuple[str, dict[str, str | None]]]:
    parser = _Etiquetas()
    parser.feed(INDEX.read_text(encoding="utf-8"))
    return parser.etiquetas


def _urls_css(texto: str) -> list[str]:
    urls = re.findall(r"url\(\s*['\"]?([^'\")]+?)['\"]?\s*\)", texto)
    urls += re.findall(r"@import\s+(?:url\()?\s*['\"]?([^'\");\s]+)", texto)
    return urls


def test_ca4_tokens_enlazados_antes_de_estilo_y_usados() -> None:
    """CA4. Dado `site/css/tokens.css` (copia de los tokens del sistema de diseño) y
    `site/estilo.css`, cuando se cargan desde `site/index.html`, entonces `index.html` enlaza
    `tokens.css` antes de `estilo.css`, las rutas `url()` de los `@font-face` resuelven a ficheros
    que existen en `site/fonts/`, y `estilo.css` ya no declara `--bg`, `--fg`, `--muted`,
    `--accent`, `--line` ni `--aviso`: usa los tokens (`--color-*`, `--space-*`, `--text-*`,
    `--radius-*`, `--font-*`)."""
    hojas = [a["href"] for t, a in _html() if t == "link" and a.get("rel") == "stylesheet"]
    assert "css/tokens.css" in hojas and "estilo.css" in hojas
    assert hojas.index("css/tokens.css") < hojas.index("estilo.css")

    # Es copia fiel de la fuente de diseño.
    fuente = RAIZ / "docs" / "design-system" / "site" / "css" / "tokens.css"
    assert TOKENS.read_text(encoding="utf-8") == fuente.read_text(encoding="utf-8")

    tokens = TOKENS.read_text(encoding="utf-8")
    rutas = [u for u in _urls_css(tokens) if u.endswith(".woff2")]
    assert len(rutas) == 3
    for ruta in rutas:
        assert (TOKENS.parent / ruta).resolve().is_file(), ruta
        assert (TOKENS.parent / ruta).resolve().parent == FONTS.resolve(), ruta

    estilo = ESTILO.read_text(encoding="utf-8")
    for viejo in ("bg", "fg", "muted", "accent", "line", "aviso"):
        assert not re.search(rf"--{viejo}\s*:", estilo), viejo
        assert not re.search(rf"var\(--{viejo}\)", estilo), viejo
    for prefijo in ("--color-", "--space-", "--text-", "--radius-", "--font-"):
        assert f"var({prefijo}" in estilo, prefijo


def test_ca5_sin_recursos_externos() -> None:
    """CA5. Dado cualquier `url(...)`, `<link href>`, `<script src>` o `@import` de
    `site/index.html`, `site/estilo.css` y `site/css/tokens.css`, cuando se analizan, entonces
    ninguno apunta a un dominio externo (`http://`, `https://` o `//`); quedan fuera de la
    comprobación los enlaces `<a>` de navegación."""
    referencias: list[str] = []
    for tag, attrs in _html():
        if tag == "link" and attrs.get("href"):
            referencias.append(attrs["href"] or "")
        if tag == "script" and attrs.get("src"):
            referencias.append(attrs["src"] or "")
    for css in (ESTILO, TOKENS):
        referencias += _urls_css(css.read_text(encoding="utf-8"))
    assert len(referencias) >= 8, referencias  # el análisis no pasa en vacío
    for ref in referencias:
        assert not ref.startswith(("http://", "https://", "//")), ref


def test_ca6_fuente_base_y_monoespaciada() -> None:
    """CA6. Dado el `body` del visor, cuando se lee `estilo.css`, entonces la fuente base es
    `var(--font-sans)` con tamaño `var(--text-base)` y los valores monoespaciados (coordenadas,
    referencias, fechas) pueden usar `var(--font-mono)`. Si faltan los WOFF2, el `font-family`
    cae a `system-ui` (la pila ya lo incluye)."""
    estilo = ESTILO.read_text(encoding="utf-8")
    cuerpo = re.search(r"\nbody\s*\{([^}]*)\}", estilo)
    assert cuerpo is not None
    assert re.search(r"font-family:\s*var\(--font-sans\)", cuerpo.group(1))
    assert re.search(r"font-size:\s*var\(--text-base\)", cuerpo.group(1))
    assert "var(--font-mono)" in estilo
    tokens = TOKENS.read_text(encoding="utf-8")
    pila = re.search(r"--font-sans:\s*([^;]+);", tokens)
    assert pila is not None and "system-ui" in pila.group(1)


# --- Contraste WCAG 2.x -------------------------------------------------------------------


def _bloque(texto: str, cabecera: str) -> str:
    inicio = texto.index(cabecera)
    abre = texto.index("{", inicio)
    nivel, i = 0, abre
    while True:
        if texto[i] == "{":
            nivel += 1
        elif texto[i] == "}":
            nivel -= 1
            if nivel == 0:
                return texto[abre + 1 : i]
        i += 1


def _variables(bloque: str) -> dict[str, str]:
    return dict(re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\b", bloque))


def _temas() -> dict[str, dict[str, str]]:
    tokens = TOKENS.read_text(encoding="utf-8")
    claro = _variables(_bloque(tokens, ":root {"))
    oscuro_pref = _variables(_bloque(tokens, ':root:not([data-tema="claro"])'))
    oscuro_forzado = _variables(_bloque(tokens, ':root[data-tema="oscuro"]'))
    return {
        "claro": claro,
        "oscuro (prefers-color-scheme)": {**claro, **oscuro_pref},
        'oscuro (data-tema="oscuro")': {**claro, **oscuro_forzado},
    }


def _luminancia(color: str) -> float:
    canales = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lineal = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
    return 0.2126 * lineal[0] + 0.7152 * lineal[1] + 0.0722 * lineal[2]


def _contraste(a: str, b: str) -> float:
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_contraste_calculo_de_referencia() -> None:
    """Comprueba la fórmula WCAG con valores conocidos (negro/blanco = 21; gris #767676 sobre
    blanco ≈ 4,54)."""
    assert _contraste("#000000", "#ffffff") == pytest.approx(21.0)
    assert _contraste("#767676", "#ffffff") == pytest.approx(4.54, abs=0.01)


def test_ca7_contraste_wcag_en_los_dos_temas() -> None:
    """CA7. Dado cada par de colores texto/fondo que usa el visor (`--color-fg`/`--color-bg`,
    `--color-muted`/`--color-bg`, `--color-accent`/`--color-bg`, `--color-on-accent`/
    `--color-accent`, `--color-nota-fg`/`--color-nota-bg`; #166 retira el rojo de error:
    usa los tokens de nota), cuando se calcula el contraste WCAG 2.x en tema claro y en oscuro
    (incluido `data-tema="oscuro"`), entonces es de al menos 4,5:1 para texto y 3:1 para el color
    de foco y los bordes de controles frente al fondo."""
    temas = _temas()
    assert len(temas) == 3
    texto = [
        ("--color-fg", "--color-bg"),
        ("--color-muted", "--color-bg"),
        ("--color-accent", "--color-bg"),
        ("--color-on-accent", "--color-accent"),
        ("--color-nota-fg", "--color-nota-bg"),
    ]
    # El borde de los controles es el token que usa `.campo select` en estilo.css.
    borde = re.search(
        r"\.campo select\s*\{[^}]*border:\s*1px solid var\((--[\w-]+)\)",
        ESTILO.read_text(encoding="utf-8"),
    )
    assert borde is not None
    no_texto = [("--color-focus", "--color-bg"), (borde.group(1), "--color-bg")]
    fallos: list[str] = []
    for tema, v in temas.items():
        for fg, bg in texto:
            r = _contraste(v[fg], v[bg])
            if r < 4.5:
                fallos.append(f"{tema}: {fg} sobre {bg} = {r:.2f} (< 4,5)")
        for fg, bg in no_texto:
            r = _contraste(v[fg], v[bg])
            if r < 3.0:
                fallos.append(f"{tema}: {fg} sobre {bg} = {r:.2f} (< 3)")
    assert not fallos, fallos


def test_ca8_tests_del_visor_siguen_en_verde() -> None:
    """CA8. Dado el visor, cuando se ejecutan `tests/site/` (Node y Python), entonces siguen en
    verde sin modificar su lógica; los selectores y clases que usan `app.js`/`vista.js` no
    cambian."""
    resultado = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/site", "-q", "-p", "no:cacheprovider"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stdout[-2000:]
    # Las clases que usa la vista siguen definidas en estilo.css.
    estilo = ESTILO.read_text(encoding="utf-8")
    clases = (".pc-capa", ".pc-capa__estado", ".mensaje", ".ficha", ".ficha-fuente", ".aviso-base")
    for clase in clases:
        assert clase in estilo, clase


def test_ca9_despliegue_incluye_fonts_y_css(tmp_path: Path) -> None:
    """CA9. Dado `.github/workflows/desplegar.yml`, cuando publica `site/`, entonces `site/fonts/`
    y `site/css/` van incluidos (están dentro de `site/` y no hay exclusiones que los dejen
    fuera)."""
    flujo = (RAIZ / ".github" / "workflows" / "desplegar.yml").read_text(encoding="utf-8")
    assert "scripts/construir_sitio.py site _site" in flujo
    assert "path: _site" in flujo
    destino = tmp_path / "_sitio"
    resultado = subprocess.run(
        [
            sys.executable,
            "-I",
            str(RAIZ / "scripts" / "construir_sitio.py"),
            str(SITE),
            str(destino),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr
    for ruta in (
        "css/tokens.css",
        "fonts/atkinson-hyperlegible-next-400.woff2",
        "fonts/atkinson-hyperlegible-next-700.woff2",
        "fonts/atkinson-hyperlegible-mono-400.woff2",
        "fonts/OFL.txt",
    ):
        assert (destino / ruta).is_file(), ruta
