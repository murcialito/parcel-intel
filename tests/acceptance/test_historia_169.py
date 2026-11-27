"""Aceptación de la historia #169: ficha pública del candidato a corte."""

import dataclasses
import re
from datetime import date

import pytest

from parcel_intel.domain.cut_candidate import CutCandidate
from parcel_intel.domain.discrepancy import SourceRef, TrailRef
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.public_candidate_card import (
    CANDIDATE_LABEL,
    CANDIDATE_LAYER_NAME,
    CANDIDATE_VALIDATION,
    CATASTRO_WARNING_ADDENDUM,
    MissingCatastroDateError,
    build_candidate_card,
    compute_candidate_text_hash,
)
from parcel_intel.domain.public_card import (
    BANNED_WORDS,
    CATASTRO_ATTRIBUTION,
    HIGH_CONFIDENCE_MIN,
    MEDIUM_CONFIDENCE_MIN,
    OMISSION_NOTICE,
    SOURCE_POLICY,
    WARNING,
    banned_words_in,
)
from tests.domain.test_public_candidate_card import _catastro, candidate

pytestmark = pytest.mark.acceptance

_CATASTRAL_REF = re.compile(r"\b(?=[0-9A-Z]*\d)[0-9A-Z]{14}(?:[0-9A-Z]{6})?\b")


def _con_catastro() -> CutCandidate:
    return candidate(fraction=0.5, length=120.4, provenance=(_catastro(26),))


def test_ca1_ficha_con_la_senal_de_catastro() -> None:
    """CA1. Dado un candidato con la señal `parcela_no_camino`, cuando se construye la
    ficha, entonces el texto es la plantilla con Catastro con longitud (`longitud_tramo_m`,
    en metros enteros), fuente y año del trazado del sujeto, fecha de consulta y porcentaje
    (`support_fraction` × 100, redondeado a entero) sustituidos, y el aviso es `WARNING`
    más el añadido de Catastro con la misma fecha."""
    card = build_candidate_card(_con_catastro())
    assert card.text == (
        "Indicio a verificar: este tramo de 120 m figura como "
        f"{SOURCE_POLICY['via_pecuaria_oficial'].public_label}, 2019, y no aparece en el "
        "camino actual del IGN. Al cruzarlo con datos de la Dirección General del Catastro "
        "(consultados el 26/11/2026), el 50 % del tramo cae dentro de parcelas que no "
        "figuran como vía de comunicación. Conviene comprobarlo sobre el terreno."
    )
    assert card.warning == f"{WARNING} {CATASTRO_WARNING_ADDENDUM.format(fecha='26/11/2026')}"
    assert card.label == CANDIDATE_LABEL
    assert card.layer_name == CANDIDATE_LAYER_NAME


def test_ca2_ficha_sin_la_senal_de_catastro() -> None:
    """CA2. Dado un candidato sin la señal de Catastro, cuando se construye la ficha,
    entonces el texto es la plantilla corta (primera y última frase) y el aviso es solo
    `WARNING`, sin el añadido de Catastro ni mención a Catastro en ningún texto."""
    card = build_candidate_card(candidate(with_signal=False))
    assert card.text.startswith("Indicio a verificar: este tramo de 120 m figura como")
    assert card.text.endswith(
        "no aparece en el camino actual del IGN. Conviene comprobarlo sobre el terreno."
    )
    assert card.warning == WARNING
    assert "catastro" not in card.as_text().casefold()


def test_ca3_cambiar_el_texto_exige_nueva_validacion() -> None:
    """CA3. Dado el texto de la ficha, cuando cambia cualquier etiqueta, plantilla, aviso
    añadido o nombre de capa sin actualizar `VALIDATION` (nueva constante en el módulo,
    con la URL del comentario del fundador y la fecha 2026-11-27), entonces un test
    falla."""
    assert CANDIDATE_VALIDATION.validated_by_founder == date(2026, 11, 27)
    assert CANDIDATE_VALIDATION.validation_url == (
        "https://github.com/murcialito/paso-comun/issues/103#issuecomment-7214693909"
    )
    assert compute_candidate_text_hash() == CANDIDATE_VALIDATION.text_hash, (
        "Cambió el texto público de la ficha del candidato: hace falta nueva validación "
        "del fundador y actualizar CANDIDATE_VALIDATION (fecha, enlace y hash)."
    )


def test_ca4_sin_palabras_vetadas_ni_referencias_ni_numero_de_parcelas() -> None:
    """CA4. Dado cualquier candidato, cuando se construye la ficha, entonces ninguna
    cadena visible (`strings()`) contiene palabras de `BANNED_WORDS` (por
    `banned_words_in`), ni un patrón de referencia catastral (14 o 20 caracteres
    alfanuméricos de formato catastral), ni el número de parcelas."""
    for cand in (_con_catastro(), candidate(with_signal=False)):
        for text in build_candidate_card(cand).strings():
            assert banned_words_in(text) == (), (text, BANNED_WORDS)
            assert _CATASTRAL_REF.search(text) is None
            assert "parcelas)" not in text and not re.search(r"\d+ parcelas", text)
        assert not any(
            field.name in {"stretch", "zone", "geometry", "trail_id", "parcels"}
            for field in dataclasses.fields(build_candidate_card(cand))
        )


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (0.0, "baja"),
        (MEDIUM_CONFIDENCE_MIN - 0.001, "baja"),
        (MEDIUM_CONFIDENCE_MIN, "media"),
        (HIGH_CONFIDENCE_MIN - 0.001, "media"),
        (HIGH_CONFIDENCE_MIN, "alta"),
        (1.0, "alta"),
    ],
)
def test_ca5_confianza_en_palabras(confidence: float, expected: str) -> None:
    """CA5. Dado un candidato, cuando se construye la ficha, entonces la confianza sale
    en palabras (`baja`/`media`/`alta`) con los umbrales de `confidence_level` de #16
    aplicados a `confidence`, y la ficha no expone el número."""
    card = build_candidate_card(candidate(confidence=confidence, provenance=(_catastro(26),)))
    assert card.confidence_level == expected
    assert not any(isinstance(getattr(card, f.name), float) for f in dataclasses.fields(card))
    assert card.confidence_level in card.as_text()


def test_ca6_fuentes_con_catastro() -> None:
    """CA6. Dado un candidato con la señal de Catastro, entonces `sources` incluye el
    trazado del sujeto (etiqueta, procedencia y atribución de `SOURCE_POLICY`) y una
    fuente «Dirección General del Catastro» con `CATASTRO_ATTRIBUTION`, la fecha de
    consulta y su licencia. No incluye geometría ni identificadores de trazado ni de
    parcela."""
    card = build_candidate_card(_con_catastro())
    subject, catastro = card.sources
    policy = SOURCE_POLICY["via_pecuaria_oficial"]
    assert (subject.label, subject.attribution) == (policy.public_label, policy.attribution)
    assert subject.source == "vp" and subject.url == "https://example.invalid/vp"
    assert catastro.label == "Dirección General del Catastro"
    assert catastro.attribution == CATASTRO_ATTRIBUTION
    assert catastro.retrieved_at == date(2026, 11, 26)
    assert catastro.license == "INSPIRE v1.0"
    assert "VP-1" not in card.as_text()
    assert not any(f.name in {"trail_id", "stretch"} for f in dataclasses.fields(catastro))


def test_ca7_sin_fecha_de_catastro_se_lanza_error() -> None:
    """CA7. Dado un candidato con la señal de Catastro cuya procedencia no tiene fecha de
    consulta (ninguna entrada de Catastro en `provenance`), cuando se construye la ficha,
    entonces se lanza un error explícito (excepción de dominio) y no se produce ficha.
    Con varias entradas, la fecha es la más reciente."""
    with pytest.raises(MissingCatastroDateError):
        build_candidate_card(candidate(provenance=()))
    card = build_candidate_card(candidate(provenance=(_catastro(20), _catastro(26), _catastro(22))))
    assert "consultados el 26/11/2026" in card.text


def test_ca8_fuente_sin_licencia_se_omite() -> None:
    """CA8. Dado un sujeto cuya fuente no tiene licencia de redistribución verificada
    (`_is_publishable` de #16), cuando se construye la ficha para publicación, entonces la
    fuente se rotula «una fuente cuya evidencia no se publica» y se omite de `sources`,
    con el `omission_notice` de #16, igual que en `build_card`."""
    base = _con_catastro()
    source = SourceRef(
        "via_pecuaria_oficial",
        Provenance("vp", "https://example.invalid/vp", date(2026, 11, 26), None),
        date(2019, 1, 1),
    )
    card = build_candidate_card(dataclasses.replace(base, subject=TrailRef("VP-1", source)))
    assert "una fuente cuya evidencia no se publica, 2019" in card.text
    assert [s.label for s in card.sources] == ["Dirección General del Catastro"]
    assert card.omission_notice == OMISSION_NOTICE
    assert "vía pecuaria" not in card.as_text().casefold()


def test_ca9_determinista() -> None:
    """CA9. Dado el mismo candidato, cuando se construye la ficha dos veces, entonces el
    resultado es idéntico (función pura, sin LLM, sin red, sin fecha del reloj)."""
    cand = _con_catastro()
    assert build_candidate_card(cand) == build_candidate_card(cand)
