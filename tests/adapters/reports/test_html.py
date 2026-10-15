import pytest

from parcel_intel.adapters.reports.html import EmptyGeometryError, render_parcel_report_html
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.report import ParcelReport
from tests.factories import make_building, make_parcel


def test_render_con_edificios_incluye_tabla_y_svg() -> None:
    parcel = make_parcel(cadastral_reference="REFCAT-RETIRADA", area_m2=707.0)
    building = make_building(area_m2=152.0, construction_year=1980)
    report = ParcelReport(parcel=parcel, buildings=(building,))

    html = render_parcel_report_html(report)

    assert "REFCAT-RETIRADA" in html
    assert "707 m²" in html
    assert "152 m²" in html
    assert "1980" in html
    assert html.count('class="parcel"') == 1
    assert html.count('class="building"') == 1


def test_render_sin_edificios_muestra_mensaje() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())

    html = render_parcel_report_html(report)

    assert "Sin edificios registrados en Catastro." in html
    assert 'class="building"' not in html


def test_render_edificio_multianillo_dibuja_todos_los_anillos() -> None:
    cuerpo_principal = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0))
    anexo = ((20.0, 0.0), (25.0, 0.0), (25.0, 5.0), (20.0, 5.0), (20.0, 0.0))
    building = make_building(rings=(cuerpo_principal, anexo))
    report = ParcelReport(parcel=make_parcel(), buildings=(building,))

    html = render_parcel_report_html(report)

    assert html.count('class="building"') == 2


def test_construction_year_cero_no_se_trata_como_ausente() -> None:
    building = make_building(construction_year=0)
    report = ParcelReport(parcel=make_parcel(), buildings=(building,))

    html = render_parcel_report_html(report)

    assert "<td>0</td>" in html


def test_parcela_sin_geometria_lanza_error_explicito() -> None:
    parcel = make_parcel(rings=())
    report = ParcelReport(parcel=parcel, buildings=())

    with pytest.raises(EmptyGeometryError):
        render_parcel_report_html(report)


def test_todos_los_puntos_en_la_misma_coordenada_no_falla() -> None:
    punto_repetido = ((5.0, 5.0), (5.0, 5.0), (5.0, 5.0))
    parcel = make_parcel(rings=(punto_repetido,))
    report = ParcelReport(parcel=parcel, buildings=())

    html = render_parcel_report_html(report)

    assert "<svg" in html


def test_geometry_import_usada_para_tipado() -> None:
    # Confirma que Geometry sigue siendo el tipo esperado por domain/report.py,
    # para que un cambio de forma en el dominio rompa este test en vez de
    # fallar silenciosamente en producción.
    geometry = make_parcel().geometry
    assert isinstance(geometry, Geometry)
