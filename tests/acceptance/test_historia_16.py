"""Historia #16: texto público y presentación de discrepancias como indicios a verificar.

Discrepancias construidas a mano (sin red); la evidencia de Catastro y la de una
fuente sin licencia verificada se prueban con fuentes sintéticas.
"""

import dataclasses
from datetime import date
from types import MappingProxyType
from typing import get_args

import pytest

from parcel_intel.domain import public_card
from parcel_intel.domain.discrepancy import (
    Discrepancy,
    DiscrepancyKind,
    Measurement,
    SourceRef,
    TrailRef,
)
from parcel_intel.domain.discrepancy_criterion import CRITERION, SourceKind
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.public_card import (
    BANNED_WORDS,
    HIGH_CONFIDENCE_MIN,
    KIND_LABEL,
    MEDIUM_CONFIDENCE_MIN,
    OMISSION_NOTICE,
    TEMPLATES,
    VALIDATION,
    WARNING,
    banned_words_in,
    build_card,
    compute_text_hash,
)

pytestmark = pytest.mark.acceptance

_DATA_DATE: dict[SourceKind, date | None] = {
    "via_pecuaria_oficial": date(2014, 11, 29),
    "catastro_vt": date(2026, 6, 1),
    "ign_red_transporte": date(2025, 3, 15),
    "planimetria_historica": date(1875, 1, 1),
    "mtn50_historico": date(1881, 1, 1),
}


def _source(kind: SourceKind, license: str | None = "CC BY 4.0") -> SourceRef:
    return SourceRef(
        kind=kind,
        provenance=Provenance(
            source=f"fuente sintética {kind}",
            url=f"https://example.invalid/{kind}",
            retrieved_at=date(2026, 11, 25),
            license=license,
        ),
        data_date=_DATA_DATE[kind],
    )


def _discrepancy(
    kind: DiscrepancyKind = "DESPLAZAMIENTO",
    *,
    a: SourceKind = "via_pecuaria_oficial",
    b: SourceKind = "planimetria_historica",
    confidence: float = 0.6,
    license_a: str | None = "CC BY 4.0",
    license_b: str | None = "CC BY 4.0",
) -> Discrepancy:
    evidence = {
        "AUSENTE_EN_FUENTE": (Measurement("radio_busqueda_m", 30.0, "m"),),
        "DESPLAZAMIENTO": (Measurement("desplazamiento_mediano_m", 42.4, "m"),),
        "SOLAPE": (Measurement("fraccion_solapada", 0.5, "fraccion"),),
    }[kind]
    subject = TrailRef("TRAMO-1", _source(a, license_a))
    return Discrepancy(
        kind=kind,
        zone=MultiLineGeometry(lines=(((0.0, 0.0), (100.0, 0.0)),), srid=25830),
        subject=subject,
        counterpart_source=_source(b, license_b),
        counterpart_trails=(),
        confidence=confidence,
        evidence=evidence,
        criterion=CRITERION,
    )


def test_ca1_cada_tipo_tiene_plantilla_aprobada() -> None:
    """CA1. Dado cada tipo de discrepancia definido en #14, cuando se pide su etiqueta y su
    texto, entonces existe una plantilla aprobada para ese tipo y falla un test si se añade
    un tipo sin plantilla."""
    kinds = set(get_args(DiscrepancyKind))
    assert kinds == set(TEMPLATES) == set(KIND_LABEL)
    for kind in kinds:
        card = build_card(_discrepancy(kind))
        assert card.label == KIND_LABEL[kind]
        assert card.text.startswith("Indicio a verificar:")


def test_ca2_ficha_con_confianza_en_palabras_fuentes_y_criterio() -> None:
    """CA2. Dado una discrepancia con confianza y evidencia, cuando se genera su ficha,
    entonces contiene la confianza como nivel en palabras (baja / media / alta; sin valor
    numérico), la lista de fuentes con fecha y licencia/atribución, y la regla o criterio
    que la produjo, junto al texto (no en otra vista)."""
    card = build_card(_discrepancy(confidence=0.6))

    assert card.confidence_level == "alta"
    assert "0.6" not in card.as_text() and "0,6" not in card.as_text()
    assert [s.role for s in card.sources] == ["sujeto", "contraparte"]
    subject = card.sources[0]
    assert subject.data_year == 2014
    assert subject.retrieved_at == date(2026, 11, 25)
    assert subject.license == "CC BY 4.0"
    assert "CC BY 4.0 Comunidad de Madrid" in subject.attribution
    assert card.criterion == "discrepancia_trazados v1"
    assert card.criterion_description
    assert card.text


def test_ca3_toda_ficha_lleva_el_aviso_fijo() -> None:
    """CA3. Dada cualquier ficha generada, cuando se inspecciona el texto, entonces incluye
    el aviso fijo aprobado de que es un indicio a verificar y no un dictamen."""
    assert WARNING == (
        "Esto no es un dictamen ni afirma que haya ninguna irregularidad. Es un indicio "
        "automático, con la confianza indicada, que debe contrastarse con la administración "
        "competente."
    )
    for kind in get_args(DiscrepancyKind):
        for publication in (True, False):
            card = build_card(_discrepancy(kind), for_publication=publication)
            assert WARNING in card.as_text()


def test_ca4_ninguna_palabra_vetada() -> None:
    """CA4. Dado el conjunto de plantillas y fichas generadas, cuando se buscan palabras
    vetadas (ilegal, ilegalidad, usurpación, usurpado, delito, invasión, apropiación,
    propietario, dueño, titular), entonces no aparece ninguna."""
    assert BANNED_WORDS == (
        "ilegal",
        "ilegalidad",
        "usurpación",
        "usurpado",
        "delito",
        "invasión",
        "apropiación",
        "propietario",
        "dueño",
        "titular",
    )
    texts = [*TEMPLATES.values(), *KIND_LABEL.values(), WARNING]
    for kind in get_args(DiscrepancyKind):
        for a in get_args(SourceKind):
            texts.append(build_card(_discrepancy(kind, a=a)).as_text())
            texts.append(build_card(_discrepancy(kind, a=a), for_publication=False).as_text())
    for text in texts:
        assert banned_words_in(text) == ()


def test_ca5_evidencia_de_catastro_solo_derivada() -> None:
    """CA5. Dada una discrepancia con evidencia procedente de Catastro, cuando se genera la
    ficha, entonces solo aparece el trazado derivado, sin rotularlo "cartografía catastral"
    ni incluir el dato original."""
    for catastro_side in ("sujeto", "contraparte"):
        if catastro_side == "sujeto":
            discrepancy = _discrepancy(a="catastro_vt", b="via_pecuaria_oficial")
        else:
            discrepancy = _discrepancy(a="via_pecuaria_oficial", b="catastro_vt")
        card = build_card(discrepancy)
        text = card.as_text().casefold()

        assert "cartografía catastral" not in text and "cartografia catastral" not in text
        assert "derivado" in text
        assert "TRAMO-1" not in card.as_text()  # sin identificadores del dato original
        assert not any(
            field.name in {"zone", "geometry", "trail_id"} for field in dataclasses.fields(card)
        )


def test_ca6_fuente_sin_licencia_verificada_se_omite(monkeypatch: pytest.MonkeyPatch) -> None:
    """CA6. Dada una discrepancia cuya fuente carece de licencia de redistribución
    verificada, cuando se genera la ficha para publicación, entonces esa evidencia se omite
    y la ficha lo indica, sin inventar sustituto."""
    # Desde #94 (ADR 0044) la red de transporte del IGN está verificada (#24), así que ya
    # no sirve de ejemplo real: se marca como no verificada solo en este test.
    policy = dict(public_card.SOURCE_POLICY)
    policy["ign_red_transporte"] = dataclasses.replace(
        policy["ign_red_transporte"], redistribution_verified=False, attribution=""
    )
    monkeypatch.setattr(public_card, "SOURCE_POLICY", MappingProxyType(policy))
    card = build_card(_discrepancy(a="ign_red_transporte", b="via_pecuaria_oficial"))
    assert [s.role for s in card.sources] == ["contraparte"]
    assert card.omission_notice == OMISSION_NOTICE
    assert "red de transporte" not in card.as_text()

    # Sin licencia en la procedencia tampoco hay verificación.
    sin_licencia = build_card(_discrepancy(license_b=None))
    assert [s.role for s in sin_licencia.sources] == ["sujeto"]
    assert sin_licencia.omission_notice == OMISSION_NOTICE

    # Para uso interno no se omite nada.
    interna = build_card(
        _discrepancy(a="ign_red_transporte", b="via_pecuaria_oficial"), for_publication=False
    )
    assert len(interna.sources) == 2
    assert interna.omission_notice is None

    # Con todo verificado no hay aviso de omisión.
    assert build_card(_discrepancy()).omission_notice is None


def test_ca7_cambiar_el_texto_exige_nueva_validacion() -> None:
    """CA7. Dadas las plantillas, cuando cambia su texto sin actualizar la marca de
    validación (fecha y enlace al comentario de aprobación), entonces un test falla. La
    marca inicial es 2026-11-26 y el enlace del comentario citado arriba."""
    assert VALIDATION.validated_by_founder == date(2026, 11, 26)
    assert VALIDATION.validation_url == (
        "https://github.com/murcialito/paso-comun/issues/16#issuecomment-7186000359"
    )
    assert compute_text_hash() == VALIDATION.text_hash, (
        "Cambió el texto público (plantillas, etiquetas o aviso): hace falta nueva "
        "validación del fundador y actualizar VALIDATION (fecha, enlace y hash)."
    )


def test_ca8_umbrales_de_confianza_en_un_unico_sitio() -> None:
    """CA8. Dado un valor numérico de confianza interno, cuando se genera la ficha, entonces
    se traduce a un nivel en palabras con umbrales definidos en un único sitio y probados
    en sus límites."""
    cases = [
        (0.0, "baja"),
        (MEDIUM_CONFIDENCE_MIN - 0.001, "baja"),
        (MEDIUM_CONFIDENCE_MIN, "media"),
        (HIGH_CONFIDENCE_MIN - 0.001, "media"),
        (HIGH_CONFIDENCE_MIN, "alta"),
        (1.0, "alta"),
    ]
    for value, level in cases:
        assert build_card(_discrepancy(confidence=value)).confidence_level == level
