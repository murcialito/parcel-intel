"""Ficha pública de una discrepancia: texto fijo, confianza en palabras y
evidencia al lado (historia #16).

Función pura y determinista: `Discrepancy` → `PublicCard`. Ningún LLM, ningún
dato de titularidad. Los textos los redactó el fundador (aprobados en la
issue #16) y se publican tal cual; cambiar cualquiera sin actualizar
`VALIDATION` hace fallar el test de la marca (CA7).

La ficha **no lleva geometría ni identificadores de trazado**: el visor
(épica #6) pinta la zona aparte. Así, ni la geometría original de Catastro ni
la referencia catastral de una parcela 9xxx salen en la ficha (CA5).
"""

import hashlib
import unicodedata
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Literal

from parcel_intel.domain.discrepancy import Discrepancy, DiscrepancyKind, SourceRef
from parcel_intel.domain.discrepancy_criterion import SOURCE_LABEL, SourceKind

ConfidenceLevel = Literal["baja", "media", "alta"]

# --- Umbrales numérico → nivel: el ÚNICO sitio (CA8). -------------------------
# Propuestos por el desarrollador (a revisar con el fundador): la confianza de
# #14 es `fuerza × CONFIDENCE_SCALE_M / (CONFIDENCE_SCALE_M + tolerancia)`; con
# tolerancias de par de 7-11 m el máximo ronda 0,7-0,8, y con las históricas
# (40-56 m) 0,3-0,4. Por debajo de 0,25 es poco más que ruido; desde 0,5 la
# discrepancia es fuerte para el par de fuentes. El límite inferior de cada
# nivel es inclusivo.
MEDIUM_CONFIDENCE_MIN = 0.25
HIGH_CONFIDENCE_MIN = 0.5


def confidence_level(value: float) -> ConfidenceLevel:
    """Traduce la confianza interna [0, 1] a un nivel en palabras."""
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"La confianza debe estar en [0, 1]; recibido {value!r}.")
    if value >= HIGH_CONFIDENCE_MIN:
        return "alta"
    if value >= MEDIUM_CONFIDENCE_MIN:
        return "media"
    return "baja"


# --- Textos aprobados y su marca de validación (CA1, CA7). --------------------
KIND_LABEL: Mapping[DiscrepancyKind, str] = MappingProxyType(
    {
        "AUSENTE_EN_FUENTE": "Trazado en una fuente y no en otra",
        "DESPLAZAMIENTO": "Desplazamiento entre fuentes",
        "SOLAPE": "Solape parcial",
    }
)

TEMPLATES: Mapping[DiscrepancyKind, str] = MappingProxyType(
    {
        "AUSENTE_EN_FUENTE": (
            "Indicio a verificar: según {fuente_a}, {anio_a} existe un trazado en este "
            "tramo que no aparece en {fuente_b}, {anio_b}."
        ),
        "DESPLAZAMIENTO": (
            "Indicio a verificar: el trazado de {fuente_a} y el de {fuente_b} difieren "
            "unos {n} m en este tramo."
        ),
        "SOLAPE": (
            "Indicio a verificar: el trazado de {fuente_a} coincide en parte con otro "
            "elemento del mapa; conviene comprobarlo sobre el terreno."
        ),
    }
)

WARNING = (
    "Esto no es un dictamen ni afirma que haya ninguna irregularidad. Es un indicio "
    "automático, con la confianza indicada, que debe contrastarse con la administración "
    "competente."
)


@dataclass(frozen=True)
class TextValidation:
    validated_by_founder: date
    validation_url: str
    text_hash: str  # SHA-256 de `text_fingerprint()` en el momento de la validación


VALIDATION = TextValidation(
    validated_by_founder=date(2026, 11, 26),
    validation_url="https://github.com/murcialito/parcel-intel/issues/16#issuecomment-7186000359",
    text_hash="e188f341db01c25879884b6a62d6515321b06819af375a9fa30768fe5ccb651c",
)


def text_fingerprint() -> str:
    """Texto canónico de todo lo que el fundador valida: etiquetas, plantillas y aviso."""
    parts = [f"{kind}|{KIND_LABEL[kind]}|{TEMPLATES[kind]}" for kind in sorted(TEMPLATES)]
    parts.append(f"AVISO|{WARNING}")
    return "\n".join(parts)


def compute_text_hash() -> str:
    return hashlib.sha256(text_fingerprint().encode("utf-8")).hexdigest()


# --- Palabras vetadas (CA4). --------------------------------------------------
BANNED_WORDS = (
    "ilegal",
    "ilegalidad",
    "usurpación",
    "usurpado",
    "delito",
    "invasión",
    "apropiación",
    "propietario",
    "dueño",
    "titular",
)


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def banned_words_in(text: str) -> tuple[str, ...]:
    """Palabras vetadas que aparecen en `text` (sin distinguir mayúsculas ni tildes;
    por subcadena, así que `titularidad` también se detecta)."""
    haystack = _normalize(text)
    return tuple(word for word in BANNED_WORDS if _normalize(word) in haystack)


# --- Licencias y rótulos públicos por fuente (CA5, CA6). ----------------------
@dataclass(frozen=True)
class PublicSourcePolicy:
    public_label: str
    redistribution_verified: bool
    attribution: str  # texto de atribución que debe verse junto a la evidencia


# Verificada = licencia leída o declarada por el proveedor y anotada como
# `confirmado` en REGISTRY.md (historia 0021). La red de transporte del IGN
# figura como `asumido` para ese servicio: no está verificada, así que su
# evidencia se omite en publicación hasta que se confirme.
SOURCE_POLICY: Mapping[SourceKind, PublicSourcePolicy] = MappingProxyType(
    {
        "via_pecuaria_oficial": PublicSourcePolicy(
            SOURCE_LABEL["via_pecuaria_oficial"],
            True,
            "CC BY 4.0 Comunidad de Madrid. Cartografía informativa, no es un deslinde.",
        ),
        "catastro_vt": PublicSourcePolicy(
            "trazado derivado de datos del Catastro",
            True,
            "Producto transformado a partir de datos de la Dirección General del Catastro "
            "(licencia INSPIRE v1.0). No incluye el dato original.",
        ),
        "ign_red_transporte": PublicSourcePolicy(
            SOURCE_LABEL["ign_red_transporte"],
            False,
            "",
        ),
        "planimetria_historica": PublicSourcePolicy(
            SOURCE_LABEL["planimetria_historica"],
            True,
            "Obra derivada de planimetrías del IGN CC-BY 4.0 scne.es",
        ),
        "mtn50_historico": PublicSourcePolicy(
            SOURCE_LABEL["mtn50_historico"],
            True,
            "Obra derivada de MTN50 del IGN CC-BY 4.0 scne.es",
        ),
    }
)

OMITTED_SOURCE_LABEL = "una fuente cuya evidencia no se publica"
OMISSION_NOTICE = (
    "Parte de la evidencia se omite porque su fuente no tiene una licencia de "
    "redistribución verificada."
)
UNKNOWN_YEAR = "año no declarado"


@dataclass(frozen=True)
class PublicSource:
    role: Literal["sujeto", "contraparte"]
    label: str
    data_year: int | None
    source: str
    url: str
    retrieved_at: date
    license: str
    attribution: str


@dataclass(frozen=True)
class PublicCard:
    kind: DiscrepancyKind
    label: str
    text: str
    warning: str
    confidence_level: ConfidenceLevel
    sources: tuple[PublicSource, ...]
    criterion: str  # "<identificador> v<versión>"
    criterion_description: str
    omission_notice: str | None

    def strings(self) -> Iterator[str]:
        """Todo el texto visible de la ficha (para inspeccionarlo)."""
        yield self.label
        yield self.text
        yield self.warning
        yield self.confidence_level
        yield self.criterion
        yield self.criterion_description
        if self.omission_notice is not None:
            yield self.omission_notice
        for item in self.sources:
            yield from (item.label, item.source, item.url, item.license, item.attribution)

    def as_text(self) -> str:
        return "\n".join(self.strings())


CRITERION_DESCRIPTION = (
    "Se compara el trazado de una fuente con los de la otra, a lo largo del tramo, "
    "con una tolerancia según la precisión de cada fuente."
)


def _is_publishable(source: SourceRef) -> bool:
    policy = SOURCE_POLICY[source.kind]
    return policy.redistribution_verified and bool(source.provenance.license)


def _year(source: SourceRef) -> str:
    return str(source.data_date.year) if source.data_date is not None else UNKNOWN_YEAR


def _public_source(role: Literal["sujeto", "contraparte"], source: SourceRef) -> PublicSource:
    policy = SOURCE_POLICY[source.kind]
    return PublicSource(
        role=role,
        label=policy.public_label,
        data_year=source.data_date.year if source.data_date is not None else None,
        source=source.provenance.source,
        url=source.provenance.url,
        retrieved_at=source.provenance.retrieved_at,
        license=source.provenance.license or "",
        attribution=policy.attribution,
    )


def build_card(discrepancy: Discrepancy, *, for_publication: bool = True) -> PublicCard:
    """Ficha de `discrepancy`. Con `for_publication` (por defecto) se omite la
    evidencia de toda fuente sin licencia de redistribución verificada y la
    ficha lo indica, sin sustituirla por nada."""
    subject = discrepancy.subject.source
    other = discrepancy.counterpart_source
    pairs: tuple[tuple[Literal["sujeto", "contraparte"], SourceRef], ...] = (
        ("sujeto", subject),
        ("contraparte", other),
    )
    kept = [(r, s) for r, s in pairs if not for_publication or _is_publishable(s)]
    omitted = len(kept) != len(pairs)

    def label(source: SourceRef) -> str:
        if for_publication and not _is_publishable(source):
            return OMITTED_SOURCE_LABEL
        return SOURCE_POLICY[source.kind].public_label

    values: dict[str, str] = {
        "fuente_a": label(subject),
        "fuente_b": label(other),
        "anio_a": _year(subject),
        "anio_b": _year(other),
    }
    if discrepancy.kind == "DESPLAZAMIENTO":
        values["n"] = f"{discrepancy.measurement('desplazamiento_mediano_m'):.0f}"

    return PublicCard(
        kind=discrepancy.kind,
        label=KIND_LABEL[discrepancy.kind],
        text=TEMPLATES[discrepancy.kind].format(**values),
        warning=WARNING,
        confidence_level=confidence_level(discrepancy.confidence),
        sources=tuple(_public_source(r, s) for r, s in kept),
        criterion=f"{discrepancy.criterion.identifier} v{discrepancy.criterion.version}",
        criterion_description=CRITERION_DESCRIPTION,
        omission_notice=OMISSION_NOTICE if omitted else None,
    )
