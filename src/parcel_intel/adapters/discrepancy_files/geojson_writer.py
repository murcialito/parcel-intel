"""Escritor del fichero estático de discrepancias de un municipio (historia #32,
ADR 0030).

Una `FeatureCollection` en EPSG:25830 con una feature por discrepancia. Dos
variantes: interna (completa, nunca se publica) y publicable (redactada).
Serialización determinista: claves ordenadas, redondeo solo al escribir y sin
fecha de generación. No lleva ningún campo de titularidad ni texto libre: el
tipo va como código y las medidas como números (el texto público es #16).
"""

import json
import os
import tempfile
from pathlib import Path

from parcel_intel.domain.discrepancy import Measurement
from parcel_intel.domain.discrepancy_report import (
    DiscrepancyRecord,
    LayerSummary,
    MunicipalDiscrepancyReport,
    TrailEvidence,
)
from parcel_intel.domain.geometry import Geometry, MultiLineGeometry, TrailShape
from parcel_intel.domain.provenance import Provenance

NOTICE = "Indicios automáticos a verificar; no son un dictamen."
_CRS = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25830"}}
_DECIMALS = 2  # coordenadas y metros (0,01 m)
_CONFIDENCE_DECIMALS = 3


class UnredactedReportError(Exception):
    """El escritor publicable recibió un informe sin redactar: segunda barrera
    tras `redact_for_publication` (nunca se escribe geometría no redistribuible)."""

    def __init__(self, municipality_code: str) -> None:
        super().__init__(
            f"El informe de {municipality_code} no está redactado para publicación; "
            "no se escribe ningún fichero."
        )
        self.municipality_code = municipality_code


def _provenance(provenance: Provenance) -> dict[str, object]:
    return {
        "fuente": provenance.source,
        "url": provenance.url,
        "fecha_descarga": provenance.retrieved_at.isoformat(),
        "licencia": provenance.license,
    }


def _coords(points: tuple[tuple[float, float], ...]) -> list[list[float]]:
    return [[round(x, _DECIMALS), round(y, _DECIMALS)] for x, y in points]


def _geometry(shape: TrailShape) -> dict[str, object] | None:
    """GeoJSON de una forma; `None` si no tiene partes (nada que dibujar)."""
    if isinstance(shape, Geometry):
        if not shape.rings:
            return None
        if len(shape.rings) == 1:
            return {"type": "Polygon", "coordinates": [_coords(shape.rings[0])]}
        return {
            "type": "MultiPolygon",
            "coordinates": [[_coords(ring)] for ring in shape.rings],
        }
    assert isinstance(shape, MultiLineGeometry)
    if not shape.lines:
        return None
    if len(shape.lines) == 1:
        return {"type": "LineString", "coordinates": _coords(shape.lines[0])}
    return {"type": "MultiLineString", "coordinates": [_coords(line) for line in shape.lines]}


def _trail(evidence: TrailEvidence, side: str) -> dict[str, object]:
    geometry = _geometry(evidence.geometry) if evidence.geometry is not None else None
    item: dict[str, object] = {
        "id": evidence.trail_id,
        "lado": side,
        "fuente": evidence.source,
        "procedencia": _provenance(evidence.provenance),
        "fecha_dato": evidence.data_date.isoformat() if evidence.data_date else None,
        "geometria": geometry,
    }
    if evidence.geometry is None:
        item["geometria_omitida"] = "licencia"
    return item


def _measure(measurement: Measurement) -> float:
    """Metros a 2 decimales; fracciones a 3 (como la confianza)."""
    decimals = _CONFIDENCE_DECIMALS if measurement.unit == "fraccion" else _DECIMALS
    return round(measurement.value, decimals)


def _feature(record: DiscrepancyRecord) -> dict[str, object]:
    discrepancy = record.discrepancy
    measurements = discrepancy.evidence
    zone = None if record.zone_redacted else _geometry(discrepancy.zone)
    return {
        "type": "Feature",
        "id": record.record_id,
        "geometry": zone,
        "properties": {
            "tipo": discrepancy.kind,
            "fuente_a": discrepancy.subject.source.kind,
            "fuente_b": discrepancy.counterpart_source.kind,
            "medidas": {m.name: _measure(m) for m in measurements},
            "confianza": round(discrepancy.confidence, _CONFIDENCE_DECIMALS),
            "evidencia": [
                {"medida": m.name,"unidad": m.unit, "valor": _measure(m)} for m in measurements
            ],
            "criterio": f"{discrepancy.criterion.identifier}@{discrepancy.criterion.version}",
            "zona_omitida_por_licencia": record.zone_redacted,
            "trazados": [
                _trail(evidence, "A" if index == 0 else "B")
                for index, evidence in enumerate(record.trails)
            ],
        },
    }


def _layer(summary: LayerSummary) -> dict[str, object]:
    return {
        "fuente": summary.source,
        "estado": summary.status.value,
        "procedencia": _provenance(summary.provenance) if summary.provenance else None,
        "trazados": summary.trail_count,
        "ids_sin_geometria": list(summary.empty_geometry_ids),
        "motivo_ausencia": summary.missing_reason,
    }


def report_to_geojson_text(report: MunicipalDiscrepancyReport) -> str:
    collection = {
        "type": "FeatureCollection",
        "crs": _CRS,
        "properties": {
            "municipio": report.municipality_code,
            "criterio": report.criterion_id,
            "publicable": report.redacted,
            "aviso": NOTICE,
            "capas": [_layer(summary) for summary in report.layers],
        },
        "features": [_feature(record) for record in report.records],
    }
    return (
        json.dumps(collection, ensure_ascii=False, sort_keys=True, indent=1, separators=(",", ": "))
        + "\n"
    )


class GeoJsonDiscrepancyWriter:
    """Implementa `DiscrepancyReportSink`: `<directory>/<ine>.geojson`, atómico."""

    def __init__(self, directory: Path, publishable: bool) -> None:
        self._directory = directory
        self._publishable = publishable

    def write(self, report: MunicipalDiscrepancyReport) -> None:
        if self._publishable and not report.redacted:
            raise UnredactedReportError(report.municipality_code)
        data = report_to_geojson_text(report).encode("utf-8")
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"{report.municipality_code}.geojson"
        fd, tmp_name = tempfile.mkstemp(dir=self._directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(data)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
