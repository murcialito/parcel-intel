"""Listado del estado de revisión de los candidatos a corte — historia #168, ADR 0047.

Por municipio: candidatos (#128), revisiones humanas (`curated/candidatos/`) y
disponibilidad de imágenes de comparación (#122). No escribe nada, no usa red ni
base de datos. Un municipio que falla no frena el lote.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from parcel_intel.domain.candidate_inventory import (
    CandidateInventoryState,
    InvalidInventoryCodeError,
    reconcile_inventory,
)
from parcel_intel.domain.candidate_review import (
    CandidateReviewState,
    ImageAvailability,
    InvalidCandidateReviewError,
    reconcile,
)
from parcel_intel.ports.candidate_inventory_source import CandidateInventorySource
from parcel_intel.ports.candidate_review_source import CandidateReviewSource
from parcel_intel.ports.comparison_availability import ComparisonAvailabilitySource
from parcel_intel.ports.cut_candidate_source import CutCandidateSource
from parcel_intel.ports.errors import (
    CandidateInventoryFileError,
    CandidateReviewFileError,
    ComparisonManifestFileError,
    CutCandidateFileError,
)

_MUNICIPALITY_RE = re.compile(r"[0-9]{5}")

ListingOutcome = Literal["listado", "sin_candidatos", "fallo"]


@dataclass(frozen=True)
class MunicipalReviewListing:
    municipality_code: str
    outcome: ListingOutcome
    state: CandidateReviewState | None = None  # solo con "listado"
    images: Mapping[str, ImageAvailability] = field(default_factory=dict)  # por candidate_id
    has_manifest: bool = False  # solo con "listado"
    unchecked_reviews: int = 0  # revisiones leídas con "sin_candidatos"
    inventory: CandidateInventoryState | None = None  # "listado" con port de inventario (#288)
    unchecked_codes: int = 0  # códigos leídos con "sin_candidatos"
    error: str | None = None  # solo con "fallo"

    @property
    def failed(self) -> bool:
        """Fallo, o listado con aprobaciones caducadas, revisiones huérfanas, códigos
        sobre tramos no aprobados o códigos huérfanos."""
        if self.outcome == "fallo":
            return True
        if self.inventory is not None and not self.inventory.is_consistent():
            return True
        return self.state is not None and not self.state.is_current()


class ListCandidateReviewsUseCase:
    def __init__(
        self,
        candidates: CutCandidateSource,
        reviews: CandidateReviewSource,
        images: ComparisonAvailabilitySource,
        inventory: CandidateInventorySource | None = None,
    ) -> None:
        self._candidates = candidates
        self._reviews = reviews
        self._images = images
        self._inventory = inventory

    def execute(self, municipality_codes: Sequence[str]) -> tuple[MunicipalReviewListing, ...]:
        return tuple(self._one(code) for code in municipality_codes)

    def _one(self, code: str) -> MunicipalReviewListing:
        if not _MUNICIPALITY_RE.fullmatch(code):
            return MunicipalReviewListing(
                code, "fallo", error="el código de municipio no cumple ^[0-9]{5}$"
            )
        try:
            reviews = self._reviews.reviews(code)
            codes = self._inventory.codes(code) if self._inventory is not None else ()
            report = self._candidates.get_report(code)
            if report is None:
                return MunicipalReviewListing(
                    code,
                    "sin_candidatos",
                    unchecked_reviews=len(reviews),
                    unchecked_codes=len(codes),
                )
            state = reconcile(report, reviews)
            inventory = reconcile_inventory(state, codes) if self._inventory is not None else None
            manifest = self._images.availability(code)
        except (
            CandidateReviewFileError,
            CandidateInventoryFileError,
            InvalidInventoryCodeError,
            CutCandidateFileError,
            ComparisonManifestFileError,
            InvalidCandidateReviewError,
        ) as error:
            return MunicipalReviewListing(code, "fallo", error=str(error))
        images: dict[str, ImageAvailability] = {}
        for item in state.candidates:
            candidate_id = item.candidate.candidate_id
            if manifest is None:
                images[candidate_id] = "sin_manifiesto"
            else:
                images[candidate_id] = manifest.get(candidate_id, "no_en_manifiesto")
        return MunicipalReviewListing(
            code,
            "listado",
            state=state,
            images=images,
            has_manifest=manifest is not None,
            inventory=inventory,
        )
