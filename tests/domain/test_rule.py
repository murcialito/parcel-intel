from dataclasses import replace
from datetime import date

from parcel_intel.adapters.catastro.parsing import parse_wfs_parcels
from parcel_intel.adapters.hydrography.parsing import parse_watercourse_features
from parcel_intel.domain.building import Building, BuildingOrigin
from parcel_intel.domain.geometry import Geometry, LineGeometry
from parcel_intel.domain.land_classification import LandClassification
from parcel_intel.domain.norm import Norm, Provision
from parcel_intel.domain.report import EnrichedParcelReport, ParcelReport
from parcel_intel.domain.rule import (
    AttributeCondition,
    Rule,
    RuleScope,
    SpatialCondition,
    evaluate_rules,
)
from parcel_intel.domain.watercourse import Watercourse
from tests.adapters.catastro.helpers import FIXTURES_DIR as CATASTRO_FIXTURES_DIR
from tests.adapters.hydrography.helpers import FIXTURES_DIR as DPH_FIXTURES_DIR
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
        spatial=SpatialCondition(operation="within_distance", layer="dph_cauce", meters=meters),
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
) -> EnrichedParcelReport:
    parcel = make_parcel()
    return EnrichedParcelReport(
        report=ParcelReport(parcel=parcel, buildings=buildings),
        orthophoto=None,
        ndvi_summary=None,
        boe_notices=None,
        bocm_notices=None,
        land_classifications=land_classifications,
        watercourses=watercourses,
        flood_hazard=None,
        livestock_trails=None,
        protected_areas=None,
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
