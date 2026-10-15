from datetime import date

from parcel_intel.domain.bulletin import BulletinNotice, filter_by_title
from parcel_intel.domain.provenance import Provenance

_PROVENANCE = Provenance(
    source="boe", url="https://example.invalid", retrieved_at=date(2026, 10, 15)
)


def _notice(title: str, identifier: str = "BOE-A-1") -> BulletinNotice:
    return BulletinNotice(
        identifier=identifier,
        title=title,
        section_code="1",
        section_name="I. Disposiciones generales",
        pdf_url="https://example.invalid/doc.pdf",
        provenance=_PROVENANCE,
    )


def test_filtra_por_substring_simple() -> None:
    notices = [_notice("Orden sobre Colmenar de Oreja"), _notice("Resolución de otro asunto")]

    result = filter_by_title(notices, "Colmenar de Oreja")

    assert [n.title for n in result] == ["Orden sobre Colmenar de Oreja"]


def test_sin_coincidencias_devuelve_lista_vacia() -> None:
    notices = [_notice("Resolución de otro asunto")]

    assert filter_by_title(notices, "Villaconejos") == []


def test_insensible_a_mayusculas() -> None:
    notices = [_notice("ORDEN SOBRE VILLACONEJOS")]

    assert filter_by_title(notices, "villaconejos") == notices


def test_insensible_a_tildes() -> None:
    notices = [_notice("Resolución del término municipal")]

    assert filter_by_title(notices, "resolucion") == notices
    assert filter_by_title(notices, "término") == notices
    assert filter_by_title(notices, "termino") == notices


def test_lista_vacia_de_entrada() -> None:
    assert filter_by_title([], "Villaconejos") == []
