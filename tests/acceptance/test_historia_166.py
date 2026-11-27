"""Historia #166: panel de capas, avisos, atribución y estados del sistema de diseño en el visor.

Sin red ni navegador: `html.parser`, lectura de CSS en Python puro y el documento falso de Node.
"""

from __future__ import annotations

import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

from tests.acceptance.test_historia_114 import _bloque, _contraste, _variables
from tests.site.nodo import assert_node_tests_pass, volcar_base

pytestmark = pytest.mark.acceptance

RAIZ = Path(__file__).resolve().parents[2]
SITE = RAIZ / "site"
INDEX = SITE / "index.html"
ESTILO = SITE / "estilo.css"
TOKENS = SITE / "css" / "tokens.css"
TOKENS_PAQUETE = RAIZ / "docs" / "design-system" / "site" / "css" / "tokens.css"
NOTICE = RAIZ / "NOTICE"

VOID = {"meta", "link", "img", "input", "br", "hr", "source"}


# --- HTML como árbol -------------------------------------------------------------------------


class Nodo:
    def __init__(self, tag: str, attrs: dict[str, str | None], padre: Nodo | None) -> None:
        self.tag = tag
        self.attrs = attrs
        self.padre = padre
        self.hijos: list[Nodo] = []
        self.texto: list[str] = []

    def clases(self) -> list[str]:
        return (self.attrs.get("class") or "").split()

    def descendientes(self) -> list[Nodo]:
        salida: list[Nodo] = []
        for h in self.hijos:
            salida.append(h)
            salida.extend(h.descendientes())
        return salida

    def contenido(self) -> str:
        partes = list(self.texto)
        for h in self.hijos:
            partes.append(h.contenido())
        return re.sub(r"\s+", " ", " ".join(partes)).strip()

    def ancestros(self) -> list[Nodo]:
        n, salida = self.padre, []
        while n is not None:
            salida.append(n)
            n = n.padre
        return salida


class _Arbol(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.raiz = Nodo("#raiz", {}, None)
        self._actual = self.raiz

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        nodo = Nodo(tag, dict(attrs), self._actual)
        self._actual.hijos.append(nodo)
        if tag not in VOID:
            self._actual = nodo

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._actual.hijos.append(Nodo(tag, dict(attrs), self._actual))

    def handle_endtag(self, tag: str) -> None:
        n: Nodo | None = self._actual
        while n is not None and n.tag != tag:
            n = n.padre
        if n is not None and n.padre is not None:
            self._actual = n.padre

    def handle_data(self, data: str) -> None:
        self._actual.texto.append(data)


def _arbol() -> Nodo:
    p = _Arbol()
    p.feed(INDEX.read_text(encoding="utf-8"))
    return p.raiz


def _buscar(raiz: Nodo, tag: str | None = None, clase: str | None = None) -> list[Nodo]:
    return [
        n
        for n in raiz.descendientes()
        if (tag is None or n.tag == tag) and (clase is None or clase in n.clases())
    ]


def _por_id(raiz: Nodo, ident: str) -> Nodo:
    hallados = [n for n in raiz.descendientes() if n.attrs.get("id") == ident]
    assert len(hallados) == 1, ident
    return hallados[0]


# --- CSS -------------------------------------------------------------------------------------


def _sin_comentarios(texto: str) -> str:
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.DOTALL)


def _declaraciones(cuerpo: str) -> dict[str, str]:
    salida: dict[str, str] = {}
    for parte in cuerpo.split(";"):
        if ":" in parte:
            clave, valor = parte.split(":", 1)
            salida[clave.strip()] = valor.strip()
    return salida


def _reglas() -> list[tuple[str, dict[str, str]]]:
    """Todas las reglas (también las dentro de `@media`), con el selector sin partir."""
    css = _sin_comentarios(ESTILO.read_text(encoding="utf-8"))
    reglas = []
    for selector, cuerpo in re.findall(r"([^{}@]+)\{([^{}]*)\}", css):
        reglas.append((" ".join(selector.split()), _declaraciones(cuerpo)))
    return reglas


def _declaraciones_de(selector: str) -> dict[str, str]:
    """Fusiona las declaraciones de todas las reglas cuya lista de selectores incluye `selector`."""
    fusion: dict[str, str] = {}
    for lista, decl in _reglas():
        if selector in [s.strip() for s in lista.split(",")]:
            fusion.update(decl)
    return fusion


def _regla_exacta(selector: str) -> dict[str, str]:
    """Declaraciones de la primera regla (fuera de `@media`) cuyo selector incluye `selector`."""
    for lista, decl in _reglas():
        if selector in [s.strip() for s in lista.split(",")]:
            return decl
    raise AssertionError(f"sin regla para {selector}")


# --- CA1 -------------------------------------------------------------------------------------


def _titulos_config() -> dict[str, str]:
    texto = (SITE / "config.js").read_text(encoding="utf-8")
    return dict(re.findall(r'id:\s*"(\w+)",\s*titulo:\s*"([^"]+)"', texto))


def test_ca1_panel_de_capas_con_muestra_nombre_descripcion_e_interruptor() -> None:
    """CA1. Dado el panel de capas de `index.html`, cuando se lee, entonces cada capa con datos
    (vías pecuarias, camino actual, indicios) es un `<li class="pc-capa">` con: un `<label
    for="capa-<id>" class="pc-capa__fila">` que envuelve una muestra `<svg class="pc-muestra
    pc-muestra--<familia>" aria-hidden="true">` con dos `<line>` (`.h` halo, `.l` línea), el
    nombre (el `titulo` de `config.js`, literal), una descripción corta y un `<input
    type="checkbox" role="switch" class="pc-switch" id="capa-<id>">`; y un `<div
    class="pc-capa__estado" id="estado-<id>">`. Indicios lleva además la lista `pc-capa__niveles`
    con las tres muestras `baja`, `media` y `alta` y su texto. El trazado histórico no aparece.
    Siguen siendo exactamente cuatro controles nativos con su `<label for>` (#85 CA15)."""
    raiz = _arbol()
    titulos = _titulos_config()
    assert set(titulos) == {"vias_pecuarias", "camino_actual", "discrepancias"}
    familias = {"vias_pecuarias": "vias", "camino_actual": "camino", "discrepancias": "indicio"}
    capas = _buscar(raiz, "li", "pc-capa")
    assert len(capas) == 3
    visto = []
    for li in capas:
        filas = [h for h in li.hijos if h.tag == "label"]
        assert len(filas) == 1 and "pc-capa__fila" in filas[0].clases()
        fila = filas[0]
        ident = (fila.attrs["for"] or "").removeprefix("capa-")
        visto.append(ident)
        assert ident in titulos
        svgs = [h for h in fila.descendientes() if h.tag == "svg"]
        assert len(svgs) == 1
        svg = svgs[0]
        assert "pc-muestra" in svg.clases() and f"pc-muestra--{familias[ident]}" in svg.clases()
        assert svg.attrs.get("aria-hidden") == "true"
        lineas = [h for h in svg.hijos if h.tag == "line"]
        assert [x.attrs.get("class") for x in lineas] == ["h", "l"]
        nombres = _buscar(fila, "span", "pc-capa__nombre")
        assert len(nombres) == 1 and nombres[0].contenido() == titulos[ident]
        descs = _buscar(fila, "span", "pc-capa__desc")
        assert len(descs) == 1 and descs[0].contenido() != ""
        entradas = [h for h in fila.descendientes() if h.tag == "input"]
        assert len(entradas) == 1
        a = entradas[0].attrs
        assert a.get("type") == "checkbox" and a.get("role") == "switch"
        assert a.get("class") == "pc-switch" and a.get("id") == f"capa-{ident}"
        estados = [h for h in li.hijos if h.tag == "div" and "pc-capa__estado" in h.clases()]
        assert len(estados) == 1 and estados[0].attrs.get("id") == f"estado-{ident}"
        niveles = _buscar(li, "ul", "pc-capa__niveles")
        if ident == "discrepancias":
            assert "pc-muestra--media" in svg.clases()
            assert len(niveles) == 1
            items = _buscar(niveles[0], "li")
            assert len(items) == 3
            for item, nivel in zip(items, ("baja", "media", "alta"), strict=True):
                marca = [s for s in item.descendientes() if s.tag == "svg"]
                assert len(marca) == 1 and f"pc-muestra--{nivel}" in marca[0].clases()
                assert nivel in item.contenido().lower()
        else:
            assert niveles == []
    assert visto == ["vias_pecuarias", "camino_actual", "discrepancias"]
    html = INDEX.read_text(encoding="utf-8")
    assert "historico" not in html.lower() and "histórico" not in html.lower()
    # Cuatro controles nativos, cada uno con su <label for> (#85 CA15).
    nativos = ("select", "input", "button", "textarea")
    controles = [n for n in raiz.descendientes() if n.tag in nativos]
    assert len(controles) == 4
    etiquetas = {n.attrs.get("for") for n in _buscar(raiz, "label")}
    for c in controles:
        assert c.attrs.get("id") in etiquetas
    assert not any(n.attrs.get("role") == "button" for n in raiz.descendientes())


# --- CA2 -------------------------------------------------------------------------------------


def _num(valor: str) -> float:
    return float(valor)


def test_ca2_muestras_replican_los_estilos_del_mapa(tmp_path: Path) -> None:
    """CA2. Dado `estilo.css`, cuando se compara con `BASE` de `site/estilos-capas.js` (#165),
    entonces para cada muestra `stroke-width` de `.l` es `weight` y el de `.h` es `weight +
    halo.extra`; `stroke-dasharray` es el `dashArray` de la línea y del halo; `stroke-opacity`
    de `.h` es `halo.opacity`; y `stroke` usa `var(--capa-*)`. Además, cada `--capa-*` y
    `--capa-seleccion-halo` de `tokens.css` coincide con el color de `BASE` en claro y en oscuro
    (los dos bloques oscuros). El test lee los tres ficheros."""
    base = volcar_base(tmp_path)
    claro = base["claro"]
    assert isinstance(claro, dict)
    muestras = {
        "vias": (["vias"], "viasPecuarias", "--capa-vias", "--capa-vias-halo"),
        "camino": (["camino"], "caminoActual", "--capa-camino", "--capa-camino-halo"),
        "baja": (["indicio", "baja"], "indicioBaja", "--capa-indicio", "--capa-indicio-halo"),
        "media": (["indicio", "media"], "indicioMedia", "--capa-indicio", "--capa-indicio-halo"),
        "alta": (["indicio", "alta"], "indicioAlta", "--capa-indicio", "--capa-indicio-halo"),
    }
    for nombre, (clases, clave, token, token_halo) in muestras.items():
        b = claro[clave]
        linea: dict[str, str] = {}
        halo: dict[str, str] = {}
        for c in clases:
            linea.update(_declaraciones_de(f".pc-muestra--{c} .l"))
            halo.update(_declaraciones_de(f".pc-muestra--{c} .h"))
        assert _num(linea["stroke-width"]) == b["weight"], nombre
        assert _num(halo["stroke-width"]) == b["weight"] + b["halo"]["extra"], nombre
        assert _num(halo["stroke-opacity"]) == b["halo"]["opacity"], nombre
        assert linea.get("stroke-dasharray") == b["dashArray"], nombre
        assert halo.get("stroke-dasharray") == (b["halo"].get("dashArray") or None), nombre
        assert linea["stroke"] == f"var({token})", nombre
        assert halo["stroke"] == f"var({token_halo})", nombre
        if b["lineCap"] == "round":
            assert linea.get("stroke-linecap") == "round" and halo.get("stroke-linecap") == "round"
    # Tokens: cada --capa-* coincide con BASE en claro y en los dos bloques oscuros.
    texto = TOKENS.read_text(encoding="utf-8")
    bloques = {
        "claro": _variables(_bloque(texto, ":root {")),
        "oscuro": _variables(_bloque(texto, ':root:not([data-tema="claro"])')),
        "oscuro forzado": _variables(_bloque(texto, ':root[data-tema="oscuro"]')),
    }
    esperado = {
        "--capa-vias": ("viasPecuarias", "color"),
        "--capa-vias-halo": ("viasPecuarias", "halo"),
        "--capa-camino": ("caminoActual", "color"),
        "--capa-camino-halo": ("caminoActual", "halo"),
        "--capa-historico": ("trazadoHistorico", "color"),
        "--capa-historico-halo": ("trazadoHistorico", "halo"),
        "--capa-indicio": ("indicioMedia", "color"),
        "--capa-indicio-halo": ("indicioMedia", "halo"),
    }
    for bloque, variables in bloques.items():
        tema = "claro" if bloque == "claro" else "oscuro"
        for token, (clave, campo) in esperado.items():
            if bloque != "claro" and token not in variables and token.endswith("-halo"):
                continue  # los halos no cambian en oscuro: salen del bloque claro
            b = base[tema][clave]  # type: ignore[index]
            color = b["halo"]["color"] if campo == "halo" else b["color"]
            valor = variables.get(token, bloques["claro"][token])
            assert valor.lower() == color.lower(), (bloque, token)
        sel = variables.get("--capa-seleccion-halo", bloques["claro"]["--capa-seleccion-halo"])
        assert sel.lower() == base["seleccionHalo"][tema].lower(), bloque  # type: ignore[index]
    for bloque in ("oscuro", "oscuro forzado"):
        assert "--capa-vias" in bloques[bloque], bloque  # el bloque oscuro sí define los colores


# --- CA3 -------------------------------------------------------------------------------------


def test_ca3_avisos_y_atribucion_visibles_sin_interaccion(tmp_path: Path) -> None:
    """CA3. Dado el visor en cualquier estado y municipio, cuando se carga la página y sin
    interacción, entonces son visibles a la vez, en el HTML estático: «Cartografía informativa,
    no es un deslinde» e «Indicios a verificar, no ilegalidades» en un `<div class="pc-avisos"
    role="note">` superpuesto al mapa, hermano de `#mapa` (no dentro), fuera de todo
    `<details>`, sin `hidden` y sin una regla de `estilo.css` que lo oculte; el aviso de `NOTICE`
    del panel (#85 CA5); y la atribución de PNOA y de cada capa activa en el control de
    atribución, puesto por `crearMapa` antes de pedir ninguna tesela (#85 CA4). `estilo.css` no
    oculta `.leaflet-control-attribution` en ningún tamaño de pantalla y le da `color:
    var(--color-fg)` (texto de 13 px: nunca `--color-muted`, guía)."""
    raiz = _arbol()
    avisos = [n for n in _buscar(raiz, "div", "pc-avisos")]
    assert len(avisos) == 1
    div = avisos[0]
    assert div.attrs.get("role") == "note"
    mapa = _por_id(raiz, "mapa")
    assert div.padre is mapa.padre and div is not mapa and mapa not in div.ancestros()
    assert mapa.padre is not None and "pc-mapa" in mapa.padre.clases()
    for nodo in [div, *div.ancestros()]:
        assert nodo.tag != "details" and "hidden" not in nodo.attrs
    texto = div.contenido()
    assert "Cartografía informativa, no es un deslinde" in texto
    assert "Indicios a verificar, no ilegalidades" in texto
    # El aviso del panel (NOTICE) sigue en el HTML estático.
    notice = re.search(r"Aviso obligatorio: es (.+?)\.\n", NOTICE.read_text(encoding="utf-8"))
    assert notice is not None
    panel = _buscar(raiz, "aside")[0]
    assert notice.group(1) in panel.contenido()
    # Ninguna regla oculta los avisos ni la atribución, en ningún tamaño.
    for selector, decl in _reglas():
        partes = [s.strip() for s in selector.split(",")]
        if any(
            p.startswith((".pc-avisos", ".pc-aviso", ".leaflet-control-attribution"))
            or p.endswith(".leaflet-control-attribution")
            for p in partes
        ):
            assert decl.get("display") != "none", selector
            assert decl.get("visibility") not in ("hidden", "collapse"), selector
            assert decl.get("opacity") != "0", selector
    css = _sin_comentarios(ESTILO.read_text(encoding="utf-8"))
    assert not re.search(r"leaflet-control-attribution[^{]*\{[^}]*display\s*:\s*none", css)
    atrib = _declaraciones_de(".leaflet-container .leaflet-control-attribution")
    assert atrib["color"] == "var(--color-fg)"
    assert "muted" not in " ".join(atrib.values())
    # La atribución la pone crearMapa antes de pedir teselas (#85 CA4).
    assert_node_tests_pass("^CA4:", tmp_path, minimum=4)


# --- CA4 -------------------------------------------------------------------------------------


def test_ca4_estados_de_capa_carga_vacia_error(tmp_path: Path) -> None:
    """CA4. Dado una capa en carga, vacía o con error, cuando el controlador cambia su estado,
    entonces `vista.ponerEstadoCapa` rellena `#estado-<id>` así: en carga, una barra
    `.pc-progreso` (`aria-hidden`) y el texto `cargando…`; vacía, el texto de `config.js` (`sin
    trazados…` o `sin indicios publicados`); con error, el texto `no se pudo cargar`, sin barra.
    Siempre con `data-estado` y con `textContent`, que da exactamente el texto de `config.js`
    (así siguen valiendo los tests de #85 y #95). Con el L falso, el error de una capa deja las
    otras dos dibujadas y en `ok`, y el aviso de mapa base no disponible sigue funcionando (#85
    CA10)."""
    vista = (SITE / "vista.js").read_text(encoding="utf-8")
    assert "innerHTML" not in vista
    assert_node_tests_pass("^H166 CA4:", tmp_path, minimum=3)
    assert_node_tests_pass("^CA10:", tmp_path, minimum=2)


# --- CA5 -------------------------------------------------------------------------------------


def test_ca5_sin_rojo_ni_colores_literales() -> None:
    """CA5. Dado `estilo.css`, cuando se revisa, entonces no hay rojo ni variable `--error`:
    `#mensaje` y `[data-estado="error"]` usan `--color-nota-bg`, `--color-nota-fg` y
    `--color-nota-border`. No hay ningún color literal (`#hex`, `rgb(`, `rgba(`, `hsl(`) fuera de
    comentarios: todo sale de `tokens.css`."""
    css = _sin_comentarios(ESTILO.read_text(encoding="utf-8"))
    assert "--error" not in css
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", css)
    for selector in (".mensaje:not(:empty)", '.pc-capa__estado[data-estado="error"]'):
        decl = _regla_exacta(selector)
        usados = " ".join(decl.values())
        for token in ("--color-nota-bg", "--color-nota-fg", "--color-nota-border"):
            assert f"var({token})" in usados, (selector, token)


# --- CA6 -------------------------------------------------------------------------------------


def _token(valor: str) -> str:
    m = re.search(r"var\((--[\w-]+)\)", valor)
    assert m is not None, valor
    return m.group(1)


def test_ca6_contraste_wcag_de_texto_y_controles() -> None:
    """CA6. Dado `tokens.css` en los tres temas (claro, oscuro por preferencia y
    `data-tema="oscuro"`), cuando se calcula el contraste WCAG, entonces el texto cumple 4,5:1:
    `--color-fg` y `--color-muted` sobre `--color-bg`, `--color-surface` y `--color-surface-2`, y
    `--color-nota-fg` sobre `--color-nota-bg`. Los controles cumplen 3:1 frente a `--color-bg` y
    `--color-surface`: el fondo del `.pc-switch` apagado, el del encendido (`--color-accent`), el
    borde de `.campo select` y `--color-focus`. Los tokens de esos controles se leen de las
    reglas de `estilo.css`, no se fijan en el test. Ninguna regla de `.pc-switch`, `select` o
    `input` usa `--color-line-strong`, y `tokens.css` sigue idéntico al paquete."""
    texto = TOKENS.read_text(encoding="utf-8")
    claro = _variables(_bloque(texto, ":root {"))
    temas = {
        "claro": claro,
        "oscuro": {**claro, **_variables(_bloque(texto, ':root:not([data-tema="claro"])'))},
        "oscuro forzado": {**claro, **_variables(_bloque(texto, ':root[data-tema="oscuro"]'))},
    }
    apagado = _token(_regla_exacta(".pc-switch")["background"])
    encendido = _token(_regla_exacta(".pc-switch:checked")["background"])
    borde = re.search(r"var\((--[\w-]+)\)", _regla_exacta(".campo select")["border"])
    assert borde is not None
    foco = _token(_regla_exacta(".pc-switch:focus-visible")["outline"])
    assert encendido == "--color-accent"
    fallos: list[str] = []
    for tema, v in temas.items():
        for fg in ("--color-fg", "--color-muted"):
            for bg in ("--color-bg", "--color-surface", "--color-surface-2"):
                if _contraste(v[fg], v[bg]) < 4.5:
                    fallos.append(f"{tema}: {fg} sobre {bg}")
        if _contraste(v["--color-nota-fg"], v["--color-nota-bg"]) < 4.5:
            fallos.append(f"{tema}: nota")
        for control in (apagado, encendido, borde.group(1), foco):
            for bg in ("--color-bg", "--color-surface"):
                r = _contraste(v[control], v[bg])
                if r < 3.0:
                    fallos.append(f"{tema}: {control} sobre {bg} = {r:.2f}")
    assert not fallos, fallos
    for selector, decl in _reglas():
        partes = [s.strip() for s in selector.split(",")]
        if any(
            p.startswith((".pc-switch", "select", ".campo select", "input")) for p in partes
        ):
            assert "--color-line-strong" not in " ".join(decl.values()), selector
    assert TOKENS.read_bytes() == TOKENS_PAQUETE.read_bytes()


# --- CA7 -------------------------------------------------------------------------------------


def test_ca7_objetivos_tactiles_foco_y_preferencias_del_sistema() -> None:
    """CA7. Dado `estilo.css`, cuando se revisa, entonces `.pc-capa__fila` y `.campo select`
    tienen `min-height` de al menos `var(--tap)`; ningún selector quita el foco (`outline: none`
    o `0`) salvo si lo sustituye por un `:focus-visible` con `outline`; `.pc-switch:focus-visible`
    tiene `outline` con `--color-focus`; hay un bloque `@media (prefers-reduced-motion: reduce)`
    que anula animaciones y transiciones, y uno `@media (forced-colors: active)` para el
    interruptor."""
    for selector in (".pc-capa__fila", ".campo select"):
        assert _regla_exacta(selector)["min-height"] == "var(--tap)", selector
    for selector, decl in _reglas():
        for propiedad in ("outline", "outline-style", "outline-width"):
            if decl.get(propiedad) in ("none", "0"):
                assert ":focus-visible" in selector, selector
    assert "var(--color-focus)" in _regla_exacta(".pc-switch:focus-visible")["outline"]
    css = _sin_comentarios(ESTILO.read_text(encoding="utf-8"))
    movimiento = _bloque(css, "@media (prefers-reduced-motion: reduce)")
    assert "animation-duration: 0s" in movimiento and "transition-duration: 0s" in movimiento
    colores = _bloque(css, "@media (forced-colors: active)")
    assert ".pc-switch" in colores


# --- CA8 -------------------------------------------------------------------------------------


def test_ca8_todo_el_visor_en_verde() -> None:
    """CA8. Dado el visor entero, cuando se ejecutan `uv run pytest tests/site tests/acceptance`
    y `node --test`, entonces todo sigue en verde. Los tests de #85, #95 y #114 se actualizan
    solo en lo que cambia por el marcado nuevo (clases `.capa` y `.estado-capa` sustituidas por
    `.pc-capa` y `.pc-capa__estado`, `--error` retirado) y no hay red ni recursos de
    terceros."""
    resultado = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/site",
            "tests/acceptance/test_historia_85.py",
            "tests/acceptance/test_historia_95.py",
            "tests/acceptance/test_historia_114.py",
            "tests/acceptance/test_historia_165.py",
            "-q",
            "-p",
            "no:cacheprovider",
            "-m",
            "not integration",
        ],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stdout[-2000:]
    css = ESTILO.read_text(encoding="utf-8")
    for viejo in (".capa ", ".estado-capa", ".muestra-"):
        assert viejo not in css, viejo
    html = INDEX.read_text(encoding="utf-8")
    assert not re.search(r"https?://(?!www\.ign\.es|murcialito|creativecommons|github)", html)
