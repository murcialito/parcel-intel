"""Tests de `extract_tar` y `assemble` de la zona local (historia #320)."""

from pathlib import Path

import pytest

from parcel_intel.adapters.private_data import LocalPrivateDataArea
from parcel_intel.ports.errors import PrivateDataArchiveError, PrivateDataConflictError
from tests.fixtures.private_data.tar_partes import CHUNKS, MEMBERS, WHOLE, sha256, tar_gz


def test_extract_tar_devuelve_los_miembros_ordenados_y_los_coloca(tmp_path: Path) -> None:
    area = LocalPrivateDataArea(tmp_path)
    with area.staging() as staging:
        staged = staging / "objeto"
        staged.write_bytes(tar_gz(MEMBERS))
        members = area.extract_tar(staged, "raw/x/teselas")
    assert [m.path for m in members] == sorted(MEMBERS)
    for member in members:
        assert member.sha256 == sha256(MEMBERS[member.path])
        assert (tmp_path / "raw/x/teselas" / member.path).read_bytes() == MEMBERS[member.path]


def test_extract_tar_acepta_prefijo_punto_y_directorios(tmp_path: Path) -> None:
    import io
    import tarfile

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        directory = tarfile.TarInfo("./d")
        directory.type = tarfile.DIRTYPE
        archive.addfile(directory)
        info = tarfile.TarInfo("./d/f.txt")
        info.size = 2
        archive.addfile(info, io.BytesIO(b"ok"))
    area = LocalPrivateDataArea(tmp_path)
    with area.staging() as staging:
        staged = staging / "objeto"
        staged.write_bytes(buffer.getvalue())
        members = area.extract_tar(staged, "raw/x/y")
    assert [m.path for m in members] == ["d/f.txt"]
    assert (tmp_path / "raw/x/y/d/f.txt").read_bytes() == b"ok"


def test_extract_tar_ilegible_es_error_de_archivo_y_no_deja_nada(tmp_path: Path) -> None:
    area = LocalPrivateDataArea(tmp_path)
    with area.staging() as staging:
        staged = staging / "objeto"
        staged.write_bytes(b"esto no es un tar")
        with pytest.raises(PrivateDataArchiveError):
            area.extract_tar(staged, "raw/x/y")
    assert not (tmp_path / "raw").exists()


def test_extract_tar_gz_truncado_es_error_de_archivo(tmp_path: Path) -> None:
    area = LocalPrivateDataArea(tmp_path)
    data = tar_gz(MEMBERS)
    with area.staging() as staging:
        staged = staging / "objeto"
        staged.write_bytes(data[: len(data) // 2])
        with pytest.raises(PrivateDataArchiveError):
            area.extract_tar(staged, "raw/x/y")
    assert not (tmp_path / "raw").exists()


def test_extract_tar_con_un_miembro_en_conflicto_no_coloca_ninguno(tmp_path: Path) -> None:
    area = LocalPrivateDataArea(tmp_path)
    clash = tmp_path / "raw/x/y/tesela_b/tres.gml"
    clash.parent.mkdir(parents=True)
    clash.write_bytes(b"otros")
    with area.staging() as staging:
        staged = staging / "objeto"
        staged.write_bytes(tar_gz(MEMBERS))
        with pytest.raises(PrivateDataConflictError):
            area.extract_tar(staged, "raw/x/y")
    assert sorted(
        p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()
    ) == ["raw/x/y/tesela_b/tres.gml"]


def test_assemble_concatena_en_orden_y_consume_los_trozos(tmp_path: Path) -> None:
    area = LocalPrivateDataArea(tmp_path)
    with area.staging() as staging:
        parts = []
        for index, chunk in enumerate(CHUNKS):
            path = staging / f"p{index}"
            path.write_bytes(chunk)
            parts.append(path)
        target = staging / "objeto"
        area.assemble(parts, target)
        assert target.read_bytes() == WHOLE
        assert not any(path.exists() for path in parts)
