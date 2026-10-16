from datetime import date

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from parcel_intel.adapters.bocm.adapter import BocmAdapter
from parcel_intel.adapters.boe.adapter import BoeAdapter
from parcel_intel.adapters.catastro.adapter import CatastroAdapter
from parcel_intel.adapters.flood_hazard.adapter import FloodHazardAdapter
from parcel_intel.adapters.hydrography.adapter import HydrographyAdapter
from parcel_intel.adapters.idem.adapter import IdemAdapter
from parcel_intel.adapters.livestock_trails.adapter import LivestockTrailAdapter
from parcel_intel.adapters.pnoa.adapter import PnoaAdapter
from parcel_intel.adapters.postgis.connection import get_connection
from parcel_intel.adapters.postgis.repository import PostgisParcelRepository
from parcel_intel.adapters.postgis.rule_repository import PostgisRuleRepository
from parcel_intel.adapters.protected_areas.adapter import ProtectedAreaAdapter
from parcel_intel.adapters.reports.html import render_parcel_report_html
from parcel_intel.adapters.sentinel2.adapter import Sentinel2Adapter
from parcel_intel.application.generate_enriched_report import (
    GenerateEnrichedParcelReportUseCase,
)
from parcel_intel.application.generate_report import GenerateParcelReportUseCase
from parcel_intel.domain.norm import Norm, Provision
from parcel_intel.domain.rule import (
    AttributeCondition,
    OverlapsCondition,
    Rule,
    RuleScope,
    WithinDistanceCondition,
    evaluate_rules,
)
from parcel_intel.ports.errors import InvalidCadastralReferenceError, ParcelNotFoundError

app = FastAPI(title="Parcel Intel")

# MVP: solo los dos municipios verificados en sources/REGISTRY.md.
_MUNICIPIOS = {
    "colmenar-de-oreja": "COLMENAR DE OREJA",
    "villaconejos": "VILLACONEJOS",
}

# Reglas aprobadas del MVP -- escritas a mano antes de que exista un flujo
# de autoría asistida por LLM (ver docs/vision.md). Cauce: historia 0017.
# Vía pecuaria / Red Natura 2000: historia 0018 (ADR 0018) -- primer
# ejemplo del tipo de condición "overlaps" (solape polígono↔polígono),
# distinto del "within_distance" de la regla de cauces.
_APPROVED_RULES = (
    Rule(
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
                title=(
                    "Reglamento del Dominio Público Hidráulico "
                    "(Real Decreto 849/1986, de 11 de abril)"
                ),
                url="https://www.boe.es/buscar/act.php?id=BOE-A-1986-10638",
            ),
            article="art. 9 — zona de policía",
            in_force_since=date(1986, 4, 30),
        ),
        status="approved",
    ),
    Rule(
        identifier="madrid-solape-via-pecuaria",
        scope=RuleScope(region="madrid", soil_classes=()),
        spatial=OverlapsCondition(operation="overlaps", layer="via_pecuaria"),
        attributes=AttributeCondition(building_origin=("catastro", "detected")),
        outcome="requires_authorization",
        authority="Comunidad de Madrid — Consejería de Medio Ambiente, Agricultura e Interior",
        citation=Provision(
            norm=Norm(
                title="Ley 8/1998, de 15 de junio, de Vías Pecuarias de la Comunidad de Madrid",
                url="https://www.bocm.es/boletin/CM_Orden_BOCM/1998/06/24/1998062400.pdf",
            ),
            article="art. 17 — régimen de autorizaciones de uso y ocupación",
            in_force_since=date(1998, 6, 25),
        ),
        status="approved",
    ),
    Rule(
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
            article=(
                "art. 45 — evaluación de planes y proyectos con posible "
                "afección a la Red Natura 2000"
            ),
            in_force_since=date(2007, 12, 14),
        ),
        status="approved",
    ),
)


def _deduplicate_approved_rules(rules: tuple[Rule, ...]) -> tuple[Rule, ...]:
    """Dos `Rule` `approved` que comparten la misma condición espacial
    exacta (`spatial`, incluye `meters` cuando aplica), el mismo filtro de
    suelo (`scope.soil_classes`) y de edificios (`attributes`), y la misma
    consecuencia (`outcome`), describen -- a efectos de lo que ve el
    usuario -- el mismo hallazgo real sobre la misma evidencia real:
    evaluarlas por separado produciría dos Finding casi idénticos sin
    ninguna señal de que son la misma cosa (verificado con un caso real,
    ADR 0020). `outcome` SÍ entra en la clave de identidad -- si dos reglas
    exigen la misma condición espacial pero imponen consecuencias legales
    distintas, no son "la misma cosa" y ambas deben llegar al usuario sin
    fundirse.

    Se conserva solo la primera aparición de cada combinación, en el orden
    en que `rules` llega -- las reglas escritas a mano van primero por
    construcción (ver más abajo), así que ganan el desempate sobre
    cualquier regla equivalente aprobada por el flujo de autoría. Entre dos
    reglas aprobadas por el flujo de autoría que coincidan entre sí, gana
    la más antigua (`list_approved` ya ordena por `created_at`)."""
    seen: set[tuple[object, ...]] = set()
    deduplicated: list[Rule] = []
    for rule in rules:
        key = (rule.spatial, rule.scope.soil_classes, rule.attributes, rule.outcome)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(rule)
    return tuple(deduplicated)


@app.get("/reports/{municipio}/{referencia}", response_class=HTMLResponse)
def get_parcel_report(municipio: str, referencia: str) -> str:
    nombre_municipio = _MUNICIPIOS.get(municipio)
    if nombre_municipio is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Municipio no soportado en el MVP: {municipio!r}. Usa uno de {list(_MUNICIPIOS)}."
            ),
        )

    adapter = CatastroAdapter(provincia="MADRID", municipio=nombre_municipio)

    try:
        with get_connection() as conn:
            repository = PostgisParcelRepository(conn)
            rule_repository = PostgisRuleRepository(conn)
            base_use_case = GenerateParcelReportUseCase(
                parcel_port=adapter, building_port=adapter, repository=repository
            )
            enriched_use_case = GenerateEnrichedParcelReportUseCase(
                base_use_case=base_use_case,
                orthophoto_port=PnoaAdapter(),
                ndvi_port=Sentinel2Adapter(),
                boe_port=BoeAdapter(),
                bocm_port=BocmAdapter(),
                land_classification_port=IdemAdapter(),
                watercourse_port=HydrographyAdapter(),
                flood_hazard_port=FloodHazardAdapter(),
                livestock_trail_port=LivestockTrailAdapter(),
                protected_area_port=ProtectedAreaAdapter(),
            )
            report = enriched_use_case.execute(referencia)
            try:
                db_approved_rules: tuple[Rule, ...] = tuple(rule_repository.list_approved())
                rule_catalog_warning = None
            except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
                db_approved_rules = ()
                rule_catalog_warning = (
                    "Catálogo de reglas de autoría no disponible en esta generación "
                    "del informe; se muestran solo las reglas revisadas a mano."
                )
            all_approved_rules = _deduplicate_approved_rules(_APPROVED_RULES + db_approved_rules)
            findings = evaluate_rules(report, all_approved_rules)
    except psycopg.OperationalError as error:
        raise HTTPException(
            status_code=503,
            detail="Servicio de caché no disponible; inténtalo de nuevo en unos segundos.",
        ) from error
    except InvalidCadastralReferenceError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ParcelNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return render_parcel_report_html(report, findings, rule_catalog_warning)
