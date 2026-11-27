"""Candidato a corte: entidad y tipos de señal (historia #126, ADR 0039 §5).

Un `CutCandidate` es un **indicio a verificar**, nunca un dictamen: un tramo de
un trazado que debería ser público, en discrepancia con el camino actual, en el
que alguna señal apoya una condición (no se distingue / dentro de un cierre).
No tiene ningún campo de titularidad, de propietario ni de referencia catastral
de finca. Solo stdlib.
"""

from dataclasses import dataclass
from typing import Literal

from parcel_intel.domain.discrepancy import Measurement, TrailRef
from parcel_intel.domain.discrepancy_criterion import METRIC_SRID, CriterionRef
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.provenance import Provenance

CutCondition = Literal["no_se_distingue", "dentro_de_cierre"]  # (i), (ii)
SignalVerdict = Literal["apoya", "no_apoya", "sin_dato"]

CONDITION_ORDER: tuple[CutCondition, ...] = ("no_se_distingue", "dentro_de_cierre")
"""Orden fijo de las condiciones en `CutCandidate.conditions`."""


@dataclass(frozen=True)
class SignalRef:
    identifier: str  # "parcela_no_camino", "visibilidad_ortofoto", ...
    version: int
    condition: CutCondition


@dataclass(frozen=True)
class SignalReading:
    """Lo que devuelve una señal para un trazado A."""

    signal: SignalRef
    verdicts: tuple[SignalVerdict, ...]  # una por muestra de `trail_samples(A)`, mismo orden
    evidence: tuple[Measurement, ...]  # parámetros aplicados (p. ej. margen_borde_parcela_m)
    provenance: tuple[Provenance, ...]  # datos usados, ordenados, con su marca de redistribución


@dataclass(frozen=True)
class SignalSupport:
    """Una señal que concurre en un candidato."""

    signal: SignalRef
    support_fraction: float  # f_s, 3 decimales
    no_data_fraction: float  # n_s, 3 decimales
    provenance: tuple[Provenance, ...]


@dataclass(frozen=True)
class CutCandidate:
    candidate_id: str  # 16 hex de sha256: método+versión, municipio, fuente y trazado A, tramo
    municipality_code: str  # INE
    subject: TrailRef  # trazado que debería ser público (lado A del Discrepancy)
    discrepancy_ids: tuple[str, ...]  # record_id de los registros base que toca; nunca vacío
    stretch: MultiLineGeometry  # tramo, EPSG:25830, nunca vacío
    conditions: tuple[CutCondition, ...]  # orden fijo `CONDITION_ORDER`; nunca vacío
    signals: tuple[SignalSupport, ...]  # solo las que concurren (f_s > 0), por identificador
    confidence: float  # [0, 1], 3 decimales; orden relativo, no probabilidad
    evidence: tuple[Measurement, ...]  # orden fijo: longitud_tramo_m, longitud_base_m, ...
    method: CriterionRef  # CUT_METHOD

    def __post_init__(self) -> None:
        if self.stretch.srid != METRIC_SRID:
            raise ValueError(
                f"El tramo debe estar en EPSG:{METRIC_SRID}; recibido EPSG:{self.stretch.srid}."
            )
        if not any(len(line) >= 2 for line in self.stretch.lines):
            raise ValueError("El tramo de un candidato no puede estar vacío.")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"La confianza debe estar en [0, 1]; recibida {self.confidence}.")
        if not self.conditions:
            raise ValueError("Un candidato necesita al menos una condición.")
        if not self.discrepancy_ids:
            raise ValueError("Un candidato necesita al menos un registro base.")
        for condition in self.conditions:
            if not any(support.signal.condition == condition for support in self.signals):
                raise ValueError(f"La condición {condition!r} no tiene ninguna señal que la apoye.")


@dataclass(frozen=True)
class SignalRunSummary:
    """Por municipio y señal: qué se ejecutó y qué faltó."""

    signal: SignalRef
    status: Literal["ejecutada", "sin_datos"]
    reason: str | None
    provenance: tuple[Provenance, ...]


@dataclass(frozen=True)
class MunicipalCutCandidateReport:
    municipality_code: str
    method: CriterionRef
    discrepancy_criterion_id: str  # criterion_id del informe base
    base_record_ids: tuple[str, ...]  # registros base considerados, ordenados
    signals: tuple[SignalRunSummary, ...]
    candidates: tuple[CutCandidate, ...]  # orden canónico
