"""Escritor del kit de campo en `<salida>/kit/<ine>/tramos.{gpx,kml}` (historia #213).

Todo o nada: serializa y mide todos los ficheros (y el índice) en memoria antes de escribir el
primero; ninguno pasa de `MAX_KIT_FILE_BYTES`. Escritura atómica. Nunca borra nada.
"""

import json
from collections.abc import Sequence
from pathlib import Path

from parcel_intel.adapters.kit_campo.formats import KIT_NOTICE, kit_description, to_gpx, to_kml
from parcel_intel.adapters.road_layer_files.common import write_atomic
from parcel_intel.domain.kit_campo import MAX_KIT_FILE_BYTES, MunicipalKit, PublishedKitFile
from parcel_intel.ports.kit_campo import KitSinkError

KIT_DIR = "kit"
INDEX_NAME = "indice.json"
_FORMATS = ("gpx", "kml")


def _json_text(document: object) -> str:
    return json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def _size(text: str) -> int:
    return len(text.encode("utf-8"))


class FileFieldKitSink:
    def __init__(self, output_dir: Path, repository_url: str) -> None:
        self._output_dir = output_dir
        self._repository_url = repository_url

    def write(self, kits: Sequence[MunicipalKit]) -> tuple[PublishedKitFile, ...]:
        files: dict[str, str] = {}
        entries: dict[str, dict[str, object]] = {}
        published: list[PublishedKitFile] = []
        for kit in kits:
            code = kit.municipality_code
            texts = {
                "gpx": to_gpx(kit, self._repository_url),
                "kml": to_kml(kit, self._repository_url),
            }
            sizes: dict[str, int] = {}
            for extension in _FORMATS:
                relative = f"{KIT_DIR}/{code}/tramos.{extension}"
                text = texts[extension]
                sizes[extension] = _size(text)
                files[relative] = text
                files[relative + ".procedencia.json"] = _json_text(self._provenance(kit, relative))
                published.append(PublishedKitFile(code, relative, sizes[extension]))
            entries[code] = {
                "ine": code,
                "capas": [layer.layer for layer in kit.layers],
                "capas_no_publicadas": list(kit.missing),
                "ficheros": {
                    extension: {
                        "ruta": f"{code}/tramos.{extension}",
                        "bytes": sizes[extension],
                    }
                    for extension in _FORMATS
                },
            }
        files[f"{KIT_DIR}/{INDEX_NAME}"] = _json_text(self._index(entries))
        for relative, text in files.items():
            if _size(text) > MAX_KIT_FILE_BYTES:
                raise KitSinkError(
                    f"{relative}: {_size(text)} bytes, por encima de {MAX_KIT_FILE_BYTES}"
                )
        for relative, text in files.items():
            path = self._output_dir / relative
            write_atomic(path.parent, path.name, text)
        return tuple(published)

    def _provenance(self, kit: MunicipalKit, relative: str) -> dict[str, object]:
        return {
            "aviso": KIT_NOTICE,
            "capas": [
                {
                    "capa": layer.layer,
                    "fichero": f"{layer.layer}/{kit.municipality_code}.geojson",
                    "fuente": layer.source,
                    "licencia": layer.license,
                    "atribucion": list(layer.attribution),
                    "aviso": layer.notice,
                    "tramos": len(layer.tramos),
                }
                for layer in kit.layers
            ],
            "capas_no_publicadas": list(kit.missing),
            "descripcion": kit_description(kit, self._repository_url),
            "fecha_generacion": kit.generated_on.isoformat(),
            "fichero": relative,
            "licencia": " | ".join(sorted({layer.license for layer in kit.layers})),
            "municipio": kit.municipality_code,
            "url": self._repository_url,
        }

    def _index(self, new_entries: dict[str, dict[str, object]]) -> dict[str, object]:
        entries: dict[str, object] = {}
        path = self._output_dir / KIT_DIR / INDEX_NAME
        if path.is_file():
            try:
                previous = json.loads(path.read_text(encoding="utf-8"))
                for item in previous["municipios"]:
                    entries[str(item["ine"])] = item
            except (ValueError, KeyError, TypeError) as error:
                raise KitSinkError(f"{path}: índice existente no válido: {error}") from error
        entries.update(new_entries)
        return {"aviso": KIT_NOTICE, "municipios": [entries[code] for code in sorted(entries)]}
