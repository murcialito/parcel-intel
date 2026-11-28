"""Tests de aceptación de la historia #320: `datos-privados sincronizar` con entradas
`formato: tar` y entradas troceadas en `partes` (ADR 0055 §3, ADR 0059).

Fixtures SINTÉTICAS (`tests/fixtures/private_data/tar_partes.py`): año 2099, sin referencias
catastrales ni nombres. Ningún test lanza `gh` ni toca la red: el almacén es
`FakePrivateDataStore` y la zona local es la real (`LocalPrivateDataArea`) sobre `tmp_path`.
El ADR que dice «ADR 0057» en la issue es el ADR 0059 (ver su nota de numeración).
"""

import hashlib
import io
import json
import subprocess
import tarfile
from collections.abc import Callable
from pathlib import Path

import pytest

from parcel_intel.adapters.private_data import LocalPrivateDataArea
from parcel_intel.application.sync_private_data import SyncPrivateDataUseCase
from parcel_intel.cli import main
from tests.application.fake_private_data_store import FakePrivateDataStore, asset_key
from tests.fixtures.private_data.tar_partes import (
    CHUNKS,
    MEMBERS,
    PARTS_DESTINATION,
    PARTS_ID,
    TAG,
    TAR_DESTINATION,
    TAR_ID,
    WHOLE,
    mundo_partes,
    mundo_tar,
    sha256,
    tar_gz,
)

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _sin_guarda(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in main.PRIVATE_DATA_ENV_GUARD:
        monkeypatch.delenv(name, raising=False)


def _run(monkeypatch: pytest.MonkeyPatch, store: FakePrivateDataStore, datos: Path) -> int:
    monkeypatch.setattr(
        main,
        "build_private_data_sync",
        lambda root: SyncPrivateDataUseCase(store=store, area=LocalPrivateDataArea(root)),
    )
    parsed = main._build_parser().parse_args(
        ["datos-privados", "sincronizar", "--datos", str(datos)]
    )
    code: int = parsed.func(parsed)
    return code


def _lines(capsys: pytest.CaptureFixture[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in capsys.readouterr().out.splitlines():
        key, _, value = line.partition(": ")
        out[key] = value
    return out


def _tree(directory: Path) -> dict[str, str]:
    if not directory.exists():
        return {}
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def _record(datos: Path, entry_id: str) -> dict[str, object]:
    data: dict[str, object] = json.loads(
        (datos / "privados" / f"{entry_id}.json").read_text("utf-8")
    )
    return data


# --- CA1 ---------------------------------------------------------------------------------


def test_ca1_tar_se_desempaqueta_y_el_registro_lista_los_miembros(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA1. Dado un catálogo (fixture) con una entrada `tar` y un `.tar.gz` sintético de 3
    miembros en 2 subdirectorios, cuando se sincroniza, entonces cada miembro queda bajo
    `data/<destino>/` con sus bytes, el registro `data/privados/<id>.json` lista cada miembro
    con su ruta relativa, sha256 y tamaño (orden por ruta), y el resumen cuenta la entrada
    como `descargado`."""
    store, _ = mundo_tar(tmp_path / "mundo")
    datos = tmp_path / "data"
    code = _run(monkeypatch, store, datos)
    assert code == 0
    for name, data in MEMBERS.items():
        assert (datos / TAR_DESTINATION / name).read_bytes() == data
    record = _record(datos, TAR_ID)
    assert record["miembros"] == [
        {"ruta": name, "sha256": sha256(MEMBERS[name]), "tamano_bytes": len(MEMBERS[name])}
        for name in sorted(MEMBERS)
    ]
    assert len(MEMBERS) == 3 and len({name.split("/")[0] for name in MEMBERS}) == 2
    lines = _lines(capsys)
    assert lines[TAR_ID] == "descargado"
    assert lines["resumen"] == "1 descargados, 0 ya estaban, 0 saltados, 0 fallidos"
    assert not (datos / "privados" / ".preparacion").exists()


# --- CA2 ---------------------------------------------------------------------------------


def test_ca2_repetir_no_descarga_nada_y_deja_el_arbol_igual(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA2. Dado ese mismo estado, cuando se vuelve a ejecutar, entonces no se descarga nada
    (el doble del store no recibe ninguna llamada `download`), se comprueba el sha256 de cada
    miembro listado en el registro y la entrada sale `ya estaba`; el árbol de `data/` queda
    idéntico byte a byte."""
    store, _ = mundo_tar(tmp_path / "mundo")
    datos = tmp_path / "data"
    _run(monkeypatch, store, datos)
    capsys.readouterr()
    before = _tree(datos)
    store.downloads.clear()
    code = _run(monkeypatch, store, datos)
    assert code == 0
    assert store.downloads == []
    assert _lines(capsys)[TAR_ID] == "ya estaba"
    assert _tree(datos) == before


def test_ca2_un_miembro_borrado_se_vuelve_a_bajar_y_uno_alterado_es_fallo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA2 (complemento). El sha256 de cada miembro del registro se comprueba de verdad:
    uno que falta vuelve a bajar el archivo; uno con otros bytes falla la entrada."""
    store, _ = mundo_tar(tmp_path / "mundo")
    datos = tmp_path / "data"
    _run(monkeypatch, store, datos)
    capsys.readouterr()
    (datos / TAR_DESTINATION / "tesela_b" / "tres.gml").unlink()
    code = _run(monkeypatch, store, datos)
    assert code == 0
    assert _lines(capsys)[TAR_ID] == "descargado"
    assert (datos / TAR_DESTINATION / "tesela_b" / "tres.gml").read_bytes() == MEMBERS[
        "tesela_b/tres.gml"
    ]
    (datos / TAR_DESTINATION / "tesela_a" / "uno.gml").write_bytes(b"otros bytes")
    code = _run(monkeypatch, store, datos)
    assert code == 1
    assert _lines(capsys)[TAR_ID].startswith("fallo")
    assert (datos / TAR_DESTINATION / "tesela_a" / "uno.gml").read_bytes() == b"otros bytes"


# --- CA3 ---------------------------------------------------------------------------------


def test_ca3_miembro_local_distinto_falla_sin_escribir_ninguno(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA3. Dado un miembro que ya existe en local con otros bytes, cuando se sincroniza,
    entonces la entrada falla sin escribir **ningún** miembro (todo o nada por entrada: se
    extrae a la zona de preparación y se comprueba todo antes de colocar nada) y el comando
    sale con 1. Un miembro que ya existe con los mismos bytes no es conflicto (la caché del
    portátil del fundador)."""
    store, _ = mundo_tar(tmp_path / "mundo")
    datos = tmp_path / "data"
    existing = datos / TAR_DESTINATION / "tesela_b" / "tres.gml"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"otros bytes")
    code = _run(monkeypatch, store, datos)
    assert code == 1
    assert _lines(capsys)[TAR_ID] == "fallo (conflicto con lo que ya hay en local)"
    assert _tree(datos) == {
        f"{TAR_DESTINATION}/tesela_b/tres.gml": hashlib.sha256(b"otros bytes").hexdigest()
    }

    existing.write_bytes(MEMBERS["tesela_b/tres.gml"])
    code = _run(monkeypatch, store, datos)
    assert code == 0
    assert _lines(capsys)[TAR_ID] == "descargado"
    for name, data in MEMBERS.items():
        assert (datos / TAR_DESTINATION / name).read_bytes() == data


def test_ca3_un_directorio_que_es_fichero_en_local_es_conflicto_sin_escribir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CA3 (complemento). Un fichero local donde el archivo necesita un directorio falla
    la entrada sin colocar ningún miembro."""
    store, _ = mundo_tar(tmp_path / "mundo")
    datos = tmp_path / "data"
    blocker = datos / TAR_DESTINATION / "tesela_b"
    blocker.parent.mkdir(parents=True)
    blocker.write_bytes(b"un fichero")
    code = _run(monkeypatch, store, datos)
    assert code == 1
    assert list(_tree(datos)) == [f"{TAR_DESTINATION}/tesela_b"]


# --- CA4 ---------------------------------------------------------------------------------


def _symlink(archive: tarfile.TarFile) -> None:
    info = tarfile.TarInfo("enlace")
    info.type = tarfile.SYMTYPE
    info.linkname = "/etc/passwd"
    archive.addfile(info)


def _hardlink(archive: tarfile.TarFile) -> None:
    info = tarfile.TarInfo("duro")
    info.type = tarfile.LNKTYPE
    info.linkname = "tesela_a/uno.gml"
    archive.addfile(info)


def _device(archive: tarfile.TarFile) -> None:
    info = tarfile.TarInfo("dispositivo")
    info.type = tarfile.CHRTYPE
    info.devmajor, info.devminor = 1, 3
    archive.addfile(info)


def _fifo(archive: tarfile.TarFile) -> None:
    info = tarfile.TarInfo("tuberia")
    info.type = tarfile.FIFOTYPE
    archive.addfile(info)


def _file(name: str) -> Callable[[tarfile.TarFile], None]:
    def add(archive: tarfile.TarFile) -> None:
        info = tarfile.TarInfo(name)
        info.size = 4
        archive.addfile(info, io.BytesIO(b"mal\n"))

    return add


def _duplicate(archive: tarfile.TarFile) -> None:
    _file("tesela_a/uno.gml")(archive)


def _file_and_directory(archive: tarfile.TarFile) -> None:
    _file("tesela_a")(archive)


HOSTILE = {
    "relativo_con_puntos": _file("../fuera"),
    "relativo_anidado": _file("tesela_a/../../fuera"),
    "absoluto": _file("/tmp/paso_comun_fuera"),
    "enlace_simbolico": _symlink,
    "enlace_fisico": _hardlink,
    "dispositivo": _device,
    "tuberia": _fifo,
    "repetido": _duplicate,
    "fichero_y_directorio": _file_and_directory,
}


@pytest.mark.parametrize("case", sorted(HOSTILE))
def test_ca4_miembro_hostil_falla_sin_escribir_nada(
    case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CA4. Dado un `tar` con un miembro `../fuera`, uno absoluto, un enlace simbólico o
    físico, o un dispositivo, cuando se sincroniza, entonces la entrada falla sin escribir
    nada fuera ni dentro de `destino` (test por cada caso)."""
    payload = tar_gz(MEMBERS, HOSTILE[case])
    store, _ = mundo_tar(tmp_path / "mundo", payload)
    datos = tmp_path / "data"
    datos.mkdir()
    code = _run(monkeypatch, store, datos)
    assert code == 1
    assert _lines(capsys)[TAR_ID] == "fallo (el archivo tar no es válido)"
    assert _tree(datos) == {}
    assert not (datos / "raw").exists()
    assert not (datos / "privados" / ".preparacion").exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["data", "mundo"]
    assert not Path("/tmp/paso_comun_fuera").exists()


# --- CA5 ---------------------------------------------------------------------------------


def test_ca5_partes_se_concatenan_y_se_comprueba_cada_trozo_y_el_total(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA5. Dada una entrada con `partes` (3 trozos sintéticos), cuando se sincroniza,
    entonces se comprueba el sha256 y el tamaño de cada trozo, se concatenan en orden en la
    zona de preparación, se comprueba el sha256 y el tamaño del fichero entero, y solo
    entonces se coloca."""
    store = mundo_partes(tmp_path / "mundo")
    datos = tmp_path / "data"
    code = _run(monkeypatch, store, datos)
    assert code == 0
    assert (datos / PARTS_DESTINATION).read_bytes() == WHOLE
    assert len(CHUNKS) == 3
    assert store.downloads[:3] == [
        asset_key(TAG, f"{PARTS_ID}.bin.{index:03d}") for index in (1, 2, 3)
    ]
    assert _lines(capsys)[PARTS_ID] == "descargado"
    assert _record(datos, PARTS_ID)["entrada"]["partes"][2]["sha256"] == sha256(CHUNKS[2])  # type: ignore[index]
    assert not (datos / "privados" / ".preparacion").exists()


def test_ca5_trozo_o_total_incorrecto_no_deja_nada_en_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA5. Si falla un trozo o el total, no queda nada en `data/` (ni trozos ni el fichero)
    y sale con 1."""
    store = mundo_partes(tmp_path / "mundo")
    datos = tmp_path / "data"
    store.replaced_bytes[asset_key(TAG, f"{PARTS_ID}.bin.002")] = b"trozo alterado"
    code = _run(monkeypatch, store, datos)
    assert code == 1
    assert _lines(capsys)[PARTS_ID] == "fallo (una parte descargada no es la del catálogo)"
    assert _tree(datos) == {}
    assert not (datos / "raw").exists()

    # El total no coincide aunque cada trozo cuadre: catálogo con el sha256 de otro fichero.
    root = tmp_path / "otro"
    store2 = mundo_partes(root, CHUNKS, whole=WHOLE + b"x")
    datos2 = tmp_path / "data2"
    code = _run(monkeypatch, store2, datos2)
    assert code == 1
    assert _lines(capsys)[PARTS_ID] == "fallo (el fichero descargado no es el del catálogo)"
    assert _tree(datos2) == {}
    assert not (datos2 / "raw").exists()


def test_ca5_partes_repetir_no_descarga_nada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA5 (complemento). El fichero ya colocado con su registro sale `ya estaba` sin
    volver a bajar los trozos."""
    store = mundo_partes(tmp_path / "mundo")
    datos = tmp_path / "data"
    _run(monkeypatch, store, datos)
    capsys.readouterr()
    store.downloads.clear()
    code = _run(monkeypatch, store, datos)
    assert code == 0
    assert store.downloads == []
    assert _lines(capsys)[PARTS_ID] == "ya estaba"


# --- CA6 ---------------------------------------------------------------------------------


def test_ca6_claude_md_ya_no_dice_que_tar_y_partes_se_saltan() -> None:
    """CA6. Dado `lint-imports`, `mypy` y `ruff`, cuando se ejecutan, entonces pasan, y
    `CLAUDE.md` actualiza la entrada del comando (ya no dice que `tar` y `partes` se
    saltan)."""
    text = (ROOT / "CLAUDE.md").read_text("utf-8")
    commands = text[text.index("## Comandos") : text.index("## Contexto de negocio")]
    start = commands.index("datos-privados sincronizar [")
    block = commands[commands.rindex("# Sincronización de bajada", 0, start) : start]
    assert "pendientes de #320" not in block
    assert "pendiente de #320" not in block
    assert "tar" in block and "partes" in block
    assert "miembros" in block
    result = subprocess.run(
        ["uv", "run", "lint-imports"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
