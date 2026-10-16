from datetime import date

from parcel_intel.domain.norm import Norm, Provision, effective_url

_NORM = Norm(title="Reglamento del Dominio Público Hidráulico", url="https://example.org/norma")


def test_effective_url_usa_la_del_norm_si_la_provision_no_tiene_propia() -> None:
    provision = Provision(norm=_NORM, article="art. 9", in_force_since=date(1986, 4, 30))

    assert effective_url(provision) == "https://example.org/norma"


def test_effective_url_usa_la_propia_si_difiere_de_la_del_norm() -> None:
    provision = Provision(
        norm=_NORM,
        article="art. 9",
        in_force_since=date(1986, 4, 30),
        url="https://example.org/articulo-9-version-vigente",
    )

    assert effective_url(provision) == "https://example.org/articulo-9-version-vigente"
