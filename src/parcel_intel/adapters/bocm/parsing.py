import html
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import TypedDict

# Confirmado real sobre las 80 disposiciones del boletín del 15-oct-2026
# (ver REGISTRY.md / ADR 0009): cada entrada del listado en <description>
# sigue este patrón repetitivo exacto.
_PAIR_RE = re.compile(
    r'<a href="/([^"]+)">(BOCM-[^<]+)</a>.*?<a href="([^"]+)\.PDF">Descargar PDF</a>',
    re.S,
)
_SECTION_RE = re.compile(r"^([IVXLCDM]+)\.\s*(.+)$")


class RawBulletinIndexEntry(TypedDict):
    identifier: str
    pdf_url: str


def find_item_description_for_day(rss_body: bytes, day: str) -> str | None:
    """`sumarios.rss` es una ventana rodante de los últimos 20 boletines
    (no "el boletín de hoy" — confirmado real, ADR 0009). Devuelve la
    `<description>` (HTML escapado) del `<item>` cuyo `<pubDate>` coincide
    con `day` (`AAAAMMDD`), o `None` si ese día no está entre los últimos
    20 — el adapter decide qué excepción de dominio lanzar con ese `None`."""
    root = ET.fromstring(rss_body)
    target = datetime.strptime(day, "%Y%m%d").date()
    for item in root.iter("item"):
        pubdate_el = item.find("pubDate")
        if pubdate_el is None or pubdate_el.text is None:
            continue
        # ISO 8601 sin huso horario, NO RFC 822 pese a que RSS 2.0 lo exige
        # (hallazgo real, ADR 0009) -- fromisoformat, no email.utils.
        item_date: date = datetime.fromisoformat(pubdate_el.text).date()
        if item_date == target:
            description_el = item.find("description")
            if description_el is not None and description_el.text:
                return description_el.text
            return None
    return None


def extract_identifier_pdf_pairs(description_html: str) -> list[RawBulletinIndexEntry]:
    unescaped = html.unescape(description_html)
    return [
        RawBulletinIndexEntry(identifier=identifier, pdf_url=f"{pdf_url}.PDF")
        for _slug, identifier, pdf_url in _PAIR_RE.findall(unescaped)
    ]


def derive_xml_url(pdf_url: str) -> str:
    """El XML hermano del PDF comparte base y solo cambia la extensión
    (confirmado real contra el `encoding` JSON-LD de la disposición y con
    80/80 peticiones reales exitosas — ver ADR 0009), no una heurística."""
    assert pdf_url.endswith(".PDF")
    return pdf_url[: -len(".PDF")] + ".xml"


class RawDisposicionMetadata(TypedDict):
    identifier: str
    title: str
    section_code: str
    section_name: str


def _child_text(element: ET.Element, tag: str) -> str:
    child = element.find(tag)
    assert child is not None and child.text is not None
    return child.text.strip()


def parse_disposicion_xml(body: bytes) -> RawDisposicionMetadata:
    root = ET.fromstring(body)
    metadatos = root.find("metadatos")
    assert metadatos is not None

    identifier = _child_text(metadatos, "identificador")
    title = " ".join(_child_text(metadatos, "titulo").split())  # colapsa saltos de línea reales
    seccion_raw = _child_text(metadatos, "seccion")

    match = _SECTION_RE.match(seccion_raw)
    if match:
        section_code, section_name = match.group(1), match.group(2).strip()
    else:
        section_code, section_name = "", seccion_raw

    return RawDisposicionMetadata(
        identifier=identifier,
        title=title,
        section_code=section_code,
        section_name=section_name,
    )
