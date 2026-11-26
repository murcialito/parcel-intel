"""Huellas SHA-256 de referencias catastrales y anillos de una respuesta de Catastro.

Historia #45. Sirve para comprobar que las fixtures sintéticas de
`tests/fixtures/catastro/` no reutilizan ninguna referencia ni ningún anillo de
las respuestas originales, sin versionar esos datos: solo se guardan sus huellas
en `tests/fixtures/catastro_huellas_reales.json`.

La misma normalización se aplica en los dos sentidos (originales y sintéticas):

- referencias: `nationalCadastralReference`, `localId`, `reference`
  (`ExternalReference` de edificios), sufijo del `gml:id` de `CadastralParcel` y
  `Building`, y `pc1 + pc2` de CPMRC/DNPPP; todas recortadas a 14 caracteres;
- anillos: cada `gml:posList`, normalizado con `normalize_pos_list`.

Solo stdlib y sin importar `parcel_intel`. Uso (una sola vez, con los originales
aún en disco):

    uv run python -m tests.fixtures.catastro_fingerprints <dir_originales> \
        --salida tests/fixtures/catastro_huellas_reales.json
"""

from __future__ import annotations

import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from pathlib import Path

ALGORITHM = "sha256"
NORMALIZATION = (
    "referencias: nationalCadastralReference, localId, reference, sufijo de gml:id de "
    "CadastralParcel/Building y pc1+pc2, recortadas a 14 caracteres; anillos: cada "
    "gml:posList como ' '.join(f'{float(v):.2f}' for v in texto.split()); vértices (historia "
    "#46): cada par x y de un gml:posList como f'{float(x):.2f} {float(y):.2f}'"
)

_GML_ID = "{http://www.opengis.net/gml/3.2}id"
_REFERENCE_TAGS = frozenset({"nationalCadastralReference", "localId", "reference"})
_FEATURE_TAGS = frozenset({"CadastralParcel", "Building"})
_REFERENCE_LENGTH = 14


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_pos_list(text: str) -> str:
    return " ".join(f"{float(v):.2f}" for v in text.split())


def _normalize_reference(text: str) -> str:
    return text.strip()[:_REFERENCE_LENGTH]


def _references(root: ET.Element) -> Iterable[str]:
    for element in root.iter():
        name = _local_name(element.tag)
        if name in _REFERENCE_TAGS and element.text and element.text.strip():
            yield _normalize_reference(element.text)
        if name in _FEATURE_TAGS:
            gml_id = element.get(_GML_ID) or ""
            if gml_id:
                yield _normalize_reference(gml_id.rsplit(".", 1)[-1])
        if name in ("pc", "rc"):
            parts = {_local_name(child.tag): (child.text or "").strip() for child in element}
            if parts.get("pc1") and parts.get("pc2"):
                yield _normalize_reference(parts["pc1"] + parts["pc2"])


def reference_fingerprints(xml_bytes: bytes) -> set[str]:
    """SHA-256 (hex) de cada referencia catastral normalizada del documento."""
    root = ET.fromstring(xml_bytes)
    return {_sha256(reference) for reference in _references(root)}


def ring_fingerprints(xml_bytes: bytes) -> set[str]:
    """SHA-256 (hex) de cada `gml:posList` normalizado del documento."""
    root = ET.fromstring(xml_bytes)
    return {
        _sha256(normalize_pos_list(element.text))
        for element in root.iter()
        if _local_name(element.tag) == "posList" and element.text and element.text.strip()
    }


def normalize_vertex(x: str, y: str) -> str:
    return f"{float(x):.2f} {float(y):.2f}"


def vertex_fingerprints(xml_bytes: bytes) -> set[str]:
    """SHA-256 (hex) de cada vértice (`x y`, dos decimales) de cada `gml:posList` (historia #46)."""
    root = ET.fromstring(xml_bytes)
    result: set[str] = set()
    for element in root.iter():
        if _local_name(element.tag) == "posList" and element.text and element.text.strip():
            values = element.text.split()
            pairs = zip(values[::2], values[1::2], strict=False)
            result |= {_sha256(normalize_vertex(x, y)) for x, y in pairs}
    return result


def fingerprints_of_directory(directory: Path, pattern: str = "*.xml") -> dict[str, object]:
    references: set[str] = set()
    rings: set[str] = set()
    vertices: set[str] = set()
    for path in sorted(directory.glob(pattern)):
        body = path.read_bytes()
        references |= reference_fingerprints(body)
        rings |= ring_fingerprints(body)
        vertices |= vertex_fingerprints(body)
    return {
        "algoritmo": ALGORITHM,
        "normalizacion": NORMALIZATION,
        "referencias": sorted(references),
        "anillos": sorted(rings),
        "vertices": sorted(vertices),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Imprime las huellas de un directorio; con `--salida <fichero>` las escribe en él."""
    args = list(sys.argv[1:] if argv is None else argv)
    output: Path | None = None
    if len(args) == 3 and args[1] == "--salida":
        output = Path(args[2])
        args = args[:1]
    if len(args) != 1:
        print(
            "uso: python -m tests.fixtures.catastro_fingerprints <directorio> [--salida <fichero>]",
            file=sys.stderr,
        )
        return 2
    text = json.dumps(fingerprints_of_directory(Path(args[0])), ensure_ascii=False, indent=2)
    if output is None:
        print(text)
    else:
        output.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
