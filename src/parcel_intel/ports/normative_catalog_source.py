from typing import Protocol

from parcel_intel.domain.normative_citation import NormativeCatalog


class NormativeCatalogSource(Protocol):
    """Capacidad: leer el catálogo cerrado de citas normativas (#187, ADR 0060).

    Un fichero ausente o que no cumple el formato lanza `NormativeCatalogFileError`
    (nunca un catálogo vacío: el vacío es un fichero válido sin citas); el mensaje
    no repite el valor rechazado."""

    def catalog(self) -> NormativeCatalog: ...
