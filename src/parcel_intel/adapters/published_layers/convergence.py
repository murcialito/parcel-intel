"""Serialización de la tabla de convergencia publicada (historia #315, ADR 0057 §6 y §8).

La comparten el sink de tramos a verificar (#315) y el de indicios (#316). Lista blanca
cerrada: la tabla lleva `titulo`, `filas`, `imagenes`, `aviso`, `metodo` y `criterio`; cada
fila, `fuente`, `rotulo`, `tipo_evidencia`, `valor`, `texto`, `anio`, `fecha_consulta`,
`enlaces` y `atribucion`. Ninguna de las dos funciones lleva ids, códigos de municipio ni
geometría: la entidad publicada no los tiene.
"""

from parcel_intel.domain.convergence import VALUE_TEXT, ConvergenceRow
from parcel_intel.domain.public_card import UNKNOWN_YEAR
from parcel_intel.domain.published_convergence import ConvergenceNotes, PublishedConvergence

TABLE_KEYS = ("titulo", "filas", "imagenes", "aviso", "metodo", "criterio")
ROW_KEYS = (
    "fuente",
    "rotulo",
    "tipo_evidencia",
    "valor",
    "texto",
    "anio",
    "fecha_consulta",
    "enlaces",
    "atribucion",
)
SIDECAR_KEYS = ("metodo", "criterio", "umbral_aparece", "red_ign", "fuentes")
SIDECAR_SOURCE_KEYS = ("fuente", "atribucion", "fecha_consulta")


def _year(row: ConvergenceRow) -> str | None:
    """Igual que `ConvergenceRow.strings()`: nada sin cobertura; si no, el año o «año no
    declarado»."""
    if row.value == "sin_cobertura":
        return None
    return row.years.label() if row.years is not None else UNKNOWN_YEAR


def _row(row: ConvergenceRow) -> dict[str, object]:
    return {
        "fuente": row.source_key,
        "rotulo": row.label,
        "tipo_evidencia": row.evidence_kind,
        "valor": row.value,
        "texto": VALUE_TEXT[row.value],
        "anio": _year(row),
        "fecha_consulta": row.consulted_on.isoformat() if row.consulted_on is not None else None,
        "enlaces": list(row.links),
        "atribucion": list(row.attributions),
    }


def convergence_document(table: PublishedConvergence) -> dict[str, object]:
    """La propiedad `convergencia` de una feature."""
    return {
        "titulo": table.title,
        "filas": [_row(row) for row in table.rows],
        "imagenes": table.images_note,
        "aviso": table.warning,
        "metodo": table.method,
        "criterio": table.criterion,
    }


def convergence_sidecar(notes: ConvergenceNotes) -> dict[str, object]:
    """El bloque `convergencia` del `.procedencia.json`."""
    return {
        "metodo": notes.method,
        "criterio": notes.criterion,
        "umbral_aparece": notes.appears_min_fraction,
        "red_ign": notes.ign_network,
        "fuentes": [
            {
                "fuente": key,
                "atribucion": list(attributions),
                "fecha_consulta": consulted.isoformat() if consulted is not None else None,
            }
            for key, attributions, consulted in notes.sources
        ],
    }
