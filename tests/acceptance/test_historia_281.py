"""Historia #281: leer en el BOE las órdenes de clasificación de Chinchón, Villarejo de Salvanés
y Villaconejos.

Tests de documentación sobre ficheros locales (fixtures y REGISTRY.md). No llaman a red.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "src" / "parcel_intel" / "sources" / "REGISTRY.md"
FIXTURES = REPO / "tests" / "fixtures" / "caminos"

ENCABEZADO = "### Órdenes de clasificación leídas en el BOE — historia #281"
CABECERA_CLASIFICACION = "| Municipio | INE | Orden de clasificación | Estado |"
DISPOSICIONES = (
    "BOE-A-1974-44784",
    "BOE-A-1969-49149",
    "BOE-A-1974-44786",
    "BOE-A-1972-46448",
)
MUNICIPIOS_281 = {
    "Chinchón": "BOE-A-1974-44784",
    "Villarejo de Salvanés": "BOE-A-1969-49149",
    "Villaconejos": "BOE-A-1972-46448",
}
OTROS = ("Colmenar de Oreja", "Aranjuez", "Belmonte de Tajo", "Valdelaguna")


def _texto() -> str:
    return REGISTRY.read_text(encoding="utf-8")


def _seccion() -> str:
    texto = _texto()
    inicio = texto.index(ENCABEZADO)
    fines = [texto.find(marca, inicio + 5) for marca in ("\n### ",)]
    fines = [fin for fin in fines if fin != -1]
    return texto[inicio : min(fines)] if fines else texto[inicio:]


def _celdas(linea: str) -> list[str]:
    return [celda.strip() for celda in linea.strip().strip("|").split("|")]


def _filas_clasificacion() -> dict[str, list[str]]:
    lineas = _texto().splitlines()
    inicio = lineas.index(CABECERA_CLASIFICACION)
    filas: dict[str, list[str]] = {}
    for linea in lineas[inicio + 2 :]:
        if not linea.startswith("|"):
            break
        celdas = _celdas(linea)
        if len(celdas) == 4:
            filas[celdas[0]] = celdas
    return filas


def _subseccion(titulo: str) -> str:
    seccion = _seccion()
    inicio = seccion.index(titulo)
    fin = seccion.find("\n#### ", inicio + 5)
    return seccion[inicio:] if fin == -1 else seccion[inicio:fin]


def test_ca1_un_pdf_por_disposicion() -> None:
    """Dado el listado de las cuatro disposiciones (BOE-A-1974-44784, BOE-A-1969-49149,
    BOE-A-1974-44786, BOE-A-1972-46448), cuando se consulta `tests/fixtures/caminos/`, entonces
    hay un PDF grabado por disposición, no vacío, que empieza por `%PDF`, con nombre que incluye
    el identificador BOE."""
    for identificador in DISPOSICIONES:
        pdfs = [p for p in FIXTURES.glob("*.pdf") if identificador in p.name]
        assert len(pdfs) == 1, identificador
        datos = pdfs[0].read_bytes()
        assert len(datos) > 0, identificador
        assert datos.startswith(b"%PDF"), identificador


def test_ca2_municipios_dejan_de_estar_bloqueados() -> None:
    """Dado `REGISTRY.md`, cuando se lee la sección «Vías pecuarias — clasificación y deslinde
    por municipio», entonces Chinchón, Villarejo de Salvanés y Villaconejos dejan de estar
    `bloqueado` y cada uno enlaza su orden con identificador BOE, fecha de la orden, URL de la
    ficha y URL del PDF, fecha de descarga y estado `confirmado` o `asumido`; los otros cuatro
    municipios no pasan a `confirmado`/`asumido` (se tratan en otra hija)."""
    filas = _filas_clasificacion()
    for municipio, identificador in MUNICIPIOS_281.items():
        fila = filas[municipio]
        assert "bloqueado" not in fila[3], municipio
        assert fila[3] in ("`confirmado`", "`asumido`"), municipio
        assert identificador in fila[2], municipio
        assert re.search(r"\d{2}/\d{2}/\d{4}", fila[2]), municipio
    seccion = _seccion()
    for identificador in DISPOSICIONES:
        assert f"https://www.boe.es/buscar/doc.php?id={identificador}" in seccion
        assert re.search(
            rf"https://www\.boe\.es/boe/dias/\d{{4}}/\d{{2}}/\d{{2}}/pdfs/\S+\.pdf[^\n]*"
            rf"`boe_{identificador}\.pdf`",
            seccion,
        ), identificador
    assert re.search(r"\d{4}-\d{2}-\d{2} \(BOE", seccion)
    assert "2026-11-27" in seccion
    for municipio in OTROS:
        estado = _filas_clasificacion()[municipio][3]
        assert estado not in ("`confirmado`", "`asumido`"), municipio


def test_ca3_licencia_citada_del_documento_primario() -> None:
    """Dado el registro, cuando se busca la licencia, entonces consta la condición de
    reutilización del BOE citada del documento primario (aviso legal de `boe.es`, con su URL
    leída en esta historia) y no una suposición."""
    seccion = _seccion()
    assert "https://www.boe.es/informacion/aviso_legal/index.php" in seccion
    assert "Condiciones de reutilización" in seccion
    assert "fines comerciales y no comerciales" in seccion
    assert "Basado en datos de la Agencia Estatal Boletín Oficial del Estado" in seccion


def test_ca4_tablas_de_vias_por_orden() -> None:
    """Dado cada orden, cuando se lee su sección en `REGISTRY.md`, entonces lista una tabla con
    una fila por vía: nombre, clase, anchura tal como figura en la orden, tramo o descripción y
    la frase de deslinde marcando qué vías afecta. Chinchón recoge sus 10 vías."""
    chinchon = _subseccion("#### Chinchón")
    filas = [
        _celdas(linea)
        for linea in chinchon.splitlines()
        if re.match(r"\| \d+ \|", linea)
    ]
    assert len(filas) == 10
    assert [fila[0] for fila in filas] == [str(n) for n in range(1, 11)]
    esperadas = {
        "Cañada Galiana": ("cañada", "37,61", "75,22"),
        "Cordel llamado de La Julia": ("cordel", "37,61"),
        "Vereda de La Blanca": ("vereda", "6,69", "20,89"),
        "Vereda de La Carcabilla y Mojón Alto": ("vereda", "20,89"),
        "Vereda de Molincaldo": ("vereda", "20,89"),
        "Vereda del Rosario, Rostro de Valquegigoso y Valladares": ("vereda", "20,89"),
        "Vereda de La Cuesta del Gramoso": ("vereda", "20,89"),
        "Vereda de Valdelazarza": ("vereda", "20,89"),
        "Colada del Puente de Tablas o del Quiñón": ("colada", "6,69"),
        "Colada del Serranillo": ("colada", "12 m"),
    }
    for fila in filas:
        clase, *anchuras = esperadas[fila[1]]
        assert fila[2] == clase, fila[1]
        assert all(a in fila[3] for a in anchuras), fila[1]
    assert "Abrevaderos y descansaderos" in chinchon
    assert "46 áreas y 50 centiáreas" in chinchon

    villarejo = _subseccion("#### Villarejo de Salvanés — Orden de 08/10/1969")
    for via in ("Vereda del Cañuelo", "Vereda de San José", "Vereda de las Esperillas"):
        assert via in villarejo
    assert villarejo.count("20,89 m") >= 3

    modificacion = _subseccion("#### Villarejo de Salvanés — primera modificación")
    assert "33,43 m" in modificacion
    assert "Colada Toledana" in modificacion
    assert "mínimo 6 m" in modificacion

    villaconejos = _subseccion("#### Villaconejos")
    assert "Vereda del Raso" in villaconejos
    assert "Vereda del Rosario" in villaconejos
    assert villaconejos.count("20,89 m") >= 2

    # La frase de deslinde consta, con las vías a las que afecta.
    seccion = _seccion()
    assert "quedará definitivamente fijada al practicarse el deslinde" in seccion
    assert "Frase de deslinde: afecta a las 10 vías" in chinchon


def test_ca5_sin_nombres_de_propietarios_ni_colindantes() -> None:
    """Dado el texto del registro y las fixtures, cuando se buscan nombres de propietarios o
    colindantes, entonces no aparece ninguno (solo nombres de vías, parajes y términos
    municipales)."""
    seccion = _seccion()
    assert not re.search(r"\bdon\s+[A-ZÁÉÍÓÚ]", seccion)
    assert not re.search(r"\bdoña\s+[A-ZÁÉÍÓÚ]", seccion)
    for nombre in ("Fernando", "González de Miguel", "Luis González", "Yustos", "López de Merlo"):
        assert nombre not in seccion, nombre
    for ruta in FIXTURES.glob("*.txt"):
        texto = ruta.read_text(encoding="utf-8")
        assert not re.search(r"\bdon\s+[A-ZÁÉÍÓÚ][a-záéíóú]+ [A-ZÁÉÍÓÚ]", texto), ruta.name


def test_ca6_consta_lo_verificado_y_lo_no_verificado() -> None:
    """Dado el registro, cuando se revisa lo leído, entonces consta qué se verificó contra el
    PDF y qué quedó sin verificar o ilegible (canal ilegible ≠ «no hay»), y las anchuras aparecen
    como dato de la orden, no como prueba de ocupación."""
    seccion = _seccion()
    assert "#### Qué se verificó y qué no (#281)" in seccion
    assert "Verificado contra la imagen del PDF" in seccion
    assert "No verificado" in seccion
    assert "Canal ilegible ≠ «no hay»" in seccion
    assert "no prueba de ocupación" in seccion
