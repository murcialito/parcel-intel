"""Filtro "camino según Catastro" (REGISTRY.md, «Catastro — cómo aparecen los caminos en rústico»).

Un camino es una parcela con número 9000 o superior cuya clase de subparcela
(`Consulta_DNPPP`) es `VT`. Las demás clases de una parcela 9xxx (p. ej. `HG`,
hidrografía natural: río, laguna, arroyo) no son camino. Catastro no prueba la
titularidad: que un arroyo tenga parcela propia no dice nada sobre quién es su dueño.
"""

from collections.abc import Iterable

CLASE_VIA_DE_COMUNICACION = "VT"
PARCELA_MINIMA_DE_DOMINIO_PUBLICO = 9000


def es_camino(clase: str) -> bool:
    """True si la clase de subparcela es `VT` (vía de comunicación de dominio público)."""
    return clase.strip().upper() == CLASE_VIA_DE_COMUNICACION


def es_camino_catastro(parcela: int, clases: Iterable[str]) -> bool:
    """Parcela ≥ 9000 cuyas subparcelas son todas `VT` (y hay al menos una)."""
    lista = list(clases)
    return (
        parcela >= PARCELA_MINIMA_DE_DOMINIO_PUBLICO
        and bool(lista)
        and all(es_camino(c) for c in lista)
    )
