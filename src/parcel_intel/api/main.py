import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from parcel_intel.adapters.bocm.adapter import BocmAdapter
from parcel_intel.adapters.boe.adapter import BoeAdapter
from parcel_intel.adapters.catastro.adapter import CatastroAdapter
from parcel_intel.adapters.pnoa.adapter import PnoaAdapter
from parcel_intel.adapters.postgis.connection import get_connection
from parcel_intel.adapters.postgis.repository import PostgisParcelRepository
from parcel_intel.adapters.reports.html import render_parcel_report_html
from parcel_intel.adapters.sentinel2.adapter import Sentinel2Adapter
from parcel_intel.application.generate_enriched_report import (
    GenerateEnrichedParcelReportUseCase,
)
from parcel_intel.application.generate_report import GenerateParcelReportUseCase
from parcel_intel.ports.errors import InvalidCadastralReferenceError, ParcelNotFoundError

app = FastAPI(title="Parcel Intel")

# MVP: solo los dos municipios verificados en sources/REGISTRY.md.
_MUNICIPIOS = {
    "colmenar-de-oreja": "COLMENAR DE OREJA",
    "villaconejos": "VILLACONEJOS",
}


@app.get("/reports/{municipio}/{referencia}", response_class=HTMLResponse)
def get_parcel_report(municipio: str, referencia: str) -> str:
    nombre_municipio = _MUNICIPIOS.get(municipio)
    if nombre_municipio is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Municipio no soportado en el MVP: {municipio!r}. "
                f"Usa uno de {list(_MUNICIPIOS)}."
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
            )
            report = enriched_use_case.execute(referencia)
    except psycopg.OperationalError as error:
        raise HTTPException(
            status_code=503,
            detail="Servicio de caché no disponible; inténtalo de nuevo en unos segundos.",
        ) from error
    except InvalidCadastralReferenceError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ParcelNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return render_parcel_report_html(report)
