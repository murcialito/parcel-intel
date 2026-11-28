"""Catálogo cerrado y versionado de citas normativas — historia #187, ADR 0060.

Una cita es el **texto literal** de un artículo, copiado del texto consolidado del BOE por
una persona (ningún LLM), con su procedencia completa (identificador, URL, fecha de consulta,
última actualización y licencia) y una huella sha256 del literal. Se asocia a uno o varios
tipos de fuente (`SourceKind`), nunca a una finca, un tramo ni un municipio.

El literal es el único campo donde se admiten las palabras vetadas de #16 («titular»): las
leyes las usan. Los demás campos de texto las rechazan, igual que las referencias catastrales
y los localizadores de parcela.

Los mensajes de error tienen la forma «<id>: <campo>: <motivo>» (o «cita: <campo>: …» si el
id aún no es válido) y **nunca repiten el valor rechazado** (lección de #168). La única cifra
que dan es la huella *calculada* de un texto, que es lo que quien edita necesita copiar.

Solo stdlib; importa solo de `domain`.
"""

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import get_args

from parcel_intel.domain.parcel_identifiers import CADASTRAL_REFERENCE_RE, PARCEL_LOCATOR_RE
from parcel_intel.domain.public_card import banned_words_in
from parcel_intel.domain.trail import SourceKind

BOE_CONSOLIDATED_URL_PREFIX = "https://www.boe.es/buscar/act.php?id="
BOE_REUSE_LICENSE = (
    "Condiciones de reutilización de la Agencia Estatal Boletín Oficial del Estado "
    "(https://www.boe.es/informacion/aviso_legal/index.php)"
)
BOE_SOURCE_NOTICE = "Fuente de los datos: Agencia Estatal Boletín Oficial del Estado"
BOE_INFORMATIVE_NOTICE = (
    "Texto consolidado de carácter meramente informativo. Únicamente tienen la "
    "consideración de oficiales y auténticos los textos publicados en la edición "
    "electrónica del Boletín Oficial del Estado."
)
CITATION_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
BOE_ID_RE = re.compile(r"BOE-A-[0-9]{4}-[0-9]+")
_ANCHOR_RE = re.compile(r"[a-z0-9]+")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
MAX_CITATION_ID_LENGTH = 80
MAX_NORM_LENGTH = 300
MAX_ARTICLE_LENGTH = 100
MAX_NOTE_LENGTH = 500
MAX_TEXT_LENGTH = 20_000

SOURCE_KINDS: tuple[SourceKind, ...] = tuple(sorted(get_args(SourceKind)))


class InvalidNormativeCitationError(ValueError):
    """Mensaje «<citation_id>: <campo>: <motivo>»; nunca repite el valor rechazado."""


_Fail = Callable[[str, str], InvalidNormativeCitationError]


def text_fingerprint(text: str) -> str:
    """sha256 hex de `text.encode("utf-8")`, sin normalizar nada."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_citation_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= MAX_CITATION_ID_LENGTH
        and CITATION_ID_RE.fullmatch(value) is not None
    )


def _free_text_problem(value: object, max_length: int) -> str | None:
    """Motivo por el que un campo de texto que no es el literal no vale, o `None`.
    El motivo no cita el texto ni la palabra que lo rechaza."""
    if not isinstance(value, str) or not value.strip():
        return "debe ser texto no vacío"
    if len(value) > max_length:
        return f"pasa de {max_length} caracteres"
    if CADASTRAL_REFERENCE_RE.search(value) or PARCEL_LOCATOR_RE.search(value):
        return "contiene una referencia catastral o un localizador de parcela"
    if banned_words_in(value):
        return "contiene palabras vetadas (#16); solo se admiten en el texto literal"
    return None


def _is_date(value: object) -> bool:
    return isinstance(value, date)


@dataclass(frozen=True)
class NormativeCitation:
    citation_id: str
    norm_title: str
    boe_id: str
    article: str
    norm_date: date
    last_updated: date
    text: str
    url: str
    retrieved_at: date
    license: str
    catalog_version: int
    text_sha256: str
    source_kinds: tuple[SourceKind, ...]
    note: str | None = None

    def __post_init__(self) -> None:
        if not is_citation_id(self.citation_id):
            raise InvalidNormativeCitationError(
                f"cita: id: no cumple ^[a-z0-9]+(-[a-z0-9]+)*$ con un máximo de "
                f"{MAX_CITATION_ID_LENGTH} caracteres"
            )
        cid = self.citation_id

        def fail(field: str, reason: str) -> InvalidNormativeCitationError:
            return InvalidNormativeCitationError(f"{cid}: {field}: {reason}")

        for field, value, limit in (
            ("norma", self.norm_title, MAX_NORM_LENGTH),
            ("articulo", self.article, MAX_ARTICLE_LENGTH),
        ):
            problem = _free_text_problem(value, limit)
            if problem is not None:
                raise fail(field, problem)
        if self.note is not None:
            problem = _free_text_problem(self.note, MAX_NOTE_LENGTH)
            if problem is not None:
                raise fail("nota", problem)
        if self.license != BOE_REUSE_LICENSE:
            raise fail("licencia", "debe ser exactamente las condiciones de reutilización del BOE")
        if not isinstance(self.boe_id, str) or not BOE_ID_RE.fullmatch(self.boe_id):
            raise fail("identificador", "no cumple ^BOE-A-AAAA-N$")
        if not self._url_matches():
            raise fail(
                "url",
                "debe ser el texto consolidado del BOE de su identificador "
                f"({BOE_CONSOLIDATED_URL_PREFIX}<identificador>, con ancla #[a-z0-9]+ opcional)",
            )
        for field, value in (
            ("fecha_norma", self.norm_date),
            ("ultima_actualizacion", self.last_updated),
            ("consultado", self.retrieved_at),
        ):
            if not _is_date(value):
                raise fail(field, "debe ser una fecha")
        if self.last_updated < self.norm_date:
            raise fail("ultima_actualizacion", "anterior a fecha_norma")
        if self.retrieved_at < self.norm_date:
            raise fail("consultado", "anterior a fecha_norma")
        if self.retrieved_at < self.last_updated:
            raise fail("consultado", "anterior a ultima_actualizacion")
        self._check_text(fail)
        if (
            not isinstance(self.catalog_version, int)
            or isinstance(self.catalog_version, bool)
            or self.catalog_version < 1
        ):
            raise fail("version_catalogo", "debe ser un entero >= 1")
        self._check_kinds(fail)

    def _url_matches(self) -> bool:
        if not isinstance(self.url, str):
            return False
        base = BOE_CONSOLIDATED_URL_PREFIX + self.boe_id
        if self.url == base:
            return True
        anchor_prefix = base + "#"
        return self.url.startswith(anchor_prefix) and (
            _ANCHOR_RE.fullmatch(self.url[len(anchor_prefix) :]) is not None
        )

    def _check_text(self, fail: _Fail) -> None:
        text = self.text
        if not isinstance(text, str) or not text:
            raise fail("texto", "debe ser texto no vacío")
        if text != text.strip():
            raise fail("texto", "empieza o acaba en espacio en blanco")
        if not unicodedata.is_normalized("NFC", text):
            raise fail("texto", "no está en forma Unicode NFC")
        if len(text) > MAX_TEXT_LENGTH:
            raise fail("texto", f"pasa de {MAX_TEXT_LENGTH} caracteres")
        if CADASTRAL_REFERENCE_RE.search(text):
            raise fail("texto", "contiene una referencia catastral")
        if not isinstance(self.text_sha256, str) or not _SHA256_RE.fullmatch(self.text_sha256):
            raise fail("texto_sha256", "debe ser 64 hexadecimales en minúscula")
        computed = text_fingerprint(text)
        if self.text_sha256 != computed:
            raise fail("texto_sha256", f"no coincide con el texto (huella calculada: {computed})")

    def _check_kinds(self, fail: _Fail) -> None:
        kinds = self.source_kinds
        if not isinstance(kinds, tuple) or not kinds:
            raise fail("tipos_fuente", "debe ser una lista no vacía")
        if any(kind not in SOURCE_KINDS for kind in kinds):
            raise fail("tipos_fuente", f"valor no reconocido (válidos: {', '.join(SOURCE_KINDS)})")
        if len(set(kinds)) != len(kinds):
            raise fail("tipos_fuente", "tiene valores repetidos")
        if list(kinds) != sorted(kinds):
            raise fail("tipos_fuente", "no está en orden alfabético")


@dataclass(frozen=True)
class CitationAttribution:
    """Lo que debe acompañar a una cita mostrada (CA9; licencia del BOE)."""

    source_notice: str
    url: str
    retrieved_at: date
    last_updated: date
    informative_notice: str


def citation_attribution(citation: NormativeCitation) -> CitationAttribution:
    return CitationAttribution(
        source_notice=BOE_SOURCE_NOTICE,
        url=citation.url,
        retrieved_at=citation.retrieved_at,
        last_updated=citation.last_updated,
        informative_notice=BOE_INFORMATIVE_NOTICE,
    )


def citation_payload(citation: NormativeCitation) -> dict[str, object]:
    """La cita con las claves del formato de `curated/normativa/catalogo.json`."""
    return {
        "id": citation.citation_id,
        "norma": citation.norm_title,
        "identificador": citation.boe_id,
        "articulo": citation.article,
        "fecha_norma": citation.norm_date.isoformat(),
        "ultima_actualizacion": citation.last_updated.isoformat(),
        "texto": citation.text,
        "texto_sha256": citation.text_sha256,
        "url": citation.url,
        "consultado": citation.retrieved_at.isoformat(),
        "licencia": citation.license,
        "version_catalogo": citation.catalog_version,
        "tipos_fuente": list(citation.source_kinds),
        "nota": citation.note,
    }


def catalog_fingerprint(version: int, citations: Sequence[NormativeCitation]) -> str:
    """sha256 del JSON canónico (`sort_keys`, separadores compactos, `ensure_ascii`) de la
    versión y las citas ordenadas por id: el orden del fichero no cuenta (CA11)."""
    ordered = sorted(citations, key=lambda citation: citation.citation_id)
    payload = {"version": version, "citas": [citation_payload(c) for c in ordered]}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class NormativeCatalog:
    version: int
    citations: tuple[NormativeCitation, ...]
    fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise InvalidNormativeCitationError("catálogo: version: debe ser un entero >= 1")
        ids = [citation.citation_id for citation in self.citations]
        seen: set[str] = set()
        for citation_id in ids:
            if citation_id in seen:
                raise InvalidNormativeCitationError(f"{citation_id}: id: repetido")
            seen.add(citation_id)
        for citation in self.citations:
            if citation.catalog_version != self.version:
                raise InvalidNormativeCitationError(
                    f"{citation.citation_id}: version_catalogo: no coincide con la version "
                    "del catálogo"
                )
        if ids != sorted(ids):
            raise InvalidNormativeCitationError("catálogo: citas: no están ordenadas por id")
        computed = catalog_fingerprint(self.version, self.citations)
        if self.fingerprint != computed:
            raise InvalidNormativeCitationError(
                f"catálogo: huella_catalogo: no coincide (huella calculada: {computed})"
            )

    def for_source(self, kind: SourceKind) -> tuple[NormativeCitation, ...]:
        return tuple(citation for citation in self.citations if kind in citation.source_kinds)

    def by_source(self) -> Mapping[SourceKind, tuple[NormativeCitation, ...]]:
        """Las 5 claves de `SourceKind`, en orden de `sorted()`; tupla vacía si no hay citas."""
        return MappingProxyType({kind: self.for_source(kind) for kind in SOURCE_KINDS})


def build_catalog(version: int, citations: Sequence[NormativeCitation]) -> NormativeCatalog:
    """Catálogo con las citas ordenadas por id y su huella calculada (para tests y
    para quien prepara el fichero)."""
    ordered = tuple(sorted(citations, key=lambda citation: citation.citation_id))
    return NormativeCatalog(
        version=version, citations=ordered, fingerprint=catalog_fingerprint(version, ordered)
    )
