import json
from datetime import UTC, date, datetime
from datetime import datetime as _datetime

from parcel_intel.adapters.boe.client import (
    SUMARIO_URL_TEMPLATE,
    DailySummaryGetter,
    default_daily_summary_getter,
)
from parcel_intel.adapters.boe.parsing import parse_daily_summary
from parcel_intel.domain.bulletin import BulletinNotice
from parcel_intel.domain.provenance import Provenance
from parcel_intel.ports.errors import BulletinNotPublishedError, InvalidBulletinDayError


def _validate_day(day: str) -> None:
    """`AAAAMMDD`, fecha de calendario real — lanza antes de cualquier
    petición de red (el propio servidor también valida el formato, pero el
    AC de esta historia exige que el cliente nunca llegue a mandar una
    fecha inválida, confirmado real en REGISTRY.md)."""
    if len(day) != 8 or not day.isdigit():
        raise InvalidBulletinDayError(day)
    try:
        datetime.strptime(day, "%Y%m%d")
    except ValueError as error:
        raise InvalidBulletinDayError(day) from error


def _today() -> date:
    return _datetime.now(tz=UTC).date()


class BoeAdapter:
    """Implementa `OfficialBulletinPort` contra la API de datos abiertos de
    BOE confirmada en `sources/REGISTRY.md`. Cliente aislado (ADR 0008): no
    se conecta todavía a ningún caso de uso ni cachea resultados."""

    def __init__(
        self, get_daily_summary: DailySummaryGetter = default_daily_summary_getter
    ) -> None:
        self._get_daily_summary = get_daily_summary

    def get_daily_bulletin(self, day: str) -> list[BulletinNotice]:
        _validate_day(day)
        status_code, body = self._get_daily_summary(day)
        if status_code == 404:
            raise BulletinNotPublishedError(day)
        response = json.loads(body)
        url = SUMARIO_URL_TEMPLATE.format(day=day)
        provenance = Provenance(source="boe", url=url, retrieved_at=_today(), license=None)
        return [
            BulletinNotice(
                identifier=notice["identifier"],
                title=notice["title"],
                section_code=notice["section_code"],
                section_name=notice["section_name"],
                pdf_url=notice["pdf_url"],
                provenance=provenance,
            )
            for notice in parse_daily_summary(response)
        ]
