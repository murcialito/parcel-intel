from dataclasses import replace
from datetime import date

import pytest

from parcel_intel.adapters.catastro.parsing import parse_wfs_parcels
from parcel_intel.adapters.hydrography.parsing import parse_watercourse_features
from parcel_intel.adapters.livestock_trails.parsing import parse_wfs_livestock_trails
from parcel_intel.adapters.protected_areas.parsing import parse_wfs_protected_areas
from parcel_intel.domain.building import Building, BuildingOrigin
from parcel_intel.domain.geometry import Geometry, LineGeometry
from parcel_intel.domain.land_classification import LandClassification
from parcel_intel.domain.livestock_trail import LivestockTrail
from parcel_intel.domain.norm import Norm, Provision
from parcel_intel.domain.protected_area import ProtectedArea
from parcel_intel.domain.report import EnrichedParcelReport, ParcelReport
from parcel_intel.domain.rule import (
    AttributeCondition,
    OverlapsCondition,
    Rule,
    RuleScope,
    WithinDistanceCondition,
    evaluate_rules,
    spatial_condition_for_layer,
)
from parcel_intel.domain.watercourse import Watercourse
from tests.adapters.catastro.helpers import FIXTURES_DIR as CATASTRO_FIXTURES_DIR
from tests.adapters.hydrography.helpers import FIXTURES_DIR as DPH_FIXTURES_DIR
from tests.adapters.livestock_trails.helpers import FIXTURES_DIR as LIVESTOCK_FIXTURES_DIR
from tests.adapters.protected_areas.helpers import FIXTURES_DIR as PROTECTED_AREAS_FIXTURES_DIR
from tests.factories import make_building, make_parcel, make_provenance

_CITATION = Provision(
    norm=Norm(
        title="Reglamento del Dominio Público Hidráulico (Real Decreto 849/1986)",
        url="https://www.boe.es/buscar/act.php?id=BOE-A-1986-10638",
    ),
    article="art. 9 — zona de policía",
    in_force_since=date(1986, 4, 30),
)


def _rule(
    status: str = "approved",
    soil_classes: tuple[str, ...] = ("no_urbanizable",),
    meters: float = 100.0,
    building_origin: tuple[BuildingOrigin, ...] = ("catastro", "detected"),
) -> Rule:
    return Rule(
        identifier="madrid-colmenar-distancia-cauce",
        scope=RuleScope(region="madrid", soil_classes=soil_classes),  # type: ignore[arg-type]
        spatial=WithinDistanceCondition(
            operation="within_distance", layer="dph_cauce", meters=meters
        ),
        attributes=AttributeCondition(building_origin=building_origin),
        outcome="requires_authorization",
        authority="Confederación Hidrográfica del Tajo",
        citation=_CITATION,
        status=status,  # type: ignore[arg-type]
    )


def _land_classification(general_category: str) -> LandClassification:
    return LandClassification(
        general_category=general_category,
        detailed_category=general_category.lower(),
        short_code="SUBNS",
        reference_date=date(2025, 6, 29),
        municipality_code="170",
        municipality_name="VILLACONEJOS",
        area_m2=1000.0,
        geometry=Geometry(rings=(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)),), srid=25830),
        provenance=make_provenance(source="idem"),
    )


def _watercourse(
    points: tuple[tuple[float, float], ...], name: str = "Barranco cercano"
) -> Watercourse:
    return Watercourse(
        name=name,
        hydrographic_demarcation_code="ES030",
        hydrographic_demarcation_name="Tajo",
        course_type="Curso natural",
        persistence="Estacional",
        min_width_m=1.0,
        max_width_m=5.0,
        length_m=100.0,
        geometry=LineGeometry(points=points, srid=25830),
        provenance=make_provenance(source="idee-watercourse"),
    )


def _report(
    land_classifications: tuple[LandClassification, ...] | None = None,
    watercourses: tuple[Watercourse, ...] | None = None,
    buildings: tuple[Building, ...] = (),
    livestock_trails: tuple[LivestockTrail, ...] | None = None,
    protected_areas: tuple[ProtectedArea, ...] | None = None,
    parcel_rings: tuple[tuple[tuple[float, float], ...], ...] | None = None,
) -> EnrichedParcelReport:
    parcel = make_parcel(rings=parcel_rings) if parcel_rings is not None else make_parcel()
    return EnrichedParcelReport(
        report=ParcelReport(parcel=parcel, buildings=buildings),
        orthophoto=None,
        ndvi_summary=None,
        boe_notices=None,
        bocm_notices=None,
        land_classifications=land_classifications,
        watercourses=watercourses,
        flood_hazard=None,
        livestock_trails=livestock_trails,
        protected_areas=protected_areas,
    )


def _livestock_trail_rule(status: str = "approved") -> Rule:
    return Rule(
        identifier="madrid-solape-via-pecuaria",
        scope=RuleScope(region="madrid", soil_classes=()),
        spatial=OverlapsCondition(operation="overlaps", layer="via_pecuaria"),
        attributes=AttributeCondition(building_origin=("catastro", "detected")),
        outcome="requires_authorization",
        authority="Comunidad de Madrid — Consejería de Medio Ambiente, Agricultura e Interior",
        citation=_CITATION,
        status=status,  # type: ignore[arg-type]
    )


def _red_natura_rule(status: str = "approved") -> Rule:
    return Rule(
        identifier="madrid-solape-red-natura",
        scope=RuleScope(region="madrid", soil_classes=()),
        spatial=OverlapsCondition(operation="overlaps", layer="red_natura_plan"),
        attributes=AttributeCondition(building_origin=("catastro", "detected")),
        outcome="requires_environmental_assessment",
        authority="Comunidad de Madrid — Dirección General de Biodiversidad y Recursos Naturales",
        citation=_CITATION,
        status=status,  # type: ignore[arg-type]
    )


def test_regla_no_aprobada_nunca_produce_hallazgo() -> None:
    report = _report(
        land_classifications=(_land_classification("Suelo No Urbanizable Común"),),
        watercourses=(_watercourse(((20.0, 0.0), (20.0, 10.0))),),
    )

    findings = evaluate_rules(report, (_rule(status="proposed"),))

    assert findings == ()


def test_sin_clasificacion_de_suelo_no_produce_hallazgo() -> None:
    report = _report(
        land_classifications=None,
        watercourses=(_watercourse(((20.0, 0.0), (20.0, 10.0))),),
    )

    findings = evaluate_rules(report, (_rule(),))

    assert findings == ()


def test_clasificacion_que_no_coincide_no_produce_hallazgo() -> None:
    report = _report(
        land_classifications=(_land_classification("Suelo Urbano Consolidado"),),
        watercourses=(_watercourse(((20.0, 0.0), (20.0, 10.0))),),
    )

    findings = evaluate_rules(report, (_rule(),))

    assert findings == ()


def test_sin_cursos_de_agua_no_produce_hallazgo() -> None:
    report = _report(
        land_classifications=(_land_classification("Suelo No Urbanizable Común"),),
        watercourses=None,
    )

    findings = evaluate_rules(report, (_rule(),))

    assert findings == ()


def test_cursos_de_agua_tupla_vacia_no_produce_hallazgo() -> None:
    report = _report(
        land_classifications=(_land_classification("Suelo No Urbanizable Común"),),
        watercourses=(),
    )

    findings = evaluate_rules(report, (_rule(),))

    assert findings == ()


def test_distancia_mayor_que_el_umbral_no_produce_hallazgo() -> None:
    report = _report(
        land_classifications=(_land_classification("Suelo No Urbanizable Común"),),
        watercourses=(_watercourse(((200.0, 0.0), (200.0, 10.0))),),
    )

    findings = evaluate_rules(report, (_rule(meters=100.0),))

    assert findings == ()


def test_origen_de_edificio_excluido_no_produce_hallazgo() -> None:
    edificio_detectado = replace(make_building(), origin="detected")
    report = _report(
        land_classifications=(_land_classification("Suelo No Urbanizable Común"),),
        watercourses=(_watercourse(((20.0, 0.0), (20.0, 10.0))),),
        buildings=(edificio_detectado,),
    )

    # La regla solo permite edificios "catastro", pero el único edificio
    # real es "detected" -- debe excluirse (ver ADR 0017, decisión 4).
    findings = evaluate_rules(report, (_rule(building_origin=("catastro",)),))

    assert findings == ()


def test_sin_edificios_no_excluye_vacuamente_verdadero() -> None:
    # Villaconejos real no tiene edificios -- `all()` sobre una secuencia
    # vacía es `True`, así que la condición de atributos se cumple pese a
    # no haber ningún edificio que la "cumpla" explícitamente (ver ADR
    # 0017, decisión 4 -- decisión verificada, no asumida).
    report = _report(
        land_classifications=(_land_classification("Suelo No Urbanizable Común"),),
        watercourses=(_watercourse(((20.0, 0.0), (20.0, 10.0))),),
        buildings=(),
    )

    findings = evaluate_rules(report, (_rule(building_origin=("catastro",)),))

    assert len(findings) == 1


def test_caso_real_villaconejos_produce_el_hallazgo_documentado() -> None:
    # El fixture trae 7 parcelas (centroide + bbox de vecinas) -- filtrar
    # por la referencia real de la parcela rústica objetivo.
    parcel_xml = (
        CATASTRO_FIXTURES_DIR / "wfsCP_villaconejos_rustica_por_centroide.xml"
    ).read_bytes()
    raw_parcel = next(
        p for p in parse_wfs_parcels(parcel_xml) if p["reference"] == "REFCAT-RETIRADA"
    )
    parcel = make_parcel(
        cadastral_reference=raw_parcel["reference"],
        rings=raw_parcel["rings"],
        area_m2=raw_parcel["area_m2"],
    )

    watercourse_body = (
        DPH_FIXTURES_DIR
        / "features_watercourse_villaconejos_rustica_margin2m_barranco_montero.json"
    ).read_bytes()
    raw_watercourse = parse_watercourse_features(watercourse_body)[0]
    watercourse = _watercourse(
        raw_watercourse["points"], name=raw_watercourse["name"] or "sin nombre"
    )

    report = EnrichedParcelReport(
        report=ParcelReport(parcel=parcel, buildings=()),
        orthophoto=None,
        ndvi_summary=None,
        boe_notices=None,
        bocm_notices=None,
        land_classifications=(_land_classification("Suelo No Urbanizable Común"),),
        watercourses=(watercourse,),
        flood_hazard=None,
        livestock_trails=None,
        protected_areas=None,
    )

    findings = evaluate_rules(report, (_rule(),))

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule.outcome == "requires_authorization"
    assert finding.severity == "actionable"
    assert finding.confidence == 0.9
    assert len(finding.evidence) == 1
    evidence = finding.evidence[0]
    assert evidence.source_name == "Barranco del Montero"
    assert evidence.measured_value == 8.535301066249467
    assert evidence.unit == "m"


# --- Vía pecuaria (solape) -- historia 0018 ---


def test_via_pecuaria_regla_no_aprobada_nunca_produce_hallazgo() -> None:
    report = _report(livestock_trails=())

    findings = evaluate_rules(report, (_livestock_trail_rule(status="proposed"),))

    assert findings == ()


def test_via_pecuaria_sin_evidencia_no_produce_hallazgo() -> None:
    report = _report(livestock_trails=None)

    findings = evaluate_rules(report, (_livestock_trail_rule(),))

    assert findings == ()


def test_via_pecuaria_tupla_vacia_no_produce_hallazgo() -> None:
    report = _report(livestock_trails=())

    findings = evaluate_rules(report, (_livestock_trail_rule(),))

    assert findings == ()


def test_via_pecuaria_caso_real_villaconejos_sin_afeccion_no_produce_hallazgo() -> None:
    # Confirmado real (ADR 0018): la fixture "sin afección" devuelve 0
    # features -- sin riesgo de falso positivo por filtro BBOX laxo (a
    # diferencia de Red Natura 2000), ya que esta capa tiene features
    # compactos.
    fixture = (
        LIVESTOCK_FIXTURES_DIR
        / "wfs_getfeature_bbox_villaconejos_rustica_margin2m_sin_afeccion.xml"
    ).read_bytes()
    trails_raw = parse_wfs_livestock_trails(fixture)
    assert trails_raw == []
    report = _report(livestock_trails=())

    findings = evaluate_rules(report, (_livestock_trail_rule(),))

    assert findings == ()


def test_via_pecuaria_caso_positivo_sintetico_documentado() -> None:
    # Geometría REAL de "Vereda del Cristo" (384 puntos, fixture real) +
    # parcela SINTÉTICA (no real, documentada como tal) construida para
    # solapar con ella -- el MVP no tiene hoy ninguna parcela real con
    # esta afección (ver ADR 0018).
    fixture = (
        LIVESTOCK_FIXTURES_DIR / "wfs_cql_colmenar_municipio_completo_15_tramos.xml"
    ).read_bytes()
    cristo = next(
        t for t in parse_wfs_livestock_trails(fixture) if t["name"] == "Vereda del Cristo"
    )
    trail = LivestockTrail(
        trail_type=cristo["trail_type"],
        name=cristo["name"],
        municipality_code=cristo["municipality_code"],
        municipality_name=cristo["municipality_name"],
        trail_code=cristo["trail_code"],
        length_m=cristo["length_m"],
        area_m2=cristo["area_m2"],
        geometry=Geometry(rings=cristo["rings"], srid=25830),
        provenance=make_provenance(source="idem"),
    )

    cx, cy = 468484.75, 4438002.64
    half = 2.0
    parcela_sintetica = (
        (cx - half, cy - half),
        (cx + half, cy - half),
        (cx + half, cy + half),
        (cx - half, cy + half),
        (cx - half, cy - half),
    )
    report = _report(livestock_trails=(trail,), parcel_rings=(parcela_sintetica,))

    findings = evaluate_rules(report, (_livestock_trail_rule(),))

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule.outcome == "requires_authorization"
    assert finding.severity == "actionable"
    assert finding.confidence == 0.85
    assert len(finding.evidence) == 1
    evidence = finding.evidence[0]
    assert evidence.source_name == "Vereda del Cristo"
    assert evidence.measured_value == 122148.090639
    assert evidence.unit == "m2"


# --- Red Natura 2000 (solape) -- historia 0018 ---


def test_red_natura_regla_no_aprobada_nunca_produce_hallazgo() -> None:
    report = _report(protected_areas=())

    findings = evaluate_rules(report, (_red_natura_rule(status="proposed"),))

    assert findings == ()


def test_red_natura_sin_evidencia_no_produce_hallazgo() -> None:
    report = _report(protected_areas=None)

    findings = evaluate_rules(report, (_red_natura_rule(),))

    assert findings == ()


def test_red_natura_tupla_vacia_no_produce_hallazgo() -> None:
    report = _report(protected_areas=())

    findings = evaluate_rules(report, (_red_natura_rule(),))

    assert findings == ()


def test_red_natura_caso_real_villaconejos_no_solapa_no_produce_hallazgo() -> None:
    # Hallazgo del ADR 0018: pese a que el WFS devuelve la zona SE/X para
    # la bbox de consulta de Villaconejos, la geometría real no la
    # contiene (distancia real ~1.36 km, confirmada con shapely en el
    # ADR) -- el filtro BBOX de esta capa es laxo (envolvente de un
    # MultiSurface disperso en ~46x41 km), a diferencia de vías pecuarias.
    parcel_xml = (
        CATASTRO_FIXTURES_DIR / "wfsCP_villaconejos_rustica_por_centroide.xml"
    ).read_bytes()
    raw_parcel = next(
        p for p in parse_wfs_parcels(parcel_xml) if p["reference"] == "REFCAT-RETIRADA"
    )

    pa_xml = (
        PROTECTED_AREAS_FIXTURES_DIR / "wfs_getfeature_bbox_villaconejos_rustica_margin2m.xml"
    ).read_bytes()
    raw_area = parse_wfs_protected_areas(pa_xml)[0]
    area = ProtectedArea(
        plan_code=raw_area["plan_code"],
        plan_name=raw_area["plan_name"],
        zone_code=raw_area["zone_code"],
        zone_name=raw_area["zone_name"],
        geometry=Geometry(rings=raw_area["rings"], srid=25830),
        provenance=make_provenance(source="idem"),
    )
    report = _report(protected_areas=(area,), parcel_rings=raw_parcel["rings"])

    findings = evaluate_rules(report, (_red_natura_rule(),))

    assert findings == ()


def test_red_natura_caso_positivo_sintetico_documentado_contencion_total() -> None:
    # Geometría REAL del anillo nº 4 (el más pequeño, 90 puntos, área
    # real 35828.36 m²) de la zona SE/X + parcela SINTÉTICA construida
    # para quedar íntegramente contenida sin que ningún borde cruce --
    # el caso de contención total que esta historia exige cubrir (ADR
    # 0018), ya que ni Villaconejos ni Colmenar rústica solapan realmente.
    pa_xml = (
        PROTECTED_AREAS_FIXTURES_DIR / "wfs_getfeature_bbox_villaconejos_rustica_margin2m.xml"
    ).read_bytes()
    raw_area = parse_wfs_protected_areas(pa_xml)[0]
    ring4 = raw_area["rings"][4]
    assert len(ring4) == 90
    area = ProtectedArea(
        plan_code=raw_area["plan_code"],
        plan_name=raw_area["plan_name"],
        zone_code=raw_area["zone_code"],
        zone_name=raw_area["zone_name"],
        geometry=Geometry(rings=(ring4,), srid=25830),
        provenance=make_provenance(source="idem"),
    )

    cx, cy = 446993.04, 4435015.90
    half = 3.0
    parcela_sintetica = (
        (cx - half, cy - half),
        (cx + half, cy - half),
        (cx + half, cy + half),
        (cx - half, cy + half),
        (cx - half, cy - half),
    )
    report = _report(protected_areas=(area,), parcel_rings=(parcela_sintetica,))

    findings = evaluate_rules(report, (_red_natura_rule(),))

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule.outcome == "requires_environmental_assessment"
    assert finding.severity == "actionable"
    assert finding.confidence == 0.9
    assert len(finding.evidence) == 1
    evidence = finding.evidence[0]
    assert evidence.source_name == (
        "Plan de gestión de vegas, cuestas y páramos del sureste de Madrid (ZEC), "
        "cortados y cantiles de los ríos Jarama y Manzanares (ZEPA) y carrizales y "
        "sotos de Aranjuez (ZEPA) (X — Espacio previamente ordenado / zonificado o "
        "en el que se ha considerado que no es necesario establecer una "
        "zonificación específica)"
    )
    assert evidence.measured_value is None
    assert evidence.unit is None


def test_mas_de_un_finding_simultaneo_no_se_mezcla() -> None:
    # Dos reglas distintas (cauce + vía pecuaria) evaluadas sobre el
    # mismo EnrichedParcelReport deben producir dos Finding independientes
    # sin que ningún campo de uno se mezcle con el otro.
    fixture = (
        LIVESTOCK_FIXTURES_DIR / "wfs_cql_colmenar_municipio_completo_15_tramos.xml"
    ).read_bytes()
    cristo = next(
        t for t in parse_wfs_livestock_trails(fixture) if t["name"] == "Vereda del Cristo"
    )
    trail = LivestockTrail(
        trail_type=cristo["trail_type"],
        name=cristo["name"],
        municipality_code=cristo["municipality_code"],
        municipality_name=cristo["municipality_name"],
        trail_code=cristo["trail_code"],
        length_m=cristo["length_m"],
        area_m2=cristo["area_m2"],
        geometry=Geometry(rings=cristo["rings"], srid=25830),
        provenance=make_provenance(source="idem"),
    )
    cx, cy = 468484.75, 4438002.64
    half = 2.0
    parcela_sintetica = (
        (cx - half, cy - half),
        (cx + half, cy - half),
        (cx + half, cy + half),
        (cx - half, cy + half),
        (cx - half, cy - half),
    )

    report = _report(
        land_classifications=(_land_classification("Suelo No Urbanizable Común"),),
        watercourses=(_watercourse(((cx + 50.0, cy), (cx + 50.0, cy + 10.0))),),
        livestock_trails=(trail,),
        parcel_rings=(parcela_sintetica,),
    )

    findings = evaluate_rules(report, (_rule(meters=1000.0), _livestock_trail_rule()))

    assert len(findings) == 2
    cauce_finding = next(
        f for f in findings if f.rule.identifier == "madrid-colmenar-distancia-cauce"
    )
    via_finding = next(f for f in findings if f.rule.identifier == "madrid-solape-via-pecuaria")
    assert cauce_finding.rule.outcome == "requires_authorization"
    assert cauce_finding.evidence[0].unit == "m"
    assert via_finding.rule.outcome == "requires_authorization"
    assert via_finding.evidence[0].source_name == "Vereda del Cristo"
    assert via_finding.evidence[0].unit == "m2"


# --- spatial_condition_for_layer -- historia 0019 ---


def test_spatial_condition_for_layer_dph_cauce_con_meters() -> None:
    condition = spatial_condition_for_layer("dph_cauce", 100.0)

    assert condition == WithinDistanceCondition(
        operation="within_distance", layer="dph_cauce", meters=100.0
    )


def test_spatial_condition_for_layer_dph_cauce_sin_meters_lanza_error() -> None:
    with pytest.raises(ValueError, match="meters es obligatorio"):
        spatial_condition_for_layer("dph_cauce", None)


def test_spatial_condition_for_layer_overlap_sin_meters() -> None:
    condition = spatial_condition_for_layer("via_pecuaria", None)

    assert condition == OverlapsCondition(operation="overlaps", layer="via_pecuaria")


def test_spatial_condition_for_layer_overlap_con_meters_lanza_error() -> None:
    with pytest.raises(ValueError, match="no aplica"):
        spatial_condition_for_layer("red_natura_plan", 50.0)
