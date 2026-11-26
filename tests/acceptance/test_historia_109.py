"""Historia #109: ADR del método de candidatos a corte (entidad de dominio, señales y orden).

Es una historia de documentación: los tests leen el ADR nuevo de `docs/adr/` (buscado por
sufijo, no por número, lección de #43) y `docs/vision.md`. No llaman a red ni importan código
que todavía no existe (la entidad y el método los implementan las historias hijas).
"""

import math
import re
from pathlib import Path

import pytest

from parcel_intel.domain.discrepancy_criterion import (
    CONFIDENCE_SCALE_M,
    SAMPLE_STEP_M,
    pair_tolerance_m,
)
from parcel_intel.domain.public_card import BANNED_WORDS, banned_words_in

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
ADR_DIR = REPO / "docs" / "adr"
VISION = REPO / "docs" / "vision.md"
SUFIJO = (
    "-candidatos-a-corte-discrepancia-con-el-camino-actual"
    "-senales-por-muestra-y-entidad-cutcandidate.md"
)


def _adr_path() -> Path:
    adrs = sorted(ADR_DIR.glob(f"*{SUFIJO}"))
    assert len(adrs) == 1, "debe existir exactamente un ADR de candidatos a corte por sufijo"
    return adrs[0]


def _adr() -> str:
    return _adr_path().read_text(encoding="utf-8")


def _seccion(titulo: str) -> str:
    """Texto de una sección `### titulo` del ADR (título incluido), hasta el siguiente
    `### ` o `## `."""
    lineas = _adr().splitlines()
    inicio = next(i for i, linea in enumerate(lineas) if linea.startswith(f"### {titulo}"))
    resto = lineas[inicio + 1 :]
    fin = next(
        (i for i, linea in enumerate(resto) if linea.startswith("### ") or linea.startswith("## ")),
        len(resto),
    )
    return "\n".join([lineas[inicio], *resto[:fin]])


def _bloque_entidad() -> str:
    """Bloque ```python``` del §5 con las dataclasses."""
    seccion = _seccion("5. Entidad")
    match = re.search(r"```python\n(.*?)```", seccion, re.DOTALL)
    assert match is not None
    return match.group(1)


def _campos(clase: str) -> list[str]:
    """Nombres de los campos de `clase` en el bloque de la entidad, en orden."""
    bloque = _bloque_entidad()
    match = re.search(rf"class {clase}:.*?\n((?:    .*\n)+)", bloque)
    assert match is not None, clase
    return re.findall(r"^    (\w+):", match.group(1), re.MULTILINE)


def _filas_orden() -> list[list[str]]:
    seccion = _seccion("Orden de las señales")
    filas = []
    for linea in seccion.splitlines():
        if linea.startswith("| H"):
            filas.append([c.strip() for c in linea.strip().strip("|").split("|")])
    return filas


def test_ca1_metodo_completo_condiciones_y_confianza() -> None:
    """Dado el ADR nuevo en `docs/adr/`, cuando se lee, entonces describe el método completo:
    cómo una `Discrepancy` pasa a candidato, qué condición (i) o (ii) se evalúa con qué señal,
    y cómo se combinan las señales y la confianza (con la escala y su interpretación, "orden
    relativo, no probabilidad" como en ADR 0025)."""
    que_es = _seccion("1. Qué es un candidato")
    assert "Discrepancia base" in que_es
    assert "`AUSENTE_EN_FUENTE`" in que_es and "`SOLAPE`" in que_es
    assert "`ign_red_transporte`" in que_es
    assert "(i)" in que_es and "(ii)" in que_es

    assert "veredicto por muestra" in _seccion("2. La muestra como unidad común")
    assert "MIN_LENGTH_M" in _seccion("3. Del veredicto al tramo")

    combinacion = _seccion("4. Combinación y confianza")
    assert "**O**" in combinacion
    assert "confianza = round(d · (1 − Π_s (1 − w_s · f_s)), 3)" in combinacion
    assert "orden relativo, no una probabilidad" in combinacion
    assert "ADR 0025" in combinacion

    # Cada señal dice qué condición evalúa.
    assert "condición (ii)" in _seccion("6. Primera señal")
    for fila in _filas_orden():
        if fila[0] in ("H4", "H5"):
            assert fila[2] == "(i)", fila
        if fila[0] in ("H2", "H6"):
            assert fila[2] == "(ii)", fila


def test_ca2_primera_senal_la_mas_barata_con_coste_y_descartes() -> None:
    """Dado el ADR, cuando se busca la **primera señal**, entonces está elegida con el criterio
    "la más barata que dé algo medible", con una estimación de coste (datos, cómputo por lote,
    dependencias) y la razón de descartar o aplazar las demás (incluida LiDAR)."""
    primera = _seccion("6. Primera señal")
    assert "`parcela_no_camino`" in primera
    assert "la más barata que da algo medible" in primera
    for partida in ("**datos:**", "**cómputo:**", "**dependencias:**"):
        assert partida in primera, partida
    assert "0 €" in primera

    adr = _adr()
    assert "**LiDAR**" in adr
    assert "Aplazadas sin historia" in adr
    assert "Que la señal de imagen fuera la primera" in adr


def test_ca3_orden_de_senales_como_historias_con_toca_y_dependencia() -> None:
    """Dado el ADR, cuando se busca el orden de señales, entonces lista cada señal posterior
    como una historia candidata con su zona `Toca:` aproximada y su dependencia, para que el
    refinador las parta sin releer el método."""
    seccion = _seccion("Orden de las señales")
    cabecera = "| # | Historia | Condición | Talla | Toca (aproximado) | Depende de |"
    assert cabecera in seccion
    filas = _filas_orden()
    assert [fila[0] for fila in filas] == ["H1", "H2", "H3", "H4", "H5", "H6"]
    for fila in filas:
        assert len(fila) == 6, fila
        assert "`src/parcel_intel/" in fila[4], fila
        assert fila[5], fila
    for senal in ("`visibilidad_ortofoto`", "`serie_historica`", "OpenStreetMap"):
        assert any(senal in fila[1] for fila in filas), senal


def test_ca4_entidad_congelada_stdlib_sin_titularidad() -> None:
    """Dada la entidad de dominio del candidato (`CutCandidate` o nombre que decida el
    arquitecto) documentada en el ADR, cuando se revisa, entonces es una dataclass congelada,
    solo stdlib, con: la discrepancia de origen o su identificador rastreable, tramo (geometría
    EPSG:25830), confianza, evidencia (medidas con nombre, como `Measurement`), señales que
    concurren, y la regla/criterio con versión que lo señaló. **No tiene campos de titularidad
    ni referencia catastral de la finca** (decisión del fundador: solo se muestra el tramo)."""
    bloque = _bloque_entidad()
    clases = re.findall(r"^class (\w+):", bloque, re.MULTILINE)
    decoradores = re.findall(r"^@dataclass\(frozen=True\)$", bloque, re.MULTILINE)
    assert "CutCandidate" in clases
    assert len(decoradores) == len(clases)
    assert "solo stdlib, dataclasses congeladas" in _seccion("5. Entidad")

    assert _campos("CutCandidate") == [
        "candidate_id",
        "municipality_code",
        "subject",
        "discrepancy_ids",
        "stretch",
        "conditions",
        "signals",
        "confidence",
        "evidence",
        "method",
    ]
    assert "stretch: MultiLineGeometry         # tramo, EPSG:25830" in bloque
    assert "evidence: tuple[Measurement, ...]" in bloque
    assert "method: CriterionRef" in bloque

    prohibidos = ("titular", "propiet", "owner", "cadastral", "catastr", "parcel", "finca")
    for clase in clases:
        for campo in _campos(clase):
            for palabra in prohibidos:
                assert palabra not in campo.lower(), f"{clase}.{campo}"
    frase = "**No hay ningún campo de titularidad, propietario ni referencia catastral de finca.**"
    assert frase in _seccion("5. Entidad")


def test_ca5_condicion_ii_sin_identificar_y_que_sale_a_lo_publicable() -> None:
    """Dado el ADR, cuando se revisa el tratamiento de la condición (ii) "dentro de un cierre",
    entonces dice cómo se detecta sin nombrar ni identificar al propietario (por ejemplo, cruce
    con parcelas que no son camino usado solo internamente) y qué parte del dato interno puede
    aparecer en la salida publicable."""
    primera = _seccion("6. Primera señal")
    assert "**descarta la referencia**" in primera
    assert "La huella no tiene campo de referencia" in primera

    publicable = _seccion("7. Condición (ii) sin identificar a nadie")
    assert "No entra ningún dato de titularidad" in publicable
    assert "**Qué puede publicar #103.**" in publicable
    assert "**Nunca se publica**" in publicable
    assert "la geometría de las parcelas" in publicable
    assert "referencias catastrales" in publicable
    # Decisión del fundador en #99: el ADR 0041 corrige el 0035 §3 y se cita.
    assert "ADR 0041" in publicable
    assert "Dirección General del Catastro" in publicable
    assert "no publicar hasta la consulta jurídica" not in _adr()


def test_ca6_lenguaje_de_indicio_sin_palabras_vetadas_en_plantillas() -> None:
    """Dado el ADR, cuando se revisa el lenguaje, entonces la salida es siempre "indicio a
    verificar" y las plantillas internas no usan "ilegal", "usurpación" ni similares (ver
    riesgos de `docs/vision.md`; el texto público lo validará el fundador)."""
    lenguaje = _seccion("11. Lenguaje")
    assert "La salida es siempre un indicio a verificar." in lenguaje
    assert '"Indicio a verificar, no es un dictamen."' in lenguaje
    plantillas = re.findall(r"«([^»]+)»", lenguaje)
    plantillas = [p for p in plantillas if "{" in p]
    assert len(plantillas) == 2
    for plantilla in plantillas:
        assert banned_words_in(plantilla) == (), plantilla
    assert "lo valida el fundador" in lenguaje


def test_ca7_sin_llm_al_evaluar_y_reglas_ia_con_aprobacion() -> None:
    """Dado el ADR, cuando se revisa la ejecución, entonces no hay ningún LLM al evaluar; si el
    método admite reglas autoradas por IA, pasan por el flujo de aprobación humana existente
    (ADR 0019/0020)."""
    llm = _seccion("10. LLM y reglas propuestas por IA")
    assert "Ningún LLM interviene al evaluar ni al construir candidatos." in llm
    assert "ADR 0019" in llm and "ADR 0020" in llm
    assert "`review approve`" in llm


def test_ca8_contrato_minimo_con_la_medicion() -> None:
    """Dado el ADR, cuando se revisa la medición, entonces define el contrato mínimo que #100
    necesita (qué recibe y qué devuelve el detector para poder medirlo con independencia de la
    señal) y dice que el método se ajusta sin tocar el conjunto de validación congelado."""
    contrato = _seccion("9. Contrato con la medición")
    assert "**El detector recibe**" in contrato
    assert "**Devuelve** un `MunicipalCutCandidateReport`" in contrato
    assert "`(candidate_id, municipality_code, stretch)`" in contrato
    assert "El arnés no lee `signals` ni `evidence`" in contrato
    assert "**Ajustar el método no toca el conjunto de validación.**" in contrato
    assert "`docs/validacion/casos.json` no se edita" in contrato


def test_ca9_reparto_de_capas_hexagonal() -> None:
    """Dado el ADR, cuando se revisa el reparto de capas, entonces indica ports nuevos (si los
    hay), casos de uso y adapters, respetando la arquitectura hexagonal y `lint-imports`."""
    capas = _seccion("8. Reparto de capas")
    for capa in ("| domain |", "| application |", "| ports |", "| adapters |", "| cli |"):
        assert capa in capas, capa
    assert "`cut_candidate_sink.py`" in capas
    assert "`cut_candidate_source.py`" in capas
    assert "`DetectCutCandidatesUseCase(" in capas
    assert "`lint-imports`" in capas
    assert "no un port" in capas


def test_ca10_solo_documentacion_codigo_en_historias_hijas() -> None:
    """Dado este cambio, cuando se hace PR, entonces solo toca documentación (ADR, y
    `docs/vision.md` marcando la decisión abierta "Método de detección" como resuelta, si
    procede); no hay código, y `uv run lint-imports`, `mypy`, `ruff` y `pytest` siguen en
    verde.

    El diff de la PR (solo `.md` y este test) y los cinco comandos se comprueban a mano y se
    anotan en la PR. Aquí se fija que el ADR asigna todo el código a historias hijas."""
    capas = _seccion("8. Reparto de capas")
    filas = [linea for linea in capas.splitlines() if linea.startswith("| ") and "---" not in linea]
    filas = filas[1:]  # sin cabecera
    assert filas
    for fila in filas:
        historia = fila.strip().strip("|").split("|")[-1].strip()
        assert historia in ("H1", "H2", "H3"), fila


def test_ca11_historias_hijas_con_titulo_talla_y_toca() -> None:
    """Dado el cierre del diseño, cuando el arquitecto termina, entonces deja comentada en #99
    la lista de historias hijas por señal (título, talla, `Toca:`) para que el refinador las
    cree, y señala cualquier pregunta que requiera al fundador (p. ej. texto público o
    licencias). → **Hecho por el arquitecto** (comentario en #99). El desarrollador no lo
    repite.

    El comentario en #99 no está en el repo; se comprueba que el ADR lleva la misma lista."""
    for fila in _filas_orden():
        assert fila[1], fila
        assert fila[3] in ("s", "m", "l"), fila
        assert fila[4], fila
    assert "Umbrales de producto a revisar con el fundador" in _adr()


def test_ca12_numero_libre_y_nombre_del_fichero() -> None:
    """Dado `docs/adr/` al abrir la PR (y otra vez tras cada merge de `main`), cuando se lista,
    entonces el ADR nuevo lleva el **siguiente número libre** (0039 si #94 ya ocupó el 0038 o lo
    tiene reservado; nunca el 0038) y no hay dos ADR con el mismo número creados por esta PR.
    Si el 0039 está ocupado, se usa el siguiente libre y se anota en la PR. El nombre del
    fichero termina en
    `-candidatos-a-corte-discrepancia-con-el-camino-actual-senales-por-muestra-y-entidad-cutcandidate.md`."""
    ruta = _adr_path()
    numero = ruta.name.split("-", 1)[0]
    assert re.fullmatch(r"\d{4}", numero)
    assert numero != "0038"
    assert int(numero) >= 39
    assert _adr().startswith(f"# ADR {numero} — Candidatos a corte")

    numeros = [p.name.split("-", 1)[0] for p in ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")]
    assert numeros.count(numero) == 1


def test_ca13_ejemplo_trabajado_cuadra_con_las_formulas() -> None:
    """Dado el ejemplo trabajado del ADR (§4), cuando se recalcula con las fórmulas del propio
    ADR, a mano o con un script local que no se versiona, entonces da exactamente: 40 muestras,
    16 que apoyan, tramo de (60, 0) a (140, 0), `longitud_tramo_m = 80.0`,
    `confianza_base = 0.691` y `confianza = 0.415`. Si algún número no cuadra, se corrige el
    ejemplo y se anota en la PR. No se cambia la fórmula."""
    # Recalculo independiente con las constantes del criterio de discrepancia (ADR 0025).
    tolerancia = pair_tolerance_m("via_pecuaria_oficial", "ign_red_transporte")
    assert tolerancia == pytest.approx(math.hypot(10, 5))
    d = round(1 * CONFIDENCE_SCALE_M / (CONFIDENCE_SCALE_M + tolerancia), 3)
    assert d == 0.691

    longitud = 200.0
    n = math.ceil(longitud / SAMPLE_STEP_M)
    centros = [SAMPLE_STEP_M * (i + 0.5) for i in range(n)]
    assert n == 40 and centros[0] == 2.5 and centros[-1] == 197.5

    margen = math.hypot(10, 5)  # §6: hypot(tol(A), tol(catastro_vt))
    x_min, x_max, y_min, y_max = 50.0, 150.0, -50.0, 50.0

    def apoya(x: float) -> bool:
        dentro = x_min < x < x_max and y_min < 0.0 < y_max
        distancia_borde = min(x - x_min, x_max - x, 0.0 - y_min, y_max - 0.0)
        return dentro and distancia_borde >= margen

    apoyan = [x for x in centros if apoya(x)]
    assert len(apoyan) == 16
    assert (apoyan[0], apoyan[-1]) == (62.5, 137.5)
    inicio = apoyan[0] - SAMPLE_STEP_M / 2
    fin = apoyan[-1] + SAMPLE_STEP_M / 2
    assert (inicio, fin) == (60.0, 140.0)
    longitud_tramo = len(apoyan) * SAMPLE_STEP_M
    assert longitud_tramo == 80.0

    f = len(apoyan) * SAMPLE_STEP_M / longitud_tramo
    confianza = round(d * (1 - (1 - 0.6 * f)), 3)
    assert confianza == 0.415

    # El ADR dice exactamente esos números.
    ejemplo = _seccion("4. Combinación y confianza")
    assert "Hay 40 muestras, en x = 2,5 … 197,5. Apoyan las 16" in ejemplo
    assert "tramo de (60, 0) a (140, 0) y `longitud_tramo_m = 80.0`" in ejemplo
    assert "= 0,691." in ejemplo
    assert "= 0,415." in ejemplo


def test_ca14_vision_metodo_de_deteccion_resuelto() -> None:
    """Dado `docs/vision.md`, cuando se lee la sección entre `**Decisiones abiertas:**` y
    `## Convenciones (sin cambios)` (no se renombra ninguno de los dos, porque los leen los tests
    de #42 y #43), entonces no queda ninguna línea `- [ ] Método de detección` y hay exactamente
    una `- [x] Método de detección de "candidato a corte"` que cita el ADR y la fecha
    2026-11-26. Las demás líneas de esa sección no cambian."""
    lineas = VISION.read_text(encoding="utf-8").splitlines()
    inicio = lineas.index("**Decisiones abiertas:**")
    fin = lineas.index("## Convenciones (sin cambios)")
    seccion = lineas[inicio:fin]
    assert [linea for linea in seccion if linea.startswith("- [ ] Método de detección")] == []
    resueltas = [
        linea
        for linea in seccion
        if linea.startswith('- [x] Método de detección de "candidato a corte"')
    ]
    assert len(resueltas) == 1
    numero = _adr_path().name.split("-", 1)[0]
    assert f"ADR {numero}" in resueltas[0]
    assert "2026-11-26" in resueltas[0]


_REFERENCIA = re.compile(
    r"(?<![0-9A-Za-z])(?=[0-9A-Z]*\d)(?:[0-9A-Z]{20}|[0-9A-Z]{14})(?![0-9A-Za-z])"
)
# Marcas de una frase que prohíbe o niega: la única forma en que el ADR puede nombrar
# una palabra vetada.
_NEGACION = re.compile(r"\b(?:No|no|Ninguna|ninguna|ningún|Nunca|nunca|ni)\b")


def test_ca15_sin_referencias_nombres_ni_palabras_vetadas() -> None:
    """Dado el ADR, cuando se busca, entonces no contiene ninguna referencia catastral (patrón
    de 14 o 20 caracteres de `domain/public_card.py`/#94), ningún nombre de persona o sociedad
    y ninguna palabra de `BANNED_WORDS` fuera de la frase que dice que están prohibidas.
    Comprobación manual anotada en la PR.

    Automatizado: referencias y palabras vetadas. Una línea con una palabra vetada debe ser
    una frase que la prohíbe o niega. Los nombres de persona o sociedad, a mano."""
    adr = _adr()
    assert _REFERENCIA.findall(adr) == []
    for sociedad in (" S.L.", " S.A.", " SL ", " SA ", "S.Coop"):
        assert sociedad not in adr, sociedad

    assert BANNED_WORDS  # la lista existe y no está vacía
    for linea in adr.splitlines():
        if banned_words_in(linea):
            assert _NEGACION.search(linea), linea
