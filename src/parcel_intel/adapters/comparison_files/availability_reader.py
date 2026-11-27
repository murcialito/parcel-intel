"""Disponibilidad de imágenes por tramo en el manifiesto interno de #122 — historia #168.

Lee `<directorio>/<ine>.json` (escrito por `JsonComparisonManifestWriter`) y solo
mira `municipio`, `tramos[].id`, `tramos[].estado` y si alguna `ventanas[].imagenes`
no está vacía. Ignora el resto de claves: el manifiesto es nuestro. Sin fichero:
`None` («sin manifiesto»). Ilegible, con otro formato o de otro municipio:
`ComparisonManifestFileError`.
"""

import json
import re
from collections.abc import Mapping
from pathlib import Path

from parcel_intel.domain.candidate_review import ManifestImageState, is_candidate_id
from parcel_intel.ports.errors import ComparisonManifestFileError

_MUNICIPALITY_RE = re.compile(r"[0-9]{5}")
_STATES = frozenset({"generada", "tramo_demasiado_largo"})


def _has_images(windows: object, where: str) -> bool:
    if not isinstance(windows, list):
        raise ValueError(f"{where}: ventanas debe ser una lista")
    found = False
    for window in windows:
        images = window.get("imagenes") if isinstance(window, dict) else None
        if not isinstance(images, list):
            raise ValueError(f"{where}: cada ventana necesita la lista imagenes")
        found = found or bool(images)
    return found


def parse_availability(document: object, municipality_code: str) -> dict[str, ManifestImageState]:
    if not isinstance(document, dict):
        raise ValueError("se esperaba un objeto JSON")
    if document.get("municipio") != municipality_code:
        raise ValueError("el manifiesto es de otro municipio")
    stretches = document.get("tramos")
    if not isinstance(stretches, list):
        raise ValueError("falta la lista tramos")
    result: dict[str, ManifestImageState] = {}
    for index, stretch in enumerate(stretches):
        where = f"tramo {index}"
        if not isinstance(stretch, dict):
            raise ValueError(f"{where}: debe ser un objeto")
        stretch_id = stretch.get("id")
        if not is_candidate_id(stretch_id):
            raise ValueError(f"{where}: id debe ser de 16 hexadecimales en minúscula")
        assert isinstance(stretch_id, str)
        if stretch_id in result:
            raise ValueError(f"{where}: id repetido")
        status = stretch.get("estado")
        if status not in _STATES:
            raise ValueError(f"{where}: estado no reconocido")
        if status == "tramo_demasiado_largo":
            result[stretch_id] = "tramo_demasiado_largo"
        elif _has_images(stretch.get("ventanas"), where):
            result[stretch_id] = "con_imagenes"
        else:
            result[stretch_id] = "sin_imagenes"
    return result


class JsonComparisonAvailabilityReader:
    """Implementa `ComparisonAvailabilitySource` sobre `<directory>/<ine>.json`."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def availability(self, municipality_code: str) -> Mapping[str, ManifestImageState] | None:
        if not _MUNICIPALITY_RE.fullmatch(municipality_code):
            raise ValueError("código INE de 5 dígitos esperado")
        path = self._directory / f"{municipality_code}.json"
        if not path.is_file():
            return None
        try:
            document = json.loads(path.read_bytes().decode("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as error:
            raise ComparisonManifestFileError(str(path), "JSON ilegible") from error
        try:
            return parse_availability(document, municipality_code)
        except ValueError as error:
            raise ComparisonManifestFileError(str(path), str(error)) from error
