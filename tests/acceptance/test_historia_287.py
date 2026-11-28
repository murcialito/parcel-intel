"""Historia #287: registrar en REGISTRY.md el Catastro histórico de rústica de Colmenar.

Historia solo de documentación. Los tests leen la sección nueva de `REGISTRY.md` y comprueban
las frases y cifras que pide cada criterio. No llaman a red y no abren los PDF de `data/raw/`.
"""

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "src" / "parcel_intel" / "sources" / "REGISTRY.md"
INICIO = "## Catastro histórico de rústica (Sede Electrónica, historia #287)"
# Referencia catastral de finca (14 o 20 posiciones): no debe aparecer en el registro.
REF_CATASTRAL = re.compile(
    r"\b\d{7}[A-Z]{2}\d{4}[A-Z]\b|\b\d{7}[A-Z]{2}\d{4}[A-Z]\d{4}[A-Z]{2}\b"
)


def _texto() -> str:
    return REGISTRY.read_text(encoding="utf-8")


def _seccion() -> str:
    texto = _texto()
    inicio = texto.index(INICIO)
    fin = texto.find("\n## ", inicio + len(INICIO))
    return texto[inicio : fin if fin != -1 else len(texto)]


def _fila(seccion: str, prefijo: str) -> str:
    filas = [ln for ln in seccion.splitlines() if ln.startswith(f"| {prefijo}")]
    assert len(filas) == 1, prefijo
    return filas[0]


def test_ca1_cinco_productos_de_rustica_sin_retintada_ni_inventario() -> None:
    """Dado `REGISTRY.md`, cuando se lee la nueva sección «Catastro histórico de rústica (Sede
    Electrónica, historia #<n>)», entonces recoge los 5 productos de rústica que ofrece la Sede
    en Colmenar (Avance catastral, Topográfico Parcelario, 1.ª, 2.ª y 3.ª renovación), indica que
    **no hay foto aérea retintada** y que el inventario Excel de Madrid «aún no está disponible»."""
    s = _seccion()
    for producto in (
        "Avance catastral",
        "Topográfico Parcelario",
        "1.ª renovación",
        "2.ª renovación",
        "3.ª renovación",
    ):
        assert producto in s, producto
    assert "**No hay foto aérea retintada**" in s
    assert "aún no está disponible" in s
    assert "inventario Excel" in s


def test_ca2_tabla_de_los_productos_descargados() -> None:
    """Dado el mismo apartado, cuando se lee la tabla de los tres productos descargados (AC, TP,
    1R), entonces cada fila trae nº de PDF, nº de polígonos, resolución del escaneado, época y
    escala, y su nota (numeración propia del AC, romanos del TP, distribuidor 1:25 000 de la 1R y
    su uso como índice del TP), con los valores del comentario del fundador."""
    s = _seccion()
    assert "| Producto | Nº PDF | Polígonos | Escaneado | Época y escala | Nota |" in s
    ac = _fila(s, "Avance catastral (AC)")
    datos_ac = ("| 79 |", "| 49 (numeración propia", "~254 ppp", "1902-1913", "croquis sin escala")
    for dato in datos_ac:
        assert dato in ac, dato
    tp = _fila(s, "Topográfico Parcelario (TP)")
    for dato in ("| 105 |", "| 79 |", "10029×7677 px", "~250 ppp", "1947", "1:2000", "romanos"):
        assert dato in tp, dato
    r1 = _fila(s, "1.ª renovación (1R)")
    datos_1r = (
        "| 83 |",
        "~200 ppp",
        "1985-1988",
        "1:5000",
        "distribuidor (1:25 000)",
        "índice del TP",
    )
    for dato in datos_1r:
        assert dato in r1, dato


def test_ca3_acceso_formato_y_renovaciones() -> None:
    """Dado el mismo apartado, cuando se lee el acceso y el formato, entonces dice que exige Cl@ve
    o certificado personal (acción del fundador, no automatizable), que cada producto es un `.7z`
    con un PDF por polígono y hoja, escaneado JPEG sin texto y **sin georreferenciar** (el TP no
    trae el distribuidor `jpg`+`jgw` del manual), y que la 2.ª y la 3.ª renovación no se bajaron
    porque desde 1994 hay PNOA."""
    s = _seccion()
    assert "Cl@ve" in s
    assert "certificado" in s
    assert "no automatizable" in s or "un agente no puede" in s
    assert "`.7z`" in s
    assert "un PDF por polígono y hoja" in s
    assert "JPEG sin texto" in s
    assert "**sin georreferenciar**" in s
    assert "`jpg`+`jgw`" in s or "`jgw`" in s
    # Corregido con el complemento del fundador en #287: la 2.ª y la 3.ª sí se bajaron.
    assert "sí se bajaron" in s
    assert "PNOA desde 1994" in s


def test_ca4_licencia_citada_y_publicable_no() -> None:
    """Dado el mismo apartado, cuando se lee la licencia, entonces resume las cláusulas 5, 6, 7, 8
    y 12 de la resolución de 2011 con la URL del documento primario leído y la fecha de lectura,
    declara `publicable: no` para originales y recortes, y fija la cita del dossier tal como la
    decidió el fundador."""
    s = _seccion()
    assert (
        "https://www.catastro.hacienda.gob.es/ayuda/legislacion/ovc/resoluciondgc20110323_tfs.pdf"
        in s
    )
    assert "23 de marzo de 2011" in s
    assert "2026-11-27" in s
    for clausula in ("Cláusula 5", "Cláusula 6", "Cláusula 7", "Cláusula 8", "Cláusula 12"):
        assert clausula in s, clausula
    assert (
        "No se autoriza el uso público ni la comercialización de la información catastral original"
        in s
    )
    assert "En ningún caso se autoriza" in s
    assert "publicable: no" in s
    assert (
        "Dirección General del Catastro, cartografía histórica, Sede Electrónica, "
        "municipio, producto y polígono, fecha de acceso"
    ) in s


def test_ca5_exclusiones_sin_referencias_ni_nombres() -> None:
    """Dado el mismo apartado, cuando se lee la lista de exclusiones, entonces dice que Hojas de
    Características, Relación de Propietarios y Fichas parcelarias **no se bajan nunca** (llevan
    nombres de propietarios) y que no se copia ninguna referencia catastral ni nombre en el
    registro."""
    s = _seccion()
    assert "**Nunca se bajan**" in s
    for documento in ("Hojas de Características", "Relación de Propietarios", "Fichas parcelarias"):
        assert documento in s, documento
    assert "no copia ninguna referencia catastral" in s
    assert REF_CATASTRAL.search(s) is None


def test_ca6_siguiente_paso_ficha_interna_y_tuberia_historico() -> None:
    """Dado el mismo apartado, cuando se lee «Siguiente paso», entonces recoge que la ficha interna
    por trazado en `curated/` (cita de la fuente, sin imagen publicada) queda como decisión
    posterior y que se valorará si sirve la tubería de `curated/historico` (#139, ADR 0043) para el
    TP, con la dificultad de que no está georreferenciado y de que la numeración del AC y la del TP
    son distintas (la anotación roja del AC parece dar la equivalencia)."""
    s = _seccion()
    siguiente = s[s.index("### Siguiente paso") :]
    assert "`curated/`" in siguiente
    assert "decisión posterior" in siguiente
    assert "`curated/historico`" in siguiente
    assert "#139" in siguiente
    assert "ADR 0043" in siguiente
    assert "no está georreferenciado" in siguiente
    assert "numeraciones distintas" in siguiente
    assert "anotación roja del AC" in siguiente


def test_ca7_mosaico_de_ortofotos_como_fuente_no_verificada() -> None:
    """Dado `REGISTRY.md`, cuando se busca «Mosaico de ortofotos históricas catastrales», entonces
    aparece como fuente **no verificada** (acceso y licencia sin comprobar) con el hueco de 1957 a
    1997 que podría cubrir, sin afirmar nada más."""
    texto = _texto()
    mosaico = "Mosaico de ortofotos históricas catastrales"
    lineas = [ln for ln in texto.splitlines() if mosaico in ln]
    assert len(lineas) == 1
    linea = lineas[0]
    assert "no verificada" in linea
    assert "acceso y licencia sin comprobar" in linea
    assert "1957 a 1997" in linea


def test_ca8_solo_documentacion_en_el_diff() -> None:
    """Dado el repositorio, cuando se ejecuta la suite, entonces `ruff`, `mypy`, `lint-imports` y
    `pytest` siguen en verde y el diff solo toca documentación (ningún fichero de `src/` salvo
    `REGISTRY.md`).

    La parte de la suite la comprueban los cinco comandos de la PR. Aquí se miran los ficheros de
    los commits de esta historia («Historia #287: …», en su rama o ya fusionados en `main`), no el
    diff de la rama actual contra `origin/main`: eso fallaba en cualquier otra rama con cambios de
    código. Si el clon no tiene esos commits (CI con historia corta), el test se salta."""
    salida = subprocess.run(
        ["git", "log", "--format=", "--name-only", "--grep=^Historia #287:", "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    cambios = {linea for linea in salida.splitlines() if linea.strip()}
    if not cambios:
        pytest.skip("no hay commits de la historia #287 en este clon")
    permitidos = {
        "src/parcel_intel/sources/REGISTRY.md",
        "tests/acceptance/test_historia_287.py",
        "docs/lessons/LESSONS.md",
    }
    assert cambios <= permitidos, sorted(cambios - permitidos)
