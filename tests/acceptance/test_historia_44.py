"""Historia #44: scripts y runbook de purga del historial de git.

Los tests de los scripts crean repos temporales con `git` y `tmp_path`; no llaman a red. Se
saltan con mensaje claro si `git-filter-repo` no está instalado (es herramienta de operador,
no dependencia del proyecto).
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
PURGAR = REPO / "scripts" / "purgar_historial.sh"
VERIFICAR = REPO / "scripts" / "verificar_purga.sh"
RUTAS_VERSIONADAS = REPO / "scripts" / "rutas_purga.txt"
RUNBOOK = REPO / "docs" / "runbook-publicacion.md"

# El venv del proyecto puede no estar en PATH si pytest se lanza sin `uv run`.
ENTORNO = {
    **os.environ,
    "PATH": os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")]),
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}

requiere_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo", path=ENTORNO["PATH"]) is None,
    reason="git-filter-repo no está instalado (pip install git-filter-repo)",
)

RUTAS_TXT = "tests/fixtures/catastro/\nglob:tests/fixtures/caminos/catastro_*\n"
SECRETO = "contenido-con-licencia-restrictiva"


def git(cwd: Path, *args: str) -> str:
    resultado = subprocess.run(
        ["git", *args], cwd=cwd, env=ENTORNO, check=True, capture_output=True, text=True
    )
    return resultado.stdout


def escribir(repo: Path, ruta: str, contenido: str) -> None:
    destino = repo / ruta
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido, encoding="utf-8")


def confirmar(repo: Path, mensaje: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", mensaje)


def crear_origen(base: Path) -> Path:
    """Repo con altas, cambios y borrados de rutas a purgar, más ficheros legítimos."""
    origen = base / "origen"
    origen.mkdir()
    git(origen, "init", "-q", "-b", "main")
    escribir(origen, "src/modulo.py", "VERSION = 1\n")
    escribir(origen, "tests/fixtures/catastro/respuesta_a.xml", SECRETO + " a\n")
    escribir(origen, "tests/fixtures/caminos/catastro_parcelas.gml", SECRETO + " gml\n")
    escribir(origen, "tests/fixtures/caminos/ign_viales.json", "{}\n")
    confirmar(origen, "alta inicial")
    escribir(origen, "tests/fixtures/catastro/respuesta_a.xml", SECRETO + " a2\n")
    escribir(origen, "tests/fixtures/catastro/respuesta_b.xml", SECRETO + " b\n")
    escribir(origen, "src/modulo.py", "VERSION = 2\n")
    confirmar(origen, "modifica fixtures y código")
    (origen / "tests/fixtures/catastro/respuesta_b.xml").unlink()
    (origen / "tests/fixtures/caminos/catastro_parcelas.gml").unlink()
    confirmar(origen, "borra fixtures")
    escribir(origen, "README.md", "hola\n")
    confirmar(origen, "documentación")
    return origen


def clonar(origen: Path, destino: Path) -> Path:
    git(origen.parent, "clone", "-q", str(origen), str(destino))
    return destino


def ejecutar(*cmd: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", *map(str, cmd)], env=ENTORNO, capture_output=True, text=True, check=False
    )


def rutas_de_todo_el_historial(repo: Path) -> set[str]:
    salida = git(repo, "log", "--all", "--no-renames", "--name-only", "--format=")
    return {linea for linea in salida.splitlines() if linea}


def purgar(clon: Path, rutas: Path) -> subprocess.CompletedProcess[str]:
    return ejecutar(PURGAR, clon, rutas, "--copia-desechable")


@pytest.fixture
def escenario(tmp_path: Path) -> tuple[Path, Path, Path]:
    """(origen, clon, fichero de rutas)."""
    origen = crear_origen(tmp_path)
    clon = clonar(origen, tmp_path / "clon")
    rutas = tmp_path / "rutas.txt"
    rutas.write_text(RUTAS_TXT, encoding="utf-8")
    return origen, clon, rutas


@requiere_filter_repo
def test_ca1_purga_elimina_rutas_y_conserva_lo_legitimo(
    escenario: tuple[Path, Path, Path],
) -> None:
    """Dado un repo git temporal con commits que añaden, modifican y borran ficheros bajo las
    rutas a purgar (más ficheros legítimos), cuando se ejecuta
    `scripts/purgar_historial.sh <clon> <fichero-de-rutas>` sobre un clon, entonces ningún
    commit del historial resultante contiene esas rutas y los ficheros legítimos conservan su
    contenido y su mensaje de commit."""
    origen, clon, rutas = escenario
    resultado = purgar(clon, rutas)
    assert resultado.returncode == 0, resultado.stderr

    tocadas = rutas_de_todo_el_historial(clon)
    assert not any(r.startswith("tests/fixtures/catastro/") for r in tocadas)
    assert not any(r.startswith("tests/fixtures/caminos/catastro_") for r in tocadas)
    assert {"src/modulo.py", "tests/fixtures/caminos/ign_viales.json", "README.md"} <= tocadas
    assert SECRETO not in git(clon, "log", "--all", "-p")

    assert git(clon, "show", "main:src/modulo.py") == "VERSION = 2\n"
    assert git(clon, "show", "main:README.md") == "hola\n"
    asuntos = git(clon, "log", "--format=%s").splitlines()
    for esperado in ("alta inicial", "modifica fixtures y código", "documentación"):
        assert esperado in asuntos
    # El original no se toca: sigue teniendo el rastro.
    assert "tests/fixtures/catastro/respuesta_a.xml" in rutas_de_todo_el_historial(origen)


@requiere_filter_repo
def test_ca2_arbol_de_main_igual_salvo_rutas_purgadas(
    escenario: tuple[Path, Path, Path],
) -> None:
    """Dado el mismo escenario, cuando se ejecuta el script, entonces el árbol de la punta de
    `main` es idéntico al previo salvo las rutas purgadas, y el script se niega (salida ≠ 0) a
    ejecutarse si el directorio no es un clon o si no se le indica explícitamente que es una
    copia de trabajo desechable."""
    _origen, clon, rutas = escenario
    git(clon, "checkout", "-q", "-b", "extra")
    escribir(clon, "tests/fixtures/catastro/otra.xml", SECRETO + " otra\n")
    escribir(clon, "tests/fixtures/caminos/catastro_otra.gml", SECRETO + " otra\n")
    confirmar(clon, "rastro en rama secundaria")
    git(clon, "tag", "v-con-rastro")
    git(clon, "checkout", "-q", "main")

    antes = set(git(clon, "ls-tree", "-r", "--name-only", "main").splitlines())
    contenidos_antes = {r: git(clon, "show", f"main:{r}") for r in antes}

    resultado = purgar(clon, rutas)
    assert resultado.returncode == 0, resultado.stderr

    despues = set(git(clon, "ls-tree", "-r", "--name-only", "main").splitlines())
    purgadas = {
        r
        for r in antes
        if r.startswith("tests/fixtures/catastro/")
        or r.startswith("tests/fixtures/caminos/catastro_")
    }
    assert despues == antes - purgadas
    for ruta in despues:
        assert git(clon, "show", f"main:{ruta}") == contenidos_antes[ruta]


def test_ca2_se_niega_sin_confirmacion_de_copia_desechable(
    escenario: tuple[Path, Path, Path],
) -> None:
    """(CA2, rechazo) El script se niega a ejecutarse si no se le indica explícitamente que
    es una copia de trabajo desechable."""
    _origen, clon, rutas = escenario
    antes = git(clon, "rev-parse", "HEAD")
    sin_flag = ejecutar(PURGAR, clon, rutas)
    flag_erroneo = ejecutar(PURGAR, clon, rutas, "--si")
    assert sin_flag.returncode != 0
    assert flag_erroneo.returncode != 0
    assert git(clon, "rev-parse", "HEAD") == antes


def test_ca2_se_niega_si_el_directorio_no_es_un_clon(tmp_path: Path) -> None:
    """(CA2, rechazo) El script se niega a ejecutarse si el directorio no es un clon."""
    rutas = tmp_path / "rutas.txt"
    rutas.write_text(RUTAS_TXT, encoding="utf-8")
    sin_git = tmp_path / "sin_git"
    sin_git.mkdir()
    inexistente = tmp_path / "no_existe"
    assert purgar(sin_git, rutas).returncode != 0
    assert purgar(inexistente, rutas).returncode != 0

    # Un subdirectorio de un repo tampoco es un clon.
    origen = crear_origen(tmp_path)
    subdirectorio = origen / "src"
    resultado = purgar(subdirectorio, rutas)
    assert resultado.returncode != 0
    assert "tests/fixtures/catastro/respuesta_a.xml" in rutas_de_todo_el_historial(origen)


@requiere_filter_repo
def test_ca3_verificacion_ok_sobre_historial_purgado(
    escenario: tuple[Path, Path, Path],
) -> None:
    """Dado un historial ya purgado, cuando se ejecuta
    `scripts/verificar_purga.sh <repo> <fichero-de-rutas>`, entonces devuelve 0 e informa de
    que no queda rastro en commits de todas las refs (`git log --all --`), tags, blobs
    alcanzables (`git rev-list --objects --all`) y reflog/objetos sueltos tras
    `gc --prune=now`."""
    _origen, clon, rutas = escenario
    git(clon, "tag", "v1")
    assert purgar(clon, rutas).returncode == 0
    resultado = verificar(clon, rutas)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    for palabra in ("commits de todas las refs", "tags", "blobs alcanzables", "reflog"):
        assert palabra in resultado.stdout
    assert "objetos sueltos" in resultado.stdout


def verificar(repo: Path, rutas: Path) -> subprocess.CompletedProcess[str]:
    return ejecutar(VERIFICAR, repo, rutas)


def test_ca4_verificacion_falla_y_lista_rastros_en_rama_y_tag(
    escenario: tuple[Path, Path, Path],
) -> None:
    """Dado un historial con rastro de alguna ruta (p. ej. en una rama o tag secundario),
    cuando se ejecuta `verificar_purga.sh`, entonces devuelve ≠ 0 y lista las rutas y commits
    que aún contienen rastro."""
    _origen, clon, rutas = escenario
    # En el clon sin purgar hay rastro en main; añadimos además una rama y un tag secundarios.
    git(clon, "checkout", "-q", "-b", "secundaria")
    escribir(clon, "tests/fixtures/caminos/catastro_extra.gml", SECRETO + " extra\n")
    confirmar(clon, "rastro en rama")
    commit_rama = git(clon, "rev-parse", "HEAD").strip()
    git(clon, "tag", "v-rastro")
    git(clon, "checkout", "-q", "main")
    git(clon, "branch", "-q", "-D", "secundaria")

    resultado = verificar(clon, rutas)
    assert resultado.returncode != 0
    assert "tests/fixtures/caminos/catastro_extra.gml" in resultado.stdout
    assert commit_rama in resultado.stdout
    assert "tests/fixtures/catastro/respuesta_a.xml" in resultado.stdout
    assert "tag v-rastro" in resultado.stdout


@requiere_filter_repo
def test_ca4_purga_parcial_sigue_fallando(escenario: tuple[Path, Path, Path]) -> None:
    """(CA4) Purgar solo una de las dos rutas deja rastro de la otra y la verificación
    falla."""
    _origen, clon, rutas = escenario
    parcial = rutas.parent / "parcial.txt"
    parcial.write_text("tests/fixtures/catastro/\n", encoding="utf-8")
    assert purgar(clon, parcial).returncode == 0
    resultado = verificar(clon, rutas)
    assert resultado.returncode != 0
    assert "tests/fixtures/caminos/catastro_parcelas.gml" in resultado.stdout


def test_ca5_runbook_contiene_los_apartados_exigidos() -> None:
    """Dado el repo, cuando se lee `docs/runbook-publicacion.md`, entonces contiene:
    precondiciones comprobables (repo privado, sin PRs abiertas, #38 fusionada, copia de
    seguridad `git clone --mirror`), pasos en orden (clon, purga, verificación, **visto bueno
    explícito del fundador antes del `push --force`**, push de ramas y tags, re-clonado de
    verificación), purga en GitHub (Support para `refs/pull/*` y cachés, comprobar forks y
    artefactos/cachés de Actions), plan de comunicación (los clones antiguos se descartan, no
    se hace merge), rollback con el mirror, y el paso final a público como acción manual del
    fundador."""
    texto = RUNBOOK.read_text(encoding="utf-8")
    for apartado in (
        "## Precondiciones",
        "## Pasos",
        "## Purga en GitHub",
        "## Comunicación",
        "## Rollback",
        "## Paso final: hacer público",
    ):
        assert apartado in texto, apartado
    # Precondiciones comprobables.
    for fragmento in (
        "--json visibility",
        "PRIVATE",
        "gh pr list --state open",
        "#38",
        "git clone --mirror",
    ):
        assert fragmento in texto, fragmento
    # Pasos en orden.
    orden = [
        "git clone --no-local",
        "scripts/purgar_historial.sh",
        "scripts/verificar_purga.sh",
        "VISTO BUENO EXPLÍCITO DEL FUNDADOR",
        "git push --force",
        "--tags",
        "re-clonado",
    ]
    inicio_pasos = texto.index("## Pasos")
    posiciones = [texto.index(f, inicio_pasos) for f in orden]
    assert posiciones == sorted(posiciones), dict(zip(orden, posiciones, strict=True))
    # Purga en GitHub.
    for fragmento in ("GitHub Support", "refs/pull/", "forks", "artefactos", "cachés de Actions"):
        assert fragmento in texto, fragmento
    # Comunicación, rollback y paso final.
    assert "se descartan" in texto
    assert "no se hace merge" in texto.lower()
    assert "git push --mirror" in texto
    seccion_final = texto[texto.index("## Paso final: hacer público") :]
    assert "manual" in seccion_final
    assert "fundador" in seccion_final


def test_ca6_runbook_no_nombra_propietarios_ni_reproduce_respuestas() -> None:
    """Dado el runbook, cuando se revisa, entonces no nombra propietarios ni reproduce
    contenido de las respuestas de Catastro."""
    texto = RUNBOOK.read_text(encoding="utf-8")
    prohibidos = ("<cadastral", "<gml:", "<?xml", "nationalCadastralReference", "propietari")
    for fragmento in prohibidos:
        if fragmento == "propietari":
            # Solo se admite la mención genérica de la regla, nunca un nombre.
            for linea in texto.splitlines():
                if fragmento in linea.lower():
                    assert "no se nombra" in linea.lower() or "ningún" in linea.lower(), linea
        else:
            assert fragmento not in texto, fragmento
    # Ninguna referencia catastral (14 o 20 caracteres) ni ruta de fichero concreto de Catastro.
    import re

    assert re.search(r"\b\d{5}[A-Z]\d{8}\w*\b", texto) is None
    assert re.search(r"\b\d{7}[A-Z]{2}\d{4}[A-Z]\b", texto) is None


def test_rutas_versionadas_cubren_las_rutas_de_la_historia() -> None:
    """El fichero versionado `scripts/rutas_purga.txt` lista las rutas de la historia."""
    lineas = [
        linea
        for linea in RUTAS_VERSIONADAS.read_text(encoding="utf-8").splitlines()
        if linea and not linea.startswith("#")
    ]
    assert lineas == [
        "tests/fixtures/catastro/",
        "glob:tests/fixtures/caminos/catastro_*",
    ]
