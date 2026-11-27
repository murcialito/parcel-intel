"""Cobertura del visor: qué municipios tienen datos publicados (historia #185, ADR 0051).

El visor abre sobre toda España y resalta los municipios cubiertos; el resto queda en gris
«aún sin cobertura». Para eso publica los contornos de los municipios cubiertos, que son
límites administrativos de referencia, nunca un deslinde.
"""

from dataclasses import dataclass

COVERAGE_LAYER_ID = "cobertura"
COVERAGE_NOTICE = "Límite administrativo de referencia, no es un deslinde."


@dataclass(frozen=True)
class CoverageFile:
    """Fichero de cobertura escrito: ruta relativa al directorio publicado, peso y municipios."""

    path: str
    size_bytes: int
    municipality_codes: tuple[str, ...]
