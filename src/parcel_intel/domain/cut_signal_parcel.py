"""Señal `parcela_no_camino` de los candidatos a corte (historia #127, ADR 0039 §6 y §7).

Criterio: dentro de la zona base, ¿cae el eje del trazado dentro de una parcela
catastral rústica ordinaria (número < 9000), a una distancia de su borde de al
menos el margen del par de fuentes, y fuera de toda infraestructura (número
>= 9000)? Es un **indicio a verificar**: una parcela no es un cierre.

La huella (`ParcelFootprint`) no tiene campo de referencia catastral: quien la
construye la descarta, así que no llega al dominio de la señal ni al candidato.
Sin titularidad. Función pura, solo stdlib.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from parcel_intel.domain.cut_candidate import (
    SignalReading,
    SignalRef,
    SignalVerdict,
)
from parcel_intel.domain.discrepancy import Measurement, TrailSample
from parcel_intel.domain.discrepancy_criterion import DECIMALS
from parcel_intel.domain.geometry import (
    BBox,
    Geometry,
    Point,
    Ring,
    bbox_of,
    point_in_any_ring,
)
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.spatial_index import GridIndex

FootprintKind = Literal["ordinaria", "infraestructura", "otra"]

PARCEL_SIGNAL = SignalRef("parcela_no_camino", 1, "dentro_de_cierre")
"""Su peso (`w_s` = 0,6) está en `cut_method.SIGNAL_WEIGHTS`."""

MARGIN_EVIDENCE = "margen_borde_parcela_m"


@dataclass(frozen=True)
class ParcelFootprint:
    """Huella de una parcela: solo geometría y clase, nunca la referencia."""

    geometry: Geometry  # EPSG:25830
    kind: FootprintKind


def index_footprints(footprints: Sequence[ParcelFootprint]) -> GridIndex[ParcelFootprint]:
    """Índice de rejilla de las huellas (las vacías no entran)."""
    items: list[tuple[BBox, ParcelFootprint]] = []
    for footprint in footprints:
        if any(len(ring) >= 3 for ring in footprint.geometry.rings):
            items.append((bbox_of(footprint.geometry), footprint))
    return GridIndex.build(items)


def _distance_to_segment(point: Point, a: Point, b: Point) -> float:
    px, py = point
    dx, dy = b[0] - a[0], b[1] - a[1]
    squared = dx * dx + dy * dy
    if squared == 0.0:
        return math.hypot(px - a[0], py - a[1])
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / squared))
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def _distance_to_ring_boundary(point: Point, ring: Ring) -> float:
    """Distancia al anillo tratado como polilínea cerrada."""
    return min(
        _distance_to_segment(point, a, b) for a, b in zip(ring, (*ring[1:], ring[0]), strict=False)
    )


def _boundary_distance(point: Point, geometry: Geometry) -> float:
    """Distancia al borde de los anillos de la huella que contienen el punto."""
    return min(
        _distance_to_ring_boundary(point, ring)
        for ring in geometry.rings
        if len(ring) >= 3 and point_in_any_ring(point, (ring,))
    )


def _contains(footprint: ParcelFootprint, point: Point) -> bool:
    return any(
        len(ring) >= 3 and point_in_any_ring(point, (ring,)) for ring in footprint.geometry.rings
    )


def parcel_verdict(
    point: Point, candidates: Sequence[ParcelFootprint], margin_m: float
) -> SignalVerdict:
    """Veredicto de una muestra con las huellas que pueden contenerla."""
    supported = False
    for footprint in candidates:
        if not _contains(footprint, point):
            continue
        if footprint.kind == "infraestructura":
            return "no_apoya"  # un enclave >= 9000 anula el apoyo (ADR 0039 §6)
        if footprint.kind == "ordinaria" and _boundary_distance(point, footprint.geometry) >= (
            margin_m
        ):
            supported = True
    return "apoya" if supported else "no_apoya"


def read_parcel_signal(
    samples: Sequence[TrailSample],
    footprints: GridIndex[ParcelFootprint],
    margin_m: float,
    no_data: Sequence[bool],
    provenance: tuple[Provenance, ...] = (),
) -> SignalReading:
    """Un veredicto por muestra, en el mismo orden. `no_data[i]` marca las muestras
    cuya tesela no se pudo obtener: su veredicto es `sin_dato`."""
    if len(no_data) != len(samples):
        raise ValueError(f"no_data trae {len(no_data)} marcas para {len(samples)} muestras.")
    verdicts: list[SignalVerdict] = []
    for sample, missing in zip(samples, no_data, strict=True):
        if missing:
            verdicts.append("sin_dato")
            continue
        x, y = sample.point
        verdicts.append(parcel_verdict(sample.point, footprints.query((x, y, x, y)), margin_m))
    return SignalReading(
        signal=PARCEL_SIGNAL,
        verdicts=tuple(verdicts),
        evidence=(Measurement(MARGIN_EVIDENCE, round(margin_m, DECIMALS), "m"),),
        provenance=provenance,
    )
