"""Ficha pública de un candidato a corte: texto validado y aviso (historia #169).

Función pura y determinista: `CutCandidate` → `PublicCandidateCard`. Ningún LLM, ninguna
red, ningún reloj. Los textos los validó el fundador (comentario citado en
`CANDIDATE_VALIDATION`) y se publican tal cual; cambiar cualquiera sin actualizar esa
marca hace fallar un test. «Candidato a corte» es un término interno: la ficha habla de
«tramo a verificar» y nunca de corte, cierre ni finca.

La ficha **no lleva geometría ni identificadores** de trazado o de parcela, ni cuántas
parcelas son. Reutiliza de #16 (`public_card`) la confianza en palabras, el aviso, las
políticas de fuente y las palabras vetadas; no cambia ninguno de sus textos.
"""

import hashlib
import math
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

from parcel_intel.domain.cut_candidate import CutCandidate, SignalSupport
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.public_card import (
    CATASTRO_ATTRIBUTION,
    OMISSION_NOTICE,
    OMITTED_SOURCE_LABEL,
    SOURCE_POLICY,
    WARNING,
    ConfidenceLevel,
    PublicSource,
    TextValidation,
    _is_publishable,
    _public_source,
    _year,
    confidence_level,
)

CATASTRO_SIGNAL_ID = "parcela_no_camino"
LENGTH_MEASUREMENT = "longitud_tramo_m"
CATASTRO_PROVENANCE_PREFIX = "catastro"
"""Las `Provenance.source` de Catastro empiezan así (`catastro_wfs_cp`, ...)."""

# --- Textos validados por el fundador (CA3). ----------------------------------
CANDIDATE_LAYER_NAME = "Tramos a verificar (no son un dictamen)"
CANDIDATE_LABEL = "Tramo a verificar: trazado sin equivalente en el camino actual"

_FIRST_SENTENCE = (
    "Indicio a verificar: este tramo de {longitud} m figura como {fuente_a}, {anio_a}, "
    "y no aparece en el camino actual del IGN."
)
_CATASTRO_SENTENCE = (
    " Al cruzarlo con datos de la Dirección General del Catastro (consultados el {fecha}), "
    "el {porcentaje} % del tramo cae dentro de parcelas que no figuran como vía de "
    "comunicación."
)
_LAST_SENTENCE = " Conviene comprobarlo sobre el terreno."

CANDIDATE_TEMPLATE_BASE = _FIRST_SENTENCE + _LAST_SENTENCE
CANDIDATE_TEMPLATE_WITH_CATASTRO = _FIRST_SENTENCE + _CATASTRO_SENTENCE + _LAST_SENTENCE

CATASTRO_WARNING_ADDENDUM = (
    "Dato derivado de la Dirección General del Catastro, consultado el {fecha}. No es "
    "información catastral, no es fehaciente y puede haber cambiado desde la consulta."
)

CATASTRO_PUBLIC_LABEL = "Dirección General del Catastro"

CANDIDATE_VALIDATION = TextValidation(
    validated_by_founder=date(2026, 11, 27),
    validation_url="https://github.com/murcialito/paso-comun/issues/103#issuecomment-7214693909",
    text_hash="ef7bd590524e8bd54912161cccc1bb3a80af445bb635b7f87c0206e4d09f2244",
)


def candidate_text_fingerprint() -> str:
    """Texto canónico de todo lo que el fundador valida en la ficha del candidato."""
    return "\n".join(
        [
            f"CAPA|{CANDIDATE_LAYER_NAME}",
            f"ETIQUETA|{CANDIDATE_LABEL}",
            f"PLANTILLA_CATASTRO|{CANDIDATE_TEMPLATE_WITH_CATASTRO}",
            f"PLANTILLA_BASE|{CANDIDATE_TEMPLATE_BASE}",
            f"AVISO|{WARNING}",
            f"AVISO_CATASTRO|{CATASTRO_WARNING_ADDENDUM}",
        ]
    )


def compute_candidate_text_hash() -> str:
    return hashlib.sha256(candidate_text_fingerprint().encode("utf-8")).hexdigest()


class MissingCatastroDateError(ValueError):
    """El candidato tiene la señal de Catastro pero ninguna procedencia de Catastro con
    fecha de consulta: no se puede citar ni avisar, así que no se produce ficha."""


@dataclass(frozen=True)
class PublicCandidateCard:
    layer_name: str
    label: str
    text: str
    warning: str
    confidence_level: ConfidenceLevel
    sources: tuple[PublicSource, ...]
    method: str  # "<identificador> v<versión>"
    omission_notice: str | None

    def strings(self) -> Iterator[str]:
        """Todo el texto visible de la ficha (para inspeccionarlo)."""
        yield self.layer_name
        yield self.label
        yield self.text
        yield self.warning
        yield self.confidence_level
        yield self.method
        if self.omission_notice is not None:
            yield self.omission_notice
        for item in self.sources:
            yield from (item.label, item.source, item.url, item.license, item.attribution)

    def as_text(self) -> str:
        return "\n".join(self.strings())


def _round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def _format_date(value: date) -> str:
    return f"{value.day:02d}/{value.month:02d}/{value.year}"


def _catastro_support(candidate: CutCandidate) -> SignalSupport | None:
    for support in candidate.signals:
        if support.signal.identifier == CATASTRO_SIGNAL_ID:
            return support
    return None


def _latest_catastro_provenance(candidate: CutCandidate, support: SignalSupport) -> Provenance:
    entries = [
        item for item in support.provenance if item.source.startswith(CATASTRO_PROVENANCE_PREFIX)
    ]
    if not entries:
        raise MissingCatastroDateError(
            f"El candidato {candidate.candidate_id} apoya la señal {CATASTRO_SIGNAL_ID} sin "
            "ninguna procedencia de Catastro con fecha de consulta."
        )
    return max(entries, key=lambda item: item.retrieved_at)


def _length(candidate: CutCandidate) -> int:
    for item in candidate.evidence:
        if item.name == LENGTH_MEASUREMENT:
            return _round_half_up(item.value)
    raise KeyError(LENGTH_MEASUREMENT)


def build_candidate_card(
    candidate: CutCandidate, *, for_publication: bool = True
) -> PublicCandidateCard:
    """Ficha de `candidate`. Con `for_publication` (por defecto) se omite la evidencia
    del trazado si su fuente no tiene licencia de redistribución verificada y la ficha
    lo indica, sin sustituirla por nada."""
    subject = candidate.subject.source
    publishable = not for_publication or _is_publishable(subject)
    support = _catastro_support(candidate)
    catastro = _latest_catastro_provenance(candidate, support) if support is not None else None

    values: dict[str, str] = {
        "longitud": str(_length(candidate)),
        "fuente_a": (
            SOURCE_POLICY[subject.kind].public_label if publishable else OMITTED_SOURCE_LABEL
        ),
        "anio_a": _year(subject),
    }
    sources: list[PublicSource] = []
    if publishable:
        sources.append(_public_source("sujeto", subject))

    warning = WARNING
    if support is not None and catastro is not None:
        values["fecha"] = _format_date(catastro.retrieved_at)
        values["porcentaje"] = str(_round_half_up(support.support_fraction * 100))
        text = CANDIDATE_TEMPLATE_WITH_CATASTRO.format(**values)
        warning = f"{WARNING} {CATASTRO_WARNING_ADDENDUM.format(**values)}"
        sources.append(
            PublicSource(
                role="contraparte",
                label=CATASTRO_PUBLIC_LABEL,
                data_year=None,
                source=catastro.source,
                url=catastro.url,
                retrieved_at=catastro.retrieved_at,
                license=catastro.license or "",
                attribution=CATASTRO_ATTRIBUTION,
            )
        )
    else:
        text = CANDIDATE_TEMPLATE_BASE.format(**values)

    return PublicCandidateCard(
        layer_name=CANDIDATE_LAYER_NAME,
        label=CANDIDATE_LABEL,
        text=text,
        warning=warning,
        confidence_level=confidence_level(candidate.confidence),
        sources=tuple(sources),
        method=f"{candidate.method.identifier} v{candidate.method.version}",
        omission_notice=None if publishable else OMISSION_NOTICE,
    )
