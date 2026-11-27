"""Historia #165: estilos de capa del sistema de diseño en el mapa (halo, selección, tema).

Un test por criterio. La lógica se prueba en Node (`tests/site/visor.test.mjs`, casos
`H165 CA<n>:`) con `L` falso y el original del sistema de diseño en `node:vm`; aquí van las
comprobaciones estáticas y el lanzamiento de esos casos. Ninguna prueba toca la red.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.site.nodo import SITE, assert_node_tests_pass

pytestmark = pytest.mark.acceptance

VENDOR = SITE / "vendor"
ESTILOS = SITE / "estilos-capas.js"
TOKENS = SITE / "css" / "tokens.css"


def _leer(nombre: str) -> str:
    return (SITE / nombre).read_text(encoding="utf-8")


def test_ca1_estilo_identico_al_del_sistema_de_diseno(tmp_path: Path) -> None:
    """CA1. Dado `site/estilos-capas.js`, cuando se pide `estilo(clave, estado, tema)` para
    `viasPecuarias`, `caminoActual`, `trazadoHistorico`, `indicioBaja`, `indicioMedia` o
    `indicioAlta`, en estado `normal`, `hover` o `seleccionado` y tema `claro` u `oscuro`,
    entonces devuelve `{ halo, linea }` idéntico (`deepStrictEqual`) al que devuelve el `estilo`
    original de `docs/design-system/site/js/estilos-capas.js` ejecutado en `node:vm` con un
    `window` y un `document` falsos. Lo mismo para la tabla `ESTILOS` completa. Una clave, un
    estado o un tema desconocidos lanzan `Error`."""
    assert_node_tests_pass("^H165 CA1:", tmp_path)


def test_ca2_familias_distintas_y_confianza_creciente(tmp_path: Path) -> None:
    """CA2. Dado el estilo `normal` de cada capa, cuando se comparan entre sí, entonces las
    cuatro familias (vías pecuarias, camino actual, trazado histórico, indicio medio) tienen
    pares (`weight`, `dashArray`) distintos dos a dos: banda ancha continua, línea fina
    continua, discontinua y punteada. Los tres niveles de indicio crecen en `weight` y en
    `opacity`, y su hueco del `dashArray` se estrecha (`baja` < `media` < `alta`)."""
    assert_node_tests_pass("^H165 CA2:", tmp_path)


def test_ca3_hover_seleccion_unica_y_halo_de_seleccion(tmp_path: Path) -> None:
    """CA3. Dado un trazado dibujado, cuando pasa a `hover`, entonces la línea y el halo
    engordan y el halo conserva su color. Cuando pasa a `seleccionado`, el halo toma
    `BASE.seleccionHalo[tema]` (`#ffffff` en claro, `#e8ebe8` en oscuro, iguales a
    `--capa-seleccion-halo` de `tokens.css`) y la línea engorda. Con el L falso: pulsar A y
    luego B deja B `seleccionado` y A `normal`, aunque sean de capas distintas. `mouseout` sobre
    el seleccionado no lo devuelve a `normal`, y cerrar su popup sí."""
    assert_node_tests_pass("^H165 CA3:", tmp_path, minimum=2)
    tokens = TOKENS.read_text(encoding="utf-8")
    assert re.search(r"--capa-seleccion-halo:\s*#ffffff", tokens)
    assert re.search(r"--capa-seleccion-halo:\s*#e8ebe8", tokens)


def test_ca4_cada_capa_con_su_clave_y_dos_dibujos(tmp_path: Path) -> None:
    """CA4. Dado el visor con las tres capas del índice, cuando se dibujan, entonces vías
    pecuarias usa `viasPecuarias`, camino actual `caminoActual` e indicios
    `indicioBaja|Media|Alta` según `properties.confianza`. Una confianza ausente o desconocida
    (`null`, `"ALTA"`, sin propiedad) usa `indicioBaja`. Cada feature se dibuja dos veces: el
    halo (`interactive: false`) debajo y la línea encima, en el mismo pane. Pulsar un trazado
    sigue mostrando la ficha de #85 o la de #95, como nodo construido con `textContent` y nunca
    como HTML."""
    assert_node_tests_pass("^H165 CA4:", tmp_path, minimum=3)
    assert not re.search(r"innerHTML|insertAdjacentHTML", _leer("mapa.js"))


def test_ca5_solo_mapa_js_usa_leaflet_y_estilos_es_puro() -> None:
    """CA5. Dado `site/`, cuando se revisan todos sus ficheros salvo `vendor/`, entonces solo
    `mapa.js` referencia `L.`, `L[` o `globalThis.L` (test de #85 CA7). `estilos-capas.js` no
    usa `window`, `document`, `globalThis` ni `matchMedia`, solo exporta con `export` y no deja
    ningún global."""
    patron = re.compile(r"\bL\s*[.\[]|window\.L\b|globalThis\.L\b")
    for fichero in sorted(SITE.rglob("*")):
        if (
            fichero.is_file()
            and fichero.suffix in {".html", ".js", ".mjs", ".css"}
            and VENDOR not in fichero.parents
            and fichero.name != "mapa.js"
        ):
            assert not patron.search(fichero.read_text(encoding="utf-8")), fichero.name
    texto = ESTILOS.read_text(encoding="utf-8")
    for prohibido in ("window", "document", "globalThis", "matchMedia", "import ", "https://"):
        assert prohibido not in texto, prohibido
    # Un módulo ES no crea globales; lo que no puede haber es asignación a uno.
    assert re.search(r"^export (?:const|function) ", texto, re.MULTILINE)
    assert not re.search(r"^\s*(?:self|this|global)\.\w+\s*=", texto, re.MULTILINE)


def test_ca6_exports_congelados_y_copias(tmp_path: Path) -> None:
    """CA6. Dado `estilos-capas.js`, cuando otro módulo lo importa, entonces exporta `BASE`
    (congelado en profundidad), `ESTILOS`, `CLAVES`, `RELLENO`, `estilo`, `estiloTrazado` y
    `temaDe`, con `trazadoHistorico` e `indicioBaja|Media|Alta` probados aunque el visor no
    dibuje el histórico. Mutar lo que devuelve `estilo` no cambia la siguiente llamada."""
    assert_node_tests_pass("^H165 CA6:", tmp_path)


def test_ca7_poligonos_con_contorno_y_relleno_tenue(tmp_path: Path) -> None:
    """CA7. Dado un feature `Polygon` o `MultiPolygon` de vías pecuarias o de indicios, cuando
    se dibuja, entonces el halo es solo contorno (`fill: false`) y la línea es el contorno con
    el estilo de la capa más un relleno del mismo color (`fill: true`, `fillColor` = color de la
    línea, `fillOpacity` = `RELLENO[clave]` en `normal` y `RELLENO[clave] + 0.1` en `hover` y
    `seleccionado`). Un `LineString` o `MultiLineString` de la misma capa se dibuja con
    `fill: false`. Un `MultiPolygon` de dos partes es un solo trazado, con un popup y una
    selección."""
    assert_node_tests_pass("^H165 CA7:", tmp_path)


def test_ca8_orden_de_apilado_por_pane(tmp_path: Path) -> None:
    """CA8. Dado que camino actual termina de cargar antes que vías pecuarias, cuando ambas se
    dibujan, entonces el orden de apilado sigue siendo, de abajo arriba, vías pecuarias <
    camino actual < indicios. Cada capa va en su pane `pc-capa-<id>` con `zIndex` = 400 +
    `orden` de `config.js` (10, 30, 40; el 20 queda para el histórico)."""
    assert_node_tests_pass("^H165 CA8:", tmp_path)


def test_ca9_sin_seleccion_colgada_y_cambio_de_tema(tmp_path: Path) -> None:
    """CA9. Dado un trazado seleccionado, cuando se cambia de municipio (`quitarCapa`),
    entonces no queda selección colgada: el siguiente clic selecciona sin intentar restaurar un
    trazado ya quitado. Y cuando cambia el tema (`ponerTema`), todos los trazados se reestilan
    con la variante del tema nuevo y el seleccionado sigue seleccionado."""
    assert_node_tests_pass("^H165 CA9:", tmp_path)


def test_ca10_tema_lo_resuelve_app_js_y_la_ortofoto_se_atenua(tmp_path: Path) -> None:
    """CA10. Dado `temaDe(forzado, prefiereOscuro)`, cuando `forzado` es `"claro"` u
    `"oscuro"`, entonces gana. Si no, devuelve `"oscuro"` cuando `prefiereOscuro` es verdadero
    y `"claro"` en otro caso. `app.js` es el único fichero JS que lee `data-tema` y
    `prefers-color-scheme`: llama a `temaDe`, pasa el tema a `crearMapa` y, si cambia la
    preferencia del sistema, llama a `mapa.ponerTema`. `estilo.css` aplica
    `filter: var(--map-tiles-filter)` a `#mapa .leaflet-tile-pane`."""
    assert_node_tests_pass("^H165 CA10:", tmp_path, minimum=2)
    for fichero in sorted(SITE.glob("*.js")):
        texto = fichero.read_text(encoding="utf-8")
        lee = bool(re.search(r"data-tema|prefers-color-scheme", texto))
        assert lee == (fichero.name == "app.js"), fichero.name
    app = _leer("app.js")
    assert "temaDe(" in app
    assert re.search(r"tema:\s*temaActual\(\)", app)
    assert re.search(r"addEventListener\?\.\(\s*\"change\".*?ponerTema", app, re.DOTALL)
    css = _leer("estilo.css")
    assert re.search(
        r"#mapa\s+\.leaflet-tile-pane\s*\{[^}]*filter:\s*var\(--map-tiles-filter\)", css
    )


def test_ca11_config_sin_colores_y_muestras_con_tokens(tmp_path: Path) -> None:
    """CA11. Dado `config.js`, cuando se lee, entonces ninguna capa lleva colores (no queda
    ningún `#rrggbb` ni objeto de estilo de Leaflet). Cada capa lleva `estilo: { clave }` o
    `estilo: { porPropiedad, claves, defecto }` y `orden`, y toda clave que nombra está en
    `CLAVES`. `estilo.css` ya no tiene colores hexadecimales en las muestras de capa: usan
    `--capa-*`."""
    assert_node_tests_pass("^H165 CA11:", tmp_path)
    assert not re.search(r"#[0-9a-fA-F]{6}\b", _leer("config.js"))
    muestras = re.findall(r"^\.muestra-[\w_]+\s*\{[^}]*\}", _leer("estilo.css"), re.MULTILINE)
    assert len(muestras) == 3
    for regla in muestras:
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", regla), regla
        assert "var(--capa-" in regla, regla


def test_ca12_el_visor_entero_sigue_en_verde(tmp_path: Path) -> None:
    """CA12. Dado el visor entero, cuando se ejecutan `uv run pytest tests/site
    tests/acceptance` y `node --test`, entonces todo sigue en verde. Los tests de #85 y #95 se
    actualizan solo donde cambia la interfaz de `mapa.js` (`estilo` → `clave`/`claveDe`), y no
    hay red ni recursos de terceros."""
    assert_node_tests_pass(".*", tmp_path, minimum=50)
    for fichero in sorted(SITE.glob("*.js")):
        assert "fetch(" not in fichero.read_text(encoding="utf-8") or fichero.name == "app.js"
    assert not re.search(r"https?://", ESTILOS.read_text(encoding="utf-8"))
