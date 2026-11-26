"""Historia #33: marca de redistribución en Provenance y guarda de publicación."""

from dataclasses import dataclass
from datetime import date

import pytest

from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.publication import NotRedistributableError, PublishableLayer

pytestmark = pytest.mark.acceptance

_DATE = date(2026, 11, 26)


@dataclass(frozen=True)
class _Item:
    name: str
    provenance: Provenance


def _public(name: str) -> _Item:
    return _Item(
        name=name,
        provenance=Provenance(
            source=f"fuente {name}",
            url=f"https://example.invalid/{name}",
            retrieved_at=_DATE,
            license="CC BY 4.0",
            redistribution=Redistribution.PUBLIC,
        ),
    )


def _internal(name: str) -> _Item:
    return _Item(
        name=name,
        provenance=Provenance(
            source=f"fuente interna {name}",
            url=f"https://example.invalid/interna/{name}",
            retrieved_at=_DATE,
            license="licencia restrictiva",
            redistribution=Redistribution.INTERNAL_ONLY,
        ),
    )


def test_ca1_procedencia_sin_redistribucion_vale_solo_uso_interno() -> None:
    """Dado un `Provenance` construido sin indicar `redistribution`, cuando se inspecciona,
    entonces vale `Redistribution.INTERNAL_ONLY`."""
    provenance = Provenance(source="catastro", url="https://example.invalid", retrieved_at=_DATE)

    assert provenance.redistribution is Redistribution.INTERNAL_ONLY


def test_ca2_capa_con_elementos_publicos_se_construye_en_orden() -> None:
    """Dados dos elementos con `provenance.redistribution == Redistribution.PUBLIC`, cuando se
    construye `PublishableLayer(name, items)`, entonces se construye y conserva los dos
    elementos en orden."""
    first, second = _public("primero"), _public("segundo")

    layer = PublishableLayer(name="caminos", items=(first, second))

    assert layer.name == "caminos"
    assert layer.items == (first, second)


def test_ca3_capa_con_elemento_interno_lanza_error_con_fuente_y_url() -> None:
    """Dada una lista con un elemento `PUBLIC` y otro `INTERNAL_ONLY`, cuando se construye
    `PublishableLayer`, entonces lanza `NotRedistributableError`, y el mensaje incluye el nombre
    de la capa y la `source` y la `url` del elemento interno."""
    internal = _internal("interno")

    with pytest.raises(NotRedistributableError) as caught:
        PublishableLayer(name="mezcla", items=(_public("publico"), internal))

    message = str(caught.value)
    assert "mezcla" in message
    assert internal.provenance.source in message
    assert internal.provenance.url in message


def test_ca4_procedencia_por_defecto_se_rechaza_en_capa_publicable() -> None:
    """Dado un elemento cuyo `Provenance` usa el valor por defecto, cuando se intenta meter en
    `PublishableLayer`, entonces se rechaza: lo publicable hay que declararlo."""

    @dataclass(frozen=True)
    class _DefaultItem:
        provenance: Provenance

    item = _DefaultItem(
        provenance=Provenance(
            source="nueva fuente", url="https://example.invalid", retrieved_at=_DATE
        )
    )

    with pytest.raises(NotRedistributableError):
        PublishableLayer(name="por_defecto", items=(item,))


def test_ca5_construccion_anterior_no_cambia_de_comportamiento() -> None:
    """Dado el repositorio con el cambio, cuando se ejecutan literalmente `uv run pytest`,
    `uv run mypy`, `uv run ruff check .` y `uv run lint-imports`, entonces todo pasa sin tocar
    el comportamiento de ningún adapter existente.

    Los cuatro comandos se verifican en la PR. Aquí se comprueba la parte que este test puede
    observar: la forma de construir `Provenance` que usan los adapters existentes sigue valiendo
    y equivale a marcar explícitamente `INTERNAL_ONLY`."""
    legacy = Provenance(
        source="boe", url="https://example.invalid", retrieved_at=_DATE, license=None
    )
    explicit = Provenance(
        source="boe",
        url="https://example.invalid",
        retrieved_at=_DATE,
        license=None,
        redistribution=Redistribution.INTERNAL_ONLY,
    )

    assert legacy == explicit
