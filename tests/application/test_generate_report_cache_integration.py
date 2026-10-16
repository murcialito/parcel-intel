import pytest

from parcel_intel.adapters.catastro.adapter import CatastroAdapter
from parcel_intel.adapters.postgis.repository import PostgisParcelRepository
from parcel_intel.adapters.reports.html import render_parcel_report_html
from parcel_intel.application.generate_report import GenerateParcelReportUseCase
from parcel_intel.domain.report import EnrichedParcelReport
from tests.adapters.catastro.helpers import FIXTURES_DIR, SequenceHttpGetter

pytestmark = pytest.mark.integration

# El ciclo completo de una referencia hace 5 peticiones reales a Catastro:
# get_parcel (centroide + bbox) y get_buildings (centroide + bbox parcela +
# bbox edificios, ver adapters/catastro/adapter.py). Fixtures reales de la
# historia 0002/0004: REFCAT-RETIRADA (parcela urbana con un edificio real
# de 2 anillos -- cuerpo principal + anexo).
_FIXTURES_UN_CICLO_COMPLETO = [
    FIXTURES_DIR / "cpmrc_colmenar_edificio_real.xml",
    FIXTURES_DIR / "wfsCP_colmenar_parcela_con_edificios.xml",
    FIXTURES_DIR / "cpmrc_colmenar_edificio_real.xml",
    FIXTURES_DIR / "wfsCP_colmenar_parcela_con_edificios.xml",
    FIXTURES_DIR / "wfsBU_colmenar_dense_bbox.xml",
]


def test_segunda_peticion_no_llama_a_catastro_y_sirve_el_mismo_html(
    repository: PostgisParcelRepository,
) -> None:
    http_get = SequenceHttpGetter(_FIXTURES_UN_CICLO_COMPLETO)
    adapter = CatastroAdapter(provincia="MADRID", municipio="COLMENAR DE OREJA", http_get=http_get)
    use_case = GenerateParcelReportUseCase(
        parcel_port=adapter, building_port=adapter, repository=repository
    )

    primer_informe = use_case.execute("REFCAT-RETIRADA")
    assert len(http_get.calls) == 5
    assert len(primer_informe.buildings) == 1
    assert len(primer_informe.buildings[0].geometry.rings) == 3  # cuerpo + 2 anexos

    # Si execute() intentara llamar a Catastro otra vez, SequenceHttpGetter
    # lanzaría IndexError: solo hay 5 fixtures cargadas, ya consumidas.
    segundo_informe = use_case.execute("REFCAT-RETIRADA")
    assert len(http_get.calls) == 5

    enriched_primero = EnrichedParcelReport(
        report=primer_informe,
        orthophoto=None,
        ndvi_summary=None,
        boe_notices=None,
        bocm_notices=None,
        land_classifications=None,
        watercourses=None,
        flood_hazard=None,
        livestock_trails=None,
        protected_areas=None,
    )
    enriched_segundo = EnrichedParcelReport(
        report=segundo_informe,
        orthophoto=None,
        ndvi_summary=None,
        boe_notices=None,
        bocm_notices=None,
        land_classifications=None,
        watercourses=None,
        flood_hazard=None,
        livestock_trails=None,
        protected_areas=None,
    )
    assert render_parcel_report_html(enriched_primero) == render_parcel_report_html(
        enriched_segundo
    )


def test_referencias_distintas_no_comparten_cache(
    repository: PostgisParcelRepository,
) -> None:
    http_get = SequenceHttpGetter(
        _FIXTURES_UN_CICLO_COMPLETO
        + [
            FIXTURES_DIR / "cpmrc_colmenar_14char.xml",
            FIXTURES_DIR / "wfsCP_colmenar_rustica_por_centroide.xml",
            FIXTURES_DIR / "cpmrc_colmenar_14char.xml",
            FIXTURES_DIR / "wfsCP_colmenar_rustica_por_centroide.xml",
            FIXTURES_DIR / "wfsBU_colmenar_urbano_por_centroide.xml",
        ]
    )
    adapter = CatastroAdapter(provincia="MADRID", municipio="COLMENAR DE OREJA", http_get=http_get)
    use_case = GenerateParcelReportUseCase(
        parcel_port=adapter, building_port=adapter, repository=repository
    )

    use_case.execute("REFCAT-RETIRADA")
    assert len(http_get.calls) == 5

    informe_rustico = use_case.execute("REFCAT-RETIRADA")
    assert len(http_get.calls) == 10
    assert informe_rustico.parcel.cadastral_reference == "REFCAT-RETIRADA"
    assert informe_rustico.buildings == ()
