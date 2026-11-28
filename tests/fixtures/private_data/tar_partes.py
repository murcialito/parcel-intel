"""Fixtures SINTÉTICAS de entradas `tar` y en `partes` del repo privado (historia #320).

No se versionan ficheros binarios: cada test construye en `tmp_path` un repo y unos adjuntos
mínimos (`escribir_mundo`) con un `.tar.gz` de 3 miembros en 2 subdirectorios o un fichero
troceado en 3. Los sha256 y tamaños del catálogo se calculan de los bytes. Todo es inventado
(año 2099): ni referencias catastrales ni nombres.
"""

import gzip
import hashlib
import io
import json
import tarfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from tests.application.fake_private_data_store import FakePrivateDataStore

SOURCE = "catastro_inspire"
TAG = "catastro-inspire-28043-20990103"
TAR_ID = "catastro-inspire-28043-teselas-20990103"
PARTS_ID = "catastro-inspire-28043-grande-20990103"
TAR_DESTINATION = "raw/catastro/28043/teselas"
PARTS_DESTINATION = "raw/catastro/28043/grande.bin"

MEMBERS: dict[str, bytes] = {
    "tesela_a/uno.gml": b"<sintetico>uno</sintetico>\n",
    "tesela_a/dos.gml": b"<sintetico>dos</sintetico>\n",
    "tesela_b/tres.gml": b"<sintetico>tres</sintetico>\n",
}
WHOLE = b"fichero sintetico grande de 2099, troceado en tres partes\n" * 3
CHUNKS: tuple[bytes, ...] = (WHOLE[:60], WHOLE[60:120], WHOLE[120:])

Extra = Callable[[tarfile.TarFile], None]


def tar_gz(members: Mapping[str, bytes], extra: Extra | None = None) -> bytes:
    """`.tar.gz` determinista con los ficheros dados y, si se pide, miembros adicionales
    (enlaces, rutas hostiles...) añadidos por `extra`."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(data))
        if extra is not None:
            extra(archive)
    return gzip.compress(buffer.getvalue(), mtime=0)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(data: object) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()


def _entry(entry_id: str, destination: str, adjunto: str, payload: bytes) -> dict[str, Any]:
    return {
        "id": entry_id,
        "fuente": SOURCE,
        "producto": "Producto sintético",
        "municipio_ine": "28043",
        "url": "https://example.invalid/sintetico",
        "fecha_descarga": "2099-01-03",
        "licencia": "Licencia sintética de prueba (historia #320)",
        "publicable": False,
        "restricciones_uso": ["solo uso interno", "fixture sintética: no es un dato real"],
        "sha256": sha256(payload),
        "tamano_bytes": len(payload),
        "almacen": {"tipo": "release", "etiqueta": TAG, "adjunto": adjunto},
        "formato": "fichero",
        "destino": destination,
        "procedencia": f"procedencia/{SOURCE}/{entry_id}.procedencia.json",
    }


def tar_entry(payload: bytes, entry_id: str = TAR_ID) -> dict[str, Any]:
    entry = _entry(entry_id, TAR_DESTINATION, f"{entry_id}.tar.gz", payload)
    entry["formato"] = "tar"
    return entry


def parts_entry(
    chunks: Sequence[bytes] = CHUNKS, whole: bytes = WHOLE, entry_id: str = PARTS_ID
) -> dict[str, Any]:
    entry = _entry(entry_id, PARTS_DESTINATION, f"{entry_id}.bin", whole)
    entry["partes"] = [
        {
            "adjunto": f"{entry_id}.bin.{index:03d}",
            "sha256": sha256(chunk),
            "tamano_bytes": len(chunk),
        }
        for index, chunk in enumerate(chunks, start=1)
    ]
    return entry


def escribir_mundo(
    root: Path, entries: Sequence[dict[str, Any]], assets: Mapping[str, bytes]
) -> FakePrivateDataStore:
    """Escribe bajo `root` un repo con un catálogo de `entries`, su procedencia y los
    adjuntos de la etiqueta `TAG` (nombre → bytes); devuelve el almacén falso sobre él."""
    repo = root / "repo"
    assets_dir = root / "adjuntos"
    (repo / "catalogo").mkdir(parents=True)
    catalog = {"esquema": 1, "fuente": SOURCE, "entradas": list(entries)}
    (repo / "catalogo" / f"{SOURCE}.json").write_bytes(_json(catalog))
    for entry in entries:
        path = repo / entry["procedencia"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_json({"fuente": SOURCE, "nota": "procedencia sintética de #320"}))
    (assets_dir / TAG).mkdir(parents=True)
    for name, data in assets.items():
        (assets_dir / TAG / name).write_bytes(data)
    return FakePrivateDataStore(repo_dir=repo, assets_dir=assets_dir)


def mundo_tar(root: Path, payload: bytes | None = None) -> tuple[FakePrivateDataStore, bytes]:
    data = tar_gz(MEMBERS) if payload is None else payload
    store = escribir_mundo(root, [tar_entry(data)], {f"{TAR_ID}.tar.gz": data})
    return store, data


def mundo_partes(
    root: Path, chunks: Sequence[bytes] = CHUNKS, whole: bytes = WHOLE
) -> FakePrivateDataStore:
    assets = {f"{PARTS_ID}.bin.{i:03d}": chunk for i, chunk in enumerate(chunks, start=1)}
    return escribir_mundo(root, [parts_entry(chunks, whole)], assets)
