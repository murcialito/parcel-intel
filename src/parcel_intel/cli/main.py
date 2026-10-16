import argparse
import sys
from pathlib import Path

import requests

from parcel_intel.adapters.deepseek.adapter import DeepSeekAdapter, MissingDeepSeekApiKeyError
from parcel_intel.adapters.deepseek.client import DeepSeekApiError
from parcel_intel.adapters.postgis.connection import get_connection
from parcel_intel.adapters.postgis.rule_repository import PostgisRuleRepository
from parcel_intel.application.author_rule_proposal import AuthorRuleProposalUseCase
from parcel_intel.domain.rule import Rule, WithinDistanceCondition
from parcel_intel.ports.errors import (
    InvalidLlmProposalError,
    InvalidRuleLayerError,
    RuleProposalNotFoundError,
)

_LAYER_CHOICES = ["dph_cauce", "via_pecuaria", "red_natura_plan"]


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

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    exit_code: int = args.func(args)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
