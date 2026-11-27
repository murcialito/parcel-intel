"""Escritor del fichero interno de estrechamiento de vías pecuarias (historia #243).

Una `FeatureCollection` en EPSG:25830 con una feature por pieza evaluada (Polygon o
MultiPolygon, la franja de la vía) y el resultado en las propiedades. Serialización
determinista y escritura atómica (formato común de ADR 0030). Fichero **interno**: deriva
de Catastro y nunca se publica. Sin titularidad ni referencias catastrales; las propiedades
son una lista blanca.
"""

from pathlib import Path

from parcel_intel.adapters.road_layer_files.common import (
    CRS,
    dump_collection,
    provenance_properties,
    round_coords,
    write_atomic,
)
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.width_signal import MunicipalWidthReport, PieceWidthResult

_VALUE_DECIMALS = 3


class WidthSignalFileError(ValueError):
    """El informe no se puede escribir."""


def _closed(ring: tuple[tuple[float, float], ...]) -> tuple[tuple[float, float], ...]:
    return ring if ring[0] == ring[-1] else (*ring, ring[0])


def _geometry(geometry: Geometry) -> dict[str, object]:
    if not geometry.rings:
        raise WidthSignalFileError("pieza sin geometría")
    rings = [round_coords(_closed(ring)) for ring in geometry.rings]
    if len(rings) == 1:
        return {"type": "Polygon", "coordinates": [rings[0]]}
    return {"type": "MultiPolygon", "coordinates": [[ring] for ring in rings]}


def _feature(piece: PieceWidthResult) -> dict[str, object]:
    assessment = piece.assessment
    evidence = assessment.evidence
    properties: dict[str, object] = {
        "codigo_via": piece.trail_code,
        "nombre": piece.name,
        "resultado": assessment.outcome,
        "ratio": None if assessment.ratio is None else round(assessment.ratio, _VALUE_DECIMALS),
        "confianza": None
        if assessment.confidence is None
        else round(assessment.confidence, _VALUE_DECIMALS),
        "motivo": assessment.reason,
        "evidencia": None
        if evidence is None
        else {
            "tipo_via": evidence.trail_type,
            "anchura_oficial_m": round(evidence.official_width_m, _VALUE_DECIMALS),
            "anchura_catastral_m": round(evidence.cadastral_width_m, _VALUE_DECIMALS),
            "parcelas_de_camino": evidence.road_parcel_count,
        },
    }
    return {
        "type": "Feature",
        "id": piece.piece_id,
        "geometry": _geometry(piece.geometry),
        "properties": properties,
    }


def report_to_geojson_text(report: MunicipalWidthReport) -> str:
    collection: dict[str, object] = {
        "type": "FeatureCollection",
        "crs": CRS,
        "properties": {
            "municipio": report.municipality_code,
            "metodo": report.method,
            "procedencia_vias": [provenance_properties(p) for p in report.trail_provenance],
            "procedencia_catastro": [provenance_properties(p) for p in report.cadastral_provenance],
            "aviso": report.notice,
        },
        "features": [_feature(piece) for piece in report.pieces],
    }
    return dump_collection(collection)


class GeoJsonWidthSignalWriter:
    """Implementa `WidthSignalSink`: `<directory>/<ine>.geojson`, atómico."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def write(self, report: MunicipalWidthReport) -> None:
        write_atomic(
            self._directory, f"{report.municipality_code}.geojson", report_to_geojson_text(report)
        )
