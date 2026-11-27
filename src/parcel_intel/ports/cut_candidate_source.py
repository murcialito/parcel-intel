from typing import Protocol

from parcel_intel.domain.cut_candidate import MunicipalCutCandidateReport


class CutCandidateSource(Protocol):
    """Capacidad: leer el informe de candidatos a corte de un municipio (#128).

    `None` es «sin capas» (no hay informe escrito); un informe presente, aunque
    sin candidatos, es «municipio evaluable» (ADR 0039 §9). Un informe ilegible
    lanza `CutCandidateFileError`: un fichero roto no es «sin capas»."""

    def get_report(self, municipality_code: str) -> MunicipalCutCandidateReport | None: ...
