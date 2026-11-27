import argparse
import sys
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import requests

from parcel_intel.adapters.catastro import client as catastro_client
from parcel_intel.adapters.catastro.area_adapter import (
    CATASTRO_WFS_TILE_SIDE_M,
    CatastroAreaAdapter,
)
from parcel_intel.adapters.comparison_files import (
    JsonComparisonManifestWriter,
    ManifestTooLargeError,
    StretchFileFormatError,
    read_stretches,
)
from parcel_intel.adapters.deepseek.adapter import DeepSeekAdapter, MissingDeepSeekApiKeyError
from parcel_intel.adapters.deepseek.client import DeepSeekApiError
from parcel_intel.adapters.discrepancy_files import (
    DiscrepancyFileFormatError,
    GeoJsonDiscrepancyReportReader,
    GeoJsonDiscrepancyWriter,
)
from parcel_intel.adapters.ign_admin_units import IgnAdministrativeUnitsAdapter
from parcel_intel.adapters.ign_admin_units import client as ign_client
from parcel_intel.adapters.livestock_trails import client as livestock_client
from parcel_intel.adapters.livestock_trails.adapter import LivestockTrailAdapter
from parcel_intel.adapters.pnoa import client as pnoa_client
from parcel_intel.adapters.pnoa.window import PnoaWindowAdapter
from parcel_intel.adapters.postgis.connection import get_connection
from parcel_intel.adapters.postgis.rule_repository import PostgisRuleRepository
from parcel_intel.adapters.published_layers import (
    GeoJsonPublishedDiscrepancySink,
    GeoJsonPublishedLayerSink,
    PublishedLayerError,
)
from parcel_intel.adapters.raw_cache import (
    CachedRawFetcher,
    HttpGet,
    RawCacheCorruptError,
    RawCacheMissError,
)
from parcel_intel.adapters.road_layer_files import (
    GeoJsonLivestockTrailLayerWriter,
    GeoJsonRoadLayerWriter,
    LivestockTrailLayerFileError,
)
from parcel_intel.adapters.road_network import client as roadlink_client
from parcel_intel.adapters.road_network.adapter import RoadNetworkAdapter
from parcel_intel.adapters.shapely_geometry import ShapelyLineClipper, ShapelyPolygonClipper
from parcel_intel.adapters.trail_layers import GeoJsonTrailLayerReader, TrailLayerFormatError
from parcel_intel.application.author_rule_proposal import AuthorRuleProposalUseCase
from parcel_intel.application.build_cadastral_road_layer import BuildCadastralRoadLayerUseCase
from parcel_intel.application.build_comparison_images import BuildComparisonImagesUseCase
from parcel_intel.application.build_municipal_comparisons import (
    BuildMunicipalComparisonsUseCase,
    ComparisonFailuresError,
    MunicipalWindowLimitError,
)
from parcel_intel.application.build_municipal_livestock_trail_layers import (
    BuildMunicipalLivestockTrailLayersUseCase,
)
from parcel_intel.application.build_municipal_road_layers import BuildMunicipalRoadLayersUseCase
from parcel_intel.application.detect_discrepancies import DetectDiscrepanciesUseCase
from parcel_intel.application.publish_discrepancies import PublishDiscrepanciesUseCase
from parcel_intel.application.publish_layers import (
    DEFAULT_LAYERS,
    PublishLayersUseCase,
)
from parcel_intel.domain.cadastral_road import CadastralRoadLayer
from parcel_intel.domain.comparison_image import DegenerateStretchError
from parcel_intel.domain.discrepancy import DiscrepancyKind
from parcel_intel.domain.discrepancy_report import LayerStatus
from parcel_intel.domain.geometry import BBox
from parcel_intel.domain.municipal_livestock_trails import MunicipalLivestockTrailLayer
from parcel_intel.domain.municipal_road_layer import MunicipalRoadLayerBatch
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.published_discrepancy import OmittedByLicense
from parcel_intel.domain.published_layers import PUBLISHED_LAYERS, PublishedLayerId
from parcel_intel.domain.rule import Rule, WithinDistanceCondition
from parcel_intel.ports.errors import (
    AreaQueryLimitExceededError,
    CadastralServiceError,
    ClippedGeometryHasHolesError,
    IncompleteWfsResponseError,
    InvalidLlmProposalError,
    InvalidRuleLayerError,
    MunicipalBoundaryNotFoundError,
    MunicipalBoundaryUnusableError,
    RuleProposalNotFoundError,
    TruncatedAreaQueryError,
)

_LAYER_CHOICES = ["dph_cauce", "via_pecuaria", "red_natura_plan"]

AMBITO_HITO_INE = ("28043", "28013", "28052", "28019", "28170", "28180", "28157")
"""Los 7 municipios del primer hito (REGISTRY.md, "Ámbito del hito"): Colmenar de
Oreja, Aranjuez, Chinchón, Belmonte de Tajo, Villaconejos, Villarejo de Salvanés y
Valdelaguna. Configuración del hito, no dominio."""

AMBITO_HITO_BBOX_ETRS89 = (39.98, -3.62, 40.22, -3.15)
"""(lat_min, lon_min, lat_max, lon_max) en EPSG:4258 con el que se pide el WFS del IGN."""

REPOSITORY_URL = "https://github.com/murcialito/paso-comun"
"""Procedencia del índice de capas publicadas (historia #84)."""

PUBLISH_SIZE_THRESHOLD_BYTES = 3_000_000
"""Por encima de este peso, `publicar-capas` simplifica la geometría (ADR 0036, umbral de
producto alineado con #86)."""


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
    writer = GeoJsonLivestockTrailLayerWriter(args.salida)
    failed = False
    for layer in layers:
        try:
            path = writer.write(layer)
        except (OSError, LivestockTrailLayerFileError) as error:
            print(
                f"FALLO {layer.municipality.ine_code} {layer.municipality.name}: {error}",
                file=sys.stderr,
            )
            failed = True
            continue
        print(_format_layer(layer))
        print(f"  fichero: {path}")
    return 1 if failed else 0


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


def build_cadastral_road_layer(
    provincia: str,
    municipio: str,
    municipality_code: str,
    bbox: BBox,
    cache_dir: Path,
    offline: bool,
    http_get: HttpGet = catastro_client.default_http_getter,
    today: Callable[[], date] = _today,
    sleep: Callable[[float], None] = time.sleep,
) -> CadastralRoadLayer:
    """Composition root de la capa interna de caminos de Catastro (historia #37, ADR 0028).

    Con `offline=True` nada llama a la red: solo se lee la caché cruda."""
    fetcher = CachedRawFetcher(http_get, cache_dir, today, sleep=sleep, offline=offline)
    adapter = CatastroAreaAdapter(provincia, municipio, fetcher)
    use_case = BuildCadastralRoadLayerUseCase(
        parcels=adapter, land_use=adapter, tile_side_m=CATASTRO_WFS_TILE_SIDE_M
    )
    return use_case.execute(municipality_code, bbox)


def _format_cadastral_road_layer(layer: CadastralRoadLayer, municipio: str) -> str:
    lines = [
        f"{layer.municipality_code} {municipio}",
        f"  teselas: {layer.tiles}",
        f"  parcelas vistas: {layer.parcels_seen}",
        f"  candidatas (número >= 9000): {layer.road_number_candidates}",
        f"  caminos: {len(layer.roads)}",
        f"  excluidas por clase: {len(layer.excluded)}",
        f"  sin clasificar: {len(layer.unclassified)}",
    ]
    for road in layer.roads:
        lines.append(
            f"    {road.cadastral_reference} area_m2={road.area_m2:.1f} "
            f"clases={','.join(road.land_use_classes)}"
        )
    lines.append("Capa de uso interno: no publicable (licencia INSPIRE de Catastro).")
    return "\n".join(lines)


def _bbox_argument(value: str) -> BBox:
    parts = value.split(",")
    try:
        numbers = tuple(float(part) for part in parts)
    except ValueError:
        numbers = ()
    if len(numbers) != 4 or numbers[0] >= numbers[2] or numbers[1] >= numbers[3]:
        raise argparse.ArgumentTypeError(
            f"bbox MINX,MINY,MAXX,MAXY en EPSG:25830 (E,N) esperado: {value!r}"
        )
    return (numbers[0], numbers[1], numbers[2], numbers[3])


def _catastro_caminos(args: argparse.Namespace) -> int:
    try:
        layer = build_cadastral_road_layer(
            args.provincia,
            args.municipio,
            args.codigo,
            args.bbox,
            args.cache_dir,
            args.sin_red,
        )
    except (
        AreaQueryLimitExceededError,
        TruncatedAreaQueryError,
        CadastralServiceError,
        RawCacheMissError,
        RawCacheCorruptError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 1
    except requests.RequestException as error:
        print(f"Error de red: {error}", file=sys.stderr)
        return 1
    print(_format_cadastral_road_layer(layer, args.municipio))
    return 0


def build_discrepancy_use_case(derived_dir: Path, output_dir: Path) -> DetectDiscrepanciesUseCase:
    """Composition root de la detección de discrepancias (historia #32).

    Lee las capas derivadas de `derived_dir` y escribe el interno y el publicable
    bajo `output_dir`. Sin red ni LLM. El histórico no tiene ruta todavía: cuenta
    como fuente ausente."""
    return DetectDiscrepanciesUseCase(
        layers=GeoJsonTrailLayerReader(
            {
                "via_pecuaria_oficial": derived_dir / "vias_pecuarias",
                "ign_red_transporte": derived_dir / "camino_actual",
                "catastro_vt": derived_dir / "catastro_caminos",
            }
        ),
        internal_sink=GeoJsonDiscrepancyWriter(output_dir / "interno", publishable=False),
        public_sink=GeoJsonDiscrepancyWriter(output_dir / "publicable", publishable=True),
    )


def _municipality_code(value: str) -> str:
    if not (len(value) == 5 and value.isdigit()):
        raise argparse.ArgumentTypeError(f"código INE de 5 dígitos esperado: {value!r}")
    return value


def _discrepancias(args: argparse.Namespace) -> int:
    codes: list[str] = list(AMBITO_HITO_INE) if args.ambito else []
    codes.extend(code for code in args.municipio if code not in codes)
    if not codes:
        print("Indica --municipio <INE> (repetible) o --ambito.", file=sys.stderr)
        return 2
    use_case = build_discrepancy_use_case(args.entrada, args.salida)
    failed = False
    for code in codes:
        started = time.monotonic()
        try:
            report = use_case.execute(code)
        except TrailLayerFormatError as error:
            print(
                f"FALLO {code}: fuente={error.source} fichero={error.path}: {error.detail}",
                file=sys.stderr,
            )
            failed = True
            continue
        except Exception as error:  # un municipio roto no frena el lote
            print(f"FALLO {code}: {type(error).__name__}: {error}", file=sys.stderr)
            failed = True
            continue
        by_kind = Counter(record.discrepancy.kind for record in report.records)
        summary = ", ".join(f"{kind}={by_kind[kind]}" for kind in sorted(by_kind)) or "ninguna"
        absent = [layer.source for layer in report.layers if layer.status is LayerStatus.AUSENTE]
        print(
            f"{code}: {len(report.records)} discrepancias ({summary}); "
            f"capas ausentes: {', '.join(absent) or 'ninguna'}; "
            f"{time.monotonic() - started:.1f} s -> {args.salida}"
        )
    return 1 if failed else 0


def build_publish_use_case(
    derived_dir: Path,
    output_dir: Path,
    size_threshold_bytes: int = PUBLISH_SIZE_THRESHOLD_BYTES,
) -> PublishLayersUseCase:
    """Composition root de `publicar-capas` (historia #84, ADR 0036).

    Lee las mismas capas derivadas que `discrepancias` y escribe en `output_dir`
    (normalmente `site/datos`). Sin red."""
    return PublishLayersUseCase(
        layers=GeoJsonTrailLayerReader(
            {
                "via_pecuaria_oficial": derived_dir / "vias_pecuarias",
                "ign_red_transporte": derived_dir / "camino_actual",
            }
        ),
        sink=GeoJsonPublishedLayerSink(
            output_dir, REPOSITORY_URL, size_threshold_bytes=size_threshold_bytes
        ),
    )


_REGENERATE_HINT = (
    "regenera la capa con vias-pecuarias-municipios --sin-red "
    "o camino-actual-municipios --sin-red"
)


def _publicar_capas(args: argparse.Namespace) -> int:
    codes: list[str] = list(AMBITO_HITO_INE) if args.ambito else []
    codes.extend(code for code in args.municipio if code not in codes)
    if not codes:
        print("Indica --municipio <INE> (repetible) o --ambito.", file=sys.stderr)
        return 2
    layer_ids: list[PublishedLayerId] = []
    for layer_id in args.capa or DEFAULT_LAYERS:
        if layer_id not in layer_ids:
            layer_ids.append(layer_id)
    use_case = build_publish_use_case(
        args.entrada, args.salida, size_threshold_bytes=PUBLISH_SIZE_THRESHOLD_BYTES
    )
    try:
        result = use_case.execute(codes, layer_ids)
    except TrailLayerFormatError as error:
        print(
            f"ERROR fichero corrupto {error.path} (fuente {error.source}): {error.detail}; "
            "no se ha publicado nada",
            file=sys.stderr,
        )
        return 1
    except (PublishedLayerError, OSError) as error:
        print(f"ERROR al publicar: {error}; no se ha publicado nada", file=sys.stderr)
        return 1
    for failure in result.failures:
        hint = ""
        if failure.reason.startswith("no redistribuible"):
            hint = f"; {_REGENERATE_HINT}"
        print(
            f"ERROR {failure.layer_id} {failure.municipality_code}: {failure.reason}{hint}",
            file=sys.stderr,
        )
    if result.failures:
        print(f"No se ha escrito nada en {args.salida}.", file=sys.stderr)
        return 1
    for layer_id, code in result.empty:
        print(f"capa vacía, no se publica: {layer_id} {code}")
    for published in result.published:
        print(f"publicada {args.salida / published.path} {published.size_bytes} bytes")
        if published.simplification is not None:
            print(
                f"  simplificada con tolerancia {published.simplification.tolerance_m} m "
                f"(antes {published.simplification.bytes_before} bytes)"
            )
        if published.over_threshold:
            print("  AVISO: sigue por encima del umbral")
    return 0


def build_publish_discrepancies_use_case(
    input_dir: Path,
    output_dir: Path,
    size_threshold_bytes: int = PUBLISH_SIZE_THRESHOLD_BYTES,
) -> PublishDiscrepanciesUseCase:
    """Composition root de `publicar-discrepancias` (historia #94, ADR 0044).

    Lee el fichero publicable de `discrepancias` en `input_dir` y escribe en
    `output_dir` (normalmente `site/datos`). Sin red ni LLM."""
    return PublishDiscrepanciesUseCase(
        reports=GeoJsonDiscrepancyReportReader(input_dir),
        sink=GeoJsonPublishedDiscrepancySink(
            output_dir, REPOSITORY_URL, size_threshold_bytes=size_threshold_bytes
        ),
    )


_INDICIO_KINDS: tuple[DiscrepancyKind, ...] = ("AUSENTE_EN_FUENTE", "DESPLAZAMIENTO", "SOLAPE")


def _format_omitted(omitted: OmittedByLicense) -> str:
    return (
        f"omitidos por licencia {omitted.total} "
        f"(lado A: {omitted.subject}, contraparte: {omitted.counterpart})"
    )


def _publicar_discrepancias(args: argparse.Namespace) -> int:
    codes: list[str] = list(AMBITO_HITO_INE) if args.ambito else []
    codes.extend(code for code in args.municipio if code not in codes)
    if not codes:
        print("Indica --municipio <INE> (repetible) o --ambito.", file=sys.stderr)
        return 2
    use_case = build_publish_discrepancies_use_case(args.entrada, args.salida)
    try:
        result = use_case.execute(codes)
    except DiscrepancyFileFormatError as error:
        print(f"ERROR fichero corrupto {error.path}: {error.detail}", file=sys.stderr)
        print(f"No se ha escrito nada en {args.salida}.", file=sys.stderr)
        return 1
    except (PublishedLayerError, OSError) as error:
        print(f"ERROR al publicar: {error}", file=sys.stderr)
        print(f"No se ha escrito nada en {args.salida}.", file=sys.stderr)
        return 1
    for failure in result.failures:
        print(f"ERROR {failure.municipality_code}: {failure.reason}", file=sys.stderr)
    if result.failures:
        print(f"No se ha escrito nada en {args.salida}.", file=sys.stderr)
        return 1
    omitted = dict(result.omitted)
    for code in result.empty:
        print(f"sin indicios publicables, no se publica: {code}; {_format_omitted(omitted[code])}")
        previous = args.salida / "discrepancias" / f"{code}.geojson"
        if previous.is_file():
            print(
                f"  AVISO: sigue publicado el fichero anterior {previous}; "
                "bórralo a mano si procede"
            )
    kinds = dict(result.kinds)
    for published in result.published:
        by_kind = Counter(kinds[published.municipality_code])
        total = sum(by_kind.values())
        summary = ", ".join(f"{kind}={by_kind[kind]}" for kind in _INDICIO_KINDS)
        print(
            f"publicado {args.salida / published.path} {published.size_bytes} bytes: "
            f"{total} indicios ({summary}); "
            f"{_format_omitted(omitted[published.municipality_code])}"
        )
        if published.over_threshold:
            print("  AVISO: por encima del umbral de peso (ver #96)")
    return 0


def build_comparison_use_case(
    cache_dir: Path,
    output_dir: Path,
    offline: bool,
    http_get: HttpGet = pnoa_client.default_http_getter,
    today: Callable[[], date] = _today,
    sleep: Callable[[float], None] = time.sleep,
) -> BuildMunicipalComparisonsUseCase:
    """Composition root de `imagenes-comparacion` (historia #122, ADR 0042 §5).

    Las imágenes entran en la caché cruda; el manifiesto interno va a `output_dir`.
    Con `offline=True` nada llama a la red. Nada se escribe en `site/`."""
    fetcher = CachedRawFetcher(http_get, cache_dir, today, sleep=sleep, offline=offline)
    return BuildMunicipalComparisonsUseCase(
        builder=BuildComparisonImagesUseCase(PnoaWindowAdapter(fetcher)),
        sink=JsonComparisonManifestWriter(output_dir),
    )


def _imagenes_comparacion(args: argparse.Namespace) -> int:
    code: str = args.municipio
    try:
        requests_ = read_stretches(args.tramos, code)
    except StretchFileFormatError as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 1
    use_case = build_comparison_use_case(args.cache, args.salida, args.sin_red)
    try:
        results = use_case.execute(code, requests_)
    except MunicipalWindowLimitError as error:
        print(f"ERROR {code}: {error}; no se ha pedido ni escrito nada", file=sys.stderr)
        return 1
    except DegenerateStretchError as error:
        print(f"ERROR {code}: tramo sin segmento medible: {error}", file=sys.stderr)
        return 1
    except ComparisonFailuresError as error:
        for stretch_id, slot, error_type in error.failures:
            print(f"FALLO {stretch_id} franja {slot}: {error_type}", file=sys.stderr)
        print(f"No se ha escrito el manifiesto de {code}.", file=sys.stderr)
        return 1
    except (ManifestTooLargeError, OSError) as error:
        print(f"ERROR {code}: {error}; no se ha escrito el manifiesto", file=sys.stderr)
        return 1
    for comparison in results:
        images = sum(len(window.images) for window in comparison.windows)
        omitted = [o for window in comparison.windows for o in window.omitted]
        reasons = Counter(o.reason for o in omitted)
        print(
            f"{comparison.stretch_id}: {comparison.status}; {len(comparison.windows)} ventanas, "
            f"{images} imágenes, {len(omitted)} omisiones "
            f"(sin_cobertura={reasons['sin_cobertura']})"
        )
    print(f"{code}: {len(results)} tramos -> {args.salida / (code + '.json')}")
    return 0


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
    vias_parser.add_argument(
        "--salida",
        type=Path,
        default=Path("data/derived/vias_pecuarias"),
        help="Directorio de los ficheros <codigo_ine>.geojson",
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

    caminos_parser = subparsers.add_parser(
        "catastro-caminos",
        help="Capa interna de caminos de Catastro (parcelas >= 9000 de clase VT) de un municipio",
    )
    caminos_parser.add_argument("--provincia", required=True, help="Nombre, p. ej. MADRID")
    caminos_parser.add_argument(
        "--municipio", required=True, help="Nombre, p. ej. 'COLMENAR DE OREJA'"
    )
    caminos_parser.add_argument(
        "--codigo", type=_municipality_code, required=True, help="Código de Catastro, 5 dígitos"
    )
    caminos_parser.add_argument(
        "--bbox",
        type=_bbox_argument,
        required=True,
        help="MINX,MINY,MAXX,MAXY del término en EPSG:25830 (orden E,N)",
    )
    caminos_parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data/raw/catastro"),
        help="Directorio de la caché cruda de Catastro",
    )
    caminos_parser.add_argument(
        "--sin-red", action="store_true", help="Solo la caché cruda; falla si falta algo"
    )
    caminos_parser.set_defaults(func=_catastro_caminos)

    discrepancias_parser = subparsers.add_parser(
        "discrepancias",
        help="Discrepancias entre las capas de trazados de uno o varios municipios, en GeoJSON",
    )
    discrepancias_parser.add_argument(
        "--municipio",
        type=_municipality_code,
        action="append",
        default=[],
        help="Código INE de 5 dígitos (repetible)",
    )
    discrepancias_parser.add_argument(
        "--ambito", action="store_true", help="Los 7 municipios del primer hito"
    )
    discrepancias_parser.add_argument(
        "--entrada",
        type=Path,
        default=Path("data/derived"),
        help="Directorio con las capas derivadas (vias_pecuarias/, camino_actual/, ...)",
    )
    discrepancias_parser.add_argument(
        "--salida",
        type=Path,
        default=Path("data/derived/discrepancias"),
        help="Directorio de salida (interno/ y publicable/)",
    )
    discrepancias_parser.set_defaults(func=_discrepancias)

    publicar_parser = subparsers.add_parser(
        "publicar-capas",
        help="Publica vías pecuarias y camino actual en site/datos (EPSG:4326, con procedencia)",
    )
    publicar_parser.add_argument(
        "--municipio",
        type=_municipality_code,
        action="append",
        default=[],
        help="Código INE de 5 dígitos (repetible)",
    )
    publicar_parser.add_argument(
        "--ambito", action="store_true", help="Los 7 municipios del primer hito"
    )
    publicar_parser.add_argument(
        "--capa",
        choices=sorted(PUBLISHED_LAYERS),
        action="append",
        default=[],
        help="Capa a publicar (repetible; por defecto, todas)",
    )
    publicar_parser.add_argument(
        "--entrada",
        type=Path,
        default=Path("data/derived"),
        help="Directorio con las capas derivadas (vias_pecuarias/, camino_actual/)",
    )
    publicar_parser.add_argument(
        "--salida",
        type=Path,
        default=Path("site/datos"),
        help="Directorio publicado del sitio",
    )
    publicar_parser.set_defaults(func=_publicar_capas)

    indicios_parser = subparsers.add_parser(
        "publicar-discrepancias",
        help="Publica los indicios de discrepancia en site/datos (EPSG:4326, con su ficha)",
    )
    indicios_parser.add_argument(
        "--municipio",
        type=_municipality_code,
        action="append",
        default=[],
        help="Código INE de 5 dígitos (repetible)",
    )
    indicios_parser.add_argument(
        "--ambito", action="store_true", help="Los 7 municipios del primer hito"
    )
    indicios_parser.add_argument(
        "--entrada",
        type=Path,
        default=Path("data/derived/discrepancias/publicable"),
        help="Directorio con los ficheros publicables de `discrepancias`",
    )
    indicios_parser.add_argument(
        "--salida",
        type=Path,
        default=Path("site/datos"),
        help="Directorio publicado del sitio",
    )
    indicios_parser.set_defaults(func=_publicar_discrepancias)

    comparacion_parser = subparsers.add_parser(
        "imagenes-comparacion",
        help="Imágenes de comparación de los tramos de un municipio y su manifiesto interno",
    )
    comparacion_parser.add_argument(
        "--municipio", type=_municipality_code, required=True, help="Código INE de 5 dígitos"
    )
    comparacion_parser.add_argument(
        "--tramos", type=Path, required=True, help="GeoJSON de tramos en EPSG:25830, con id opaco"
    )
    comparacion_parser.add_argument(
        "--sin-red", action="store_true", help="Solo la caché cruda; un hueco es un fallo"
    )
    comparacion_parser.add_argument(
        "--cache", type=Path, default=Path("data/raw"), help="Directorio de la caché cruda"
    )
    comparacion_parser.add_argument(
        "--salida",
        type=Path,
        default=Path("data/derived/comparacion"),
        help="Directorio de los manifiestos <codigo_ine>.json",
    )
    comparacion_parser.set_defaults(func=_imagenes_comparacion)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    exit_code: int = args.func(args)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
