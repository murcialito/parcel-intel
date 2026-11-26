"""Historia #120: ADR de las imágenes de comparación de un tramo (ventanas, vuelos, caché y
publicación).

Es una historia de documentación: los tests leen el ADR nuevo de `docs/adr/` (buscado por
sufijo, no por número, lección de #43) y `REGISTRY.md`. No llaman a red ni importan código que
todavía no existe (las entidades, el port y el adapter los implementan las historias hijas).
"""

import math
import re
from pathlib import Path

import pytest

from parcel_intel.domain.public_card import BANNED_WORDS, banned_words_in

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
ADR_DIR = REPO / "docs" / "adr"
REGISTRY = REPO / "src" / "parcel_intel" / "sources" / "REGISTRY.md"
SUFIJO = "-imagenes-de-comparacion-ventanas-del-tramo-cache-pnoa-y-enlaces-wms.md"


def _adr_path() -> Path:
    adrs = sorted(ADR_DIR.glob(f"*{SUFIJO}"))
    assert len(adrs) == 1, "debe existir exactamente un ADR de imágenes de comparación por sufijo"
    return adrs[0]


def _adr() -> str:
    return _adr_path().read_text(encoding="utf-8")


def _seccion(titulo: str, texto: str | None = None) -> str:
    """Texto de una sección `### titulo` (título incluido), hasta el siguiente `### ` o `## `."""
    lineas = (_adr() if texto is None else texto).splitlines()
    inicio = next(i for i, linea in enumerate(lineas) if linea.startswith(f"### {titulo}"))
    resto = lineas[inicio + 1 :]
    fin = next(
        (i for i, linea in enumerate(resto) if linea.startswith("### ") or linea.startswith("## ")),
        len(resto),
    )
    return "\n".join([lineas[inicio], *resto[:fin]])


def _plano(texto: str) -> str:
    """El texto con los saltos de línea y espacios repetidos reducidos a un espacio."""
    return " ".join(texto.split())


def _constante(nombre: str) -> int:
    match = re.search(rf"`{nombre} = (\d+)`", _adr())
    assert match is not None, nombre
    return int(match.group(1))


def _filas(seccion: str) -> list[list[str]]:
    """Filas de datos de las tablas de una sección (sin cabecera ni separador)."""
    filas = []
    for linea in seccion.splitlines():
        if linea.startswith("| ") and "---" not in linea:
            filas.append([c.strip() for c in linea.strip().strip("|").split("|")])
    return filas


def test_ca1_formato_tamano_margen_y_bytes_medidos() -> None:
    """Dado el ADR, cuando se lee, entonces fija el formato de imagen y su calidad, el tamaño en
    píxeles y el margen alrededor del tramo, con una estimación en bytes por imagen medida sobre
    una ortofoto real del ámbito (JPEG del WMS ya verificado)."""
    formato = _plano(_seccion("1. Formato"))
    assert "**JPEG tal como lo sirve el WMS**, sin recodificar" in formato
    assert "la calidad la fija el IGN" in formato
    assert "**Resolución fija de 0,5 m por píxel** (`GROUND_RESOLUTION_M`)" in formato
    assert "`STRETCH_MARGIN_M = 50`" in formato
    assert "`MIN_WINDOW_SIDE_M = 224`" in formato and "`MAX_WINDOW_SIDE_M = 512`" in formato
    assert "entre 448 y 1024 píxeles por lado" in formato
    assert "**Peso estimado por imagen**: ~0,23 bytes por píxel (medido: 0,134–0,262)" in formato
    assert "~47 kB" in formato

    # La medida sale de peticiones reales del ámbito, citadas en el contexto.
    contexto = _adr().split("## Decisión", 1)[0]
    assert "Verificación real del 2026-11-26" in contexto
    assert "| `PNOA2023` (histórico) | 243.158 |" in contexto
    # 243.158 bytes en 1024 × 1024 píxeles es ~0,23 bytes por píxel.
    assert round(243_158 / (1024 * 1024), 2) == 0.23


def test_ca2_anos_por_tramo_hueco_declarado_y_sin_cobertura() -> None:
    """Dado el ADR, cuando se lee, entonces fija el número máximo de años por tramo, con la regla
    para elegirlos (actual más los vuelos disponibles; el hueco 1957-1997 se declara, no se
    rellena) y qué hace cuando un vuelo no cubre el tramo."""
    vuelos = _seccion("3. Vuelos")
    plano = _plano(vuelos)
    assert "máximo 5 imágenes por ventana y 20 por tramo" in plano

    franjas = [fila[0] for fila in _filas(vuelos) if fila[0].startswith("`")]
    assert franjas == ["`1956-1957`", "`1997-2003`", "`2006-2011`", "`2014-2020`", "`reciente`"]
    assert len(franjas) == 5
    assert "`2023` (`RECENT_FLIGHT_YEAR`)" in vuelos

    assert "**Hueco declarado**" in plano
    assert "de 1957 a 1997 no hay ortofoto" in plano
    assert "no se rellenan con otra cosa" in plano

    assert "**Vuelo que no cubre**" in plano
    assert "`OrthophotoNotCoveredError`" in plano
    assert "La franja prueba el siguiente vuelo de su lista" in plano
    assert "motivo `sin_cobertura`" in plano
    assert "Nunca se toma un vuelo de otra franja." in plano
    assert "motivo `fallo`" in plano


def test_ca3_ficheros_frente_a_enlaces_con_coste_peso_y_tope() -> None:
    """Dado el ADR, cuando se lee, entonces compara publicar las imágenes como ficheros estáticos
    frente a enlaces o WMS en el visor, con coste recurrente estimado, peso añadido al sitio por
    tramo y por municipio, y el tope (ver #86 para el presupuesto de peso del sitio), y elige una
    opción."""
    publicacion = _seccion("5. Publicación")
    cabecera = (
        "| | Ficheros JPEG en `site/` | Enlaces al WMS con manifiesto (elegida) "
        "| Capa WMS en el mapa |"
    )
    assert cabecera in publicacion

    filas = {fila[0]: fila[1:] for fila in _filas(publicacion) if fila[0]}
    for partida in (
        "Peso por tramo (1–4 ventanas)",
        "Por municipio (supuesto: 50 tramos, 1,5 ventanas de media)",
        "Coste recurrente",
    ):
        assert partida in filas, partida
        assert len(filas[partida]) == 3, partida
    assert all("0 €" in celda for celda in filas["Coste recurrente"])
    assert "40 MB de #86" in filas["Por municipio (supuesto: 50 tramos, 1,5 ventanas de media)"][0]

    plano = _plano(publicacion)
    assert "**Se elige enlaces con manifiesto.**" in plano
    assert "**Topes**: `MAX_WINDOWS_PER_STRETCH = 4`; `MAX_WINDOWS_PER_MUNICIPALITY = 400`" in plano
    assert "≤ 3.000.000 bytes (umbral por fichero de #86)" in plano


def test_ca4_trazado_superpuesto_en_la_vista_sin_libreria_nueva() -> None:
    """Dado el ADR, cuando se lee, entonces decide dónde se superpone el trazado (en la imagen
    generada o en el visor) y, si exige una librería nueva, la nombra con su motivo; la
    dependencia vive solo en `adapters/`."""
    superposicion = _plano(_seccion("6. Superposición"))
    assert "### 6. Superposición del trazado: en la vista, no en la imagen" in superposicion
    assert "Se dibuja como SVG encima del `<img>`" in superposicion
    assert "Ninguna librería nueva" in superposicion
    assert "nunca con `innerHTML`" in superposicion
    assert "vive en `adapters/`" in superposicion
    assert "**Pillow para quemar el trazado**" in _seccion("Alternativas descartadas")


def test_ca5_cache_cruda_cierra_adr_0006() -> None:
    """Dado el ADR, cuando se lee, entonces decide la caché cruda de ortofotos en `data/`
    (clave, inmutabilidad, procedencia) y cierra el riesgo del ADR 0006 §6."""
    cache = _seccion("4. Caché cruda")
    assert cache.startswith("### 4. Caché cruda (cierra el ADR 0006 §6)")
    plano = _plano(cache)
    assert "`CachedRawFetcher` (#34)" in plano
    assert "`data/raw/`" in plano
    assert "clave = sha256 de la URL canónica" in plano
    assert "cuerpo inmutable" in plano
    assert "sidecar con URL, parámetros, fecha de la descarga real y sha256" in plano
    assert "una respuesta de error no entra nunca en la caché" in plano
    assert "Cierra el riesgo del ADR 0006 §6." in _adr()


def test_ca6_ortofoto_de_una_linea_multiparte_y_degenerados() -> None:
    """Dado el ADR, cuando se lee, entonces decide cómo se pide la ortofoto de una línea (con o
    sin cambio de port), con el caso multiparte y el caso de línea vacía o de un punto
    cubiertos."""
    ventanas = _seccion("2. Ventanas")
    plano = _plano(ventanas)
    assert "Sin tocar `OrthophotoPort`." in plano
    assert "`OrthophotoWindowPort.get_orthophoto_window(" in plano
    assert "**en orden, todas**" in plano
    assert "Un trozo puede reunir puntos de dos partes cercanas." in plano
    assert "`DegenerateStretchError` antes de pedir nada" in plano

    filas = _filas(ventanas)
    assert any(fila[0].startswith("Multiparte") for fila in filas)
    degenerados = [fila for fila in filas if fila[0].startswith("`lines=()`")]
    assert len(degenerados) == 1
    assert "una parte de 1 punto" in degenerados[0][0]
    assert "2 puntos iguales" in degenerados[0][0]
    assert degenerados[0][1] == "`DegenerateStretchError`"


def test_ca7_procedencia_por_imagen_sin_titularidad() -> None:
    """Dado el ADR, cuando se lee, entonces fija la procedencia por imagen (año de vuelo,
    resolución, fuente, URL, fecha de descarga, licencia, atribución con «Obra derivada de»), y
    que ninguna imagen ni su nombre de fichero lleva referencia catastral, nombre de finca ni
    titularidad."""
    procedencia = _plano(_seccion("7. Procedencia"))
    for campo in (
        "franja, vuelo, periodo, resolución",
        "atribución con «Obra derivada de»",
        "sha256, bytes",
        "fuente `pnoa-historico`",
        "URL canónica del `GetMap`",
        "fecha de la descarga real del sidecar",
        "licencia `CC BY 4.0`",
    ):
        assert campo in procedencia, campo
    assert "Ni la imagen, ni la caché (nombrada por sha256), ni el manifiesto" in procedencia
    assert "llevan referencia catastral, nombre de finca" in procedencia
    assert "id opaco de 16 hexadecimales" in procedencia

    assert BANNED_WORDS
    assert banned_words_in(_adr()) == ()


def test_ca8_historias_derivadas_en_orden_y_reutilizacion_en_106() -> None:
    """Dado el ADR, cuando se lee, entonces enumera las historias de desarrollo que se derivan y
    su orden, y confirma que #106 reutiliza esta pieza sin duplicarla."""
    historias = _seccion("8. Historias")
    filas = _filas(historias)
    assert filas[0] == ["#", "Historia", "Talla", "Depende de"]
    datos = filas[1:]
    assert [fila[0] for fila in datos] == ["1", "2", "3", "—"]
    assert datos[0][1].startswith("#121:")
    assert "`PnoaWindowAdapter`" in datos[1][1]
    assert datos[2][1].startswith("#122:")
    assert "#103" in datos[3][1]
    assert [fila[3] for fila in datos[:3]] == ["este ADR", "1", "1 y 2"]
    assert "**#106 reutiliza esta pieza sin duplicarla**" in historias
    assert "no crea otro cliente ni otra política" in _plano(historias)


def test_ca9_adr_con_el_siguiente_numero_libre() -> None:
    """Dado el cambio, entonces `uv run lint-imports`, `uv run mypy`, `uv run ruff check .` y
    `uv run pytest` siguen en verde, y `docs/adr/` contiene el ADR con el siguiente número
    libre.

    Los cuatro comandos se ejecutan a mano y se anotan en la PR. Aquí se fija que hay un único
    ADR con el sufijo, que su número no repite el de otro ADR y que es posterior al 0041."""
    ruta = _adr_path()
    numero = ruta.name.split("-", 1)[0]
    assert re.fullmatch(r"\d{4}", numero)
    assert int(numero) >= 42
    assert _adr().startswith(f"# ADR {numero} — Imágenes de comparación")
    numeros = [p.name.split("-", 1)[0] for p in ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")]
    assert numeros.count(numero) == 1


# --- CA10: oráculos de ventanas -------------------------------------------------------------

X0, Y0 = 470000, 4440000
Punto = tuple[float, float]

# Tramos de la tabla de oráculos del ADR §2, en el orden de sus filas.
_TRAMOS: list[tuple[tuple[Punto, ...], ...]] = [
    (((X0, Y0), (X0 + 80, Y0)),),
    (((X0, Y0), (X0 + 300, Y0)),),
    (((X0, Y0), (X0 + 1000, Y0)),),
    (((X0, Y0), (X0 + 2000, Y0)),),
    (((X0, Y0), (X0 + 50, Y0)), ((X0 + 3000, Y0), (X0 + 3050, Y0))),
]
_DEGENERADOS: list[tuple[tuple[Punto, ...], ...]] = [
    (),
    (((X0, Y0),),),
    (((X0, Y0), (X0, Y0)),),
]


class _Degenerado(Exception):
    pass


def _ventanas_de_referencia(partes: tuple[tuple[Punto, ...], ...]) -> list[tuple[int, ...]] | None:
    """Recalculo independiente de §2 con las constantes del ADR. `None` = tramo demasiado
    largo. Solo para este test: la implementación es de #121."""
    paso = _constante("DENSIFY_STEP_M")
    margen = _constante("STRETCH_MARGIN_M")
    escalon = _constante("WINDOW_SIDE_STEP_M")
    minimo = _constante("MIN_WINDOW_SIDE_M")
    maximo = _constante("MAX_WINDOW_SIDE_M")
    tope = _constante("MAX_WINDOWS_PER_STRETCH")
    limite = maximo - 2 * margen - 1
    assert limite == 411

    puntos: list[Punto] = []
    for parte in partes:
        if len(parte) < 2:
            continue
        densa: list[Punto] = [parte[0]]
        for (ax, ay), (bx, by) in zip(parte, parte[1:]):
            largo = math.hypot(bx - ax, by - ay)
            if largo == 0:
                continue
            n = math.ceil(largo / paso)
            densa.extend((ax + (bx - ax) * k / n, ay + (by - ay) * k / n) for k in range(1, n + 1))
        if len(densa) > 1:
            puntos.extend(densa)
    if not puntos:
        raise _Degenerado

    def extension(trozo: list[Punto]) -> float:
        xs = [p[0] for p in trozo]
        ys = [p[1] for p in trozo]
        return max(max(xs) - min(xs), max(ys) - min(ys))

    trozos: list[list[Punto]] = [[puntos[0]]]
    for punto in puntos[1:]:
        if extension([*trozos[-1], punto]) > limite:
            trozos.append([punto])
        else:
            trozos[-1].append(punto)
    if len(trozos) > tope:
        return None

    ventanas = []
    for trozo in trozos:
        xs = [p[0] for p in trozo]
        ys = [p[1] for p in trozo]
        cx = math.floor((min(xs) + max(xs)) / 2 + 0.5)
        cy = math.floor((min(ys) + max(ys)) / 2 + 0.5)
        lado = max(minimo, math.ceil((extension(trozo) + 2 * margen + 1) / escalon) * escalon)
        ventanas.append((cx - lado // 2, cy - lado // 2, cx + lado // 2, cy + lado // 2))
    return ventanas


def _oraculos() -> list[tuple[list[tuple[int, ...]], list[int]]]:
    """Filas de la tabla de oráculos: (ventanas, píxeles por lado), sin los degenerados."""
    filas = [f for f in _filas(_seccion("2. Ventanas")) if f[0] != "Tramo"]
    resultado = []
    for tramo, ventanas, pixeles in filas:
        if tramo.startswith("`lines=()`"):
            continue
        bboxes = [
            tuple(int(v) for v in m)
            for m in re.findall(r"\((\d+), (\d+), (\d+), (\d+)\)", ventanas)
        ]
        lados_px = [int(v) for v in re.findall(r"\d+", pixeles.split(";")[0])]
        resultado.append((bboxes, lados_px))
    return resultado


def test_ca10_tabla_de_oraculos_coherente_con_las_constantes() -> None:
    """Dado el ADR, cuando se lee su §2, entonces trae la tabla de oráculos de ventanas (tramos
    de 80 m, 300 m, 1000 m, 2000 m, multiparte separado y degenerados) con los bbox enteros y
    los píxeles exactos, y un test comprueba que los bbox de la tabla son coherentes con las
    constantes del propio ADR (lado múltiplo de 32 m entre 224 y 512, `ancho_px = lado / 0,5`,
    tramo de 80 m con extremos en los píxeles `(144.0, 224.0)` y `(304.0, 224.0)`)."""
    escalon = _constante("WINDOW_SIDE_STEP_M")
    minimo = _constante("MIN_WINDOW_SIDE_M")
    maximo = _constante("MAX_WINDOW_SIDE_M")
    assert (escalon, minimo, maximo) == (32, 224, 512)
    resolucion = 0.5  # `GROUND_RESOLUTION_M`, «0,5 m por píxel» en §1

    oraculos = _oraculos()
    assert len(oraculos) == len(_TRAMOS) == 5

    for (bboxes, lados_px), partes in zip(oraculos, _TRAMOS, strict=True):
        assert len(bboxes) == len(lados_px)
        for (min_x, min_y, max_x, max_y), px in zip(bboxes, lados_px, strict=True):
            lado = max_x - min_x
            assert lado == max_y - min_y
            assert lado % escalon == 0
            assert minimo <= lado <= maximo
            assert px == lado / resolucion
        if len(bboxes) == 1:
            (min_x, min_y, max_x, max_y) = bboxes[0]
            xs = [x for parte in partes for x, _ in parte]
            ys = [y for parte in partes for _, y in parte]
            assert abs((min_x + max_x) / 2 - (min(xs) + max(xs)) / 2) <= 0.5
            assert abs((min_y + max_y) / 2 - (min(ys) + max(ys)) / 2) <= 0.5

        # Recalculo independiente con el algoritmo y las constantes del propio ADR.
        referencia = _ventanas_de_referencia(partes)
        assert (referencia or []) == bboxes

    # Tramo de 2000 m: más de `MAX_WINDOWS_PER_STRETCH` trozos, ninguna ventana.
    assert _ventanas_de_referencia(_TRAMOS[3]) is None
    assert "5 trozos > 4: `tramo_demasiado_largo`" in _seccion("2. Ventanas")

    # Extremos del tramo de 80 m en píxeles de su ventana (`px = (x − min_x) / 0,5`,
    # `py = (max_y − y) / 0,5`).
    (min_x, _, _, max_y) = oraculos[0][0][0]
    extremos = [
        (round((x - min_x) / resolucion, 1), round((max_y - y) / resolucion, 1))
        for x, y in _TRAMOS[0][0]
    ]
    assert extremos == [(144.0, 224.0), (304.0, 224.0)]
    assert "extremos del trazado en (144.0, 224.0) y (304.0, 224.0)" in _seccion("2. Ventanas")

    for partes in _DEGENERADOS:
        with pytest.raises(_Degenerado):
            _ventanas_de_referencia(partes)


# --- CA11: REGISTRY.md ----------------------------------------------------------------------

# Filas de PNOA de la tabla resumen de licencias, tal como estaban antes de esta historia.
_FILAS_RESUMEN_PNOA = (
    "| PNOA ortofoto actual (IGN) | 0,25 m | Vuelo de **julio de 2023** (`confirmado`, tres "
    "puntos del ámbito). Madrid se vuela cada 3 años: 2011, 2014, 2017, 2020, 2023 → el "
    "siguiente debería ser 2026 (`asumido`) | CC BY 4.0 (`confirmado`) | **Publicar**, con "
    "atribución |",
    "| PNOA histórico (IGN) | 0,50 m (1956-57, SIGPAC 1997-2003, 2006, 2009); 0,25 m "
    "(2011-2023); 1 m (OLISTAT) | Vuelos sobre Colmenar: **1956-57**, 1997-98, 1997-2003, "
    "2006, 2009, 2011, 2014, 2017, 2020, 2023 (`confirmado`). Interministerial (1973-86) y "
    "Nacional (1981-86): **sin imagen** en el punto de prueba | CC BY 4.0 (`confirmado`) | "
    "**Publicar**, con atribución |",
)


def _atribuciones_del_adr() -> list[str]:
    """Cadenas de atribución del SCNE de la tabla de franjas del ADR §3, con `<año>`
    sustituido por cada vuelo de su fila."""
    atribuciones = []
    for fila in _filas(_seccion("3. Vuelos")):
        if not fila[0].startswith("`"):
            continue
        anos = re.findall(r"`(\d{4})`", fila[1])
        for cadena in re.findall(r"`([^`]*CC-BY 4\.0[^`]*)`", fila[3]):
            if "<año>" in cadena:
                atribuciones.extend(cadena.replace("<año>", ano) for ano in anos)
            else:
                atribuciones.append(cadena)
    return atribuciones


def test_ca11_registry_peticiones_reales_atribuciones_y_resumen_intacto() -> None:
    """Dado `REGISTRY.md`, cuando se lee, entonces tiene una subsección nueva de verificación de
    las imágenes de comparación con las peticiones reales del 2026-11-26 (URL, tamaño en bytes y
    sha256 donde se anotó), las atribuciones literales del SCNE de cada vuelo usado (incluida la
    del AMS, que es del Centro Geográfico del Ejército y no del IGN), las cabeceras CORS y de
    caché y los tamaños de las respuestas sin cobertura; y la **tabla resumen de licencias no
    cambia** (para no romper la coherencia con `NOTICE` de la historia #43)."""
    registro = REGISTRY.read_text(encoding="utf-8")
    seccion = _seccion("Imágenes de comparación (historia #120", registro)
    plano = _plano(seccion)

    assert "Peticiones reales del 2026-11-26" in plano
    assert (
        "`https://www.ign.es/wms/pnoa-historico?bbox=467344%2C4441744%2C467856%2C4442256"
        "&crs=EPSG%3A25830&format=image%2Fjpeg&height=1024&layers=PNOA2023&request=GetMap"
        "&service=WMS&styles=&version=1.3.0&width=1024`"
    ) in plano
    assert "| 243.158 | `a68b31370c9c6ab19329be1a712136698930262b824a823a29bbf54c88ea621b`" in plano
    for capa in ("PNOA2017", "PNOA2009", "SIGPAC", "OLISTAT", "AMS_1956-1957", "PNOA2010"):
        assert f"`pnoa-historico` `{capa}`" in plano, capa

    # Cabeceras CORS y de caché.
    assert "`access-control-allow-origin: *`" in plano
    assert "`cache-control: max-age=31536000`" in plano

    # Respuestas sin cobertura: imagen blanca, sin error, con su tamaño.
    assert "**Respuestas sin cobertura**" in plano
    assert "6.427 bytes" in plano and "1.819 bytes" in plano

    # Atribuciones literales del SCNE de cada vuelo que usa el ADR.
    atribuciones = _atribuciones_del_adr()
    assert "Orto-AMS 1956-1957 CC-BY 4.0 ejercito.defensa.gob.es" in atribuciones
    assert "Orto-SIGPAC 1997-2003 CC-BY 4.0 scne.es" in atribuciones
    assert "Orto-OLISTAT 1997-1999 CC-BY 4.0 scne.es" in atribuciones
    assert "PNOA 2023 CC-BY 4.0 scne.es" in atribuciones
    # AMS + SIGPAC y OLISTAT + tres de 2006-2011 + tres de 2014-2020 + 2023.
    assert len(atribuciones) == 1 + 2 + 3 + 3 + 1
    for cadena in atribuciones:
        assert f"`{cadena}`" in plano, cadena
    assert "**el AMS no es del IGN**" in plano
    assert "Centro Geográfico del Ejército de Tierra" in plano

    # La tabla resumen de licencias no cambia.
    for fila in _FILAS_RESUMEN_PNOA:
        assert fila in registro.splitlines(), fila[:40]
