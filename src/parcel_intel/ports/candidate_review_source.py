from typing import Protocol

from parcel_intel.domain.candidate_review import CandidateReview


class CandidateReviewSource(Protocol):
    """Capacidad: leer las revisiones humanas de los candidatos de un municipio (#168).

    Sin fichero de revisión devuelve `()`: todo candidato queda `propuesto`. Un
    fichero que no cumple el formato lanza `CandidateReviewFileError` (nunca `()`),
    y el mensaje no repite el valor rechazado."""

    def reviews(self, municipality_code: str) -> tuple[CandidateReview, ...]: ...
