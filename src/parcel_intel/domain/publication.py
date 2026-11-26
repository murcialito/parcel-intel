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
class PublishableLayer:
    """Capa lista para publicar. Falla al construirse si algún elemento no es `PUBLIC`."""

    name: str
    items: tuple[HasProvenance, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))
        for item in self.items:
            if item.provenance.redistribution is not Redistribution.PUBLIC:
                raise NotRedistributableError(self.name, item.provenance)
