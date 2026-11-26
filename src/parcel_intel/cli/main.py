import argparse
import sys
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import requests

from parcel_intel.adapters.deepseek.adapter import DeepSeekAdapter, MissingDeepSeekApiKeyError
from parcel_intel.adapters.deepseek.client import DeepSeekApiError
from parcel_intel.adapters.ign_admin_units import IgnAdministrativeUnitsAdapter
from parcel_intel.adapters.ign_admin_units import client as ign_client
from parcel_intel.adapters.livestock_trails import client as livestock_client
from parcel_intel.adapters.livestock_trails.adapter import LivestockTrailAdapter
from parcel_intel.adapters.postgis.connection import get_connection
from parcel_intel.adapters.postgis.rule_repository import PostgisRuleRepository
from parcel_intel.adapters.raw_cache import (
    CachedRawFetcher,
    HttpGet,
    RawCacheCorruptError,
    RawCacheMissError,
)
from parcel_intel.adapters.road_layer_files import GeoJsonRoadLayerWriter
from parcel_intel.adapters.road_network import client as roadlink_client
from parcel_intel.adapters.road_network.adapter import RoadNetworkAdapter
from parcel_intel.adapters.shapely_geometry import ShapelyLineClipper, ShapelyPolygonClipper
from parcel_intel.application.author_rule_proposal import AuthorRuleProposalUseCase
from parcel_intel.application.build_municipal_livestock_trail_layers import (
    BuildMunicipalLivestockTrailLayersUseCase,
)
from parcel_intel.application.build_municipal_road_layers import BuildMunicipalRoadLayersUseCase
from parcel_intel.domain.municipal_livestock_trails import MunicipalLivestockTrailLayer
from parcel_intel.domain.municipal_road_layer import MunicipalRoadLayerBatch
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.rule import Rule, WithinDistanceCondition
from parcel_intel.ports.errors import (
    ClippedGeometryHasHolesError,
    IncompleteWfsResponseError,
    InvalidLlmProposalError,
    InvalidRuleLayerError,
    MunicipalBoundaryNotFoundError,
    MunicipalBoundaryUnusableError,
    RuleProposalNotFoundError,
)

_LAYER_CHOICES = ["dph_cauce", "via_pecuaria", "red_natura_plan"]

AMBITO_HITO_INE = ("28043", "28013", "28052", "28019", "28170", "28180", "28157")
"""Los 7 municipios del primer hito (REGISTRY.md, "Ámbito del hito"): Colmenar de
Oreja, Aranjuez, Chinchón, Belmonte de Tajo, Villaconejos, Villarejo de Salvanés y
Valdelaguna. Configuración del hito, no dominio."""

AMBITO_HITO_BBOX_ETRS89 = (39.98, -3.62, 40.22, -3.15)
"""(lat_min, lon_min, lat_max, lon_max) en EPSG:4258 con el que se pide el WFS del IGN."""


def _author(args: argparse.Namespace) -> int:
    try:
        article_text = args.text.read_text(encoding="utf-8")
    except OSError as error:
        print(f"No se pudo leer el fichero {args.text}: {error}", file=sys.stderr)
        return 1

    with get_connection() as conn:
        repository = PostgisRuleRepository(conn)
        try:
            llm = DeepSeekAdapter()
        except MissingDeepSeekApiKeyError:
            print("Falta la variable de entorno DEEPSEEK_API_KEY.", file=sys.stderr)
            return 1
        use_case = AuthorRuleProposalUseCase(llm=llm, repository=repository)
        try:
            proposal = use_case.execute(article_text, args.layer)
        except InvalidRuleLayerError as error:
            print(f"Capa no reconocida: {error}", file=sys.stderr)
            return 1
        except InvalidLlmProposalError as error:
            print(f"Respuesta del LLM no válida, no se ha guardado nada: {error}", file=sys.stderr)
            return 1
        except DeepSeekApiError as error:
            print(f"Error llamando a DeepSeek: {error}", file=sys.stderr)
            return 1
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
            print(f"No se pudo conectar con DeepSeek: {error}", file=sys.stderr)
            return 1

    rule = proposal.rule
    print(f"Propuesta creada: {rule.identifier}")
    print(f"  outcome: {rule.outcome}")
    print(f"  authority: {rule.authority}")
    print(f"  explicación: {proposal.explanation}")
    print(
        f"  coste: ${proposal.usage.cost_usd:.6f} "
        f"({proposal.usage.prompt_tokens} + {proposal.usage.completion_tokens} tokens, "
        f"modelo {proposal.usage.model})"
    )
    return 0


def _format_spatial(rule: Rule) -> str:
    spatial = rule.spatial
    if isinstance(spatial, WithinDistanceCondition):
        return f"{spatial.operation} / {spatial.layer} / meters={spatial.meters}"
    return f"{spatial.operation} / {spatial.layer}"


def _review_list(_args: argparse.Namespace) -> int:
    with get_connection() as conn:
        repository = PostgisRuleRepository(conn)
        proposals = repository.list_proposed()
    if not proposals:
        print("No hay propuestas pendientes.")
        return 0
    for proposal in proposals:
        rule = proposal.rule
        print(f"{rule.identifier}")
        print(f"  region: {rule.scope.region}")
        print(f"  soil_classes: {rule.scope.soil_classes}")
        print(f"  spatial: {_format_spatial(rule)}")
        print(f"  building_origin: {rule.attributes.building_origin}")
        print(f"  outcome: {rule.outcome}")
        print(f"  authority: {rule.authority}")
        print(
            f"  cita: {rule.citation.norm.title} — {rule.citation.article} "
            f"(vigente desde {rule.citation.in_force_since}, "
            f"{rule.citation.url or rule.citation.norm.url})"
        )
        print(f"  explicación: {proposal.explanation}")
        print(
            f"  coste: ${proposal.usage.cost_usd:.6f} "
            f"({proposal.usage.prompt_tokens} + {proposal.usage.completion_tokens} tokens, "
            f"modelo {proposal.usage.model})"
        )
        print()
    return 0


def _review_approve(args: argparse.Namespace) -> int:
    with get_connection() as conn:
        repository = PostgisRuleRepository(conn)
        try:
            repository.approve(args.identifier)
        except RuleProposalNotFoundError as error:
            print(str(error), file=sys.stderr)
            return 1
    print(f"Aprobada: {args.identifier}")
    return 0


def _review_reject(args: argparse.Namespace) -> int:
    with get_connection() as conn:
        repository = PostgisRuleRepository(conn)
        try:
            repository.reject(args.identifier)
        except RuleProposalNotFoundError as error:
            print(str(error), file=sys.stderr)
            return 1
    print(f"Rechazada: {args.identifier}")
    return 0


def _today() -> date:
    return datetime.now(tz=UTC).date()


def _format_provenance(provenance: Provenance) -> str:
    return (
        f"fuente={provenance.source} url={provenance.url} "
        f"fecha={provenance.retrieved_at.isoformat()} licencia={provenance.license}"
    )


def _format_layer(layer: MunicipalLivestockTrailLayer) -> str:
    municipality = layer.municipality
    lines = [
        f"{municipality.ine_code} {municipality.name}",
        f"  aviso: {layer.notice}",
        f"  límite: {_format_provenance(municipality.provenance)}",
        f"  piezas: {len(layer.trails)}",
    ]
    for piece in layer.trails:
        source = piece.source
        lines.append(
            f"    trail_code={source.trail_code} trail_type={source.trail_type} "
            f"name={source.name} area_m2={piece.area_m2:.2f} "
            f"share_of_source={piece.share_of_source * 100:.2f}%"
        )
        lines.append(f"      procedencia: {_format_provenance(piece.provenance)}")
    return "\n".join(lines)


def build_municipal_layers(
    cache_dir: Path,
    offline: bool,
    ign_http_get: HttpGet = ign_client.default_http_getter,
    idem_http_get: HttpGet = livestock_client.default_http_getter,
    today: Callable[[], date] = _today,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[MunicipalLivestockTrailLayer, ...]:
    """Composition root de la capa de vías pecuarias por municipio (ADR 0032).

    Un `CachedRawFetcher` por fuente sobre el mismo directorio: la clave es la
    URL completa, así que no colisionan. Con `offline=True` nada llama a la red."""
    ign_fetcher = CachedRawFetcher(ign_http_get, cache_dir, today, sleep=sleep, offline=offline)
    idem_fetcher = CachedRawFetcher(idem_http_get, cache_dir, today, sleep=sleep, offline=offline)
    use_case = BuildMunicipalLivestockTrailLayersUseCase(
        boundaries=IgnAdministrativeUnitsAdapter(
            AMBITO_HITO_BBOX_ETRS89, fetcher=ign_fetcher, today=today
        ),
        trails=LivestockTrailAdapter(fetcher=idem_fetcher, today=today),
        clipper=ShapelyPolygonClipper(),
    )
    return use_case.execute(AMBITO_HITO_INE)


def _vias_pecuarias_municipios(args: argparse.Namespace) -> int:
    try:
        layers = build_municipal_layers(args.cache, args.sin_red)
    except (
        MunicipalBoundaryNotFoundError,
        MunicipalBoundaryUnusableError,
        IncompleteWfsResponseError,
        ClippedGeometryHasHolesError,
        RawCacheMissError,
        RawCacheCorruptError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 1
    except requests.RequestException as error:
        print(f"Error de red: {error}", file=sys.stderr)
        return 1
    for layer in layers:
        print(_format_layer(layer))
    return 0


def build_municipal_road_layers(
    cache_dir: Path,
    offline: bool,
    ign_http_get: HttpGet = ign_client.default_http_getter,
    roadlink_http_get: HttpGet = roadlink_client.default_http_getter,
    today: Callable[[], date] = _today,
    sleep: Callable[[float], None] = time.sleep,
) -> MunicipalRoadLayerBatch:
    """Composition root de la capa de camino actual por municipio (historia #27).

    Misma caché cruda inmutable que las vías pecuarias (la clave es la URL
    completa). Con `offline=True` nada llama a la red."""
    ign_fetcher = CachedRawFetcher(ign_http_get, cache_dir, today, sleep=sleep, offline=offline)
    road_fetcher = CachedRawFetcher(
        roadlink_http_get, cache_dir, today, sleep=sleep, offline=offline
    )
    use_case = BuildMunicipalRoadLayersUseCase(
        boundaries=IgnAdministrativeUnitsAdapter(
            AMBITO_HITO_BBOX_ETRS89, fetcher=ign_fetcher, today=today
        ),
        roads=RoadNetworkAdapter(fetcher=road_fetcher, today=today),
        clipper=ShapelyLineClipper(),
    )
    return use_case.execute(AMBITO_HITO_INE)


def _camino_actual_municipios(args: argparse.Namespace) -> int:
    try:
        batch = build_municipal_road_layers(args.cache, args.sin_red)
    except (
        MunicipalBoundaryNotFoundError,
        MunicipalBoundaryUnusableError,
        IncompleteWfsResponseError,
        RawCacheMissError,
        RawCacheCorruptError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 1
    except requests.RequestException as error:
        print(f"Error de red: {error}", file=sys.stderr)
        return 1
    writer = GeoJsonRoadLayerWriter(args.salida)
    for layer in batch.layers:
        path = writer.write(layer)
        print(
            f"{layer.municipality.ine_code} {layer.municipality.name}: "
            f"{len(layer.segments)} tramos -> {path}"
        )
    for failure in batch.failures:
        print(
            f"FALLO {failure.ine_code} {failure.name}: {failure.reason}",
            file=sys.stderr,
        )
    return 1 if batch.failures else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="parcel_intel.cli.main")
    subparsers = parser.add_subparsers(dest="command", required=True)

    author_parser = subparsers.add_parser(
        "author", help="Proponer una regla a partir de texto normativo real"
    )
    author_parser.add_argument(
        "--layer", choices=_LAYER_CHOICES, required=True, help="Capa de evidencia a la que aplica"
    )
    author_parser.add_argument(
        "--text", type=Path, required=True, help="Fichero con el artículo"
    )
    author_parser.set_defaults(func=_author)

    review_parser = subparsers.add_parser("review", help="Revisar propuestas pendientes")
    review_subparsers = review_parser.add_subparsers(dest="review_command", required=True)

    list_parser = review_subparsers.add_parser("list", help="Listar propuestas pendientes")
    list_parser.set_defaults(func=_review_list)

    approve_parser = review_subparsers.add_parser("approve", help="Aprobar una propuesta")
    approve_parser.add_argument("identifier")
    approve_parser.set_defaults(func=_review_approve)

    reject_parser = review_subparsers.add_parser("reject", help="Rechazar una propuesta")
    reject_parser.add_argument("identifier")
    reject_parser.set_defaults(func=_review_reject)

    vias_parser = subparsers.add_parser(
        "vias-pecuarias-municipios",
        help="Capa de vías pecuarias recortada al término de cada municipio del ámbito",
    )
    vias_parser.add_argument(
        "--sin-red", action="store_true", help="Solo la caché cruda; falla si falta algo"
    )
    vias_parser.add_argument(
        "--cache", type=Path, default=Path("data/raw"), help="Directorio de la caché cruda"
    )
    vias_parser.set_defaults(func=_vias_pecuarias_municipios)

    camino_parser = subparsers.add_parser(
        "camino-actual-municipios",
        help="Capa de camino actual (tramos sin asfaltar del IGN) por municipio, en GeoJSON",
    )
    camino_parser.add_argument(
        "--sin-red", action="store_true", help="Solo la caché cruda; falla si falta algo"
    )
    camino_parser.add_argument(
        "--cache", type=Path, default=Path("data/raw"), help="Directorio de la caché cruda"
    )
    camino_parser.add_argument(
        "--salida",
        type=Path,
        default=Path("data/derived/camino_actual"),
        help="Directorio de los ficheros <codigo_ine>.geojson",
    )
    camino_parser.set_defaults(func=_camino_actual_municipios)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    exit_code: int = args.func(args)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
