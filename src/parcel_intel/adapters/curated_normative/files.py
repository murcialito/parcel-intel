"""Lectura estricta del catálogo de citas normativas — historia #187, ADR 0060.

`<root>/catalogo.json` (por defecto `curated/normativa/`) es entrada humana versionada en
un repo **público**. Formato cerrado:

    {"version": 1, "huella_catalogo": "<64 hex>",
     "citas": [{"id", "norma", "identificador", "articulo", "fecha_norma",
                "ultima_actualizacion", "texto", "texto_sha256", "url", "consultado",
                "licencia", "version_catalogo", "tipos_fuente", "nota"?}]}

Cualquier otra clave rechaza el fichero entero (así no cabe ningún campo de finca, tramo,
municipio ni persona). Todo o nada: un fallo no devuelve nada. Con stdlib `json`, no
pydantic: sus errores repiten el valor de entrada (lección de #168). Los mensajes solo
nombran campos, posiciones («cita 3») e ids ya validados; las claves desconocidas se
cuentan sin nombrarlas.
"""

import json
from datetime import date
from pathlib import Path

from parcel_intel.domain.normative_citation import (
    SOURCE_KINDS,
    InvalidNormativeCitationError,
    NormativeCatalog,
    NormativeCitation,
    catalog_fingerprint,
    is_citation_id,
)
from parcel_intel.domain.parcel_identifiers import CADASTRAL_REFERENCE_RE, PARCEL_LOCATOR_RE
from parcel_intel.domain.trail import SourceKind
from parcel_intel.ports.errors import NormativeCatalogFileError

FILE_NAME = "catalogo.json"

_TOP_KEYS = frozenset({"version", "huella_catalogo", "citas"})
_REQUIRED_KEYS = frozenset(
    {
        "id",
        "norma",
        "identificador",
        "articulo",
        "fecha_norma",
        "ultima_actualizacion",
        "texto",
        "texto_sha256",
        "url",
        "consultado",
        "licencia",
        "version_catalogo",
        "tipos_fuente",
    }
)
_OPTIONAL_KEYS = frozenset({"nota"})


class _Invalid(Exception):
    """Motivo de rechazo, ya sin valores; se convierte en `NormativeCatalogFileError`."""


def _object(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise _Invalid(f"{what} debe ser un objeto JSON")
    return {str(k): v for k, v in value.items()}


def _check_keys(
    data: dict[str, object], required: frozenset[str], allowed: frozenset[str], what: str
) -> None:
    present = {key for key, value in data.items() if value is not None or key in required}
    missing = sorted(required - present)
    unknown = len(set(data) - allowed)
    if missing or unknown:
        parts = []
        if missing:
            parts.append(f"faltan {', '.join(missing)}")
        if unknown:
            parts.append(f"{unknown} claves desconocidas")
        raise _Invalid(f"{what}: {'; '.join(parts)}")


def _text(data: dict[str, object], key: str, where: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise _Invalid(f"{where}: {key}: debe ser texto")
    return value


def _optional_text(data: dict[str, object], key: str, where: str) -> str | None:
    if data.get(key) is None:
        return None
    return _text(data, key, where)


def _date(data: dict[str, object], key: str, where: str) -> date:
    value = data[key]
    if not isinstance(value, str) or len(value) != 10:
        raise _Invalid(f"{where}: {key}: debe ser una fecha AAAA-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise _Invalid(f"{where}: {key}: debe ser una fecha AAAA-MM-DD") from exc


def _int(data: dict[str, object], key: str, where: str) -> int:
    value = data[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise _Invalid(f"{where}: {key}: debe ser un entero")
    return value


def _kinds(data: dict[str, object], key: str, where: str) -> tuple[SourceKind, ...]:
    value = data[key]
    if not isinstance(value, list):
        raise _Invalid(f"{where}: {key}: debe ser una lista")
    kinds: list[SourceKind] = []
    for item in value:
        match = next((kind for kind in SOURCE_KINDS if kind == item), None)
        if match is None:
            raise _Invalid(
                f"{where}: {key}: valor no reconocido (válidos: {', '.join(SOURCE_KINDS)})"
            )
        kinds.append(match)
    return tuple(sorted(kinds))


def _parse_citation(raw: object, position: int) -> NormativeCitation:
    where = f"cita {position}"
    data = _object(raw, where)
    citation_id = data.get("id")
    if not is_citation_id(citation_id):
        _check_keys(data, _REQUIRED_KEYS, _REQUIRED_KEYS | _OPTIONAL_KEYS, where)
        raise _Invalid(f"{where}: id: no cumple ^[a-z0-9]+(-[a-z0-9]+)*$ (máximo 80 caracteres)")
    assert isinstance(citation_id, str)  # garantizado por is_citation_id
    _check_keys(data, _REQUIRED_KEYS, _REQUIRED_KEYS | _OPTIONAL_KEYS, citation_id)
    try:
        return NormativeCitation(
            citation_id=citation_id,
            norm_title=_text(data, "norma", citation_id),
            boe_id=_text(data, "identificador", citation_id),
            article=_text(data, "articulo", citation_id),
            norm_date=_date(data, "fecha_norma", citation_id),
            last_updated=_date(data, "ultima_actualizacion", citation_id),
            text=_text(data, "texto", citation_id),
            url=_text(data, "url", citation_id),
            retrieved_at=_date(data, "consultado", citation_id),
            license=_text(data, "licencia", citation_id),
            catalog_version=_int(data, "version_catalogo", citation_id),
            text_sha256=_text(data, "texto_sha256", citation_id),
            source_kinds=_kinds(data, "tipos_fuente", citation_id),
            note=_optional_text(data, "nota", citation_id),
        )
    except InvalidNormativeCitationError as exc:
        raise _Invalid(str(exc)) from exc


def parse_catalog(text: str) -> NormativeCatalog:
    """Valida el texto completo de un `catalogo.json`; lanza `_Invalid` con el motivo."""
    if CADASTRAL_REFERENCE_RE.search(text) or PARCEL_LOCATOR_RE.search(text):
        raise _Invalid("contiene una referencia catastral o un localizador de parcela")
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _Invalid(f"no es JSON válido (línea {exc.lineno}, columna {exc.colno})") from exc
    top = _object(document, "el documento")
    _check_keys(top, _TOP_KEYS, _TOP_KEYS, "el documento")
    version = _int(top, "version", "el documento")
    if version < 1:
        raise _Invalid("el documento: version: debe ser un entero >= 1")
    fingerprint = _text(top, "huella_catalogo", "el documento")
    raw_citations = top["citas"]
    if not isinstance(raw_citations, list):
        raise _Invalid("el documento: citas: debe ser una lista")
    citations = [_parse_citation(raw, position) for position, raw in enumerate(raw_citations, 1)]
    seen: set[str] = set()
    for citation in citations:
        if citation.citation_id in seen:
            raise _Invalid(f"{citation.citation_id}: id: repetido")
        seen.add(citation.citation_id)
        if citation.catalog_version != version:
            raise _Invalid(
                f"{citation.citation_id}: version_catalogo: no coincide con la version "
                "del documento"
            )
    ordered = tuple(sorted(citations, key=lambda citation: citation.citation_id))
    computed = catalog_fingerprint(version, ordered)
    if fingerprint != computed:
        raise _Invalid(f"el documento: huella_catalogo: no coincide (huella calculada: {computed})")
    try:
        return NormativeCatalog(version=version, citations=ordered, fingerprint=fingerprint)
    except InvalidNormativeCitationError as exc:  # pragma: no cover - ya comprobado arriba
        raise _Invalid(str(exc)) from exc


class CuratedNormativeCatalogFile:
    """Implementa `NormativeCatalogSource` sobre `<root>/catalogo.json`."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def path(self) -> Path:
        return self._root / FILE_NAME

    def catalog(self) -> NormativeCatalog:
        path = self.path
        if not path.is_file():
            raise NormativeCatalogFileError(
                str(path), "no existe (un catálogo vacío es un fichero válido sin citas)"
            )
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise NormativeCatalogFileError(str(path), "no es UTF-8") from exc
        except OSError as exc:
            raise NormativeCatalogFileError(str(path), "no se puede leer") from exc
        try:
            return parse_catalog(text)
        except _Invalid as exc:
            raise NormativeCatalogFileError(str(path), str(exc)) from exc
