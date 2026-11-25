"""Criterio de discrepancia entre trazados: el ÚNICO sitio con sus números
(historia #14, CA4; ADR 0025).

Todas las tolerancias y constantes están **razonadas, no calibradas**: son
umbrales de producto a revisar con el fundador y a calibrar contra el
conjunto de validación antes de publicar nada (#16). Cualquier cambio en esta
tabla, en las constantes o en el algoritmo de `domain/discrepancy.py` sube
`CRITERION.version` en la misma PR.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

SourceKind = Literal[
    "via_pecuaria_oficial",  # IDEM Zonas:IDEM_MA_VIAS_PECUARIAS
    "catastro_vt",  # parcelas 9xxx con subparcela VT
    "ign_red_transporte",  # roadlink, OGC API Features
    "planimetria_historica",  # planimetrías/minutas IGN 1870-1880, vectorizadas
    "mtn50_historico",  # MTN50 1.ª edición (1881…), vectorizado
]
# PNOA no figura: es referencia visual, no trazado (REGISTRY.md, historia 0021).


@dataclass(frozen=True)
class SourcePrecision:
    positional_tolerance_m: float  # error posicional típico de un eje de camino en esa fuente
    rationale: str  # de dónde sale, citando REGISTRY.md


SOURCE_PRECISION: Mapping[SourceKind, SourcePrecision] = MappingProxyType(
    {
        "catastro_vt": SourcePrecision(
            5.0,
            "Cartografía catastral rústica vectorial, digitalizada sobre ortofoto; "
            "error de pocos metros (REGISTRY.md, historia 0021).",
        ),
        "ign_red_transporte": SourcePrecision(
            5.0,
            "Red vectorial del IGN, capturada sobre PNOA/BTN25, fecha_alta 2017-2026 "
            "(REGISTRY.md, historia 0021).",
        ),
        "via_pecuaria_oficial": SourcePrecision(
            10.0,
            "Cartografía informativa de 2014, no deslinde; franja ya cartografiada cuyo "
            "borde es menos preciso que un eje vectorial (REGISTRY.md, historia 0021).",
        ),
        "planimetria_historica": SourcePrecision(
            40.0,
            "Minutas manuscritas 1870-1880, georreferenciadas a posteriori sobre puntos "
            "de control (REGISTRY.md, historias 0021 y #17).",
        ),
        "mtn50_historico": SourcePrecision(
            50.0,
            "Escala 1:50.000 (error gráfico 0,2 mm = 10 m) más la georreferenciación de "
            "una hoja de 1881 (REGISTRY.md, historias 0021 y #17).",
        ),
    }
)

SOURCE_LABEL: Mapping[SourceKind, str] = MappingProxyType(
    {
        "via_pecuaria_oficial": "vías pecuarias (IDEM)",
        "catastro_vt": "Catastro, vías de dominio público",
        "ign_red_transporte": "red de transporte del IGN",
        "planimetria_historica": "planimetría del IGN",
        "mtn50_historico": "MTN50 histórico del IGN",
    }
)

METRIC_SRID = 25830  # ETRS89 / UTM 30N: el criterio solo mide aquí, nunca reproyecta
SAMPLE_STEP_M = 5.0  # paso de muestreo a lo largo del trazado
SEARCH_RADIUS_FACTOR = 3.0  # radio de búsqueda = 3 × tolerancia del par
CONFIDENCE_SCALE_M = 25.0  # escala de penalización por tolerancia en la confianza
# Longitud a partir de la cual una ausencia o una no coincidencia pesa entera.
MIN_SIGNIFICANT_LENGTH_M = 100.0
DECIMALS = 3  # redondeo de confianza y evidencia (determinismo, CA12)


@dataclass(frozen=True)
class CriterionRef:
    identifier: str
    version: int


CRITERION = CriterionRef(identifier="discrepancia_trazados", version=1)


def pair_tolerance_m(a: SourceKind, b: SourceKind) -> float:
    """Tolerancia del par de fuentes: suma cuadrática de sus tolerancias
    posicionales (errores independientes), `math.hypot(t_a, t_b)`."""
    return math.hypot(
        SOURCE_PRECISION[a].positional_tolerance_m,
        SOURCE_PRECISION[b].positional_tolerance_m,
    )


def search_radius_m(tolerance_m: float) -> float:
    return SEARCH_RADIUS_FACTOR * tolerance_m


def correspondence_radius_m(a: SourceKind, b: SourceKind) -> float:
    """Distancia máxima a la que el criterio todavía mira un trazado de la
    fuente `b` al evaluar uno de la fuente `a`. `compare_trail` ya descarta
    las contrapartes cuyo bbox no corta el bbox del sujeto ampliado este
    radio; un prefiltro espacial externo (#15) que conserve al menos esas
    contrapartes da exactamente el mismo resultado que la fuerza bruta."""
    return search_radius_m(pair_tolerance_m(a, b))
