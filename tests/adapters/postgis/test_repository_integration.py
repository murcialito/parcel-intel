import psycopg
import pytest

from parcel_intel.adapters.postgis.repository import (
    ParcelNotFoundInRepositoryError,
    PostgisParcelRepository,
)
from tests.factories import make_building, make_parcel

pytestmark = pytest.mark.integration

_CUERPO_PRINCIPAL = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0))
_ANEXO = ((20.0, 0.0), (25.0, 0.0), (25.0, 5.0), (20.0, 5.0), (20.0, 0.0))


def test_guarda_y_lee_parcela_con_edificios_multianillo(
    repository: PostgisParcelRepository,
) -> None:
    parcel = make_parcel(cadastral_reference="REFCAT-RETIRADA", area_m2=901.0)
    edificio_multianillo = make_building(
        cadastral_reference="REFCAT-RETIRADA",
        rings=(_CUERPO_PRINCIPAL, _ANEXO),
        area_m2=152.0,
        construction_year=1980,
    )
    otro_edificio = make_building(
        cadastral_reference="REFCAT-RETIRADA",
        area_m2=60.0,
        construction_year=None,
    )

    repository.save_parcel(parcel)
    repository.save_buildings(parcel.cadastral_reference, [edificio_multianillo, otro_edificio])

    parcel_leida = repository.get_parcel("REFCAT-RETIRADA")
    edificios_leidos = repository.get_buildings_for_parcel("REFCAT-RETIRADA")

    assert parcel_leida.cadastral_reference == parcel.cadastral_reference
    assert parcel_leida.area_m2 == parcel.area_m2
    assert parcel_leida.municipality == parcel.municipality
    assert parcel_leida.geometry.srid == 25830
    assert parcel_leida.provenance == parcel.provenance

    assert len(edificios_leidos) == 2
    multianillo_leido = next(
        b for b in edificios_leidos if b.cadastral_reference == "REFCAT-RETIRADA"
    )
    assert len(multianillo_leido.geometry.rings) == 2
    # El WKT cierra los anillos (primer punto == último); el dominio original
    # no los tenía cerrados, así que se compara por conjunto de vértices,
    # no por igualdad exacta de la tupla de anillos.
    assert set(multianillo_leido.geometry.rings[0]) >= set(_CUERPO_PRINCIPAL)
    assert set(multianillo_leido.geometry.rings[1]) >= set(_ANEXO)
    assert multianillo_leido.area_m2 == 152.0
    assert multianillo_leido.construction_year == 1980
    assert multianillo_leido.origin == "catastro"

    simple_leido = next(b for b in edificios_leidos if b.cadastral_reference == "REFCAT-RETIRADA")
    assert simple_leido.construction_year is None


def test_guardar_edificio_de_parcela_inexistente_falla_por_clave_foranea(
    repository: PostgisParcelRepository,
) -> None:
    building = make_building()

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        repository.save_buildings("28043A00999999", [building])


def test_leer_parcela_inexistente_lanza_error_explicito(
    repository: PostgisParcelRepository,
) -> None:
    with pytest.raises(ParcelNotFoundInRepositoryError):
        repository.get_parcel("28043A00999999")


def test_sin_edificios_devuelve_lista_vacia(repository: PostgisParcelRepository) -> None:
    parcel = make_parcel(cadastral_reference="REFCAT-RETIRADA")
    repository.save_parcel(parcel)

    assert repository.get_buildings_for_parcel("REFCAT-RETIRADA") == []
