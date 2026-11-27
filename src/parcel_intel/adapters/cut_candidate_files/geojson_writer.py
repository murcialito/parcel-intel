"""Escritor del fichero interno de candidatos a corte de un municipio (historia #128,
ADR 0039 §8 y §9).

Una `FeatureCollection` en EPSG:25830 con una feature `MultiLineString` por
candidato. El metadato del informe va en el nivel superior (`properties`).
Serialización determinista (claves ordenadas, sin fecha de generación) y
escritura atómica: un fallo a medias no deja un fichero truncado que el lector
tomaría por «municipio evaluable». Fichero **interno**: deriva de Catastro y
nunca se publica. No lleva titularidad, referencias de finca ni geometría de parcela.
"""

import json
import os
import tempfile
from pathlib import Path

from parcel_intel.domain.cut_candidate import (
    CutCandidate,
    MunicipalCutCandidateReport,
    SignalRef,
    SignalRunSummary,
    SignalSupport,
)
from parcel_intel.domain.discrepancy import Measurement
from parcel_intel.domain.provenance import Provenance

NOTICE = "Indicios automáticos a verificar; no son un dictamen. Fichero interno: no se publica."
_CRS = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25830"}}
_COORD_DECIMALS = 2  # 0,01 m
_VALUE_DECIMALS = 3


def _provenance(provenance: Provenance) -> dict[str, object]:
    return {
        "fuente": provenance.source,
        "url": provenance.url,
        "fecha_descarga": provenance.retrieved_at.isoformat(),
        "licencia": provenance.license,
        "redistribucion": provenance.redistribution.value,
    }


def _signal(signal: SignalRef) -> dict[str, object]:
    return {
        "identificador": signal.identifier,
        "version": signal.version,
        "condicion": signal.condition,
    }


def _measure(measurement: Measurement) -> dict[str, object]:
    return {
        "medida": measurement.name,
        "unidad": measurement.unit,
        "valor": round(measurement.value, _VALUE_DECIMALS),
    }


def _support(support: SignalSupport) -> dict[str, object]:
    return {
        "senal": _signal(support.signal),
        "fraccion_apoyo": round(support.support_fraction, _VALUE_DECIMALS),
        "fraccion_sin_dato": round(support.no_data_fraction, _VALUE_DECIMALS),
        "procedencia": [_provenance(p) for p in support.provenance],
    }


def _feature(candidate: CutCandidate) -> dict[str, object]:
    subject = candidate.subject
    return {
        "type": "Feature",
        "id": candidate.candidate_id,
        "geometry": {
            "type": "MultiLineString",
            "coordinates": [
                [[round(x, _COORD_DECIMALS), round(y, _COORD_DECIMALS)] for x, y in line]
                for line in candidate.stretch.lines
            ],
        },
        "properties": {
            "candidate_id": candidate.candidate_id,
            "municipality_code": candidate.municipality_code,
            "trazado": {
                "id": subject.trail_id,
                "fuente": subject.source.kind,
                "procedencia": _provenance(subject.source.provenance),
                "fecha_dato": subject.source.data_date.isoformat()
                if subject.source.data_date
                else None,
            },
            "registros_base": list(candidate.discrepancy_ids),
            "condiciones": list(candidate.conditions),
            "senales": [_support(s) for s in candidate.signals],
            "confianza": round(candidate.confidence, _VALUE_DECIMALS),
            "evidencia": [_measure(m) for m in candidate.evidence],
            "metodo": f"{candidate.method.identifier}@{candidate.method.version}",
        },
    }


def _summary(summary: SignalRunSummary) -> dict[str, object]:
    return {
        "senal": _signal(summary.signal),
        "estado": summary.status,
        "motivo": summary.reason,
        "procedencia": [_provenance(p) for p in summary.provenance],
    }


def report_to_geojson_text(report: MunicipalCutCandidateReport) -> str:
    collection = {
        "type": "FeatureCollection",
        "crs": _CRS,
        "properties": {
            "municipio": report.municipality_code,
            "metodo": f"{report.method.identifier}@{report.method.version}",
            "criterio_discrepancias": report.discrepancy_criterion_id,
            "registros_base": list(report.base_record_ids),
            "senales": [_summary(s) for s in report.signals],
            "aviso": NOTICE,
        },
        "features": [_feature(candidate) for candidate in report.candidates],
    }
    return (
        json.dumps(collection, ensure_ascii=False, sort_keys=True, indent=1, separators=(",", ": "))
        + "\n"
    )


class GeoJsonCutCandidateWriter:
    """Implementa `CutCandidateSink`: `<directory>/<ine>.geojson`, atómico."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def write(self, report: MunicipalCutCandidateReport) -> None:
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
