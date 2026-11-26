"""Lectura estricta de la entrada humana versionada de una unidad histórica —
historia #137 (hija B de #20), ADR 0043.

`curated/historico/<unit_id>/` tiene tres ficheros de formato cerrado:
`unidad.json`, `puntos_control.csv` y `trazados.geojson`. Cualquier clave, columna
o valor fuera de lo declarado rechaza el fichero entero con un motivo; nada se
corrige ni se ignora en silencio. El sha256 del CSV se calcula sobre sus bytes
tal cual (`.gitattributes` marca estos ficheros como `-text`).
"""

import csv
import hashlib
import io
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import TypedDict, TypeVar, get_args

from parcel_intel.domain.digitization import DigitizedTrail, InvalidDigitizationError, TrailKind
from parcel_intel.domain.georeferencing import (
    ControlPoint,
    ControlPointSet,
    InvalidControlPointError,
    UnitSpec,
    WorkingImageKind,
)
from parcel_intel.domain.historic_trail import DatePrecision, HistoricDocumentKind, ReviewStatus
from parcel_intel.ports.errors import CuratedUnitNotFoundError

_UNIT_ID_RE = re.compile(r"[0-9]{4,6}-[wh][0-9]+")

_UNIT_KEYS = frozenset(
    {
        "unit_id",
        "document_id",
        "document_kind",
        "municipality_code",
        "document_date",
        "document_date_precision",
        "scale_denominator",
        "image",
        "provenance_source",
        "georeferenced_by",
        "georeferenced_at",
    }
)
_IMAGE_KEYS = frozenset({"kind", "url", "sha256", "width_px", "height_px", "retrieved_at"})

CSV_HEADER = (
    "point_id,col,row,x_25830,y_25830,coordinate_source,description,retained,discard_reason"
).split(",")

_FEATURE_KEYS = frozenset({"type", "geometry", "properties"})
_REQUIRED_PROPERTIES = frozenset({"trail_id", "kind", "review"})
_ALLOWED_PROPERTIES = _REQUIRED_PROPERTIES | {
    "label",
    "reviewed_by",
    "reviewed_at",
    "review_note",
    "control_points_sha256",
}
_REVIEW_STATES: dict[str, ReviewStatus] = {
    "propuesto": "proposed",
    "aprobado": "approved",
    "rechazado": "rejected",
}

_DOCUMENT_KINDS: tuple[HistoricDocumentKind, ...] = get_args(HistoricDocumentKind)
_DATE_PRECISIONS: tuple[DatePrecision, ...] = get_args(DatePrecision)
_IMAGE_KINDS: tuple[WorkingImageKind, ...] = get_args(WorkingImageKind)
_TRAIL_KINDS: tuple[TrailKind, ...] = get_args(TrailKind)

_T = TypeVar("_T", bound=str)


class UnitImageFile(TypedDict):
    kind: WorkingImageKind
    url: str
    sha256: str
    width_px: int
    height_px: int
    retrieved_at: date


class UnitFile(TypedDict):
    """`unidad.json` ya validado, antes de construir el `UnitSpec`."""

    unit_id: str
    document_id: str
    document_kind: HistoricDocumentKind
    municipality_code: str
    document_date: date
    document_date_precision: DatePrecision
    scale_denominator: int
    image: UnitImageFile
    provenance_source: str
    georeferenced_by: str
    georeferenced_at: datetime


# -- utilidades de validación --------------------------------------------------


def _choice(value: object, options: tuple[_T, ...], what: str) -> _T:
    for option in options:
        if value == option:
            return option
    raise ValueError(f"{what} no reconocido: {value!r} (válidos: {', '.join(options)})")


def _exact_keys(data: dict[str, object], expected: frozenset[str], what: str) -> None:
    missing = sorted(expected - set(data))
    extra = sorted(set(data) - expected)
    if missing or extra:
        raise ValueError(f"{what}: claves de menos {missing} y de más {extra}")


def _text(data: dict[str, object], key: str, what: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"{what}.{key} debe ser texto: {value!r}")
    return value


def _integer(data: dict[str, object], key: str, what: str) -> int:
    value = data[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{what}.{key} debe ser un entero: {value!r}")
    return value


def _object(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise ValueError(f"{what} debe ser un objeto JSON")
    return {str(k): v for k, v in value.items()}


def _iso_date(data: dict[str, object], key: str, what: str) -> date:
    raw = _text(data, key, what)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{what}.{key} no es una fecha ISO: {raw!r}") from exc


def _iso_datetime(raw: str, what: str) -> datetime:
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{what} no es un instante ISO: {raw!r}") from exc


class CuratedHistoricFiles:
    """Implementa `CuratedHistoricInputPort` sobre `root` (= `curated/historico/`)."""

    def __init__(self, root: Path) -> None:
        self._root = root

    # -- unidad.json -----------------------------------------------------------

    def read_unit(self, unit_id: str) -> UnitSpec:
        raw = self._read_bytes(unit_id, "unidad.json")
        try:
            document = json.loads(raw.decode("utf-8"))
        except ValueError as exc:  # JSON o UTF-8 inválidos
            raise ValueError(f"unidad.json de {unit_id} no es JSON válido: {exc}") from exc
        unit = self._parse_unit(_object(document, "unidad.json"))
        if unit["unit_id"] != unit_id:
            raise ValueError(
                f"unidad.json declara unit_id {unit['unit_id']!r} pero el directorio es {unit_id!r}"
            )
        image = unit["image"]
        return UnitSpec(
            unit_id=unit["unit_id"],
            document_id=unit["document_id"],
            document_kind=unit["document_kind"],
            municipality_code=unit["municipality_code"],
            document_date=unit["document_date"],
            document_date_precision=unit["document_date_precision"],
            scale_denominator=unit["scale_denominator"],
            image_kind=image["kind"],
            image_url=image["url"],
            image_sha256=image["sha256"],
            image_width_px=image["width_px"],
            image_height_px=image["height_px"],
            image_retrieved_at=image["retrieved_at"],
            provenance_source=unit["provenance_source"],
            georeferenced_by=unit["georeferenced_by"],
            georeferenced_at=unit["georeferenced_at"],
        )

    @staticmethod
    def _parse_unit(data: dict[str, object]) -> UnitFile:
        _exact_keys(data, _UNIT_KEYS, "unidad.json")
        image = _object(data["image"], "unidad.json.image")
        _exact_keys(image, _IMAGE_KEYS, "unidad.json.image")
        return UnitFile(
            unit_id=_text(data, "unit_id", "unidad.json"),
            document_id=_text(data, "document_id", "unidad.json"),
            document_kind=_choice(data["document_kind"], _DOCUMENT_KINDS, "document_kind"),
            municipality_code=_text(data, "municipality_code", "unidad.json"),
            document_date=_iso_date(data, "document_date", "unidad.json"),
            document_date_precision=_choice(
                data["document_date_precision"], _DATE_PRECISIONS, "document_date_precision"
            ),
            scale_denominator=_integer(data, "scale_denominator", "unidad.json"),
            image=UnitImageFile(
                kind=_choice(image["kind"], _IMAGE_KINDS, "image.kind"),
                url=_text(image, "url", "unidad.json.image"),
                sha256=_text(image, "sha256", "unidad.json.image"),
                width_px=_integer(image, "width_px", "unidad.json.image"),
                height_px=_integer(image, "height_px", "unidad.json.image"),
                retrieved_at=_iso_date(image, "retrieved_at", "unidad.json.image"),
            ),
            provenance_source=_text(data, "provenance_source", "unidad.json"),
            georeferenced_by=_text(data, "georeferenced_by", "unidad.json"),
            georeferenced_at=_iso_datetime(
                _text(data, "georeferenced_at", "unidad.json"), "georeferenced_at"
            ),
        )

    # -- puntos_control.csv ----------------------------------------------------

    def read_control_points(self, unit_id: str) -> ControlPointSet:
        raw = self._read_bytes(unit_id, "puntos_control.csv")
        try:
            text = raw.decode("utf-8-sig")  # admite BOM
        except UnicodeDecodeError as exc:
            raise InvalidControlPointError(f"puntos_control.csv no es UTF-8: {exc}") from exc
        rows = list(csv.reader(io.StringIO(text, newline="")))
        if not rows or rows[0] != CSV_HEADER:
            raise InvalidControlPointError(
                f"cabecera de puntos_control.csv distinta de {','.join(CSV_HEADER)}: "
                f"{rows[0] if rows else '(vacío)'}"
            )
        points: list[ControlPoint] = []
        for number, row in enumerate(rows[1:], start=2):
            if not row:  # línea en blanco (p. ej. la final)
                continue
            points.append(self._parse_point(row, number))
        # `ControlPointSet` rechaza los point_id repetidos.
        return ControlPointSet(points=tuple(points), sha256=hashlib.sha256(raw).hexdigest())

    @staticmethod
    def _parse_point(row: list[str], line: int) -> ControlPoint:
        if len(row) != len(CSV_HEADER):
            raise InvalidControlPointError(
                f"línea {line}: {len(row)} columnas, se esperan {len(CSV_HEADER)}"
            )
        point_id, col, row_px, x, y, source, description, retained, reason = row
        if retained not in ("true", "false"):
            raise InvalidControlPointError(
                f"línea {line} ({point_id}): retained debe ser true o false: {retained!r}"
            )
        try:
            numbers = [float(value) for value in (col, row_px, x, y)]
        except ValueError as exc:
            raise InvalidControlPointError(
                f"línea {line} ({point_id}): número no válido: {exc}"
            ) from exc
        return ControlPoint(
            point_id=point_id,
            col=numbers[0],
            row=numbers[1],
            target=(numbers[2], numbers[3]),
            coordinate_source=source,
            description=description,
            retained=retained == "true",
            discard_reason=reason if reason else None,
        )

    # -- trazados.geojson ------------------------------------------------------

    def read_trails(self, unit_id: str) -> tuple[DigitizedTrail, ...]:
        raw = self._read_bytes(unit_id, "trazados.geojson")
        try:
            document = json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise InvalidDigitizationError(f"trazados.geojson no es JSON válido: {exc}") from exc
        top = self._object_or_invalid(document, "trazados.geojson")
        if set(top) != {"type", "features"} or top["type"] != "FeatureCollection":
            raise InvalidDigitizationError(
                "trazados.geojson: las claves de primer nivel deben ser exactamente "
                "type (FeatureCollection) y features"
            )
        features = top["features"]
        if not isinstance(features, list):
            raise InvalidDigitizationError("trazados.geojson: features debe ser una lista")
        trails = [self._parse_feature(feature, index) for index, feature in enumerate(features)]
        seen: set[str] = set()
        for trail in trails:
            if trail.trail_id in seen:
                raise InvalidDigitizationError(f"{trail.trail_id}: trail_id repetido")
            seen.add(trail.trail_id)
        return tuple(trails)

    @staticmethod
    def _object_or_invalid(value: object, what: str) -> dict[str, object]:
        try:
            return _object(value, what)
        except ValueError as exc:
            raise InvalidDigitizationError(str(exc)) from exc

    def _parse_feature(self, feature: object, index: int) -> DigitizedTrail:
        where = f"feature {index}"
        data = self._object_or_invalid(feature, where)
        if set(data) != _FEATURE_KEYS or data["type"] != "Feature":
            raise InvalidDigitizationError(
                f"{where}: las claves deben ser exactamente type (Feature), geometry y properties"
            )
        properties = self._object_or_invalid(data["properties"], f"{where}.properties")
        missing = sorted(_REQUIRED_PROPERTIES - set(properties))
        unknown = sorted(set(properties) - _ALLOWED_PROPERTIES)
        if missing or unknown:
            raise InvalidDigitizationError(
                f"{where}: propiedades de menos {missing} y desconocidas {unknown}"
            )
        trail_id = self._optional_text(properties, "trail_id", where)
        label = f"{where} ({trail_id})"
        try:
            kind = _choice(properties["kind"], _TRAIL_KINDS, "kind")
            status = _choice(properties["review"], tuple(_REVIEW_STATES), "review")
        except ValueError as exc:
            raise InvalidDigitizationError(f"{label}: {exc}") from exc
        reviewed_at_raw = self._optional_text(properties, "reviewed_at", label)
        try:
            reviewed_at = (
                _iso_datetime(reviewed_at_raw, "reviewed_at") if reviewed_at_raw else None
            )
        except ValueError as exc:
            raise InvalidDigitizationError(f"{label}: {exc}") from exc
        return DigitizedTrail(
            trail_id=trail_id or "",
            pixels=self._parse_pixels(data["geometry"], label),
            kind=kind,
            label=self._optional_text(properties, "label", label),
            status=_REVIEW_STATES[status],
            reviewed_by=self._optional_text(properties, "reviewed_by", label),
            reviewed_at=reviewed_at,
            review_note=self._optional_text(properties, "review_note", label),
            control_points_sha256=self._optional_text(properties, "control_points_sha256", label),
        )

    @staticmethod
    def _optional_text(properties: dict[str, object], key: str, where: str) -> str | None:
        value = properties.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise InvalidDigitizationError(f"{where}: {key} debe ser texto: {value!r}")
        return value

    def _parse_pixels(self, geometry: object, where: str) -> tuple[tuple[float, float], ...]:
        data = self._object_or_invalid(geometry, f"{where}.geometry")
        if set(data) != {"type", "coordinates"} or data["type"] != "LineString":
            raise InvalidDigitizationError(
                f"{where}: la geometría debe ser un LineString (type y coordinates)"
            )
        coordinates = data["coordinates"]
        if not isinstance(coordinates, list):
            raise InvalidDigitizationError(f"{where}: coordinates debe ser una lista")
        pixels: list[tuple[float, float]] = []
        for vertex in coordinates:
            if (
                not isinstance(vertex, list)
                or len(vertex) != 2
                or not all(isinstance(c, int | float) and not isinstance(c, bool) for c in vertex)
            ):
                raise InvalidDigitizationError(f"{where}: vértice no válido: {vertex!r}")
            pixels.append((float(vertex[0]), float(vertex[1])))
        return tuple(pixels)

    # -- ficheros --------------------------------------------------------------

    def _read_bytes(self, unit_id: str, name: str) -> bytes:
        if not _UNIT_ID_RE.fullmatch(unit_id):
            raise ValueError(f"unit_id no cumple ^[0-9]{{4,6}}-[wh][0-9]+$: {unit_id!r}")
        directory = self._root / unit_id
        if not directory.is_dir():
            raise CuratedUnitNotFoundError(unit_id, f"no existe el directorio {directory}")
        path = directory / name
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise CuratedUnitNotFoundError(unit_id, f"falta {name}") from exc
