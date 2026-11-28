"""Generador de las fixtures SINTÉTICAS del catálogo de citas normativas (historia #187).

Escribe, bajo `tests/fixtures/normativa/`:
- `valido/catalogo.json`: tres citas inventadas (identificador `BOE-A-9999-1`), dos tipos de
  fuente compartidos y una cita con dos tipos (caso N >= 2, lección de 0001); una lleva
  «titular» en el literal (CA5) y otra una nota. Van desordenadas en el fichero a propósito.
- `vacio/catalogo.json`: un catálogo válido sin citas (CA7).

**Nada es texto legal real**: así nadie toma una fixture por una cita verificada (lección de
0012). Las huellas se **calculan** aquí con `hashlib` y un JSON canónico propio, sin usar el
código de producción (oráculo independiente); un test compara lo versionado con lo generado.
Para regenerar: `uv run python -m tests.fixtures.normativa.generar`.
"""

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).parent
VALID_DIR = FIXTURE_DIR / "valido"
EMPTY_DIR = FIXTURE_DIR / "vacio"

BOE_ID = "BOE-A-9999-1"
LICENSE = (
    "Condiciones de reutilización de la Agencia Estatal Boletín Oficial del Estado "
    "(https://www.boe.es/informacion/aviso_legal/index.php)"
)
URL = f"https://www.boe.es/buscar/act.php?id={BOE_ID}"

_TEXTS = {
    "sintetica-art-01": (
        "Texto sintético de prueba (historia #187), no es texto legal.\n"
        "1. La persona titular de la vía sintética conserva el paso común."
    ),
    "sintetica-art-02": (
        "Texto sintético de prueba (historia #187), no es texto legal.\n"
        "2. Los caminos sintéticos de ejemplo se describen aquí con tildes: camión, ñandú."
    ),
    "sintetica-art-10": "Texto sintético de prueba (historia #187), no es texto legal.",
}
_KINDS = {
    "sintetica-art-01": ["via_pecuaria_oficial"],
    "sintetica-art-02": ["catastro_vt", "via_pecuaria_oficial"],
    "sintetica-art-10": ["catastro_vt"],
}
# Orden del fichero, distinto del orden por id, para probar que se ordena al cargar.
FILE_ORDER = ("sintetica-art-10", "sintetica-art-01", "sintetica-art-02")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def citation(citation_id: str, version: int = 1) -> dict[str, Any]:
    """Una cita sintética válida, con su huella calculada."""
    text = _TEXTS[citation_id]
    number = citation_id.rsplit("-", 1)[1]
    data: dict[str, Any] = {
        "id": citation_id,
        "norma": "Ley sintética 9/2090, de 23 de marzo, de prueba",
        "identificador": BOE_ID,
        "articulo": f"Artículo {int(number)}",
        "fecha_norma": "2090-03-23",
        "ultima_actualizacion": "2095-12-23",
        "texto": text,
        "texto_sha256": sha256_text(text),
        "url": f"{URL}#a{int(number)}",
        "consultado": "2099-01-01",
        "licencia": LICENSE,
        "version_catalogo": version,
        "tipos_fuente": list(_KINDS[citation_id]),
    }
    if citation_id == "sintetica-art-10":
        data["nota"] = "Nota sintética de prueba."
    return data


def citations(version: int = 1) -> list[dict[str, Any]]:
    return [citation(citation_id, version) for citation_id in FILE_ORDER]


def catalog_fingerprint(version: int, cites: list[dict[str, Any]]) -> str:
    """Huella del catálogo según ADR 0060 §5, calculada sin el código de producción."""
    # Tolera citas mutadas por los tests (claves de menos o de tipo erróneo): su huella no
    # importa, porque el cargador las rechaza antes de compararla.
    ordered = sorted(cites, key=lambda item: str(item.get("id", "")))
    normalized = []
    for item in ordered:
        entry = copy.deepcopy(item)
        entry.setdefault("nota", None)
        if isinstance(entry.get("tipos_fuente"), list):
            entry["tipos_fuente"] = sorted(str(kind) for kind in entry["tipos_fuente"])
        normalized.append(entry)
    payload = {"version": version, "citas": normalized}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def document(cites: list[dict[str, Any]] | None = None, version: int = 1) -> dict[str, Any]:
    """Documento completo con su `huella_catalogo` recalculada."""
    items = citations(version) if cites is None else cites
    return {
        "version": version,
        "huella_catalogo": catalog_fingerprint(version, items),
        "citas": items,
    }


def render(doc: dict[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def expected_files() -> dict[Path, str]:
    return {
        VALID_DIR / "catalogo.json": render(document()),
        EMPTY_DIR / "catalogo.json": render(document([])),
    }


def main() -> None:
    for path, text in expected_files().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
