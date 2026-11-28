"""Código de inventario de los tramos (historia #288): validación y cruce."""

from datetime import UTC, datetime

import pytest

from parcel_intel.domain.candidate_inventory import (
    MUNICIPALITY_PREFIXES,
    InvalidInventoryCodeError,
    InventoryCode,
    reconcile_inventory,
)
from parcel_intel.domain.candidate_review import (
    CandidateReview,
    candidate_fingerprint,
    reconcile,
)
from tests.fixtures.candidatos_revision import generar

INE = "28043"
ID = "a" * 16
CANDIDATES = generar.candidates()


def test_prefijos_fijados() -> None:
    assert MUNICIPALITY_PREFIXES == {"28043": "COL"}


def test_codigo_con_y_sin_nombre() -> None:
    plain = InventoryCode.from_text(ID, "COL-001", INE)
    named = InventoryCode.from_text(ID, "COL-012-Camino de Uceda", INE)
    assert (plain.prefix, plain.number, plain.name, plain.code) == ("COL", 1, None, "COL-001")
    assert (named.number, named.name, named.code) == (
        12,
        "Camino de Uceda",
        "COL-012-Camino de Uceda",
    )
    assert InventoryCode.from_text(ID, "COL-1000", INE).number == 1000


@pytest.mark.parametrize(
    "text",
    [
        "VAL-001",  # otro prefijo
        "COL-01",  # menos de 3 dígitos
        "col-001",  # minúsculas
        "COL-001-",  # nombre vacío
        "COL-001-" + "x" * 61,  # demasiado largo
        "COL-001-Camino_de_Uceda",  # carácter fuera de la lista
        "COL-001-Camino  de Uceda",  # doble espacio
        "COL-001- Camino",  # espacio al borde
        "COL-0001",  # ceros de más
        "COL-001-Camino\nUceda",
        "COL-001-propietario",  # palabra vetada
        "COL-001-9872023VH5797S0001WX",  # referencia catastral
    ],
)
def test_codigos_mal_formados_se_rechazan_sin_repetir_el_valor(text: str) -> None:
    with pytest.raises(InvalidInventoryCodeError) as error:
        InventoryCode.from_text(ID, text, INE)
    message = str(error.value)
    assert message.startswith(f"{ID}: codigo:")
    tail = text.split("-", 2)[-1]
    assert text not in message and (not tail or tail not in message)


def test_municipio_sin_prefijo_fijado() -> None:
    with pytest.raises(InvalidInventoryCodeError, match="prefijo fijado"):
        InventoryCode.from_text(ID, "COL-001", "28013")


def test_constructor_valida_los_campos() -> None:
    for kwargs in (
        {"candidate_id": "x"},
        {"prefix": "co"},
        {"number": 0},
        {"name": ""},
    ):
        base = {"candidate_id": ID, "prefix": "COL", "number": 1, "name": None}
        with pytest.raises(InvalidInventoryCodeError):
            InventoryCode(**{**base, **kwargs})  # type: ignore[arg-type]


def test_repetidos_se_rechazan_al_cruzar() -> None:
    state = reconcile(generar.report(), ())
    other = "b" * 16
    with pytest.raises(InvalidInventoryCodeError, match="dos códigos"):
        reconcile_inventory(state, (InventoryCode(ID, "COL", 1), InventoryCode(ID, "COL", 2)))
    with pytest.raises(InvalidInventoryCodeError, match="número repetido"):
        reconcile_inventory(
            state, (InventoryCode(ID, "COL", 1), InventoryCode(other, "COL", 1, "X"))
        )


def test_cruce_clasifica_asignados_sin_codigo_no_aprobados_y_huerfanos() -> None:
    approved = CANDIDATES["aprobado"]
    review = CandidateReview(
        approved.candidate_id,
        "approved",
        reviewed_by="r",
        reviewed_at=datetime(2026, 11, 28, tzinfo=UTC),
        candidate_sha256=candidate_fingerprint(approved),
    )
    state = reconcile(generar.report(), (review,))
    codes = (
        InventoryCode(CANDIDATES["propuesto"].candidate_id, "COL", 3),
        InventoryCode(approved.candidate_id, "COL", 2),
        InventoryCode("f" * 16, "COL", 1),
    )
    result = reconcile_inventory(state, codes)
    assert [c.number for c in result.assigned] == [2]
    assert [c.number for c in result.on_unapproved] == [3]
    assert [c.number for c in result.orphans] == [1]
    assert result.without_code == ()
    assert not result.is_consistent()
    assert reconcile_inventory(state, ()).without_code == (approved.candidate_id,)
