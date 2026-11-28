"""Lectura estricta de los códigos de inventario de los tramos — historia #288, ADR 0047.

`<root>/<ine>/inventario.json` (por defecto `curated/candidatos/`) es entrada humana
versionada en un repo **público**. Formato cerrado:

    {"municipio": "28043", "prefijo": "COL",
     "codigos": [{"candidate_id": "<16 hex>", "codigo": "COL-001"},
                 {"candidate_id": "<16 hex>", "codigo": "COL-002-Camino de Uceda"}]}

Cualquier clave, valor o texto fuera de lo declarado rechaza el fichero entero.
Con stdlib `json`, no pydantic, y ningún mensaje repite el valor rechazado: solo
campos, posiciones («código 3») y `candidate_id` ya validados; las claves
desconocidas se cuentan sin nombrarlas.
"""

import json
import re
from pathlib import Path

from parcel_intel.domain.candidate_inventory import (
    MUNICIPALITY_PREFIXES,
    InvalidInventoryCodeError,
    InventoryCode,
    check_unique,
)
from parcel_intel.domain.candidate_review import is_candidate_id
from parcel_intel.domain.published_discrepancy import CADASTRAL_REFERENCE_RE, PARCEL_LOCATOR_RE
from parcel_intel.ports.errors import CandidateInventoryFileError

FILE_NAME = "inventario.json"

_MUNICIPALITY_RE = re.compile(r"[0-9]{5}")
_TOP_KEYS = frozenset({"municipio", "prefijo", "codigos"})
_ENTRY_KEYS = frozenset({"candidate_id", "codigo"})


class _Invalid(Exception):
    """Motivo de rechazo, ya sin valores; se convierte en `CandidateInventoryFileError`."""


def _object(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise _Invalid(f"{what} debe ser un objeto JSON")
    return {str(k): v for k, v in value.items()}


def _check_keys(data: dict[str, object], keys: frozenset[str], what: str) -> None:
    missing = sorted(keys - set(data))
    unknown = len(set(data) - keys)
    if missing or unknown:
        parts = []
        if missing:
            parts.append(f"faltan {', '.join(missing)}")
        if unknown:
            parts.append(f"{unknown} claves desconocidas")
        raise _Invalid(f"{what}: {'; '.join(parts)}")


def _parse_entry(raw: object, position: int, municipality_code: str) -> InventoryCode:
    where = f"código {position}"
    data = _object(raw, where)
    candidate_id = data.get("candidate_id")
    if not is_candidate_id(candidate_id):
        _check_keys(data, _ENTRY_KEYS, where)
        raise _Invalid(f"{where}: candidate_id no cumple ^[0-9a-f]{{16}}$")
    assert isinstance(candidate_id, str)  # garantizado por is_candidate_id
    _check_keys(data, _ENTRY_KEYS, candidate_id)
    text = data["codigo"]
    if not isinstance(text, str):
        raise _Invalid(f"{candidate_id}: codigo debe ser texto")
    try:
        return InventoryCode.from_text(candidate_id, text, municipality_code)
    except InvalidInventoryCodeError as exc:
        raise _Invalid(str(exc)) from exc


def parse_inventory(text: str, municipality_code: str) -> tuple[InventoryCode, ...]:
    """Valida el texto completo de un `inventario.json`; lanza `_Invalid` con el motivo."""
    if CADASTRAL_REFERENCE_RE.search(text) or PARCEL_LOCATOR_RE.search(text):
        raise _Invalid("contiene una referencia catastral o un localizador de parcela")
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _Invalid(f"no es JSON válido (línea {exc.lineno}, columna {exc.colno})") from exc
    top = _object(document, "el documento")
    _check_keys(top, _TOP_KEYS, "el documento")
    if top["municipio"] != municipality_code:
        raise _Invalid("municipio no coincide con el directorio")
    expected = MUNICIPALITY_PREFIXES.get(municipality_code)
    if expected is None:
        raise _Invalid("el municipio no tiene prefijo fijado")
    if top["prefijo"] != expected:
        raise _Invalid("prefijo distinto del fijado para el municipio")
    entries = top["codigos"]
    if not isinstance(entries, list):
        raise _Invalid("codigos debe ser una lista")
    codes = tuple(
        _parse_entry(raw, position, municipality_code)
        for position, raw in enumerate(entries, start=1)
    )
    try:
        check_unique(codes)
    except InvalidInventoryCodeError as exc:
        raise _Invalid(str(exc)) from exc
    return codes


class CuratedCandidateInventoryFiles:
    """Implementa `CandidateInventorySource` sobre `<root>/<ine>/inventario.json`."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def path(self, municipality_code: str) -> Path:
        return self._root / municipality_code / FILE_NAME

    def codes(self, municipality_code: str) -> tuple[InventoryCode, ...]:
        if not _MUNICIPALITY_RE.fullmatch(municipality_code):
            raise ValueError("código INE de 5 dígitos esperado")
        path = self.path(municipality_code)
        if not path.is_file():
            return ()
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CandidateInventoryFileError(str(path), "no es UTF-8") from exc
        except OSError as exc:
            raise CandidateInventoryFileError(str(path), "no se puede leer") from exc
        try:
            return parse_inventory(text, municipality_code)
        except _Invalid as exc:
            raise CandidateInventoryFileError(str(path), str(exc)) from exc
