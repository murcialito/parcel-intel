"""Zona local `data/` de los datos privados (historia #295, ADR 0059 §6 y §8).

Mismo contrato que la caché cruda (`CachedRawFetcher`): inmutable, sha256 comprobado y
escritura atómica. Todo se descarga a `data/privados/.preparacion/<temporal>` (mismo
sistema de ficheros) y solo se coloca, con `os.link`, cuando su tamaño y su sha256 son los
del catálogo; `os.link` falla si el destino ya existe, así que nunca se sobrescribe.
"""

import hashlib
import os
import shutil
import tarfile
import tempfile
import uuid
import zlib
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from parcel_intel.domain.private_catalog import ExtractedMember, LocalFileState, safe_member_path
from parcel_intel.ports.errors import (
    PrivateDataArchiveError,
    PrivateDataConflictError,
    PrivateDataStoreError,
)

PRIVATE_DIR = "privados"
STAGING_DIR = ".preparacion"
EXTRACT_DIR = "extraido"
COPY_CHUNK_BYTES = 1_048_576
SMALL_FILE_LIMIT_BYTES = 1_048_576


class LocalPrivateDataArea:
    def __init__(self, data_root: Path) -> None:
        self._root = data_root

    @property
    def _private(self) -> Path:
        return self._root / PRIVATE_DIR

    @contextmanager
    def staging(self) -> Iterator[Path]:
        base = self._private / STAGING_DIR
        base.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(dir=base))
        try:
            yield directory
        finally:
            shutil.rmtree(directory, ignore_errors=True)
            try:
                base.rmdir()
            except OSError:
                pass

    def file_state(self, path: Path) -> LocalFileState:
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        return LocalFileState(sha256=digest, size_bytes=path.stat().st_size)

    def read_small(self, path: Path) -> bytes:
        if path.stat().st_size > SMALL_FILE_LIMIT_BYTES:
            raise PrivateDataStoreError("procedencia demasiado grande")
        return path.read_bytes()

    def _resolve(self, destination: str) -> Path:
        """`data/<destination>`, comprobando que sigue dentro de `data/` (defensa además
        de `safe_destination`) y que nada en el camino es un enlace simbólico."""
        path = self._root / destination
        root = self._root.resolve()
        if not path.resolve().is_relative_to(root):
            raise PrivateDataConflictError("la ruta sale de data/")
        current = self._root
        for part in Path(destination).parts:
            current = current / part
            if current.is_symlink():
                raise PrivateDataConflictError("enlace simbólico en el destino")
        return path

    def existing_state(self, destination: str) -> LocalFileState | None:
        path = self._resolve(destination)
        if not path.exists():
            return None
        if not path.is_file():
            raise PrivateDataConflictError("el destino no es un fichero")
        return self.file_state(path)

    def place(self, staged: Path, destination: str) -> None:
        target = self._resolve(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        _link_without_overwrite(staged, target)

    def assemble(self, parts: Sequence[Path], target: Path) -> None:
        with target.open("xb") as out:
            for part in parts:
                with part.open("rb") as source:
                    shutil.copyfileobj(source, out, COPY_CHUNK_BYTES)
                part.unlink()

    def extract_tar(self, staged: Path, destination: str) -> tuple[ExtractedMember, ...]:
        extract_dir = staged.parent / EXTRACT_DIR
        extract_dir.mkdir()
        try:
            with tarfile.open(staged, "r:*") as archive:
                names = _validated_members(archive)
                archive.extractall(extract_dir, filter="data")
        except (tarfile.TarError, EOFError, zlib.error, UnicodeError):
            raise PrivateDataArchiveError("archivo ilegible o corrupto") from None
        members: list[ExtractedMember] = []
        for name in sorted(names):
            path = extract_dir / name
            if path.is_symlink() or not path.is_file():
                raise PrivateDataArchiveError("miembro que no es un fichero")
            state = self.file_state(path)
            members.append(ExtractedMember(name, state.sha256, state.size_bytes))
        missing = self._check_conflicts(destination, members)
        for member in missing:
            self.place(extract_dir / member.path, f"{destination}/{member.path}")
        return tuple(members)

    def _check_conflicts(
        self, destination: str, members: Sequence[ExtractedMember]
    ) -> list[ExtractedMember]:
        """Todo o nada: comprueba cada miembro antes de colocar ninguno. Devuelve los que
        faltan; uno que ya está con los mismos bytes no es conflicto."""
        missing: list[ExtractedMember] = []
        for member in members:
            relative = f"{destination}/{member.path}"
            pieces = member.path.split("/")
            for count in range(len(pieces)):
                directory = "/".join([destination, *pieces[:count]])
                candidate = self._resolve(directory)
                if candidate.exists() and not candidate.is_dir():
                    raise PrivateDataConflictError("un directorio del destino es un fichero")
            state = self.existing_state(relative)
            if state is None:
                missing.append(member)
            elif state != LocalFileState(member.sha256, member.size_bytes):
                raise PrivateDataConflictError("el miembro local no es el del archivo")
        return missing

    def _record_path(self, entry_id: str) -> Path:
        return self._private / f"{entry_id}.json"

    def read_record(self, entry_id: str) -> bytes | None:
        path = self._record_path(entry_id)
        if path.is_symlink():
            raise PrivateDataConflictError("enlace simbólico en el registro")
        if not path.exists():
            return None
        return path.read_bytes()

    def write_record(self, entry_id: str, content: bytes) -> None:
        path = self._record_path(entry_id)
        existing = self.read_record(entry_id)
        if existing is not None:
            if existing == content:
                return
            raise PrivateDataConflictError("ya hay otro registro de esta entrada")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
        try:
            temporary.write_bytes(content)
            _link_without_overwrite(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def _validated_members(archive: tarfile.TarFile) -> set[str]:
    """Rechaza, antes de extraer nada, todo lo que no sea un fichero o un directorio
    dentro de `destino`: enlaces, dispositivos, rutas absolutas o con `..`, repetidos o
    que usan un fichero como directorio. No se fía solo del filtro `data`."""
    files: set[str] = set()
    directories: set[str] = set()
    for member in archive.getmembers():
        if not (member.isfile() or member.isdir()):
            raise PrivateDataArchiveError("miembro que no es un fichero ni un directorio")
        try:
            name = safe_member_path(member.name)
        except ValueError:
            raise PrivateDataArchiveError("miembro con ruta no admitida") from None
        parents = {p.as_posix() for p in Path(name).parents if p.as_posix() != "."}
        if member.isdir():
            directories.add(name)
        else:
            if name in files:
                raise PrivateDataArchiveError("miembro repetido")
            files.add(name)
        directories |= parents
    if files & directories:
        raise PrivateDataArchiveError("un miembro es a la vez fichero y directorio")
    return files


def _link_without_overwrite(source: Path, target: Path) -> None:
    """Enlace físico que falla si `target` existe. Sin enlaces físicos (p. ej. exFAT),
    copia a un temporal hermano y lo renombra tras comprobar que el destino no existe."""
    try:
        os.link(source, target)
        return
    except FileExistsError:
        raise PrivateDataConflictError("el destino ya existe") from None
    except OSError:
        pass
    temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    try:
        shutil.copyfile(source, temporary)
        if target.exists() or target.is_symlink():
            raise PrivateDataConflictError("el destino ya existe")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
