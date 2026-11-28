"""Sincronización de bajada de los datos privados (historia #295, ADR 0055 §3 y §5,
ADR 0059; `tar` y `partes`, historia #320).

Lee todos los catálogos del almacén y los valida **antes** de descargar nada o de tocar
la zona local. Después procesa cada entrada por separado: un fallo en una no frena las
demás. Nada se sobrescribe: un fichero o un registro local distinto del catálogo es un
fallo de esa entrada. Los motivos son textos fijos, sin rutas ni mensajes del almacén.
"""

from collections.abc import Mapping
from pathlib import Path

from parcel_intel.domain.private_catalog import (
    EntryLayout,
    EntrySyncResult,
    ExtractedMember,
    LocalFileState,
    PrivateCatalogEntry,
    PrivateCatalogError,
    ReleaseAsset,
    SyncOutcome,
    SyncSummary,
    entry_state,
    local_record,
    parse_catalog,
    parse_provenance,
    record_matches,
    record_members,
    validate_catalog_set,
)
from parcel_intel.ports.errors import (
    PrivateDataArchiveError,
    PrivateDataConflictError,
    PrivateDataStoreError,
    PrivateDataUnavailable,
)
from parcel_intel.ports.private_data_area import PrivateDataArea
from parcel_intel.ports.private_data_store import PrivateDataStore

REASON_LOCAL_FILE_DIFFERS = "el fichero local no es el del catálogo"
REASON_LOCAL_RECORD_DIFFERS = "el registro local no es el de esta entrada"
REASON_DOWNLOAD_DIFFERS = "el fichero descargado no es el del catálogo"
REASON_STORE = "no se pudo descargar del almacén"
REASON_PROVENANCE = "procedencia no válida"
REASON_CONFLICT = "conflicto con lo que ya hay en local"
REASON_LOCAL_IO = "error al escribir en local"
REASON_ARCHIVE = "el archivo tar no es válido"
REASON_PART_DIFFERS = "una parte descargada no es la del catálogo"
REASON_PARTS_STORAGE = "las partes deben estar en un release"
REASON_SKIP_SOURCE = "fuente no pedida"

_STAGED_OBJECT = "objeto"
_STAGED_PROVENANCE = "procedencia.json"


class _EntryFailed(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class SyncPrivateDataUseCase:
    def __init__(self, store: PrivateDataStore, area: PrivateDataArea) -> None:
        self._store = store
        self._area = area

    def execute(self, sources: frozenset[str] | None = None) -> SyncSummary:
        """`PrivateDataUnavailable` y `PrivateDataStoreError` al leer los catálogos, y
        `PrivateCatalogError` si alguno no vale, salen tal cual: sin descargar nada."""
        documents = self._store.read_catalogs()
        entries = validate_catalog_set([parse_catalog(document) for document in documents])
        return SyncSummary(results=tuple(self._sync(entry, sources) for entry in entries))

    def _sync(self, entry: PrivateCatalogEntry, sources: frozenset[str] | None) -> EntrySyncResult:
        skip = _skip_reason(entry, sources)
        if skip is not None:
            return EntrySyncResult(entry.entry_id, SyncOutcome.SKIPPED, skip)
        try:
            if entry.layout is EntryLayout.TAR:
                outcome = self._sync_tar(entry)
            else:
                outcome = self._sync_file(entry)
        except _EntryFailed as failure:
            return EntrySyncResult(entry.entry_id, SyncOutcome.FAILED, failure.reason)
        except (PrivateDataStoreError, PrivateDataUnavailable):
            return EntrySyncResult(entry.entry_id, SyncOutcome.FAILED, REASON_STORE)
        except PrivateCatalogError:
            return EntrySyncResult(entry.entry_id, SyncOutcome.FAILED, REASON_PROVENANCE)
        except PrivateDataConflictError:
            return EntrySyncResult(entry.entry_id, SyncOutcome.FAILED, REASON_CONFLICT)
        except PrivateDataArchiveError:
            return EntrySyncResult(entry.entry_id, SyncOutcome.FAILED, REASON_ARCHIVE)
        except OSError:
            return EntrySyncResult(entry.entry_id, SyncOutcome.FAILED, REASON_LOCAL_IO)
        return EntrySyncResult(entry.entry_id, outcome)

    def _sync_file(self, entry: PrivateCatalogEntry) -> SyncOutcome:
        state = self._area.existing_state(entry.destination)
        if state is not None and state != entry_state(entry):
            raise _EntryFailed(REASON_LOCAL_FILE_DIFFERS)
        record = self._area.read_record(entry.entry_id)
        if record is not None and not record_matches(entry, record):
            raise _EntryFailed(REASON_LOCAL_RECORD_DIFFERS)
        if state is not None and record is not None:
            return SyncOutcome.PRESENT
        with self._area.staging() as staging:
            if state is None:
                staged = self._fetch(entry, staging)
            provenance = self._provenance(entry, staging)
            if state is None:
                self._area.place(staged, entry.destination)
            if record is None:
                self._area.write_record(entry.entry_id, local_record(entry, provenance))
        return SyncOutcome.PRESENT if state is not None else SyncOutcome.DOWNLOADED

    def _sync_tar(self, entry: PrivateCatalogEntry) -> SyncOutcome:
        """Todo o nada por entrada: se extrae a la zona de preparación y se comprueba todo
        antes de colocar ningún miembro. El registro lista los miembros (ADR 0059, #320)."""
        record = self._area.read_record(entry.entry_id)
        known: tuple[ExtractedMember, ...] | None = None
        if record is not None:
            known = record_members(record) if record_matches(entry, record) else None
            if known is None:
                raise _EntryFailed(REASON_LOCAL_RECORD_DIFFERS)
            if self._members_present(entry, known):
                return SyncOutcome.PRESENT
        with self._area.staging() as staging:
            staged = self._fetch(entry, staging)
            provenance = self._provenance(entry, staging)
            members = self._area.extract_tar(staged, entry.destination)
            if known is not None and members != known:
                raise _EntryFailed(REASON_LOCAL_RECORD_DIFFERS)
            if record is None:
                self._area.write_record(entry.entry_id, local_record(entry, provenance, members))
        return SyncOutcome.DOWNLOADED

    def _members_present(
        self, entry: PrivateCatalogEntry, members: tuple[ExtractedMember, ...]
    ) -> bool:
        """¿Están todos los miembros del registro, con sus bytes? Uno distinto es un
        conflicto; uno que falta obliga a volver a bajar el archivo."""
        complete = True
        for member in members:
            state = self._area.existing_state(f"{entry.destination}/{member.path}")
            if state is None:
                complete = False
            elif state != LocalFileState(member.sha256, member.size_bytes):
                raise _EntryFailed(REASON_LOCAL_FILE_DIFFERS)
        return complete

    def _fetch(self, entry: PrivateCatalogEntry, staging: Path) -> Path:
        """Baja el objeto entero (o sus partes, que concatena) a la zona de preparación y
        comprueba su tamaño y sha256 contra el catálogo."""
        staged = staging / _STAGED_OBJECT
        if not entry.parts:
            self._store.download(entry.storage, staged)
        else:
            if not isinstance(entry.storage, ReleaseAsset):
                raise _EntryFailed(REASON_PARTS_STORAGE)
            paths: list[Path] = []
            for index, part in enumerate(entry.parts):
                path = staging / f"parte-{index:04d}"
                self._store.download(ReleaseAsset(tag=entry.storage.tag, asset=part.asset), path)
                if self._area.file_state(path) != LocalFileState(part.sha256, part.size_bytes):
                    raise _EntryFailed(REASON_PART_DIFFERS)
                paths.append(path)
            self._area.assemble(paths, staged)
        if self._area.file_state(staged) != entry_state(entry):
            raise _EntryFailed(REASON_DOWNLOAD_DIFFERS)
        return staged

    def _provenance(self, entry: PrivateCatalogEntry, staging: Path) -> Mapping[str, object]:
        target = staging / _STAGED_PROVENANCE
        self._store.download(entry.provenance, target)
        return parse_provenance(entry.entry_id, self._area.read_small(target))


def _skip_reason(entry: PrivateCatalogEntry, sources: frozenset[str] | None) -> str | None:
    if entry.replaced_by is not None:
        return f"sustituida por {entry.replaced_by}"
    if sources is not None and entry.source not in sources:
        return REASON_SKIP_SOURCE
    return None
