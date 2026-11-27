"""Escritor del proyecto de QField en `<salida>/kit/<ine>/qfield/` (historia #222).

Todo o nada: construye y mide todos los ficheros en memoria antes de escribir el primero; ninguno
pasa de `MAX_KIT_FILE_BYTES`. Escritura atómica. Nunca borra nada. No toca `kit/indice.json` salvo
que se pida (`include_in_index`): el ZIP no se enlaza hasta anotar su apertura real en QField.
"""

import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from parcel_intel.adapters.kit_campo.formats import KIT_NOTICE, kit_description
from parcel_intel.adapters.kit_campo.qfield import (
    build_geopackage,
    build_qgs,
    build_readme,
    build_zip,
    project_base,
)
from parcel_intel.adapters.kit_campo.sink import INDEX_NAME, KIT_DIR
from parcel_intel.domain.kit_campo import (
    INCIDENCIA_FORM,
    MAX_KIT_FILE_BYTES,
    MunicipalKit,
    PublishedKitFile,
)
from parcel_intel.ports.kit_campo import KitSinkError

QFIELD_DIR = "qfield"


def _json_text(document: object) -> str:
    return json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


class FileFieldProjectSink:
    def __init__(self, output_dir: Path, repository_url: str) -> None:
        self._output_dir = output_dir
        self._repository_url = repository_url

    def write(
        self, kits: Sequence[MunicipalKit], include_in_index: bool
    ) -> tuple[PublishedKitFile, ...]:
        files: dict[str, bytes] = {}
        published: list[PublishedKitFile] = []
        entries: dict[str, dict[str, object]] = {}
        for kit in kits:
            code = kit.municipality_code
            base = project_base(code)
            try:
                gpkg = build_geopackage(kit)
            except ValueError as error:
                raise KitSinkError(f"{code}: {error}") from error
            qgs = build_qgs(kit).encode("utf-8")
            readme = build_readme(kit).encode("utf-8")
            archive = build_zip({f"{base}.gpkg": gpkg, f"{base}.qgs": qgs, "LEEME.txt": readme})
            prefix = f"{KIT_DIR}/{code}/{QFIELD_DIR}"
            contents = {
                f"{prefix}/{base}.gpkg": gpkg,
                f"{prefix}/{base}.qgs": qgs,
                f"{prefix}/LEEME.txt": readme,
                f"{prefix}/{base}.zip": archive,
            }
            provenance = _json_text(self._provenance(kit, f"{prefix}/{base}.zip", contents))
            contents[f"{prefix}/{base}.zip.procedencia.json"] = provenance.encode("utf-8")
            for relative, data in contents.items():
                files[relative] = data
                published.append(PublishedKitFile(code, relative, len(data)))
            entries[code] = {
                "ruta": f"{code}/{QFIELD_DIR}/{base}.zip",
                "bytes": len(archive),
            }
        index_text: str | None = None
        if include_in_index:
            index_text = _json_text(self._index(entries))
            files[f"{KIT_DIR}/{INDEX_NAME}"] = index_text.encode("utf-8")
        for relative, data in files.items():
            if len(data) > MAX_KIT_FILE_BYTES:
                raise KitSinkError(
                    f"{relative}: {len(data)} bytes, por encima de {MAX_KIT_FILE_BYTES}"
                )
        for relative, data in files.items():
            path = self._output_dir / relative
            write_atomic_bytes(path, data)
        return tuple(published)

    def _provenance(
        self, kit: MunicipalKit, relative: str, contents: dict[str, bytes]
    ) -> dict[str, object]:
        return {
            "aviso": KIT_NOTICE,
            "advertencia_formulario": INCIDENCIA_FORM.warning,
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
            "estado": "sin comprobar en QField: no se enlaza ni se despliega en el sitio",
            "fecha_generacion": kit.generated_on.isoformat(),
            "ficheros": {Path(name).name: len(data) for name, data in sorted(contents.items())},
            "fichero": relative,
            "licencia": " | ".join(sorted({layer.license for layer in kit.layers})),
            "municipio": kit.municipality_code,
            "url": self._repository_url,
        }

    def _index(self, new_entries: dict[str, dict[str, object]]) -> dict[str, object]:
        entries: dict[str, dict[str, object]] = {}
        path = self._output_dir / KIT_DIR / INDEX_NAME
        if path.is_file():
            try:
                previous = json.loads(path.read_text(encoding="utf-8"))
                for item in previous["municipios"]:
                    entries[str(item["ine"])] = dict(item)
            except (ValueError, KeyError, TypeError) as error:
                raise KitSinkError(f"{path}: índice existente no válido: {error}") from error
            document_notice = previous.get("aviso", KIT_NOTICE)
        else:
            document_notice = KIT_NOTICE
        for code, qfield in new_entries.items():
            entries.setdefault(code, {"ine": code})["qfield"] = qfield
        return {"aviso": document_notice, "municipios": [entries[c] for c in sorted(entries)]}


def write_atomic_bytes(path: Path, data: bytes) -> None:
    """Como `write_atomic`, pero para bytes (GeoPackage y ZIP)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
