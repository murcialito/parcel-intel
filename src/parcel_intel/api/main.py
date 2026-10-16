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
    Rule,
    RuleScope,
    SpatialCondition,
    evaluate_rules,
)
from parcel_intel.ports.errors import InvalidCadastralReferenceError, ParcelNotFoundError

app = FastAPI(title="Parcel Intel")

# MVP: solo los dos municipios verificados en sources/REGISTRY.md.
_MUNICIPIOS = {
    "colmenar-de-oreja": "COLMENAR DE OREJA",
    "villaconejos": "VILLACONEJOS",
}

# Única regla aprobada del MVP (historia 0017) -- primer ejemplo real antes
# de que exista un flujo de autoría asistida por LLM (ver docs/vision.md).
_APPROVED_RULES = (
    Rule(
        identifier="madrid-colmenar-distancia-cauce",
        scope=RuleScope(region="madrid", soil_classes=("no_urbanizable",)),
        spatial=SpatialCondition(operation="within_distance", layer="dph_cauce", meters=100.0),
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
)


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
            findings = evaluate_rules(report, _APPROVED_RULES)
    except psycopg.OperationalError as error:
        raise HTTPException(
            status_code=503,
            detail="Servicio de caché no disponible; inténtalo de nuevo en unos segundos.",
        ) from error
    except InvalidCadastralReferenceError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ParcelNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return render_parcel_report_html(report, findings)
