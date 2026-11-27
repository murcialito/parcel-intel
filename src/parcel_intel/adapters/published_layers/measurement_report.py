"""Lector del informe agregado de `medir-candidatos` (historias #111 y #170, ADR 0048).

Lee solo las claves que usa la publicación e ignora las demás (`casos`, `sha256`,
`criterio_casamiento`, `aviso`...), para que el informe pueda crecer sin romperla. Con
stdlib y helpers tipados (lección #137), no pydantic. Ausente, JSON roto o una clave de
tipo inesperado lanzan `MeasurementReportUnavailableError`; el detalle nombra la clave,
nunca su valor. Si el informe sirve para publicar lo decide el dominio.
"""

import json
import re
from datetime import date
from pathlib import Path

from parcel_intel.domain.published_candidate import MeasurementReport
from parcel_intel.ports.errors import MeasurementReportUnavailableError

_METHOD_RE = re.compile(r"[a-z_]+@\d+")


class _Invalid(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def _object(value: object, key: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _Invalid(f"«{key}» no es un objeto")
    return value


def _member(document: dict[str, object], key: str, path: str) -> object:
    if key not in document:
        raise _Invalid(f"falta la clave «{path}»")
    return document[key]


def _count(value: object, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _Invalid(f"«{key}» no es un entero mayor o igual que 0")
    return value


def _ratio(value: object, key: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _Invalid(f"«{key}» no es un número ni null")
    return float(value)


def _label(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _Invalid("«etiqueta» no es texto ni null")
    return value


def _frozen(value: object) -> bool:
    if not isinstance(value, bool):
        raise _Invalid("«congelado» no es un booleano")
    return value


def _date(value: object) -> date:
    if not isinstance(value, str):
        raise _Invalid("«fecha» no es una fecha ISO")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _Invalid("«fecha» no es una fecha ISO") from None


def _methods(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _Invalid("«metodo_candidatos» no es una lista")
    methods: list[str] = []
    for item in value:
        if not isinstance(item, str) or _METHOD_RE.fullmatch(item) is None:
            raise _Invalid("«metodo_candidatos» tiene un elemento que no cumple ^[a-z_]+@\\d+$")
        methods.append(item)
    return tuple(methods)


def _bound(value: object) -> str:
    if not isinstance(value, str):
        raise _Invalid("«precision.cota» no es texto")
    return value


def parse_measurement(document: object) -> MeasurementReport:
    """Informe de medición desde el JSON ya decodificado. Lanza `_Invalid`."""
    root = _object(document, "informe")
    no_evaluable = _object(_member(root, "no_evaluables", "no_evaluables"), "no_evaluables")
    reasons = _object(
        _member(no_evaluable, "por_motivo", "no_evaluables.por_motivo"),
        "no_evaluables.por_motivo",
    )
    coverage = _object(_member(root, "cobertura", "cobertura"), "cobertura")
    precision = _object(_member(root, "precision", "precision"), "precision")
    return MeasurementReport(
        label=_label(_member(root, "etiqueta", "etiqueta")),
        frozen=_frozen(_member(root, "congelado", "congelado")),
        run_date=_date(_member(root, "fecha", "fecha")),
        candidate_methods=_methods(_member(root, "metodo_candidatos", "metodo_candidatos")),
        total_cases=_count(_member(root, "casos_total", "casos_total"), "casos_total"),
        out_of_scope_cases=_count(
            reasons.get("fuera_del_ambito", 0), "no_evaluables.por_motivo.fuera_del_ambito"
        ),
        evaluable_cases=_count(
            _member(coverage, "casos_evaluables", "cobertura.casos_evaluables"),
            "cobertura.casos_evaluables",
        ),
        flagged_cases=_count(
            _member(coverage, "casos_senalados", "cobertura.casos_senalados"),
            "cobertura.casos_senalados",
        ),
        coverage=_ratio(_member(coverage, "valor", "cobertura.valor"), "cobertura.valor"),
        evaluable_candidates=_count(
            _member(precision, "candidatos_evaluables", "precision.candidatos_evaluables"),
            "precision.candidatos_evaluables",
        ),
        hit_candidates=_count(
            _member(precision, "candidatos_acertados", "precision.candidatos_acertados"),
            "precision.candidatos_acertados",
        ),
        precision=_ratio(_member(precision, "valor", "precision.valor"), "precision.valor"),
        precision_bound=_bound(_member(precision, "cota", "precision.cota")),
    )


class JsonMeasurementReportReader:
    """Implementa `MeasurementReportSource` sobre el fichero `path` (normalmente
    `data/derived/validacion/medicion.json`)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def get_measurement(self) -> MeasurementReport:
        path = str(self._path)
        if not self._path.is_file():
            raise MeasurementReportUnavailableError(path, "no existe")
        try:
            document = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as error:
            raise MeasurementReportUnavailableError(
                path, f"no se puede leer ({type(error).__name__})"
            ) from error
        except json.JSONDecodeError as error:
            raise MeasurementReportUnavailableError(
                path, f"no es JSON válido (línea {error.lineno})"
            ) from error
        try:
            return parse_measurement(document)
        except _Invalid as error:
            raise MeasurementReportUnavailableError(path, error.detail) from None
