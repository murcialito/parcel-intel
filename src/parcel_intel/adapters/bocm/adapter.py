from datetime import UTC, date, datetime
from datetime import datetime as _datetime

from parcel_intel.adapters.bocm.client import SUMARIOS_RSS_URL, UrlGetter, default_url_getter
from parcel_intel.adapters.bocm.parsing import (
    derive_xml_url,
    extract_identifier_pdf_pairs,
    find_item_description_for_day,
    parse_disposicion_xml,
)
from parcel_intel.domain.bulletin import BulletinNotice
from parcel_intel.domain.provenance import Provenance
from parcel_intel.ports.errors import BulletinNotPublishedError, InvalidBulletinDayError


def _validate_day(day: str) -> None:
    """Mismo contrato que `adapters/boe/adapter.py`: `AAAAMMDD`, fecha de
    calendario real, antes de cualquier petición de red."""
    if len(day) != 8 or not day.isdigit():
        raise InvalidBulletinDayError(day)
    try:
        datetime.strptime(day, "%Y%m%d")
    except ValueError as error:
        raise InvalidBulletinDayError(day) from error


def _today() -> date:
    return _datetime.now(tz=UTC).date()


class BocmAdapter:
    """Implementa `OfficialBulletinPort` contra BOCM, confirmado en
    `sources/REGISTRY.md` (ADR 0009). Cliente aislado: no se conecta
    todavía a ningún caso de uso ni cachea resultados.

    `sumarios.rss` no da el título real de ninguna disposición (confirmado
    real: solo identificador + enlace a PDF) — por cada disposición del día
    pedido, el adapter descarga también el XML hermano del PDF (mismo path,
    solo cambia la extensión) para obtener título y sección reales. Esto
    significa N+1 peticiones por llamada, no una sola como BOE.
    """

    def __init__(self, get_url: UrlGetter = default_url_getter) -> None:
        self._get_url = get_url

    def get_daily_bulletin(self, day: str) -> list[BulletinNotice]:
        _validate_day(day)
        rss_body = self._get_url(SUMARIOS_RSS_URL)
        description = find_item_description_for_day(rss_body, day)
        if description is None:
            raise BulletinNotPublishedError(day)

        notices: list[BulletinNotice] = []
        for entry in extract_identifier_pdf_pairs(description):
            xml_url = derive_xml_url(entry["pdf_url"])
            xml_body = self._get_url(xml_url)
            metadata = parse_disposicion_xml(xml_body)
            notices.append(
                BulletinNotice(
                    identifier=metadata["identifier"],
                    title=metadata["title"],
                    section_code=metadata["section_code"],
                    section_name=metadata["section_name"],
                    pdf_url=entry["pdf_url"],
                    provenance=Provenance(
                        source="bocm",
                        url=SUMARIOS_RSS_URL,
                        retrieved_at=_today(),
                        license=None,
                    ),
                )
            )
        return notices
