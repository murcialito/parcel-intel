from datetime import date

import pytest

from parcel_intel.adapters.reports.html import EmptyGeometryError, render_parcel_report_html
from parcel_intel.domain.bulletin import BulletinNotice
from parcel_intel.domain.flood_hazard import FloodHazardSample
from parcel_intel.domain.geometry import Geometry, LineGeometry
from parcel_intel.domain.land_classification import LandClassification
from parcel_intel.domain.livestock_trail import LivestockTrail
from parcel_intel.domain.ndvi import NdviSummary
from parcel_intel.domain.norm import Norm, Provision
from parcel_intel.domain.orthophoto import Orthophoto
from parcel_intel.domain.protected_area import ProtectedArea
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.report import EnrichedParcelReport, ParcelReport
from parcel_intel.domain.rule import (
    AttributeCondition,
    Evidence,
    Finding,
    OverlapsCondition,
    Rule,
    RuleScope,
    WithinDistanceCondition,
)
from parcel_intel.domain.watercourse import Watercourse
from tests.factories import make_building, make_parcel


def _enrich(
    report: ParcelReport,
    *,
    orthophoto: Orthophoto | None = None,
    ndvi_summary: NdviSummary | None = None,
    boe_notices: tuple[BulletinNotice, ...] | None = None,
    bocm_notices: tuple[BulletinNotice, ...] | None = None,
    land_classifications: tuple[LandClassification, ...] | None = None,
    watercourses: tuple[Watercourse, ...] | None = None,
    flood_hazard: tuple[FloodHazardSample, ...] | None = None,
    livestock_trails: tuple[LivestockTrail, ...] | None = None,
    protected_areas: tuple[ProtectedArea, ...] | None = None,
) -> EnrichedParcelReport:
    return EnrichedParcelReport(
        report=report,
        orthophoto=orthophoto,
        ndvi_summary=ndvi_summary,
        boe_notices=boe_notices,
        bocm_notices=bocm_notices,
        land_classifications=land_classifications,
        watercourses=watercourses,
        flood_hazard=flood_hazard,
        livestock_trails=livestock_trails,
        protected_areas=protected_areas,
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
    parcel = make_parcel(cadastral_reference="9900201ZZ0000S", area_m2=707.0)
    building = make_building(area_m2=152.0, construction_year=1980)
    report = ParcelReport(parcel=parcel, buildings=(building,))

    html = render_parcel_report_html(_enrich(report))

    assert "9900201ZZ0000S" in html
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
    assert "Clasificación de suelo (IDEM) no disponible." in html
    assert "Cursos de agua (hidrografía) no disponible." in html
    assert "Peligrosidad por inundación no disponible." in html
    assert "Vías pecuarias (IDEM) no disponible." in html
    assert "Espacios protegidos Red Natura 2000 (IDEM) no disponible." in html
    assert "Sin hallazgos de las reglas evaluadas." in html


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


def _land_classification(general_category: str, municipality_name: str) -> LandClassification:
    return LandClassification(
        general_category=general_category,
        detailed_category=general_category.lower(),
        short_code="SUBNS",
        reference_date=date(2025, 6, 29),
        municipality_code="170",
        municipality_name=municipality_name,
        area_m2=1000.0,
        geometry=Geometry(rings=(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)),), srid=25830),
        provenance=Provenance(
            source="idem", url="https://example.org", retrieved_at=date(2026, 10, 15)
        ),
    )


def test_clasificacion_de_suelo_con_solape_muestra_cada_municipio() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())
    classifications = (
        _land_classification("Suelo No Urbanizable Común", "VILLACONEJOS"),
        _land_classification("Suelo No Urbanizable Protegido", "VILLACONEJOS"),
        _land_classification("Suelo No Urbanizable Común", "CHINCHÓN"),
    )

    html = render_parcel_report_html(_enrich(report, land_classifications=classifications))

    assert html.count("Suelo No Urbanizable Común") >= 2
    assert "Suelo No Urbanizable Protegido" in html
    assert "VILLACONEJOS" in html
    assert "CHINCHÓN" in html


def _watercourse(name: str | None) -> Watercourse:
    return Watercourse(
        name=name,
        hydrographic_demarcation_code="ES030",
        hydrographic_demarcation_name="Tajo",
        course_type="Curso natural",
        persistence="Estacional",
        min_width_m=1.0,
        max_width_m=5.0,
        length_m=2058.58,
        geometry=LineGeometry(points=((0.0, 0.0), (1.0, 1.0)), srid=25830),
        provenance=Provenance(
            source="idee-watercourse", url="https://example.org", retrieved_at=date(2026, 10, 15)
        ),
    )


def test_cauces_con_tupla_vacia_se_distingue_de_no_disponible() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())

    html = render_parcel_report_html(_enrich(report, watercourses=()))

    assert "Sin cursos de agua cercanos." in html
    assert "Cursos de agua (hidrografía) no disponible." not in html


def test_cauce_real_se_lista_con_nombre_y_demarcacion() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())

    html = render_parcel_report_html(
        _enrich(report, watercourses=(_watercourse("Barranco del Montero"),))
    )

    assert "Barranco del Montero" in html
    assert "Tajo" in html


def _flood_sample(kind: str, return_period: int, depth: float | None) -> FloodHazardSample:
    return FloodHazardSample(
        kind=kind,  # type: ignore[arg-type]
        return_period_years=return_period,
        water_depth_m=depth,
        provenance=Provenance(
            source="idee-flood-hazard", url="https://example.org", retrieved_at=date(2026, 10, 15)
        ),
    )


def test_peligrosidad_inundacion_muestra_las_cinco_combinaciones_con_no_data() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())
    samples = (
        _flood_sample("fluvial", 10, None),
        _flood_sample("fluvial", 100, 1.25),
        _flood_sample("fluvial", 500, None),
        _flood_sample("marina", 100, None),
        _flood_sample("marina", 500, None),
    )

    html = render_parcel_report_html(_enrich(report, flood_hazard=samples))

    assert html.count("NO DATA") == 4
    assert "1.25 m" in html


def _livestock_trail(name: str = "Vereda del Cristo") -> LivestockTrail:
    return LivestockTrail(
        trail_type="Vereda",
        name=name,
        municipality_code="043",
        municipality_name="COLMENAR DE OREJA",
        trail_code="2804301",
        length_m=10492.0,
        area_m2=122148.0,
        geometry=Geometry(rings=(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)),), srid=25830),
        provenance=Provenance(
            source="idem", url="https://example.org", retrieved_at=date(2026, 10, 15)
        ),
    )


def test_vias_pecuarias_con_tupla_vacia_se_distingue_de_no_disponible() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())

    html = render_parcel_report_html(_enrich(report, livestock_trails=()))

    assert "Sin vías pecuarias cercanas." in html
    assert "Vías pecuarias (IDEM) no disponible." not in html


def test_via_pecuaria_real_se_lista_con_valores_y_nota_de_anchura_no_legal() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())

    html = render_parcel_report_html(_enrich(report, livestock_trails=(_livestock_trail(),)))

    assert "Vereda del Cristo" in html
    assert "Vereda" in html
    assert "COLMENAR DE OREJA" in html
    assert "122148 m²" in html
    assert "10492 m" in html
    assert "no la anchura legal" in html


def _protected_area(
    plan_name: str = "Plan de gestión de vegas, cuestas y páramos del sureste de Madrid",
) -> ProtectedArea:
    return ProtectedArea(
        plan_code="SE",
        plan_name=plan_name,
        zone_code="X",
        zone_name="Espacio previamente ordenado",
        geometry=Geometry(rings=(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)),), srid=25830),
        provenance=Provenance(
            source="idem", url="https://example.org", retrieved_at=date(2026, 10, 15)
        ),
    )


def test_red_natura_con_tupla_vacia_se_distingue_de_no_disponible() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())

    html = render_parcel_report_html(_enrich(report, protected_areas=()))

    assert "Sin espacios protegidos Red Natura 2000 cercanos." in html
    assert "Espacios protegidos Red Natura 2000 (IDEM) no disponible." not in html


def test_espacio_protegido_real_se_lista_con_codigos_y_nombres() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())

    html = render_parcel_report_html(_enrich(report, protected_areas=(_protected_area(),)))

    assert "Plan SE:" in html
    assert "Plan de gestión de vegas, cuestas y páramos del sureste de Madrid" in html
    assert "Zona X:" in html
    assert "Espacio previamente ordenado" in html
    # Sin "Plan Plan" duplicado pese a que plan_name real empieza por "Plan de gestión..."
    assert "Plan Plan" not in html


def _finding() -> Finding:
    rule = Rule(
        identifier="madrid-colmenar-distancia-cauce",
        scope=RuleScope(region="madrid", soil_classes=("no_urbanizable",)),
        spatial=WithinDistanceCondition(
            operation="within_distance", layer="dph_cauce", meters=100.0
        ),
        attributes=AttributeCondition(building_origin=("catastro", "detected")),
        outcome="requires_authorization",
        authority="Confederación Hidrográfica del Tajo",
        citation=Provision(
            norm=Norm(
                title="Reglamento del Dominio Público Hidráulico (Real Decreto 849/1986)",
                url="https://www.boe.es/buscar/act.php?id=BOE-A-1986-10638",
            ),
            article="art. 9 — zona de policía",
            in_force_since=date(1986, 4, 30),
        ),
        status="approved",
    )
    evidence = Evidence(
        description="Distancia a curso de agua",
        source_name="Barranco del Montero",
        measured_value=8.535301066249467,
        unit="m",
    )
    return Finding(rule=rule, severity="actionable", confidence=0.9, evidence=(evidence,))


def test_sin_hallazgos_muestra_frase_distinta_de_no_disponible() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())

    html = render_parcel_report_html(_enrich(report), findings=())

    assert "Sin hallazgos de las reglas evaluadas." in html


def test_hallazgo_real_muestra_outcome_autoridad_cita_y_evidencia() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())

    html = render_parcel_report_html(_enrich(report), findings=(_finding(),))

    assert "requires_authorization" in html
    assert "Confederación Hidrográfica del Tajo" in html
    assert "art. 9 — zona de policía" in html
    assert 'href="https://www.boe.es/buscar/act.php?id=BOE-A-1986-10638"' in html
    assert "Barranco del Montero" in html
    assert "8.54 m" in html
    assert "Sin hallazgos de las reglas evaluadas." not in html


def _overlap_finding_sin_magnitud() -> Finding:
    # Historia 0018: un hallazgo de solape contra una entidad sin ningún
    # campo numérico reutilizable (ProtectedArea) tiene measured_value/
    # unit en None -- el render debe mostrarlo sin número, no romper con
    # un TypeError de formato.
    rule = Rule(
        identifier="madrid-solape-red-natura",
        scope=RuleScope(region="madrid", soil_classes=()),
        spatial=OverlapsCondition(operation="overlaps", layer="red_natura_plan"),
        attributes=AttributeCondition(building_origin=("catastro", "detected")),
        outcome="requires_environmental_assessment",
        authority="Comunidad de Madrid — Dirección General de Biodiversidad y Recursos Naturales",
        citation=Provision(
            norm=Norm(
                title=(
                    "Ley 42/2007, de 13 de diciembre, del Patrimonio Natural "
                    "y de la Biodiversidad"
                ),
                url="https://www.boe.es/buscar/act.php?id=BOE-A-2007-21490",
            ),
            article="art. 45 — evaluación de planes y proyectos",
            in_force_since=date(2007, 12, 14),
        ),
        status="approved",
    )
    evidence = Evidence(
        description="Solape con plan de gestión Red Natura 2000",
        source_name="Plan SE (X — Espacio previamente ordenado)",
    )
    return Finding(rule=rule, severity="actionable", confidence=0.9, evidence=(evidence,))


def test_hallazgo_de_solape_sin_magnitud_se_renderiza_sin_numero() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())

    html = render_parcel_report_html(_enrich(report), findings=(_overlap_finding_sin_magnitud(),))

    assert "requires_environmental_assessment" in html
    assert "Plan SE (X — Espacio previamente ordenado)" in html


def test_dos_hallazgos_simultaneos_no_se_mezclan() -> None:
    report = ParcelReport(parcel=make_parcel(), buildings=())

    html = render_parcel_report_html(
        _enrich(report), findings=(_finding(), _overlap_finding_sin_magnitud())
    )

    assert "requires_authorization" in html
    assert "requires_environmental_assessment" in html
    assert "Barranco del Montero" in html
    assert "Plan SE (X — Espacio previamente ordenado)" in html
    assert html.count("<li><strong>") == 2
