"""Indicios de discrepancia publicables de un municipio (historia #94, ADR 0044).

Parte del informe **publicable** de #32 (ya redactado, ADR 0030 §4) y deja, por
indicio, solo la zona del lado A y la ficha pública de #16 (`build_card`). No
añade ni redacta ningún texto.

Reglas (ADR 0044 §4, con la corrección del ADR 0041):
- la zona sale del trazado A, así que la fuente A debe ser redistribuible; si
  no lo es (Catastro), la zona va redactada y el indicio se omite y se cuenta;
- la contraparte puede ser una fuente redistribuible o Catastro: un «no aparece
  en Catastro» es información derivada que no reproduce el dato original
  (ADR 0041 §1) y se publica con la atribución de `SOURCE_POLICY`;
- ningún identificador de trazado, referencia catastral, medida ni confianza
  numérica sale de aquí: solo `public_id`, la zona y la ficha.

El dominio no conoce EPSG:4326: la zona sigue en EPSG:25830.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Final

from parcel_intel.domain.discrepancy import Discrepancy, DiscrepancyKind
from parcel_intel.domain.discrepancy_detection import zone_coordinates
from parcel_intel.domain.discrepancy_policy import REDISTRIBUTABLE_SOURCES
from parcel_intel.domain.discrepancy_report import MunicipalDiscrepancyReport
from parcel_intel.domain.geometry import Geometry, TrailShape
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.public_card import PublicCard, build_card
from parcel_intel.domain.publication import PublishableLayer
from parcel_intel.domain.published_layers import PublishedFile
from parcel_intel.domain.trail import SourceKind

DISCREPANCY_LAYER_ID: Final = "discrepancias"
DISCREPANCY_LAYER_SOURCE = "Parcel Intel, indicios de discrepancia entre trazados"
DISCREPANCY_LAYER_LICENSE = "CC BY 4.0"  # ADR 0035 §2: datos derivados publicados

PUBLISHABLE_COUNTERPART_SOURCES: frozenset[SourceKind] = REDISTRIBUTABLE_SOURCES | {"catastro_vt"}
"""Fuentes que pueden ser contraparte de un indicio publicado. Catastro entra por el
ADR 0041: se publica el indicio y su evidencia derivada, nunca su geometría (que es
la del lado B y no se publica) ni sus referencias."""

CADASTRAL_REFERENCE_RE = re.compile(
    r"\b\d{5}[A-Z]\d{8}(?:\d{4}[A-Z]{2})?\b"  # rústica: 14 o 20 caracteres
    r"|\b\d{7}[A-Z]{2}\d{4}[A-Z](?:\d{4}[A-Z]{2})?\b"  # urbana: 14 o 20 caracteres
)
"""Forma de una referencia catastral. Última barrera del sink y del test de CA3."""

PARCEL_LOCATOR_RE = re.compile(r"[?&](?:poligono|polígono|parcela|refcat)=", re.IGNORECASE)
"""Parámetros de URL que localizan una parcela concreta (ADR 0041 §4: no se publican
números de polígono ni de parcela). También es última barrera del sink."""


class NotPublishableReportError(ValueError):
    """La entrada no es publicable (variante interna, registro sin redactar, sin
    nombre de municipio...). `reason` va en castellano para la CLI."""

    def __init__(self, municipality_code: str, reason: str) -> None:
        super().__init__(f"{municipality_code}: {reason}")
        self.municipality_code = municipality_code
        self.reason = reason


@dataclass(frozen=True)
class PublishedDiscrepancy:
    public_id: str
    zone: TrailShape  # EPSG:25830, lado A; nunca vacía
    card: PublicCard  # build_card(discrepancy) tal cual
    provenance: Provenance  # la del trazado A, de donde sale la zona (cumple HasProvenance)


@dataclass(frozen=True)
class OmittedByLicense:
    subject: int  # lado A no redistribuible (zona redactada), CA4
    counterpart: int  # contraparte fuera de PUBLISHABLE_COUNTERPART_SOURCES

    @property
    def total(self) -> int:
        return self.subject + self.counterpart


@dataclass(frozen=True)
class DiscrepancyLayerPublication:
    municipality_code: str
    municipality_name: str
    criterion_id: str  # "discrepancia_trazados@1"
    content: PublishableLayer[PublishedDiscrepancy]  # pasa la puerta de ADR 0028


@dataclass(frozen=True)
class DiscrepancyLayerBuild:
    publication: DiscrepancyLayerPublication | None  # None si no queda ningún indicio
    omitted: OmittedByLicense


@dataclass(frozen=True)
class DiscrepancyPublicationFailure:
    municipality_code: str
    reason: str


@dataclass(frozen=True)
class DiscrepancyPublicationResult:
    published: tuple[PublishedFile, ...]
    empty: tuple[str, ...]  # municipios sin indicios publicables
    omitted: tuple[tuple[str, OmittedByLicense], ...]  # por municipio, también los vacíos
    failures: tuple[DiscrepancyPublicationFailure, ...]  # si hay alguno, `published` es ()
    # Tipo de cada indicio publicado, por municipio y en orden (para el resumen de la CLI).
    kinds: tuple[tuple[str, tuple[DiscrepancyKind, ...]], ...] = ()


def _base_public_id(discrepancy: Discrepancy) -> str:
    """Solo datos ya públicos: criterio, tipo, fuentes y zona redondeada. No usa
    `record_id`, cuyo hash lleva identificadores de trazado (posibles referencias
    de Catastro) y se podría invertir por fuerza bruta."""
    payload = {
        "criterio": [discrepancy.criterion.identifier, discrepancy.criterion.version],
        "tipo": discrepancy.kind,
        "fuente_a": discrepancy.subject.source.kind,
        "fuente_b": discrepancy.counterpart_source.kind,
        "zona": zone_coordinates(discrepancy),
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def public_indicio_id(discrepancy: Discrepancy) -> str:
    """Identificador público de un indicio (sin sufijo de colisión)."""
    return _base_public_id(discrepancy)


def _has_parts(shape: TrailShape) -> bool:
    parts = shape.rings if isinstance(shape, Geometry) else shape.lines
    return any(parts)


def is_publishable_indicio(discrepancy: Discrepancy) -> bool:
    """Fuente A redistribuible y contraparte en `PUBLISHABLE_COUNTERPART_SOURCES`.

    Es la regla de publicación de un indicio (ADR 0044 §4, ADR 0041): la usan
    `build_discrepancy_layer` y el manifiesto de imágenes de los indicios (#314)."""
    return (
        discrepancy.subject.source.kind in REDISTRIBUTABLE_SOURCES
        and discrepancy.counterpart_source.kind in PUBLISHABLE_COUNTERPART_SOURCES
    )


def build_discrepancy_layer(report: MunicipalDiscrepancyReport) -> DiscrepancyLayerBuild:
    """Indicios publicables de `report`, en su orden canónico.

    Lanza `NotPublishableReportError` si el informe no es la variante publicable,
    si le falta el nombre del municipio o si un registro no redactado tiene una
    fuente A no redistribuible o una zona vacía. Un trazado A cuya procedencia no
    sea `PUBLIC` hace fallar la puerta `PublishableLayer` (`NotRedistributableError`).
    """
    code = report.municipality_code
    if not report.redacted:
        raise NotPublishableReportError(code, "no es la variante publicable del informe")
    if not report.municipality_name:
        raise NotPublishableReportError(
            code,
            "el informe no trae el nombre del municipio; regenera las capas derivadas "
            "y `discrepancias`",
        )
    items: list[PublishedDiscrepancy] = []
    seen: dict[str, int] = {}
    omitted_subject = 0
    omitted_counterpart = 0
    for record in report.records:
        discrepancy = record.discrepancy
        if record.zone_redacted:
            omitted_subject += 1
            continue
        if not is_publishable_indicio(discrepancy):
            if discrepancy.subject.source.kind not in REDISTRIBUTABLE_SOURCES:
                raise NotPublishableReportError(
                    code,
                    f"registro sin redactar con fuente A {discrepancy.subject.source.kind!r}, "
                    "que no es redistribuible",
                )
            omitted_counterpart += 1
            continue
        if not _has_parts(discrepancy.zone):
            raise NotPublishableReportError(code, "registro sin redactar con la zona vacía")
        base = _base_public_id(discrepancy)
        seen[base] = seen.get(base, 0) + 1
        public_id = base if seen[base] == 1 else f"{base}-{seen[base]}"
        items.append(
            PublishedDiscrepancy(
                public_id=public_id,
                zone=discrepancy.zone,
                card=build_card(discrepancy),
                provenance=discrepancy.subject.source.provenance,
            )
        )
    omitted = OmittedByLicense(subject=omitted_subject, counterpart=omitted_counterpart)
    if not items:
        return DiscrepancyLayerBuild(publication=None, omitted=omitted)
    content = PublishableLayer[PublishedDiscrepancy](
        name=f"{DISCREPANCY_LAYER_ID}/{code}", items=tuple(items)
    )
    return DiscrepancyLayerBuild(
        publication=DiscrepancyLayerPublication(
            municipality_code=code,
            municipality_name=report.municipality_name,
            criterion_id=report.criterion_id,
            content=content,
        ),
        omitted=omitted,
    )
