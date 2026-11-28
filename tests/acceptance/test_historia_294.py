"""Historia #294: ADR del repositorio privado de datos y reglas de acceso.

Historia solo de documentación. Los tests leen el ADR (localizado por el sufijo del nombre de
fichero, no por número; lección de #43), `CLAUDE.md`, `docs/proceso.md` y `REGISTRY.md`, y buscan
las frases y cifras clave de cada criterio. No llaman a red.
"""

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
SUFIJO_ADR = "-repositorio-privado-de-datos-internos-adjuntos-de-release-catalogo-y-reglas-de-acceso.md"
CLAUDE_MD = REPO / "CLAUDE.md"
PROCESO = REPO / "docs" / "proceso.md"
REGISTRY = REPO / "src" / "parcel_intel" / "sources" / "REGISTRY.md"
INICIO_REGISTRY = "## Datos internos: copia en el repo privado (ADR "


def _adr_path() -> Path:
    candidatos = sorted((REPO / "docs" / "adr").glob(f"[0-9][0-9][0-9][0-9]{SUFIJO_ADR}"))
    assert len(candidatos) == 1, candidatos
    return candidatos[0]


def _adr() -> str:
    return _adr_path().read_text(encoding="utf-8")


def _numero_adr() -> str:
    return _adr_path().name[:4]


def _seccion(texto: str, titulo: str) -> str:
    inicio = texto.index(titulo)
    # Un título de Markdown acaba en el siguiente de su nivel; un párrafo en negrita, en el siguiente título.
    marca = titulo.split(" ", 1)[0] + " " if titulo.startswith("#") else "#"
    fin = texto.find(f"\n{marca}", inicio + len(titulo))
    return texto[inicio : fin if fin != -1 else len(texto)]


def _sin_saltos(texto: str) -> str:
    return re.sub(r"\s+", " ", texto)


def test_ca1_compara_opciones_con_coste_y_justifica() -> None:
    """Dado el ADR nuevo, cuando se lee, entonces compara con coste estimado: repo privado de
    GitHub con adjuntos de releases (con el límite por fichero y la ausencia de tope total y de
    ancho de banda verificados contra la documentación oficial y citados), disco externo/NAS (solo
    copia de seguridad) y almacenamiento de objetos (Cloudflare R2, Backblaze B2), y justifica la
    elegida."""
    adr = _adr()
    assert "«Each file included in a release must be under 2 GiB»" in adr
    assert "«There is no limit on the total size of a release, nor bandwidth usage»" in adr
    assert "https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases" in adr
    tabla = _seccion(adr, "### 1. Dónde")
    for opcion in ("Repo privado + adjuntos de release", "Disco externo o NAS", "Cloudflare R2", "Backblaze B2"):
        assert opcion in tabla, opcion
    assert "0 €" in tabla
    assert "0,015 USD/GB-mes" in tabla and "https://developers.cloudflare.com/r2/pricing/" in tabla
    assert "6,95 USD/TB-mes" in tabla and "https://www.backblaze.com/cloud-storage/pricing" in tabla
    assert "Solo copia de seguridad" in tabla
    assert "(elegida)" in tabla
    assert "Se elige el repo privado con adjuntos de release porque" in tabla


def test_ca2_formato_del_catalogo_y_que_va_en_git_o_adjunto() -> None:
    """Dado el ADR, cuando se lee, entonces define el formato del catálogo por fuente (fuente, URL,
    fecha de descarga, sha256, licencia, `publicable`, restricciones de uso), qué va en git y qué
    como adjunto de release."""
    seccion = _seccion(_adr(), "### 3. Qué va en git")
    for clave in ('"fuente"', '"url"', '"fecha_descarga"', '"sha256"', '"licencia"', '"publicable"', '"restricciones_uso"'):
        assert clave in seccion, clave
    assert "catalogo/<fuente>.json" in seccion
    assert "- **En git:**" in seccion
    assert "- **Como adjunto de release:**" in seccion
    assert "**Solo se añade.**" in seccion


def test_ca3_autenticacion_con_gh_auth_sin_secretos_del_repo_publico() -> None:
    """Dado el ADR, cuando se lee, entonces explica cómo se autentica la sincronización en local
    con `gh auth` del fundador sin tocar secretos del repo público."""
    seccion = _sin_saltos(_seccion(_adr(), "### 5. Acceso y autenticación"))
    assert "`gh auth login` del fundador" in seccion
    assert "no lee, guarda, imprime ni pasa por argumentos ningún token" in seccion
    assert "no se toca ningún secreto del repo público" in seccion
    assert "se niega a correr si `CI` o `GITHUB_ACTIONS` están definidos" in seccion
    assert "ningún workflow lo invoca" in seccion


def test_ca4_que_parte_de_derived_interno_se_copia() -> None:
    """Dado el ADR, cuando se lee, entonces dice qué parte de `data/derived/*/interno/` va también
    al repo privado."""
    seccion = _seccion(_adr(), "### 4. Qué se copia")
    assert "`data/derived/*/interno/`" in seccion
    assert "no se copia nada de forma rutinaria" in seccion
    for fichero in (
        "`candidatos/interno/<ine>.geojson`",
        "`discrepancias/interno/<ine>.geojson`",
        "`comparacion/<ine>.json`",
        "`validacion/medicion.json`",
    ):
        assert fichero in seccion, fichero


@pytest.mark.parametrize("ruta", [CLAUDE_MD, PROCESO], ids=["CLAUDE.md", "proceso.md"])
def test_ca5_reglas_de_acceso_en_claude_md_y_proceso(ruta: Path) -> None:
    """Dado `CLAUDE.md` y `docs/proceso.md`, cuando se leen, entonces recogen que ningún agente del
    repo público tiene acceso al repo privado (logs y PR públicos), que el procesado interno es
    local o en workflows del propio repo privado, que el acceso es solo del fundador mientras no se
    aclare la licencia, que ningún dato de titularidad entra tampoco en el privado y que lo subido
    es inmutable."""
    texto = _sin_saltos(ruta.read_text(encoding="utf-8"))
    assert f"ADR {_numero_adr()}" in texto
    assert "`murcialito/paso-comun-datos`" in texto
    assert "Ningún agente del repo público tiene acceso al repo privado" in texto
    assert "públicos" in texto
    assert "procesado interno es local o en workflows del propio repo privado" in texto
    assert "acceso es solo del fundador mientras no se aclare la licencia" in texto
    assert "Ningún dato de titularidad entra tampoco en el repo privado" in texto
    assert "Lo subido es inmutable" in texto


def test_ca6_no_reutiliza_parcel_intel_archivo_y_decision_de_colaboradores() -> None:
    """Dado el ADR, cuando se lee, entonces deja explícito que no se reutiliza
    `parcel-intel-archivo` y recoge la decisión pendiente sobre colaboradores (parte del proyecto o
    cada uno con su Cl@ve)."""
    adr = _adr()
    assert "### 7. No se reutiliza `parcel-intel-archivo`" in adr
    colaboradores = _seccion(adr, "### 8. Decisión pendiente: colaboradores")
    assert "Cuentan como parte del proyecto" in colaboradores
    assert "Cada uno descarga con su propia Cl@ve" in colaboradores


def test_ca7_condiciones_previas_en_adr_y_proceso() -> None:
    """*(añadido por el arquitecto)* Dado el ADR y `docs/proceso.md`, cuando se leen, entonces
    recogen las dos condiciones previas a crear el repo privado, porque hoy el repo público tiene
    credenciales que llegarían a él: (a) `PROJECT_TOKEN` es un token clásico con `repo`, que según
    la documentación de GitHub «can access every repository that you can access», y se vuelve a
    emitir con `public_repo` y `project`, sin `repo`; (b) la App de Claude se instala con «Only
    select repositories» y sin `paso-comun-datos`. `docs/proceso.md` deja de decir que
    `PROJECT_TOKEN` necesita `repo`.

    Según el comentario del fundador en la issue, las dos condiciones ya se cumplieron el
    2026-11-27: se recogen como hechas, con fecha, y se documenta que falta `workflow`."""
    adr = _sin_saltos(_adr())
    assert "«can access every repository that you can access»" in adr
    assert "**hechas, el 2026-11-27**" in adr
    assert "**solo `public_repo` y `project`**, **sin `repo`**" in adr
    assert "«Only select repositories»" in adr and "sin `paso-comun-datos`" in adr
    assert "**Falta el ámbito `workflow` en `PROJECT_TOKEN`.**" in adr
    assert "token de GitHub App limitado a este repo" in adr

    proceso = _sin_saltos(PROCESO.read_text(encoding="utf-8"))
    assert "**hechas el 2026-11-27**" in proceso
    assert "solo los permisos `public_repo` y `project`, sin `repo`" in proceso
    assert "«Only select repositories»" in proceso and "sin `paso-comun-datos`" in proceso
    assert "permisos `repo` y `project`" not in proceso
    assert "sin `repo` el proyecto no puede resolver las issues" not in proceso


def test_ca8_corrige_la_cuota_de_git_lfs() -> None:
    """*(añadido por el arquitecto)* Dado el ADR, cuando se lee, entonces corrige la cuota de Git
    LFS que cita #293 («1 GB») con la vigente de la documentación oficial (10 GiB de almacenamiento
    y 10 GiB de ancho de banda al mes en GitHub Free) y explica por qué, aun así, no sirve."""
    adr = _sin_saltos(_adr())
    assert "«1 GB»" in adr and "desfasada" in adr
    assert "**10 GiB de almacenamiento y 10 GiB de ancho de banda al mes**" in adr
    assert "https://docs.github.com/en/billing/concepts/product-billing/git-lfs" in adr
    por_que = _seccion(_adr(), "**Por qué no Git LFS.**")
    assert "Aun así no sirve" in por_que
    assert "15 GB" in por_que and "ancho de banda del mes" in por_que


def test_ca9_apartado_en_registry() -> None:
    """*(añadido por el arquitecto)* Dado `REGISTRY.md`, cuando se lee, entonces tiene un apartado
    breve «Datos internos: copia en el repo privado (ADR NNNN)» que remite al ADR, dice qué fuentes
    se copian (Catastro INSPIRE, Catastro histórico, Fondo Documental cuando llegue) y no afirma que
    ya haya nada subido."""
    texto = REGISTRY.read_text(encoding="utf-8")
    titulo = f"{INICIO_REGISTRY}{_numero_adr()})"
    assert titulo in texto
    seccion = _seccion(texto, titulo)
    assert _adr_path().name in seccion
    assert "**Catastro INSPIRE**" in seccion
    assert "**Catastro histórico**" in seccion
    assert "**Fondo Documental de Vías Pecuarias**" in seccion and "cuando lleguen" in seccion
    assert "**todavía no se ha subido nada**" in seccion
    assert "ya se ha subido" not in seccion and "están subidos" not in seccion
    assert "https://www.sedecatastro" not in seccion  # sin URL de descarga
    assert len(seccion.splitlines()) <= 15  # apartado breve


def test_ca10_solo_documentacion_en_el_diff() -> None:
    """*(añadido por el arquitecto)* Dado el repositorio, cuando se ejecuta la suite, entonces
    `ruff`, `mypy`, `lint-imports` y `pytest` siguen en verde y el diff solo toca documentación y
    `tests/acceptance/test_historia_294.py`; ningún fichero de `src/` salvo `REGISTRY.md` y ningún
    workflow.

    La parte de la suite la comprueban los cinco comandos de la PR. Aquí se miran los ficheros de
    los commits de esta historia («Historia #294: …»), no el diff contra `origin/main` (lección de
    #287). Si el clon no tiene esos commits (CI con historia corta), el test se salta."""
    salida = subprocess.run(
        ["git", "log", "--format=", "--name-only", "--grep=^Historia #294:", "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    cambios = {linea for linea in salida.splitlines() if linea.strip()}
    if not cambios:
        pytest.skip("no hay commits de la historia #294 en este clon")
    permitidos = {
        "CLAUDE.md",
        "docs/proceso.md",
        "docs/lessons/LESSONS.md",
        "src/parcel_intel/sources/REGISTRY.md",
        "tests/acceptance/test_historia_294.py",
        f"docs/adr/{_adr_path().name}",
    }
    assert cambios <= permitidos, sorted(cambios - permitidos)
