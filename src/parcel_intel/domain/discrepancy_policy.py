"""Política de comparación y de redistribución entre fuentes (historia #31,
ADR 0030). Todas las tablas declarativas, en un único sitio.

Las cadenas de `SourceKind` ordenan las fuentes (`sorted()`); nunca se itera
un `set`/`frozenset` sin ordenar (PYTHONHASHSEED).
"""

import dataclasses

from parcel_intel.domain.discrepancy import DiscrepancyKind
from parcel_intel.domain.discrepancy_report import (
    DiscrepancyRecord,
    MunicipalDiscrepancyReport,
    TrailEvidence,
)
from parcel_intel.domain.geometry import Geometry, TrailShape
from parcel_intel.domain.trail import METRIC_SRID, SourceKind

_HISTORICAL: tuple[SourceKind, ...] = ("planimetria_historica", "mtn50_historico")

ABSENCE_PAIRS: frozenset[tuple[SourceKind, SourceKind]] = frozenset(
    {
        # (presente en A, se espera en B): B debería contener A.
        ("via_pecuaria_oficial", "catastro_vt"),
        ("via_pecuaria_oficial", "ign_red_transporte"),
        ("via_pecuaria_oficial", "planimetria_historica"),
        ("via_pecuaria_oficial", "mtn50_historico"),
        ("catastro_vt", "ign_red_transporte"),
        *((h, "catastro_vt") for h in _HISTORICAL),
        *((h, "ign_red_transporte") for h in _HISTORICAL),
    }
)
"""Solo para estos pares se conservan `AUSENTE_EN_FUENTE` y `SOLAPE` (el solape
parcial de A en B es una ausencia parcial, igual de asimétrica). Ninguna capa
espera contener los caminos de la red del IGN (pueden ser privados o nuevos) y
las vías pecuarias solo contienen vías pecuarias. Umbral de producto a revisar
con el fundador."""

REDISTRIBUTABLE_SOURCES: frozenset[SourceKind] = frozenset(
    {
        "via_pecuaria_oficial",  # CC BY 4.0 Comunidad de Madrid
        "ign_red_transporte",  # CC BY 4.0 IGN (confirmado en #24)
        "planimetria_historica",  # CC BY 4.0 IGN
        "mtn50_historico",  # CC BY 4.0 IGN
    }
)
"""Denegar por defecto: lo que no está aquí no se redistribuye. `catastro_vt`
queda fuera por su licencia INSPIRE de 2016 (REGISTRY.md, historia 0021)."""


def kinds_kept(
    a: SourceKind, b: SourceKind, subject_is_anejo: bool = False
) -> frozenset[DiscrepancyKind]:
    """Tipos de discrepancia que se conservan al evaluar un trazado de `a`
    contra la fuente `b`. Un anejo (abrevadero, descansadero) es una superficie
    de descanso, no un trazado que deba aparecer en otra fuente: no es sujeto
    de ausencia ni de solape."""
    kept: set[DiscrepancyKind] = set()
    if (a, b) in ABSENCE_PAIRS and not subject_is_anejo:
        kept.update(("AUSENTE_EN_FUENTE", "SOLAPE"))
    if a < b:  # dirección canónica: el desplazamiento es simétrico
        kept.add("DESPLAZAMIENTO")
    return frozenset(kept)


def _redact_evidence(evidence: TrailEvidence) -> TrailEvidence:
    if evidence.source in REDISTRIBUTABLE_SOURCES:
        return evidence
    return dataclasses.replace(evidence, geometry=None)


_REDACTED_ZONE: TrailShape = Geometry(rings=(), srid=METRIC_SRID)


def redact_for_publication(report: MunicipalDiscrepancyReport) -> MunicipalDiscrepancyReport:
    """Versión publicable: quita la geometría de los trazados cuya fuente no es
    redistribuible, y la zona si la fuente del lado A no lo es. Conserva
    identificador, procedencia, medidas y confianza (producto transformado)."""
    records = []
    for record in report.records:
        zone_redacted = record.discrepancy.subject.source.kind not in REDISTRIBUTABLE_SOURCES
        discrepancy = record.discrepancy
        if zone_redacted:
            discrepancy = dataclasses.replace(discrepancy, zone=_REDACTED_ZONE)
        records.append(
            DiscrepancyRecord(
                record_id=record.record_id,
                discrepancy=discrepancy,
                trails=tuple(_redact_evidence(e) for e in record.trails),
                zone_redacted=zone_redacted or record.zone_redacted,
            )
        )
    return dataclasses.replace(report, records=tuple(records), redacted=True)
