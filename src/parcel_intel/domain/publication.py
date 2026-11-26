"""Única puerta hacia una serialización pública: solo entra lo que la licencia permite publicar."""

from dataclasses import dataclass
from typing import Protocol

from parcel_intel.domain.provenance import Provenance, Redistribution


class HasProvenance(Protocol):
    @property
    def provenance(self) -> Provenance: ...


class NotRedistributableError(Exception):
    def __init__(self, layer_name: str, provenance: Provenance) -> None:
        self.layer_name = layer_name
        self.provenance = provenance
        super().__init__(
            f"la capa '{layer_name}' no es publicable: un elemento procede de "
            f"'{provenance.source}' ({provenance.url}), de solo uso interno"
        )


@dataclass(frozen=True)
class PublishableLayer[T: HasProvenance]:
    """Capa lista para publicar. Falla al construirse si algún elemento, o la
    procedencia de la capa si se da, no es `PUBLIC` (ADR 0028 y #84).

    `layer_provenance` es la procedencia de la colección: con ella, una capa
    vacía cuya procedencia es interna tampoco pasa la puerta."""

    name: str
    items: tuple[T, ...]
    layer_provenance: Provenance | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))
        if (
            self.layer_provenance is not None
            and self.layer_provenance.redistribution is not Redistribution.PUBLIC
        ):
            raise NotRedistributableError(self.name, self.layer_provenance)
        for item in self.items:
            if item.provenance.redistribution is not Redistribution.PUBLIC:
                raise NotRedistributableError(self.name, item.provenance)
