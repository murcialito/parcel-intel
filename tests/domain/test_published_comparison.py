"""Imágenes de comparación publicables (historia #172, ADR 0049). Datos sintéticos."""

import dataclasses
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from parcel_intel.domain.comparison_image import (
    COMPARISON_POLICY,
    DECLARED_GAPS,
    ComparisonManifest,
    ComparisonWindow,
    DeclaredGap,
    OmittedSlot,
    StretchComparison,
)
from parcel_intel.domain.discrepancy_criterion import CriterionRef
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.provenance import Redistribution
from parcel_intel.domain.published_comparison import (
    GAP_TEXT,
    IMAGE_ALT_TEXT,
    NOT_AVAILABLE_TEXT,
    OMISSION_TEXT,
    SERVED_BY_TEXT,
    ComparisonManifestNotUsableError,
    ComparisonNotPublishableError,
    build_published_comparison,
    check_comparison_manifest,
)
from tests.fixtures.candidatos_publicar import generar as publicar
from tests.fixtures.candidatos_revision import generar

INE = "28043"
APROBADO = generar.candidates()["aprobado"]


def _comparison() -> StretchComparison:
    return publicar.stretch_comparison(APROBADO)


def _with_window(comparison: StretchComparison, **changes: Any) -> StretchComparison:
    window = dataclasses.replace(comparison.windows[0], **changes)
    return dataclasses.replace(comparison, windows=(window, *comparison.windows[1:]))


def _with_image(comparison: StretchComparison, index: int, **changes: Any) -> StretchComparison:
    images = list(comparison.windows[0].images)
    images[index] = dataclasses.replace(images[index], **changes)
    return _with_window(comparison, images=tuple(images))


def _manifest(**changes: Any) -> ComparisonManifest:
    base = publicar.manifest_for([APROBADO])
    return dataclasses.replace(base, **changes)


# --- check_comparison_manifest ---------------------------------------------------------


def test_notas_redactadas() -> None:
    notes = check_comparison_manifest(_manifest(), INE)
    assert notes.policy == "imagenes_comparacion v1"
    assert notes.served_by == SERVED_BY_TEXT
    assert notes.not_available == NOT_AVAILABLE_TEXT == "Imagen no disponible"
    ((gap, expected),) = zip(notes.gaps, DECLARED_GAPS, strict=True)
    assert (gap.from_year, gap.to_year) == (1957, 1997)
    assert gap.text == GAP_TEXT.format(desde=1957, hasta=1997, motivo=expected.reason)
    assert gap.text.startswith("De 1957 a 1997: sin ortofoto") and gap.text.endswith(".")


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"municipality_code": "28013"}, "es del municipio 28013"),
        ({"policy": CriterionRef("imagenes_comparacion", 2)}, "otra versión de la política"),
        ({"policy": CriterionRef("otra", 1)}, "otra versión de la política"),
        ({"gaps": ()}, "otros huecos"),
        ({"gaps": (DeclaredGap(1957, 1998, "x"),)}, "otros huecos"),
    ],
)
def test_manifiesto_no_utilizable(changes: dict[str, object], fragment: str) -> None:
    with pytest.raises(ComparisonManifestNotUsableError) as error:
        check_comparison_manifest(_manifest(**changes), INE)
    assert fragment in error.value.reason
    assert COMPARISON_POLICY.version == 1


def test_manifiesto_con_ids_repetidos_no_se_construye() -> None:
    comparison = _comparison()
    with pytest.raises(ValueError, match="repetidos"):
        ComparisonManifest(INE, COMPARISON_POLICY, DECLARED_GAPS, (comparison, comparison))


# --- build_published_comparison --------------------------------------------------------


def test_publica_imagenes_en_orden_cronologico_con_textos() -> None:
    comparison = _comparison()
    # El orden de entrada no manda: se publica en el de COMPARISON_SLOTS.
    reversed_images = tuple(reversed(comparison.windows[0].images))
    published = build_published_comparison(
        APROBADO.stretch, _with_window(comparison, images=reversed_images)
    )
    (window,) = published.windows
    assert (window.width_px, window.height_px) == (640, 640)
    assert window.stretch_px == (((120.0, 320.0), (520.0, 320.0)),)
    assert [i.slot for i in window.images] == ["1997-2003", "2006-2011", "2014-2020", "reciente"]
    recent = window.images[-1]
    assert recent.alt_text == "Ortofoto de 2023 con el tramo a verificar marcado"
    assert recent.attribution == "Obra derivada de PNOA 2023 CC-BY 4.0 scne.es"
    assert recent.url == comparison.windows[0].images[-1].provenance.url
    assert recent.retrieved_at == date(2026, 11, 27)
    assert [(o.slot, o.text) for o in window.omitted] == [("1956-1957", OMISSION_TEXT)]
    assert len(published.images()) == 4


def test_tramo_de_dos_piezas_lleva_todas_las_partes() -> None:
    propuesto = generar.candidates()["propuesto"]
    published = build_published_comparison(
        propuesto.stretch, publicar.stretch_comparison(propuesto)
    )
    (window,) = published.windows
    assert window.stretch_px == (
        ((130.0, 320.0), (330.0, 320.0)),
        ((390.0, 320.0), (510.0, 320.0)),
    )


def test_varias_ventanas_en_el_orden_de_comparison_windows() -> None:
    long_one = generar.make_candidate(
        "via_pecuaria_oficial",
        "VP-LARGO",
        (((460000.0, 4438500.0), (460600.0, 4438500.0)),),
        0.8,
        0.5,
    )
    published = build_published_comparison(long_one.stretch, publicar.stretch_comparison(long_one))
    assert [w.width_px for w in published.windows] == [1024, 576]
    assert published.windows[1].stretch_px == (((-728.0, 288.0), (472.0, 288.0)),)


def test_una_ventana_sin_imagenes_se_publica_si_otra_tiene() -> None:
    long_one = generar.make_candidate(
        "via_pecuaria_oficial",
        "VP-LARGO",
        (((460000.0, 4438500.0), (460600.0, 4438500.0)),),
        0.8,
        0.5,
    )
    comparison = publicar.stretch_comparison(long_one)
    first = comparison.windows[0]
    empty = dataclasses.replace(
        first,
        images=(),
        omitted=tuple(
            OmittedSlot(slot, "sin_cobertura", (), None)
            for slot in ("1956-1957", "1997-2003", "2006-2011", "2014-2020", "reciente")
        ),
    )
    comparison = dataclasses.replace(comparison, windows=(empty, comparison.windows[1]))
    published = build_published_comparison(long_one.stretch, comparison)
    assert published.windows[0].images == ()
    assert len(published.windows[0].omitted) == 5
    assert len(published.windows[1].images) == 4


def _all_omitted(comparison: StretchComparison) -> StretchComparison:
    slots = ("1956-1957", "1997-2003", "2006-2011", "2014-2020", "reciente")
    return _with_window(
        comparison,
        images=(),
        omitted=tuple(OmittedSlot(slot, "sin_cobertura", (), None) for slot in slots),
    )


def _moved(dx: float, dy: float) -> MultiLineGeometry:
    lines = tuple(tuple((x + dx, y + dy) for x, y in line) for line in APROBADO.stretch.lines)
    return MultiLineGeometry(lines, 25830)


def _omitted_extra(comparison: StretchComparison) -> StretchComparison:
    window = comparison.windows[0]
    extra = OmittedSlot("reciente", "sin_cobertura", (2023,), None)
    return _with_window(comparison, omitted=(*window.omitted, extra))


def _failed(comparison: StretchComparison) -> StretchComparison:
    omitted = OmittedSlot("1956-1957", "fallo", ("AMS_1956-1957",), "TimeoutError")
    return _with_window(comparison, omitted=(omitted,))


def _too_long(comparison: StretchComparison) -> StretchComparison:
    return dataclasses.replace(comparison, status="tramo_demasiado_largo", windows=())


def _wrong_window(comparison: StretchComparison) -> StretchComparison:
    window = comparison.windows[0].window
    return _with_window(comparison, window=dataclasses.replace(window, width_px=641))


def _wrong_pixels(comparison: StretchComparison) -> StretchComparison:
    return _with_window(comparison, stretch_px=(((120.0, 320.0), (520.1, 320.0)),))


def _extra_window(comparison: StretchComparison) -> StretchComparison:
    return dataclasses.replace(comparison, windows=comparison.windows * 2)


@pytest.mark.parametrize(
    ("stretch", "change", "fragment"),
    [
        (APROBADO.stretch, _too_long, "tramo demasiado largo"),
        (APROBADO.stretch, _all_omitted, "sin imágenes de comparación"),
        (_moved(0, 1), lambda c: c, "no corresponde al tramo actual"),
        (_moved(0.2, 0), lambda c: c, "no corresponde al tramo actual"),
        (APROBADO.stretch, _wrong_window, "no corresponde al tramo actual"),
        (APROBADO.stretch, _wrong_pixels, "no corresponde al tramo actual"),
        (APROBADO.stretch, _extra_window, "no corresponde al tramo actual"),
        (MultiLineGeometry((), 25830), lambda c: c, "no corresponde al tramo actual"),
        (APROBADO.stretch, _omitted_extra, "cinco franjas"),
        (APROBADO.stretch, _failed, "fallo de descarga"),
        (APROBADO.stretch, lambda c: _with_image(c, 3, vintage=2020), "otra franja"),
        (APROBADO.stretch, lambda c: _with_image(c, 3, period="2020"), "periodo"),
        (APROBADO.stretch, lambda c: _with_image(c, 3, resolution_m=0.5), "resolución"),
        (APROBADO.stretch, lambda c: _with_image(c, 3, attribution="x"), "atribución"),
    ],
)
def test_no_publicable(stretch: MultiLineGeometry, change: Any, fragment: str) -> None:
    with pytest.raises(ComparisonNotPublishableError) as error:
        build_published_comparison(stretch, change(_comparison()))
    assert fragment in error.value.reason


def test_ausente() -> None:
    with pytest.raises(ComparisonNotPublishableError) as error:
        build_published_comparison(APROBADO.stretch, None)
    assert error.value.reason == (
        "no está en el manifiesto de imágenes de comparación; ejecuta imagenes-comparacion"
    )


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("source", "pnoa-ma", "WMS histórico"),
        ("license", "CC BY-SA 4.0", "licencia"),
        ("license", None, "licencia"),
        ("redistribution", Redistribution.INTERNAL_ONLY, "publicable"),
    ],
)
def test_procedencia_de_la_imagen(field: str, value: Any, fragment: str) -> None:
    comparison = _comparison()
    image = comparison.windows[0].images[0]
    changes: dict[str, Any] = {field: value}
    provenance = dataclasses.replace(image.provenance, **changes)
    with pytest.raises(ComparisonNotPublishableError) as error:
        build_published_comparison(
            APROBADO.stretch, _with_image(comparison, 0, provenance=provenance)
        )
    assert fragment in error.value.reason


def test_las_ventanas_del_dominio_no_cambian() -> None:
    """La comparación sin tocar casa exactamente (guarda de los casos anteriores)."""
    comparison = _comparison()
    assert isinstance(comparison.windows[0], ComparisonWindow)
    build_published_comparison(APROBADO.stretch, comparison)


def test_los_textos_son_los_del_adr_0049() -> None:
    """Los rótulos publicados son literales del ADR 0049 (sección «a revisar»): si cambian en
    un sitio y no en el otro, este test falla."""
    adr = next(
        (Path(__file__).resolve().parents[2] / "docs" / "adr").glob("0049-*.md")
    ).read_text(encoding="utf-8")
    for text in (
        OMISSION_TEXT,
        NOT_AVAILABLE_TEXT,
        SERVED_BY_TEXT,
        IMAGE_ALT_TEXT.replace("{periodo}", "<periodo>"),
    ):
        assert f"«{text}»" in adr, text
