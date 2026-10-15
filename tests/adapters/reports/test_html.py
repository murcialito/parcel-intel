from datetime import date

import pytest

from parcel_intel.adapters.reports.html import EmptyGeometryError, render_parcel_report_html
from parcel_intel.domain.bulletin import BulletinNotice
from parcel_intel.domain.geometry import Geometry
from parcel_intel.domain.ndvi import NdviSummary
from parcel_intel.domain.orthophoto import Orthophoto
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.report import EnrichedParcelReport, ParcelReport
from tests.factories import make_building, make_parcel


def _enrich(
    report: ParcelReport,
    *,
    orthophoto: Orthophoto | None = None,
    ndvi_summary: NdviSummary | None = None,
    boe_notices: tuple[BulletinNotice, ...] | None = None,
    bocm_notices: tuple[BulletinNotice, ...] | None = None,
) -> EnrichedParcelReport:
    return EnrichedParcelReport(
        report=report,
        orthophoto=orthophoto,
        ndvi_summary=ndvi_summary,
        boe_notices=boe_notices,
        bocm_notices=bocm_notices,
    )


def _notice(title: str) -> BulletinNotice:
    return BulletinNotice(
        identifier="BOE-A-2026-1",
        title=title,
        section_code="I",
        section_name="DISPOSICIONES GENERALES",
        pdf_url="https://example.org/boe-a-2026-1.pdf",
        provenance=Provenance(
            source="boe", url="https://example.org", retrieved_at=date(2026, 10, 15)
        ),
    )


def test_render_con_edificios_incluye_tabla_y_svg() -> None:
    parcel = make_parcel(cadastral_reference="REFCAT-RETIRADA", area_m2=707.0)
    building = make_building(area_m2=152.0, construction_year=1980)
    report = ParcelReport(parcel=parcel, buildings=(building,))

    html = render_parcel_report_html(_enrich(report))

    assert "REFCAT-RETIRADA" in html
    assert "707 m²" in html
    assert "152 m²" in html
    assert "1980" in html
    assert html.count('class="parcel"') == 1
    assert html.count('class="building"') == 1


def test_render_sin_edificios_muestra_mensaje() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())

    html = render_parcel_report_html(_enrich(report))

    assert "Sin edificios registrados en Catastro." in html
    assert 'class="building"' not in html


def test_render_edificio_multianillo_dibuja_todos_los_anillos() -> None:
    cuerpo_principal = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0))
    anexo = ((20.0, 0.0), (25.0, 0.0), (25.0, 5.0), (20.0, 5.0), (20.0, 0.0))
    building = make_building(rings=(cuerpo_principal, anexo))
    report = ParcelReport(parcel=make_parcel(), buildings=(building,))

    html = render_parcel_report_html(_enrich(report))

    assert html.count('class="building"') == 2


def test_construction_year_cero_no_se_trata_como_ausente() -> None:
    building = make_building(construction_year=0)
    report = ParcelReport(parcel=make_parcel(), buildings=(building,))

    html = render_parcel_report_html(_enrich(report))

    assert "<td>0</td>" in html


def test_parcela_sin_geometria_lanza_error_explicito() -> None:
    parcel = make_parcel(rings=())
    report = ParcelReport(parcel=parcel, buildings=())

    with pytest.raises(EmptyGeometryError):
        render_parcel_report_html(_enrich(report))


def test_todos_los_puntos_en_la_misma_coordenada_no_falla() -> None:
    punto_repetido = ((5.0, 5.0), (5.0, 5.0), (5.0, 5.0))
    parcel = make_parcel(rings=(punto_repetido,))
    report = ParcelReport(parcel=parcel, buildings=())

    html = render_parcel_report_html(_enrich(report))

    assert "<svg" in html


def test_geometry_import_usada_para_tipado() -> None:
    # Confirma que Geometry sigue siendo el tipo esperado por domain/report.py,
    # para que un cambio de forma en el dominio rompa este test en vez de
    # fallar silenciosamente en producción.
    geometry = make_parcel().geometry
    assert isinstance(geometry, Geometry)


def test_fuentes_sin_evidencia_se_muestran_como_no_disponible() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())

    html = render_parcel_report_html(_enrich(report))

    assert "Ortofoto actual (PNOA) no disponible." in html
    assert "Resumen NDVI (Sentinel-2) no disponible." in html
    assert "BOE no disponible." in html
    assert "BOCM no disponible." in html


def test_ortofoto_disponible_se_embebe_como_base64() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())
    orthophoto = Orthophoto(
        image=b"\xff\xd8\xff\xe0fake-jpeg",
        vintage="actual",
        provenance=Provenance(
            source="pnoa", url="https://example.org", retrieved_at=date(2026, 10, 15)
        ),
    )

    html = render_parcel_report_html(_enrich(report, orthophoto=orthophoto))

    assert "data:image/jpeg;base64," in html
    assert "Ortofoto actual (PNOA) no disponible." not in html


def test_ndvi_disponible_muestra_media_y_fecha() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())
    summary = NdviSummary(
        mean=0.42,
        scene_date=date(2026, 9, 1),
        cloud_cover_percent=12.0,
        provenance=Provenance(
            source="sentinel2", url="https://example.org", retrieved_at=date(2026, 10, 15)
        ),
    )

    html = render_parcel_report_html(_enrich(report, ndvi_summary=summary))

    assert "0.42" in html
    assert "2026-09-01" in html


def test_boletin_con_tupla_vacia_se_distingue_de_no_disponible() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())

    html = render_parcel_report_html(_enrich(report, boe_notices=(), bocm_notices=()))

    assert "Sin disposiciones de BOE que mencionen el municipio hoy." in html
    assert "Sin disposiciones de BOCM que mencionen el municipio hoy." in html
    assert "BOE no disponible." not in html
    assert "BOCM no disponible." not in html


def test_boletin_con_disposiciones_las_lista_con_enlace_al_pdf() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())
    notice = _notice("Convenio con el Ayuntamiento de Colmenar de Oreja")

    html = render_parcel_report_html(_enrich(report, boe_notices=(notice,)))

    assert "Convenio con el Ayuntamiento de Colmenar de Oreja" in html
    assert 'href="https://example.org/boe-a-2026-1.pdf"' in html
