import argparse
import json
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

import requests

from parcel_intel.adapters.catastro import client as catastro_client
from parcel_intel.adapters.catastro.area_adapter import (
    CATASTRO_INSPIRE_LICENSE,
    CATASTRO_WFS_TILE_SIDE_M,
    CatastroAreaAdapter,
)
from parcel_intel.adapters.comparison_files import (
    JsonComparisonManifestWriter,
    ManifestTooLargeError,
    StretchFileFormatError,
    read_stretches,
)
from parcel_intel.adapters.curated_historic import CuratedHistoricFiles
from parcel_intel.adapters.cut_candidate_files import (
    GeoJsonCutCandidateReader,
    GeoJsonCutCandidateWriter,
)
from parcel_intel.adapters.deepseek.adapter import DeepSeekAdapter, MissingDeepSeekApiKeyError
from parcel_intel.adapters.deepseek.client import DeepSeekApiError
from parcel_intel.adapters.discrepancy_files import (
    DiscrepancyFileFormatError,
    GeoJsonDiscrepancyReportReader,
    GeoJsonDiscrepancyWriter,
)
from parcel_intel.adapters.evidence import (
    PngTrailEvidence,
    PnoaPngSource,
    default_png_http_get,
)
from parcel_intel.adapters.evidence.pnoa_png import NotPngResponseError
from parcel_intel.adapters.ign_admin_units import IgnAdministrativeUnitsAdapter
from parcel_intel.adapters.ign_admin_units import client as ign_client
from parcel_intel.adapters.ign_historic import HttpGet as HistoricHttpGet
from parcel_intel.adapters.ign_historic import IgnHistoricImageAdapter
from parcel_intel.adapters.ign_historic import default_http_get as historic_default_http_get
from parcel_intel.adapters.livestock_trails import client as livestock_client
from parcel_intel.adapters.livestock_trails.adapter import LivestockTrailAdapter
from parcel_intel.adapters.pnoa import client as pnoa_client
from parcel_intel.adapters.pnoa.window import PnoaWindowAdapter
from parcel_intel.adapters.postgis.connection import get_connection
from parcel_intel.adapters.postgis.georeference_repository import PostgisGeoreferenceRepository
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
from parcel_intel.adapters.trail_layers import (
    GeoJsonCadastralRoadWriter,
    GeoJsonTrailLayerReader,
    TrailLayerFormatError,
)
from parcel_intel.adapters.validation_cases.casos_json import parse_validation_cases
from parcel_intel.adapters.validation_cases.congelacion import (
    ErrorCongelacion,
    calcular_huella,
    cargar_casos,
    versiones,
)
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
from parcel_intel.application.build_trail_evidence import BuildTrailEvidenceUseCase
from parcel_intel.application.cut_signals import CadastralParcelSignalProvider
from parcel_intel.application.detect_cut_candidates import DetectCutCandidatesUseCase
from parcel_intel.application.detect_discrepancies import DetectDiscrepanciesUseCase
from parcel_intel.application.evaluate_candidates import EvaluateCandidatesUseCase
from parcel_intel.application.load_historic_trails import HistoricUnitUseCase
from parcel_intel.application.publish_discrepancies import PublishDiscrepanciesUseCase
from parcel_intel.application.publish_layers import (
    DEFAULT_LAYERS,
    PublishLayersUseCase,
)
from parcel_intel.domain.cadastral_road import CadastralRoadLayer
from parcel_intel.domain.candidate_evaluation import (
    MATCH_CRITERION_V1,
    CandidateEvaluationInputError,
    EvaluableCandidate,
    EvaluationResult,
)
from parcel_intel.domain.comparison_image import DegenerateStretchError
from parcel_intel.domain.digitization import StaleApprovalError
from parcel_intel.domain.discrepancy import DiscrepancyKind
from parcel_intel.domain.discrepancy_report import LayerStatus
from parcel_intel.domain.geometry import BBox, outward_integer_bbox, shape_bbox
from parcel_intel.domain.georeferencing import (
    ControlPointSet,
    GeoreferenceFit,
    GeoreferenceRejectedError,
    UnitSpec,
    Verdict,
    WorkingImage,
    occupied_quadrants,
    thresholds_m,
)
from parcel_intel.domain.municipal_livestock_trails import MunicipalLivestockTrailLayer
from parcel_intel.domain.municipal_road_layer import MunicipalRoadLayerBatch
from parcel_intel.domain.municipality import HITO_MUNICIPALITY_CODES
from parcel_intel.domain.parcel import Parcel
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.published_discrepancy import OmittedByLicense
from parcel_intel.domain.published_layers import PUBLISHED_LAYERS, PublishedLayerId
from parcel_intel.domain.rule import Rule, WithinDistanceCondition
from parcel_intel.ports.errors import (
    AreaQueryLimitExceededError,
    CadastralServiceError,
    ClippedGeometryHasHolesError,
    CuratedUnitNotFoundError,
    CutCandidateFileError,
    EvidenceImageFormatError,
    IncompleteWfsResponseError,
    InvalidLlmProposalError,
    InvalidRuleLayerError,
    MunicipalBoundaryNotFoundError,
    MunicipalBoundaryUnusableError,
    RawImageMismatchError,
    RuleProposalNotFoundError,
    TruncatedAreaQueryError,
    WorkingImageUnavailableError,
)
from parcel_intel.ports.georeference_repository import GeoreferenceRepositoryPort
from parcel_intel.ports.municipal_boundary import MunicipalBoundaryPort

_LAYER_CHOICES = ["dph_cauce", "via_pecuaria", "red_natura_plan"]

AMBITO_HITO_INE = HITO_MUNICIPALITY_CODES
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


def municipality_grid_bbox(
    municipality_code: str,
    cache_dir: Path,
    offline: bool,
    ign_http_get: HttpGet = ign_client.default_http_getter,
    today: Callable[[], date] = _today,
    sleep: Callable[[float], None] = time.sleep,
) -> BBox:
    """Bbox de la rejilla de teselas de un municipio (historia #160): el del límite del IGN
    redondeado hacia fuera a metro entero, el mismo que usa `candidatos-corte`."""
    fetcher = CachedRawFetcher(ign_http_get, cache_dir, today, sleep=sleep, offline=offline)
    boundaries = IgnAdministrativeUnitsAdapter(
        AMBITO_HITO_BBOX_ETRS89, fetcher=fetcher, today=today
    )
    [boundary] = boundaries.get_municipal_boundaries([municipality_code])
    return outward_integer_bbox(shape_bbox(boundary.geometry))


def cadastral_road_layer_provenance(layer: CadastralRoadLayer) -> Provenance:
    """Procedencia de la capa: la petición WFS más antigua de sus caminos (fecha real de
    descarga); sin caminos, la fuente genérica con la fecha de hoy."""
    if layer.roads:
        first = min(layer.roads, key=lambda road: road.provenance.retrieved_at)
        return first.provenance
    return Provenance(
        source="catastro_wfs_cp",
        url=catastro_client.WFS_PARCEL_URL,
        retrieved_at=_today(),
        license=CATASTRO_INSPIRE_LICENSE,
        redistribution=Redistribution.INTERNAL_ONLY,
    )


def _format_bbox(bbox: BBox) -> str:
    return ",".join(f"{value:.2f}".rstrip("0").rstrip(".") for value in bbox)


def _catastro_caminos(args: argparse.Namespace) -> int:
    try:
        if args.bbox is None:
            bbox = municipality_grid_bbox(args.codigo, args.cache, args.sin_red)
        else:
            bbox = args.bbox
        layer = build_cadastral_road_layer(
            args.provincia,
            args.municipio,
            args.codigo,
            bbox,
            args.cache_dir,
            args.sin_red,
        )
        # Todo o nada: solo se escribe con la capa completa y validada.
        path = GeoJsonCadastralRoadWriter(args.salida).write(
            layer, cadastral_road_layer_provenance(layer)
        )
    except (
        MunicipalBoundaryNotFoundError,
        MunicipalBoundaryUnusableError,
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
    except OSError as error:
        print(f"Error al escribir la capa: {error}", file=sys.stderr)
        return 1
    print(_format_cadastral_road_layer(layer, args.municipio))
    print(f"  rejilla: bbox {_format_bbox(bbox)} (teselas de {CATASTRO_WFS_TILE_SIDE_M:g} m)")
    print(f"Capa escrita en {path}")
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


class _CachedParcels:
    """`ParcelsInAreaPort` sobre la caché cruda de Catastro. Una tesela que falta
    en la caché (modo `--sin-red`) es «tesela sin datos», no un fallo del lote:
    la señal queda `sin_datos` con su motivo."""

    def __init__(self, inner: CatastroAreaAdapter) -> None:
        self._inner = inner

    def get_parcels_in_bbox(self, bbox: BBox) -> list[Parcel]:
        try:
            return self._inner.get_parcels_in_bbox(bbox)
        except RawCacheMissError as error:
            raise CadastralServiceError(f"tesela no cacheada y sin red: {error}") from error


CUT_CANDIDATES_PROVINCE = "MADRID"


def build_cut_candidate_use_case(
    derived_dir: Path,
    output_dir: Path,
    cache_dir: Path,
    offline: bool,
    catastro_http_get: HttpGet = catastro_client.default_http_getter,
    ign_http_get: HttpGet = ign_client.default_http_getter,
    today: Callable[[], date] = _today,
    sleep: Callable[[float], None] = time.sleep,
    boundaries: MunicipalBoundaryPort | None = None,
) -> DetectCutCandidatesUseCase:
    """Composition root de `candidatos-corte` (historia #128, ADR 0039 §8).

    Lee el informe interno de discrepancias de `derived_dir/discrepancias/interno`
    y las parcelas de Catastro (#37, interno) y escribe en `output_dir`. Sin LLM.
    Con `offline=True` nada llama a la red: solo la caché cruda."""
    catastro_fetcher = CachedRawFetcher(
        catastro_http_get, cache_dir / "catastro", today, sleep=sleep, offline=offline
    )
    if boundaries is None:
        ign_fetcher = CachedRawFetcher(ign_http_get, cache_dir, today, sleep=sleep, offline=offline)
        boundaries = IgnAdministrativeUnitsAdapter(
            AMBITO_HITO_BBOX_ETRS89, fetcher=ign_fetcher, today=today
        )
    provider = CadastralParcelSignalProvider(
        parcels_for=lambda code: _CachedParcels(
            CatastroAreaAdapter(CUT_CANDIDATES_PROVINCE, code, catastro_fetcher)
        ),
        boundaries=boundaries,
        tile_side_m=CATASTRO_WFS_TILE_SIDE_M,
    )
    return DetectCutCandidatesUseCase(
        reports=GeoJsonDiscrepancyReportReader(derived_dir / "discrepancias" / "interno"),
        providers=[provider],
        sink=GeoJsonCutCandidateWriter(output_dir),
    )


def _candidatos_corte(args: argparse.Namespace) -> int:
    codes: list[str] = list(AMBITO_HITO_INE) if args.ambito else []
    codes.extend(code for code in args.municipio if code not in codes)
    if not codes:
        print("Indica --municipio <INE> (repetible) o --ambito.", file=sys.stderr)
        return 1
    use_case = build_cut_candidate_use_case(args.entrada, args.salida, args.cache, args.sin_red)
    failed = False
    for code in codes:
        try:
            report = use_case.execute(code)
        except Exception as error:  # un municipio roto no frena el lote
            print(f"FALLO {code}: {type(error).__name__}: {error}", file=sys.stderr)
            failed = True
            continue
        if not report.discrepancy_criterion_id:
            print(f"{code}: sin capas (sin informe de discrepancias); no se escribe fichero")
            continue
        no_data = [s.signal.identifier for s in report.signals if s.status == "sin_datos"]
        print(
            f"{code}: {len(report.candidates)} candidatos; "
            f"señales sin_datos: {', '.join(no_data) or 'ninguna'} -> {args.salida}"
        )
    return 1 if failed else 0


def _ratio_entry(value: float | None, **counts: int | str | list[str]) -> dict[str, object]:
    return {"valor": None if value is None else round(value, 4), **counts}


def build_measurement_report(
    result: EvaluationResult,
    *,
    label: str | None,
    sha256: str,
    frozen: bool,
    run_date: date,
    candidate_methods: list[str],
    total_cases: int,
) -> dict[str, object]:
    """Informe agregado de `medir-candidatos` (historia #111). Solo ids públicos de caso
    y agregados: ni ids de candidato, ni descripciones, ni referencias catastrales."""
    reasons = Counter(item.reason for item in result.not_evaluable_cases)
    criterion = result.criterion
    return {
        "etiqueta": label,
        "sha256": sha256,
        "congelado": frozen,
        "fecha": run_date.isoformat(),
        "metodo_candidatos": candidate_methods,
        "criterio_casamiento": {
            "identificador": criterion.identifier,
            "version": criterion.version,
            "distancia_max_m": criterion.max_distance_m,
            "solape_min": criterion.min_overlap,
            "paso_muestreo_m": result.sample_step_m,
        },
        "casos_total": total_cases,
        "evaluables": {
            "total": len(result.evaluable_case_ids),
            "casos": list(result.evaluable_case_ids),
        },
        "no_evaluables": {
            "total": len(result.not_evaluable_cases),
            "por_motivo": {reason: reasons[reason] for reason in sorted(reasons)},
            "casos": [
                {"caso": item.case_id, "motivo": item.reason} for item in result.not_evaluable_cases
            ],
        },
        "cobertura": _ratio_entry(
            result.coverage,
            casos_senalados=len(result.flagged_case_ids),
            casos_evaluables=len(result.evaluable_case_ids),
            casos=list(result.flagged_case_ids),
        ),
        "precision": _ratio_entry(
            result.precision,
            cota="inferior",
            candidatos_acertados=result.hit_candidates,
            candidatos_evaluables=result.evaluable_candidates,
        ),
        "candidatos": {
            "no_evaluables": result.not_evaluable_candidates,
            "descartados": result.discarded_candidates,
        },
    }


def _percent(entry: object) -> str:
    value = entry.get("valor") if isinstance(entry, dict) else None
    return "no calculable" if value is None else f"{value * 100:.1f} %"


def _medir_candidatos(args: argparse.Namespace) -> int:
    """Composition root de `medir-candidatos` (historia #111). Sin red ni LLM."""
    casos_path: Path = args.casos
    try:
        raw_cases = cargar_casos(casos_path)
        frozen_versions = versiones(casos_path.parent)
        cases = parse_validation_cases({"casos": raw_cases})
    except (ErrorCongelacion, ValueError, OSError) as error:
        print(f"ERROR en el conjunto de validación: {error}", file=sys.stderr)
        return 1
    sha256 = calcular_huella(casos_path)
    current = frozen_versions[-1] if frozen_versions else None
    frozen = current is not None and current.sha256 == sha256
    if not frozen:
        reason = (
            "no hay ningún CONGELADO*.md"
            if current is None
            else f"la huella no coincide con la de {current.etiqueta}"
        )
        print(f"AVISO: conjunto no congelado: {reason}", file=sys.stderr)

    reader = GeoJsonCutCandidateReader(args.entrada)
    candidates: list[EvaluableCandidate] = []
    with_candidates: set[str] = set()
    methods: set[str] = set()
    try:
        for code in sorted({case.municipality_ine for case in cases if case.municipality_ine}):
            report = reader.get_report(code)
            if report is None:
                continue
            with_candidates.add(code)
            methods.add(f"{report.method.identifier}@{report.method.version}")
            candidates.extend(
                EvaluableCandidate(c.candidate_id, c.municipality_code, c.stretch)
                for c in report.candidates
            )
        result = EvaluateCandidatesUseCase().execute(
            cases, candidates, with_candidates, MATCH_CRITERION_V1
        )
    except CutCandidateFileError as error:
        print(f"ERROR fichero de candidatos {error.path}: {error.detail}", file=sys.stderr)
        print("No se ha escrito el informe.", file=sys.stderr)
        return 1
    except CandidateEvaluationInputError as error:
        print(f"ERROR en la evaluación: {error}; no se ha escrito el informe.", file=sys.stderr)
        return 1

    report_data = build_measurement_report(
        result,
        label=current.etiqueta if frozen and current is not None else None,
        sha256=sha256,
        frozen=frozen,
        run_date=_today(),
        candidate_methods=sorted(methods),
        total_cases=len(cases),
    )
    if not frozen:
        report_data["aviso"] = "conjunto no congelado: la huella no coincide con la vigente"
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(
        json.dumps(report_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    no_eval = report_data["no_evaluables"]
    assert isinstance(no_eval, dict)
    print(
        f"Casos: {len(cases)}; evaluables: {len(result.evaluable_case_ids)}; "
        f"no evaluables: {no_eval['total']} {no_eval['por_motivo']}\n"
        f"Cobertura: {_percent(report_data['cobertura'])} "
        f"({len(result.flagged_case_ids)}/{len(result.evaluable_case_ids)} casos)\n"
        f"Precisión (cota inferior): {_percent(report_data['precision'])} "
        f"({result.hit_candidates}/{result.evaluable_candidates} candidatos)\n"
        f"-> {args.salida}"
    )
    return 0


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


def build_historic_unit_use_case(
    curated: Path,
    cache: Path,
    offline: bool,
    repository: GeoreferenceRepositoryPort | None = None,
    http_get: HistoricHttpGet = historic_default_http_get,
    today: Callable[[], date] = _today,
) -> HistoricUnitUseCase:
    """Composition root de `historico ajuste|cargar` (historia #139, ADR 0044).

    `repository` solo hace falta para `cargar`; `ajuste` no usa la base."""
    return HistoricUnitUseCase(
        inputs=CuratedHistoricFiles(curated),
        images=IgnHistoricImageAdapter(
            raw_dir=cache, http_get=http_get, clock=today, offline=offline
        ),
        repository=repository,
    )


@contextmanager
def _georeference_repository() -> Iterator[GeoreferenceRepositoryPort]:
    connection = get_connection()
    try:
        yield PostgisGeoreferenceRepository(connection)
    finally:
        connection.close()


def _format_fit(
    spec: UnitSpec,
    image: WorkingImage,
    control_points: ControlPointSet,
    fit: GeoreferenceFit,
    verdict: Verdict,
) -> list[str]:
    points = control_points.points
    loo_limit, max_limit = thresholds_m(spec.scale_denominator)
    quadrants = occupied_quadrants(points, spec.image_width_px, spec.image_height_px)
    lines = [
        f"unidad: {spec.unit_id}",
        f"documento: {spec.document_id}",
        f"imagen_sha256: {image.sha256}",
        f"puntos_sha256: {control_points.sha256}",
        f"candidatos: {len(points)}",
        f"retenidos: {fit.n_retained}",
        f"descartados: {len(points) - fit.n_retained}",
        f"cuadrantes: {quadrants}",
        f"rmse_m: {fit.rmse_m:.2f}",
        f"residuo_max_m: {fit.max_residual_m:.2f}",
        f"rmse_loo_m: {fit.loo_rmse_m:.2f}",
        f"umbral_rmse_loo_m: {loo_limit:.2f}",
        f"umbral_residuo_max_m: {max_limit:.2f}",
        "veredicto: aceptable"
        if verdict.ok
        else "veredicto: rechazada: " + "; ".join(verdict.reasons),
    ]
    retained = {p.point_id: p.retained for p in points}
    for residual in fit.residuals:
        state = "retenido" if retained[residual.point_id] else "descartado"
        loo = "-" if residual.loo_residual_m is None else f"{residual.loo_residual_m:.2f}"
        lines.append(f"{residual.point_id} {state} residuo_m={residual.residual_m:.2f} loo_m={loo}")
    return lines


def _historic_failure(error: Exception) -> str | None:
    """Motivo de un rechazo de la unidad, o `None` si el error no es de los esperados."""
    if isinstance(error, StaleApprovalError):
        return (
            "aprobación caducada: los puntos de control cambiaron; devolver a propuesto: "
            + ", ".join(error.trail_ids)
        )
    if isinstance(
        error,
        GeoreferenceRejectedError
        | RawImageMismatchError
        | WorkingImageUnavailableError
        | CuratedUnitNotFoundError
        | ValueError,
    ):
        return str(error)
    return None


def _historico_ajuste(args: argparse.Namespace) -> int:
    use_case = build_historic_unit_use_case(args.curated, args.cache, args.sin_red)
    try:
        assessment = use_case.assess(args.unit_id)
    except Exception as error:
        reason = _historic_failure(error)
        if reason is None:
            raise
        print(f"ERROR {args.unit_id}: {reason}", file=sys.stderr)
        return 1
    for line in _format_fit(
        assessment.spec,
        assessment.image,
        assessment.control_points,
        assessment.fit,
        assessment.verdict,
    ):
        print(line)
    if not assessment.verdict.ok:
        print(f"ERROR {args.unit_id}: " + "; ".join(assessment.verdict.reasons), file=sys.stderr)
        return 1
    return 0


def _historico_cargar(args: argparse.Namespace) -> int:
    try:
        with _georeference_repository() as repository:
            use_case = build_historic_unit_use_case(
                args.curated, args.cache, args.sin_red, repository
            )
            outcome = use_case.load(args.unit_id)
    except Exception as error:
        reason = _historic_failure(error)
        if reason is None:
            raise
        print(f"ERROR {args.unit_id}: {reason}; no se ha escrito nada", file=sys.stderr)
        return 1
    unit = outcome.unit
    for line in _format_fit(
        unit.spec, unit.image, unit.control_points, unit.fit, Verdict(ok=True, reasons=())
    ):
        print(line)
    sync = outcome.sync
    print(f"insertados: {len(sync.inserted)}")
    print(f"actualizados: {len(sync.updated)}")
    print(f"sin_cambios: {len(sync.unchanged)}")
    print(f"retirados: {len(sync.withdrawn)}")
    print(f"propuestos: {len(outcome.proposed)}")
    print(f"rechazados: {len(outcome.rejected)}")
    for trail_id, reason in outcome.extrapolated:
        print(f"extrapolado {trail_id}: {reason}")
    for attribution in outcome.attributions:
        print(f"atribucion: {attribution}")
    return 0


def build_evidence_use_case(
    curated: Path,
    cache: Path,
    cache_pnoa: Path,
    offline: bool,
    image_http_get: HistoricHttpGet = historic_default_http_get,
    pnoa_http_get: HttpGet = default_png_http_get,
    today: Callable[[], date] = _today,
    sleep: Callable[[float], None] = time.sleep,
) -> BuildTrailEvidenceUseCase:
    """Composition root de `historico evidencia` (historia #140, ADR 0043).

    Lee la entrada humana de `curated`, la imagen de trabajo de `cache` y pide PNOA en PNG a
    través de la caché cruda `cache_pnoa`. La evidencia se escribe junto a la entrada, en
    `curated/<unit_id>/evidencia/`. Con `offline=True` nada llama a la red."""
    fetcher = CachedRawFetcher(pnoa_http_get, cache_pnoa, today, sleep=sleep, offline=offline)
    return BuildTrailEvidenceUseCase(
        inputs=CuratedHistoricFiles(curated),
        images=IgnHistoricImageAdapter(
            cache, image_http_get, today, sleep=sleep, offline=offline
        ),
        evidence=PngTrailEvidence(cache, curated, PnoaPngSource(fetcher)),
    )


def _historico_evidencia(args: argparse.Namespace) -> int:
    unit_id: str = args.unit_id
    use_case = build_evidence_use_case(args.curated, args.cache, args.cache_pnoa, args.sin_red)
    try:
        records = use_case.execute(unit_id)
    except GeoreferenceRejectedError as error:
        print(f"ERROR {unit_id}: {error}; no se ha escrito nada", file=sys.stderr)
        return 1
    except StaleApprovalError as error:
        print(
            f"ERROR {unit_id}: {error}; devuelve esos trazados a `propuesto` y regenera la "
            "evidencia; no se ha escrito nada",
            file=sys.stderr,
        )
        return 1
    except (
        CuratedUnitNotFoundError,
        RawImageMismatchError,
        WorkingImageUnavailableError,
        EvidenceImageFormatError,
        NotPngResponseError,
        RawCacheMissError,
        RawCacheCorruptError,
        requests.RequestException,
        ValueError,
        OSError,
    ) as error:
        print(f"ERROR {unit_id}: {error}", file=sys.stderr)
        return 1
    folder = args.curated / unit_id / "evidencia"
    for record in records:
        path = folder / f"{record.trail_id}.png"
        print(f"{record.trail_id}: {path} sha256={record.png_sha256}")
    print(f"{unit_id}: {len(records)} evidencias")
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
        default=None,
        help="MINX,MINY,MAXX,MAXY en EPSG:25830 (E,N); por defecto, el límite del IGN "
        "redondeado hacia fuera (la rejilla que usa candidatos-corte)",
    )
    caminos_parser.add_argument(
        "--cache",
        type=Path,
        default=Path("data/raw"),
        help="Caché cruda del límite del IGN (solo sin --bbox)",
    )
    caminos_parser.add_argument(
        "--salida",
        type=Path,
        default=Path("data/derived/catastro_caminos"),
        help="Directorio de los ficheros <codigo>.geojson (uso interno, nunca se publica)",
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

    candidatos_parser = subparsers.add_parser(
        "candidatos-corte",
        help="Candidatos a corte de uno o varios municipios, en un fichero interno (no se publica)",
    )
    candidatos_parser.add_argument(
        "--municipio",
        type=_municipality_code,
        action="append",
        default=[],
        help="Código INE de 5 dígitos (repetible)",
    )
    candidatos_parser.add_argument(
        "--ambito", action="store_true", help="Los 7 municipios del primer hito"
    )
    candidatos_parser.add_argument(
        "--sin-red",
        action="store_true",
        help="Solo la caché cruda; una tesela que falta deja la señal sin_datos",
    )
    candidatos_parser.add_argument(
        "--entrada",
        type=Path,
        default=Path("data/derived"),
        help="Directorio con las capas derivadas (discrepancias/interno/)",
    )
    candidatos_parser.add_argument(
        "--cache", type=Path, default=Path("data/raw"), help="Directorio de la caché cruda"
    )
    candidatos_parser.add_argument(
        "--salida",
        type=Path,
        default=Path("data/derived/candidatos/interno"),
        help="Directorio de salida de los ficheros internos <codigo_ine>.geojson",
    )
    candidatos_parser.set_defaults(func=_candidatos_corte)

    medir_parser = subparsers.add_parser(
        "medir-candidatos",
        help="Cobertura y precisión de los candidatos a corte frente al conjunto de validación",
    )
    medir_parser.add_argument(
        "--casos",
        type=Path,
        default=Path("docs/validacion/casos.json"),
        help="casos.json; los CONGELADO*.md se buscan en su directorio",
    )
    medir_parser.add_argument(
        "--entrada",
        type=Path,
        default=Path("data/derived/candidatos/interno"),
        help="Directorio con los ficheros internos <codigo_ine>.geojson de candidatos",
    )
    medir_parser.add_argument(
        "--salida",
        type=Path,
        default=Path("data/derived/validacion/medicion.json"),
        help="Informe agregado en JSON (fichero de datos, no se publica)",
    )
    medir_parser.set_defaults(func=_medir_candidatos)

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

    historico_parser = subparsers.add_parser(
        "historico", help="Trazados históricos georreferenciados de una unidad (ADR 0043)"
    )
    historico_subparsers = historico_parser.add_subparsers(dest="historico_command", required=True)
    for name, helptext, handler in (
        (
            "ajuste",
            "Medir el ajuste de los puntos de control de una unidad (sin base)",
            _historico_ajuste,
        ),
        ("cargar", "Cargar en PostGIS los trazados aprobados de una unidad", _historico_cargar),
    ):
        unit_parser = historico_subparsers.add_parser(name, help=helptext)
        unit_parser.add_argument("unit_id", help="Identificador de la unidad, p. ej. 280075-w1")
        unit_parser.add_argument(
            "--curated",
            type=Path,
            default=Path("curated/historico"),
            help="Directorio con una carpeta por unidad",
        )
        unit_parser.add_argument(
            "--cache",
            type=Path,
            default=Path("data/raw/ign_planimetrias"),
            help="Caché cruda de las imágenes de trabajo",
        )
        unit_parser.add_argument(
            "--sin-red", action="store_true", help="Solo la caché; sin imagen es un error"
        )
        unit_parser.set_defaults(func=handler)
    evidencia_parser = historico_subparsers.add_parser(
        "evidencia",
        help="PNG de dos paneles de cada trazado propuesto de una unidad, para revisarlo",
    )
    evidencia_parser.add_argument("unit_id", help="Unidad, p. ej. 280075-w1")
    evidencia_parser.add_argument(
        "--curated",
        type=Path,
        default=Path("curated/historico"),
        help="Entrada humana versionada; la evidencia se escribe en <unit_id>/evidencia/",
    )
    evidencia_parser.add_argument(
        "--cache",
        type=Path,
        default=Path("data/raw/ign_planimetrias"),
        help="Caché cruda de las imágenes de trabajo",
    )
    evidencia_parser.add_argument(
        "--cache-pnoa",
        type=Path,
        default=Path("data/raw/pnoa_ma"),
        help="Caché cruda de las respuestas PNG de PNOA",
    )
    evidencia_parser.add_argument(
        "--sin-red", action="store_true", help="Solo las cachés; un hueco es un fallo"
    )
    evidencia_parser.set_defaults(func=_historico_evidencia)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    exit_code: int = args.func(args)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
