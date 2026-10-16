from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Norm:
    """Disposición normativa (ley, reglamento...) citada como base de una
    `Rule` (historia 0017)."""

    title: str
    url: str


@dataclass(frozen=True)
class Provision:
    """Artículo o apartado concreto de un `Norm`, con su propia vigencia y,
    si difiere de la del `Norm`, su propia URL."""

    norm: Norm
    article: str
    in_force_since: date
    url: str | None = None  # None = usa la de `norm`, ver `effective_url`


def effective_url(provision: Provision) -> str:
    """`provision.url` si existe, si no la de `provision.norm` — función
    pura, mismo criterio que el resto de `domain/` de no añadir métodos a
    los dataclasses (ninguna entidad del proyecto los tiene)."""
    return provision.url or provision.norm.url
