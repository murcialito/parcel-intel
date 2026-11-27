"""Kit de campo: los tramos publicados de un municipio, listos para GPX y KML
(historia #213).

Solo lee lo que ya está publicado en `site/datos/<capa>/<ine>.geojson` (EPSG:4326) y su
`.procedencia.json`. Funciones puras y deterministas: ningún reloj, ninguna red, ningún LLM.

Todo o nada y sin copiar nada por defecto: de cada elemento solo salen las propiedades de la
lista blanca de su ficha (`ALLOWED_PROPERTIES`), el aviso «siempre está» (lecciones 95 y 169) y
nunca una propiedad de titularidad ni una referencia catastral (CLAUDE.md).
"""

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Literal

from parcel_intel.domain.public_card import banned_words_in

KitLayerId = Literal["vias_pecuarias", "camino_actual", "discrepancias", "candidatos"]
KIT_LAYER_IDS: tuple[KitLayerId, ...] = (
    "vias_pecuarias",
    "camino_actual",
    "discrepancias",
    "candidatos",
)
MAX_KIT_FILE_BYTES = 3_000_000

Coordinate = tuple[float, float]  # (longitud, latitud) en EPSG:4326
Ring = tuple[Coordinate, ...]
Polygon = tuple[Ring, ...]  # anillo exterior y, después, huecos

_CARD_LAYERS: frozenset[KitLayerId] = frozenset({"discrepancias", "candidatos"})
_CARD_PROPERTIES = frozenset(
    {"etiqueta", "texto", "aviso", "confianza", "evidencia", "aviso_omision"}
)
ALLOWED_PROPERTIES: Mapping[KitLayerId, frozenset[str]] = MappingProxyType(
    {
        "vias_pecuarias": frozenset({"nombre", "tipo", "fecha_dato", "procedencia"}),
        "camino_actual": frozenset({"nombre", "tipo", "fecha_dato", "procedencia"}),
        "discrepancias": _CARD_PROPERTIES | {"criterio", "descripcion_criterio", "tipo"},
        "candidatos": _CARD_PROPERTIES | {"imagenes_comparacion"},
    }
)
DEFAULT_NAME: Mapping[KitLayerId, str] = MappingProxyType(
    {
        "vias_pecuarias": "Vía pecuaria (sin nombre)",
        "camino_actual": "Camino actual (sin nombre)",
        "discrepancias": "Indicio a verificar",
        "candidatos": "Tramo a verificar",
    }
)
LAYER_TITLE: Mapping[KitLayerId, str] = MappingProxyType(
    {
        "vias_pecuarias": "Vías pecuarias",
        "camino_actual": "Camino actual",
        "discrepancias": "Indicios de discrepancia",
        "candidatos": "Tramos a verificar",
    }
)

_FORBIDDEN_KEY_PARTS = ("titular", "propiet", "duen", "owner", "catastr", "refcat", "nif")
_CONFIDENCE_LEVELS = frozenset({"baja", "media", "alta"})


class KitExportError(ValueError):
    """Un fichero publicado no se puede exportar; no se escribe nada."""


@dataclass(frozen=True)
class KitGeometry:
    """Geometría en EPSG:4326: líneas (cada una, una secuencia de puntos) o polígonos."""

    lines: tuple[Ring, ...] = ()
    polygons: tuple[Polygon, ...] = ()


@dataclass(frozen=True)
class PublishedFeature:
    identifier: str | None
    geometry: KitGeometry
    properties: Mapping[str, object]


@dataclass(frozen=True)
class PublishedLayerFile:
    """Un `<capa>/<ine>.geojson` publicado con los campos de su `.procedencia.json`."""

    layer: KitLayerId
    municipality_code: str
    features: tuple[PublishedFeature, ...]
    source: str
    license: str
    attribution: tuple[str, ...]
    notice: str


@dataclass(frozen=True)
class KitTramo:
    name: str
    description: str
    geometry: KitGeometry
    layer: KitLayerId


@dataclass(frozen=True)
class KitLayer:
    layer: KitLayerId
    source: str
    license: str
    attribution: tuple[str, ...]
    notice: str
    tramos: tuple[KitTramo, ...]


@dataclass(frozen=True)
class MunicipalKit:
    municipality_code: str
    generated_on: date
    layers: tuple[KitLayer, ...]
    missing: tuple[KitLayerId, ...]


@dataclass(frozen=True)
class PublishedKitFile:
    municipality_code: str
    path: str  # relativo al directorio publicado
    size_bytes: int


@dataclass(frozen=True)
class KitFailure:
    municipality_code: str
    reason: str


@dataclass(frozen=True)
class KitResult:
    published: tuple[PublishedKitFile, ...]
    included: tuple[tuple[str, tuple[KitLayerId, ...], tuple[KitLayerId, ...]], ...]
    failures: tuple[KitFailure, ...]


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _forbidden_keys(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, inner in value.items():
            if any(part in _normalize(str(key)) for part in _FORBIDDEN_KEY_PARTS):
                found.append(str(key))
            found.extend(_forbidden_keys(inner))
    elif isinstance(value, list | tuple):
        for inner in value:
            found.extend(_forbidden_keys(inner))
    return found


def _text(properties: Mapping[str, object], key: str) -> str | None:
    value = properties.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _describe_card(file: PublishedLayerFile, properties: Mapping[str, object]) -> tuple[str, str]:
    label = _text(properties, "etiqueta")
    text = _text(properties, "texto")
    warning = _text(properties, "aviso")
    confidence = _text(properties, "confianza")
    if warning is None:
        raise KitExportError(f"{file.layer}/{file.municipality_code}: elemento sin aviso")
    if label is None or text is None:
        raise KitExportError(
            f"{file.layer}/{file.municipality_code}: elemento sin etiqueta o texto"
        )
    if confidence not in _CONFIDENCE_LEVELS:
        raise KitExportError(
            f"{file.layer}/{file.municipality_code}: confianza no válida {confidence!r}"
        )
    banned = banned_words_in(f"{label} {text}")
    if banned:
        raise KitExportError(
            f"{file.layer}/{file.municipality_code}: palabras vetadas en la ficha: "
            f"{', '.join(banned)}"
        )
    parts = [text, f"Confianza: {confidence}.", warning]
    omission = _text(properties, "aviso_omision")
    if omission is not None:
        parts.append(omission)
    return label, "\n".join(parts)


def _describe_trail(file: PublishedLayerFile, properties: Mapping[str, object]) -> tuple[str, str]:
    name = _text(properties, "nombre") or DEFAULT_NAME[file.layer]
    parts = [f"{LAYER_TITLE[file.layer]}.", file.notice]
    date_text = _text(properties, "fecha_dato")
    if date_text is not None:
        parts.append(f"Fecha del dato: {date_text}.")
    return name, "\n".join(parts)


def build_kit_layer(file: PublishedLayerFile) -> KitLayer:
    """Convierte un fichero publicado en los tramos del kit. Falla (`KitExportError`) si
    un elemento lleva una propiedad de titularidad o catastral, una fuera de la lista blanca
    o no lleva aviso. No omite ni copia nada por su cuenta."""
    if not file.notice.strip():
        raise KitExportError(f"{file.layer}/{file.municipality_code}: procedencia sin aviso")
    allowed = ALLOWED_PROPERTIES[file.layer]
    tramos: list[KitTramo] = []
    for feature in file.features:
        where = f"{file.layer}/{file.municipality_code} {feature.identifier or '?'}"
        forbidden = _forbidden_keys(feature.properties)
        if forbidden:
            raise KitExportError(
                f"{where}: propiedad de titularidad o referencia catastral: "
                f"{', '.join(sorted(set(forbidden)))}"
            )
        unknown = sorted(set(feature.properties) - allowed)
        if unknown:
            raise KitExportError(f"{where}: propiedades fuera de la lista blanca: {unknown}")
        if file.layer in _CARD_LAYERS:
            name, description = _describe_card(file, feature.properties)
        else:
            name, description = _describe_trail(file, feature.properties)
        attribution = " | ".join(file.attribution)
        tramos.append(
            KitTramo(
                name=name,
                description=f"{description}\nAtribución: {attribution}",
                geometry=feature.geometry,
                layer=file.layer,
            )
        )
    return KitLayer(
        layer=file.layer,
        source=file.source,
        license=file.license,
        attribution=file.attribution,
        notice=file.notice,
        tramos=tuple(tramos),
    )


# --- Proyecto de campo para QField (historia #222) ---------------------------------------

QFIELD_WARNING = (
    "Anota solo lo que ves del camino: qué obstáculo hay y en qué estado está. No fotografíes "
    "a personas ni vehículos con matrícula visible, y no escribas nombres de personas, de "
    "propietarios ni de empresas. Fotos y notas pueden identificar a alguien, y lo que recojas "
    "se queda en tu dispositivo: este proyecto no envía nada. Los tramos son indicios a "
    "verificar, no un dictamen; tu anotación confirma o desmiente lo que ves, no denuncia a "
    "nadie."
)
NOTE_FIELD_LABEL = "Nota corta (sin nombres de personas)"
NOTE_MAX_LENGTH = 280


@dataclass(frozen=True)
class FormOption:
    label: str
    value: str


@dataclass(frozen=True)
class IncidenciaFormulario:
    """Formulario de la capa editable `incidencias`: listas cerradas y advertencia aprobada."""

    obstacle_types: tuple[FormOption, ...]
    states: tuple[FormOption, ...]
    note_label: str
    warning: str


INCIDENCIA_FORM = IncidenciaFormulario(
    obstacle_types=(
        FormOption("Cancela", "cancela"),
        FormOption("Valla", "valla"),
        FormOption("Cadena", "cadena"),
        FormOption("Zanja", "zanja"),
        FormOption("Bloques", "bloques"),
        FormOption("Cartel de prohibido el paso", "cartel_prohibido"),
        FormOption("Arado", "arado"),
        FormOption("Vegetación", "vegetacion"),
    ),
    states=(
        FormOption("Practicable", "practicable"),
        FormOption("Tapado por la vegetación", "tapado_vegetacion"),
        FormOption("Con obstáculo", "con_obstaculo"),
        FormOption("Deteriorado por máquinas", "deteriorado_maquinas"),
    ),
    note_label=NOTE_FIELD_LABEL,
    warning=QFIELD_WARNING,
)
