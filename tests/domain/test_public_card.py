from datetime import date

import pytest

from parcel_intel.domain.discrepancy import (
    Discrepancy,
    Measurement,
    SourceRef,
    TrailRef,
)
from parcel_intel.domain.discrepancy_criterion import CRITERION, SourceKind
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.public_card import (
    CATASTRO_ATTRIBUTION,
    SOURCE_POLICY,
    UNKNOWN_YEAR,
    banned_words_in,
    build_card,
    confidence_level,
)
from parcel_intel.domain.published_layers import PUBLISHED_LAYERS


def _source(kind: SourceKind, data_date: date | None) -> SourceRef:
    return SourceRef(
        kind=kind,
        provenance=Provenance("s", "https://example.invalid", date(2026, 11, 25), "CC BY 4.0"),
        data_date=data_date,
    )


def _discrepancy(kind: str, evidence: tuple[Measurement, ...], year: date | None) -> Discrepancy:
    return Discrepancy(
        kind=kind,  # type: ignore[arg-type]
        zone=MultiLineGeometry(lines=(((0.0, 0.0), (1.0, 0.0)),), srid=25830),
        subject=TrailRef("T", _source("via_pecuaria_oficial", year)),
        counterpart_source=_source("mtn50_historico", date(1881, 1, 1)),
        counterpart_trails=(),
        confidence=0.4,
        evidence=evidence,
        criterion=CRITERION,
    )


def test_texto_ausente_cita_fuentes_y_anios() -> None:
    card = build_card(_discrepancy("AUSENTE_EN_FUENTE", (), date(2014, 1, 1)))
    assert card.text == (
        "Indicio a verificar: según vías pecuarias (IDEM), 2014 existe un trazado en este "
        "tramo que no aparece en MTN50 histórico del IGN, 1881."
    )


def test_texto_desplazamiento_redondea_metros() -> None:
    card = build_card(
        _discrepancy("DESPLAZAMIENTO", (Measurement("desplazamiento_mediano_m", 42.6, "m"),), None)
    )
    assert "difieren unos 43 m" in card.text


def test_fecha_no_declarada() -> None:
    card = build_card(_discrepancy("AUSENTE_EN_FUENTE", (), None))
    assert UNKNOWN_YEAR in card.text
    assert card.sources[0].data_year is None


def test_confianza_fuera_de_rango_falla() -> None:
    for value in (-0.1, 1.1):
        with pytest.raises(ValueError):
            confidence_level(value)


def test_banned_words_ignora_tildes_y_mayusculas() -> None:
    assert banned_words_in("USURPACION y titularidad") == ("usurpación", "titular")
    assert banned_words_in("Indicio a verificar") == ()


def test_la_red_del_ign_esta_verificada_con_la_atribucion_de_su_capa() -> None:
    """#94 (ADR 0044 §5): licencia confirmada en #24; misma atribución que la capa publicada.
    Se fija con un test y no con un import, para no acoplar los dos módulos."""
    policy = SOURCE_POLICY["ign_red_transporte"]
    assert policy.redistribution_verified
    assert policy.attribution == PUBLISHED_LAYERS["camino_actual"].attribution


def test_la_atribucion_de_catastro_cumple_el_adr_0041() -> None:
    text = SOURCE_POLICY["catastro_vt"].attribution
    assert text == CATASTRO_ATTRIBUTION
    assert "Dirección General del Catastro" in text
    assert "fecha" in text and "carece de fehaciencia" in text
    assert "puede haber cambiado" in text
    lowered = text.casefold()
    assert "cartografía catastral" not in lowered and "información catastral" not in lowered
    assert banned_words_in(text) == ()
