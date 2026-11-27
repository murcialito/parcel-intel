"""Historia #282: localizar la clasificación de vías pecuarias de Colmenar de Oreja, Aranjuez,
Belmonte de Tajo y Valdelaguna.

Son tests de documentación: comprueban que REGISTRY.md anota cada canal consultado con su
resultado y que las fixtures citadas existen y tienen el sha256 anotado. No llaman a red.
"""

import hashlib
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "src" / "parcel_intel" / "sources" / "REGISTRY.md"
FIXTURES = REPO / "tests" / "fixtures" / "caminos"

ENCABEZADO = "### Canales consultados — historia #282"
CABECERA_CLASIFICACION = "| Municipio | INE | Orden de clasificación | Estado |"
INE = {
    "Colmenar de Oreja": "28043",
    "Aranjuez": "28013",
    "Belmonte de Tajo": "28019",
    "Valdelaguna": "28157",
}
EXTRACTOS = {
    "clasificacion_282_extracto_boe.txt": (
        "5735e1f3fbf06c25f3664a7b02e7e46793c577bed93417214116cfc60a273fc1"
    ),
    "clasificacion_282_extracto_bocm.txt": (
        "937b1b75bfd399d521b69fbbe75acbfcf174055af74aacea8fd028455c55ebd0"
    ),
}


def _texto() -> str:
    return REGISTRY.read_text(encoding="utf-8")


def _seccion() -> str:
    texto = _texto()
    inicio = texto.index(ENCABEZADO)
    fines = [texto.find(marca, inicio + 5) for marca in ("\n### ", "\n## ")]
    fines = [fin for fin in fines if fin != -1]
    return texto[inicio : min(fines)] if fines else texto[inicio:]


def _celdas(linea: str) -> list[str]:
    return [celda.strip() for celda in linea.strip().strip("|").split("|")]


def _filas_canales(seccion: str, columnas: int) -> list[list[str]]:
    """Filas de canal («BOE…» o «BOCM…») con el número de columnas indicado."""
    filas = []
    for linea in seccion.splitlines():
        if linea.startswith("| BOE") or linea.startswith("| BOCM"):
            celdas = _celdas(linea)
            if len(celdas) == columnas:
                filas.append(celdas)
    return filas


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


def test_ca1_cada_canal_con_url_fecha_y_resultado() -> None:
    """Dado cada uno de los 4 municipios, cuando se consulta el BOE (búsqueda por título
    «clasificación de las vías pecuarias» con y sin nombre de municipio, por «proyecto de
    clasificación», órdenes agrupadas de varios términos, y la sección de Medio Ambiente/
    Agricultura de 1960-1990) y el BOCM (archivo, ELI, índices anuales de la Consejería
    competente, posteriores a 1984), entonces `REGISTRY.md` anota cada canal con su URL,
    fecha de consulta (2026-11-27 o posterior) y resultado: «localizada», «no hay» o «no se
    pudo leer» (con motivo). Un canal ilegible no se anota como «no hay»."""
    seccion = _seccion()
    assert "2026-11-27" in seccion
    for municipio in INE:
        assert municipio in seccion, municipio
    # Las dos tablas de canales: por municipio (6 columnas) y generales (3 columnas).
    por_municipio = _filas_canales(seccion, 6)
    generales = _filas_canales(seccion, 3)
    assert len(por_municipio) >= 5
    for fila in por_municipio:
        assert all(celda for celda in fila[2:]), fila[0]
    # Cada canal del criterio aparece con su consulta.
    for etiqueta in (
        "BOE, título: clasificación",
        "BOE, título: pecuarias",
        "BOE, título: proyecto de clasificación",
        "BOE, título: solo el municipio",
        "BOCM, frase exacta",
        "BOCM, texto libre",
    ):
        assert any(fila[0] == etiqueta for fila in por_municipio), etiqueta
    for etiqueta in (
        "BOE, título genérico",
        "BOE, texto completo",
        "BOE, sumarios 1960–1990 (Medio Ambiente y Agricultura)",
        "BOCM, archivo por boletín",
        "BOCM, ELI",
        "BOCM, índices anuales de la Consejería",
    ):
        assert any(fila[0] == etiqueta for fila in generales), etiqueta
    # Los canales ilegibles dicen por qué, y las URL de cada canal constan.
    assert "no se pudo leer" in seccion
    for patron in (
        "campo[1]=TITULOS",
        "search_api_views_fulltext_1",
        "https://www.bocm.es/eli",
        "https://www.bocm.es/boletin-archivo",
    ):
        assert patron in seccion, patron


def test_ca2_orden_localizada_con_referencia_url_y_fecha() -> None:
    """Dado un municipio cuya orden/resolución/decreto se localiza, cuando se abre el documento
    primario, entonces la fila del municipio en la tabla de clasificación pasa de «no
    encontrada» a la referencia exacta (BOE-A-… o BOCM, fecha, título, URL, licencia o
    condiciones de reutilización del boletín citadas del documento) y se guarda la fixture
    mínima en `tests/fixtures/caminos/` (el PDF/HTML si pesa poco; si no, solo cabecera y
    extracto de texto, con su sha256). Sin transcribir aún las vías: eso es la historia
    posterior."""
    for municipio, fila in ((municipio, _filas_clasificacion()[municipio]) for municipio in INE):
        if fila[3] != "localizada":
            continue
        # Ninguna orden se ha localizado en esta historia; si una se localizara, la fila debe
        # traer la referencia, la URL y la fecha del documento primario.
        assert re.search(r"BOE-A-\d{4}-\d+|BOCM", fila[2]), municipio
        assert "http" in fila[2], municipio
        assert re.search(r"\d{4}-\d{2}-\d{2}|\d{1,2} de \w+ de \d{4}", fila[2]), municipio
    # En esta pasada no se localiza ninguna orden legible: el criterio no se aplica.
    assert all(_filas_clasificacion()[m][3] == "no localizada" for m in INE)


def test_ca3_no_localizada_lista_canales_y_enlaza_fondo_documental() -> None:
    """Dado un municipio cuya clasificación solo exista en el Fondo Documental sin publicación
    en boletín (o no se localice), cuando se registra, entonces la fila queda «no localizada»
    (o «solo Fondo Documental») con la lista de canales probados, y se enlaza a #284
    (solicitud al Fondo Documental) como siguiente paso, sin enviar nada."""
    seccion = _seccion()
    por_municipio = _filas_canales(seccion, 6)
    for municipio, ine in INE.items():
        fila = _filas_clasificacion()[municipio]
        assert fila[1] == ine, municipio
        assert fila[3] in ("no localizada", "solo Fondo Documental"), municipio
        # Al menos un canal con resultado para ese municipio (una columna no vacía).
        columna = list(INE).index(municipio) + 2
        assert any(celda[columna] for celda in por_municipio), municipio
    assert "#284" in seccion


def test_ca4_orden_legible_propuesta_de_historia_en_280() -> None:
    """Dado que se localice alguna orden legible, cuando termine la historia, entonces se deja
    un comentario en #280 proponiendo una historia hija «leer la orden de <municipio>»
    análoga a #281 (no se crea aquí)."""
    seccion = _seccion()
    localizadas = [m for m, f in _filas_clasificacion().items() if f[3] == "localizada"]
    if not localizadas:
        # Sin orden legible no hay historia que proponer; la sección lo dice y nombra #280.
        assert "#280" in seccion
    for municipio in localizadas:
        assert "#280" in seccion, municipio


def test_ca5_fixtures_con_sha256_y_filas_completas() -> None:
    """Test de aceptación: REGISTRY.md tiene, para cada uno de los cuatro códigos INE, una fila
    en la tabla de clasificación con estado distinto de «no encontrada», con canales si es
    «no localizada»; toda fila «no localizada» lista al menos un canal con su resultado; toda
    fila «localizada» trae la referencia, URL y fecha; y las fixtures citadas existen."""
    filas = _filas_clasificacion()
    seccion = _seccion()
    for municipio, ine in INE.items():
        assert municipio in filas, municipio
        fila = filas[municipio]
        assert fila[1] == ine, municipio
        assert fila[3] != "no encontrada", municipio
        if fila[3] == "no localizada":
            columna = list(INE).index(municipio) + 2
            assert any(celda[columna] for celda in _filas_canales(seccion, 6)), municipio
    for nombre, sha in EXTRACTOS.items():
        ruta = FIXTURES / nombre
        assert ruta.is_file(), nombre
        assert hashlib.sha256(ruta.read_bytes()).hexdigest() == sha, nombre
        assert nombre in seccion, nombre
        assert sha in seccion, nombre
    # Los controles positivos que dan validez a los «no localizada» están en los extractos.
    boe = (FIXTURES / "clasificacion_282_extracto_boe.txt").read_text(encoding="utf-8")
    bocm = (FIXTURES / "clasificacion_282_extracto_bocm.txt").read_text(encoding="utf-8")
    assert "Chinchón" in boe
    assert "Orden 3/2011" in bocm and "Chapinería" in bocm
