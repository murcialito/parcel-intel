import psycopg
import pytest

from parcel_intel.adapters.postgis.repository import PostgisParcelRepository
from parcel_intel.domain.report import ParcelReport
from parcel_intel.ports.errors import ParcelNotCachedError
from tests.factories import make_building, make_parcel

pytestmark = pytest.mark.integration

_CUERPO_PRINCIPAL = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0))
_ANEXO = ((20.0, 0.0), (25.0, 0.0), (25.0, 5.0), (20.0, 5.0), (20.0, 0.0))


def test_guarda_y_lee_parcela_con_edificios_multianillo(
    repository: PostgisParcelRepository,
) -> None:
    parcel = make_parcel(cadastral_reference="99043A90100001", area_m2=901.0)
    edificio_multianillo = make_building(
        cadastral_reference="9900201ZZ0000S",
        rings=(_CUERPO_PRINCIPAL, _ANEXO),
        area_m2=152.0,
        construction_year=1980,
    )
    otro_edificio = make_building(
        cadastral_reference="9900202ZZ0000S",
        area_m2=60.0,
        construction_year=None,
    )

    repository.save_parcel(parcel)
    repository.save_buildings(parcel.cadastral_reference, [edificio_multianillo, otro_edificio])

    parcel_leida = repository.get_parcel("99043A90100001")
    edificios_leidos = repository.get_buildings_for_parcel("99043A90100001")

    assert parcel_leida.cadastral_reference == parcel.cadastral_reference
    assert parcel_leida.area_m2 == parcel.area_m2
    assert parcel_leida.municipality == parcel.municipality
    assert parcel_leida.geometry.srid == 25830
    assert parcel_leida.provenance == parcel.provenance

    assert len(edificios_leidos) == 2
    multianillo_leido = next(
        b for b in edificios_leidos if b.cadastral_reference == "9900201ZZ0000S"
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

    simple_leido = next(b for b in edificios_leidos if b.cadastral_reference == "9900202ZZ0000S")
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
    with pytest.raises(ParcelNotCachedError):
        repository.get_parcel("28043A00999999")


def test_sin_edificios_devuelve_lista_vacia(repository: PostgisParcelRepository) -> None:
    parcel = make_parcel(cadastral_reference="99170A90100001")
    repository.save_parcel(parcel)

    assert repository.get_buildings_for_parcel("99170A90100001") == []


def test_la_conexion_se_recupera_tras_un_fallo_sql(repository: PostgisParcelRepository) -> None:
    # Reproduce el bug encontrado en revisión: sin rollback explícito tras un
    # error, psycopg deja la conexión en estado "aborted" y cualquier
    # operación posterior falla con InFailedSqlTransaction, un error que no
    # tiene nada que ver con la causa real. El uso del gestor de contexto de
    # la conexión (`with self._connection:`) debe hacer rollback automático.
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        repository.save_buildings("28043A00999999", [make_building()])

    parcel = make_parcel(cadastral_reference="99043A90100001")
    repository.save_parcel(parcel)
    parcel_leida = repository.get_parcel("99043A90100001")

    assert parcel_leida.cadastral_reference == "99043A90100001"


def test_get_report_sin_cache_lanza_not_cached(repository: PostgisParcelRepository) -> None:
    with pytest.raises(ParcelNotCachedError):
        repository.get_report("28043A00999999")


def test_save_report_y_get_report_round_trip_con_multianillo(
    repository: PostgisParcelRepository,
) -> None:
    parcel = make_parcel(cadastral_reference="99043A90100001", area_m2=901.0)
    edificio_multianillo = make_building(
        cadastral_reference="9900201ZZ0000S",
        rings=(_CUERPO_PRINCIPAL, _ANEXO),
        area_m2=152.0,
        construction_year=1980,
    )
    report = ParcelReport(parcel=parcel, buildings=(edificio_multianillo,))

    repository.save_report(report)
    report_leido = repository.get_report("99043A90100001")

    assert report_leido.parcel.cadastral_reference == "99043A90100001"
    assert len(report_leido.buildings) == 1
    assert len(report_leido.buildings[0].geometry.rings) == 2


def test_save_report_dos_veces_no_duplica_edificios(
    repository: PostgisParcelRepository,
) -> None:
    # Reproduce el riesgo encontrado en revisión: dos peticiones concurrentes
    # a la misma referencia nueva ejecutarían save_report dos veces (ambas
    # cache-miss). Sin UNIQUE(parcel_reference, cadastral_reference) +
    # ON CONFLICT en building, la segunda duplicaría la fila del edificio
    # en vez de actualizarla -- y como el caché es permanente, nunca se
    # autocorregiría.
    parcel = make_parcel(cadastral_reference="99043A90100001")
    building = make_building(cadastral_reference="9900201ZZ0000S", area_m2=152.0)
    report = ParcelReport(parcel=parcel, buildings=(building,))

    repository.save_report(report)
    repository.save_report(report)

    edificios = repository.get_buildings_for_parcel("99043A90100001")
    assert len(edificios) == 1
    assert edificios[0].area_m2 == 152.0


def test_save_report_es_atomico_edificio_huerfano_no_dura_la_parcela(
    repository: PostgisParcelRepository,
) -> None:
    # save_report guarda parcela + edificios en una sola transacción. Si el
    # segundo edificio de la lista fuera inválido, la parcela tampoco debe
    # quedar persistida -- de lo contrario habría una parcela cacheada con
    # cero edificios, indistinguible de una parcela rústica real sin ellos.
    parcel = make_parcel(cadastral_reference="99043A90100001")
    edificio_valido = make_building(cadastral_reference="9900201ZZ0000S")
    edificio_con_origin_invalido = make_building(cadastral_reference="9900202ZZ0000S")
    object.__setattr__(edificio_con_origin_invalido, "origin", "no-es-un-origin-valido")
    report = ParcelReport(parcel=parcel, buildings=(edificio_valido, edificio_con_origin_invalido))

    with pytest.raises(psycopg.errors.CheckViolation):
        repository.save_report(report)

    with pytest.raises(ParcelNotCachedError):
        repository.get_report("99043A90100001")
