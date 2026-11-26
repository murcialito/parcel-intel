"""Historia #126: entidad CutCandidate y método de combinación (dominio).

Todas las geometrías son sintéticas (sin red); el oráculo es el ejemplo trabajado del
ADR 0039 §4.
"""

import dataclasses
import itertools
import math
from datetime import date
from typing import Any

import pytest

from parcel_intel.domain import cut_candidate as cut_candidate_module
from parcel_intel.domain.cut_candidate import (
    CutCandidate,
    MunicipalCutCandidateReport,
    SignalReading,
    SignalRef,
    SignalRunSummary,
    SignalSupport,
    SignalVerdict,
)
from parcel_intel.domain.cut_method import (
    BASE_COUNTERPARTS,
    BASE_KINDS,
    CUT_METHOD,
    GAP_M,
    MIN_LENGTH_M,
    SIGNAL_WEIGHTS,
    ZONE_MATCH_M,
    build_cut_candidates,
    describe_candidate,
    eligible_base_records,
)
from parcel_intel.domain.discrepancy import (
    ComparableTrail,
    Discrepancy,
    DiscrepancyKind,
    SourceRef,
    TrailRef,
    compare_trail,
    trail_samples,
)
from parcel_intel.domain.discrepancy_criterion import CRITERION, SourceKind
from parcel_intel.domain.discrepancy_report import (
    DiscrepancyRecord,
    MunicipalDiscrepancyReport,
    TrailEvidence,
)
from parcel_intel.domain.geometry import Geometry, MultiLineGeometry, TrailShape
from parcel_intel.domain.provenance import Provenance
from parcel_intel.domain.public_card import banned_words_in

pytestmark = pytest.mark.acceptance

PARCELA = SignalRef("parcela_no_camino", 1, "dentro_de_cierre")
VISIBILIDAD = SignalRef("visibilidad_ortofoto", 1, "no_se_distingue")


def _source(kind: SourceKind) -> SourceRef:
    return SourceRef(
        kind=kind,
        provenance=Provenance(kind, f"https://example.invalid/{kind}", date(2026, 11, 26)),
        data_date=date(2014, 1, 1),
    )


def _line(*points: tuple[float, float]) -> MultiLineGeometry:
    return MultiLineGeometry(lines=(tuple(points),), srid=25830)


def _record(
    record_id: str,
    kind: DiscrepancyKind,
    shape: TrailShape,
    zone: TrailShape | None = None,
    trail_id: str = "VP-1",
    a_kind: SourceKind = "via_pecuaria_oficial",
    b_kind: SourceKind = "ign_red_transporte",
    confidence: float = 0.691,
) -> DiscrepancyRecord:
    subject = TrailRef(trail_id, _source(a_kind))
    discrepancy = Discrepancy(
        kind=kind,
        zone=zone if zone is not None else shape,
        subject=subject,
        counterpart_source=_source(b_kind),
        counterpart_trails=(),
        confidence=confidence,
        evidence=(),
        criterion=CRITERION,
    )
    evidence = TrailEvidence(trail_id, a_kind, subject.source.provenance, date(2014, 1, 1), shape)
    return DiscrepancyRecord(record_id, discrepancy, (evidence,), False)


def _report(*records: DiscrepancyRecord, redacted: bool = False) -> MunicipalDiscrepancyReport:
    return MunicipalDiscrepancyReport("28043", "discrepancia_trazados@1", (), records, redacted)


def _reading(
    signal: SignalRef, verdicts: list[SignalVerdict] | tuple[SignalVerdict, ...]
) -> SignalReading:
    return SignalReading(signal, tuple(verdicts), (), ())


def _verdicts(
    n: int, apoya: range | set[int], default: SignalVerdict = "no_apoya"
) -> list[SignalVerdict]:
    return ["apoya" if i in apoya else default for i in range(n)]


def _vp(length: float = 200.0) -> MultiLineGeometry:
    return _line((0.0, 0.0), (length, 0.0))


def _key(trail_id: str = "VP-1") -> tuple[SourceKind, str]:
    return ("via_pecuaria_oficial", trail_id)


def _worked_example() -> tuple[
    MunicipalDiscrepancyReport, dict[tuple[SourceKind, str], list[SignalReading]]
]:
    report = _report(_record("r1", "AUSENTE_EN_FUENTE", _vp()))
    readings = {_key(): [_reading(PARCELA, _verdicts(40, set(range(12, 28))))]}
    return report, readings


def test_ca1_trail_samples_devuelve_tupla_con_el_muestreo_de_siempre() -> None:
    """Dado un trazado en polilínea o franja, cuando se llama a `trail_samples(shape)`, entonces
    devuelve una `tuple[TrailSample, ...]` idéntica (puntos, pesos, partes, extremos) a la que
    producía `_sample_shape`, y los tests existentes de `discrepancy` y su criterio (versión 1)
    pasan sin cambios."""
    samples = trail_samples(_line((0.0, 0.0), (12.0, 0.0)))
    assert isinstance(samples, tuple)
    assert [s.point for s in samples] == [(2.0, 0.0), (6.0, 0.0), (10.0, 0.0)]
    assert [s.weight for s in samples] == [4.0, 4.0, 4.0]
    assert [(s.start, s.end, s.part) for s in samples][-1] == ((8.0, 0.0), (12.0, 0.0), 0)

    # Franja 100 x 20: pseudo-eje desplazado una semianchura media (area/perimetro), peso 0,5.
    strip = Geometry(rings=(((0.0, 0.0), (100.0, 0.0), (100.0, 20.0), (0.0, 20.0)),), srid=25830)
    half = 2000.0 / 240.0
    strip_samples = trail_samples(strip)
    assert math.fsum(s.weight for s in strip_samples) == pytest.approx(120.0)
    assert strip_samples[0].point[1] == pytest.approx(half)
    assert strip_samples[0].weight == pytest.approx(0.5 * 100.0 / 20)

    assert trail_samples(MultiLineGeometry(lines=(), srid=25830)) == ()
    assert CRITERION.version == 1
    # El criterio no cambia: una discrepancia medida sigue dando lo de siempre.
    found = compare_trail(
        ComparableTrail(TrailRef("A", _source("via_pecuaria_oficial")), _vp()),
        _source("ign_red_transporte"),
        [],
    )
    assert found is not None and found.kind == "AUSENTE_EN_FUENTE"


def test_ca2_campos_exactos_y_sin_titularidad() -> None:
    """Dado `cut_candidate.py`, cuando se listan `dataclasses.fields` de `CutCandidate`,
    `SignalRef`, `SignalReading`, `SignalSupport`, `SignalRunSummary` y
    `MunicipalCutCandidateReport`, entonces coinciden exactamente con el ADR §5 y no hay ningún
    campo de titularidad, propietario ni referencia catastral de finca."""
    expected = {
        SignalRef: ["identifier", "version", "condition"],
        SignalReading: ["signal", "verdicts", "evidence", "provenance"],
        SignalSupport: ["signal", "support_fraction", "no_data_fraction", "provenance"],
        CutCandidate: [
            "candidate_id",
            "municipality_code",
            "subject",
            "discrepancy_ids",
            "stretch",
            "conditions",
            "signals",
            "confidence",
            "evidence",
            "method",
        ],
        SignalRunSummary: ["signal", "status", "reason", "provenance"],
        MunicipalCutCandidateReport: [
            "municipality_code",
            "method",
            "discrepancy_criterion_id",
            "base_record_ids",
            "signals",
            "candidates",
        ],
    }
    for cls, names in expected.items():
        assert [f.name for f in dataclasses.fields(cls)] == names
        assert not any(
            word in name for name in names for word in ("titular", "propiet", "owner", "cadastral")
        )
    assert cut_candidate_module.CutCandidate is CutCandidate


def _valid_candidate(**changes: Any) -> CutCandidate:
    report, readings = _worked_example()
    base = build_cut_candidates(report, readings)[0]
    return dataclasses.replace(base, **changes)


def test_ca3_candidato_invalido_lanza_value_error() -> None:
    """Dado un `CutCandidate` con `srid` ≠ 25830, tramo vacío, confianza fuera de [0, 1],
    `conditions` o `discrepancy_ids` vacíos, o una condición sin ninguna señal de esa condición
    en `signals`, cuando se construye, entonces `__post_init__` lanza `ValueError`."""
    _valid_candidate()  # el válido se construye
    good = _valid_candidate().stretch
    bad: list[dict[str, Any]] = [
        {"stretch": MultiLineGeometry(lines=good.lines, srid=4326)},
        {"stretch": MultiLineGeometry(lines=(), srid=25830)},
        {"confidence": 1.5},
        {"confidence": -0.1},
        {"conditions": ()},
        {"discrepancy_ids": ()},
        {"conditions": ("no_se_distingue", "dentro_de_cierre")},  # sin señal de la (i)
        {"signals": ()},
    ]
    for changes in bad:
        with pytest.raises(ValueError):
            _valid_candidate(**changes)


def test_ca4_registros_base_elegibles_e_informe_redactado() -> None:
    """Dado un `MunicipalDiscrepancyReport` con registros `AUSENTE_EN_FUENTE`, `SOLAPE` y
    `DESPLAZAMIENTO` frente a `ign_red_transporte` y frente a otras fuentes B, cuando se llama
    a `eligible_base_records(report)`, entonces devuelve solo los de tipo `BASE_KINDS` cuya
    fuente B está en `BASE_COUNTERPARTS`, ordenados y sin los anejos; y con un informe
    redactado (`redacted=True`) `build_cut_candidates` lanza `ValueError`."""
    shape = _vp()
    records = (
        _record("z-desp", "DESPLAZAMIENTO", shape),
        _record("y-solape", "SOLAPE", shape, trail_id="VP-2"),
        _record("x-otro", "AUSENTE_EN_FUENTE", shape, b_kind="catastro_vt"),
        _record("w-aus", "AUSENTE_EN_FUENTE", shape, trail_id="VP-3"),
        _record("v-solape-otro", "SOLAPE", shape, b_kind="mtn50_historico"),
    )
    chosen = eligible_base_records(_report(*records))
    assert [r.record_id for r in chosen] == ["y-solape", "w-aus"]
    assert BASE_KINDS == {"AUSENTE_EN_FUENTE", "SOLAPE"}
    assert BASE_COUNTERPARTS == {"ign_red_transporte"}
    assert [r.record_id for r in eligible_base_records(_report(*reversed(records)))] == [
        "y-solape",
        "w-aus",
    ]
    with pytest.raises(ValueError):
        build_cut_candidates(_report(*records, redacted=True), {})


def test_ca5_ejemplo_trabajado_del_adr() -> None:
    """Dado el ejemplo trabajado del ADR §4 (vía pecuaria de (0,0) a (200,0), `AUSENTE_EN_FUENTE`
    frente a la red del IGN con `d` = 0,691, 40 muestras, apoyan las 16 de x = 62,5 a 137,5 con
    la señal `parcela_no_camino` de peso 0,6), cuando se llama a `build_cut_candidates`, entonces
    sale un único candidato con tramo de (60,0) a (140,0), `longitud_tramo_m` = 80,0, condición
    `dentro_de_cierre`, `f_s` = 1,0 y confianza 0,415."""
    report, readings = _worked_example()
    assert SIGNAL_WEIGHTS["parcela_no_camino"] == 0.6
    (candidate,) = build_cut_candidates(report, readings)
    (line,) = candidate.stretch.lines
    assert line[0] == pytest.approx((60.0, 0.0))
    assert line[-1] == pytest.approx((140.0, 0.0))
    assert candidate.stretch.srid == 25830
    assert {m.name: m.value for m in candidate.evidence}["longitud_tramo_m"] == 80.0
    assert candidate.conditions == ("dentro_de_cierre",)
    assert candidate.signals[0].support_fraction == 1.0
    assert candidate.confidence == 0.415
    assert candidate.discrepancy_ids == ("r1",)
    assert candidate.method == CUT_METHOD


def test_ca6_rachas_cercanas_se_funden_y_lejanas_no() -> None:
    """Dadas rachas del mismo trazado separadas ≤ `GAP_M` (10 m) y otras separadas más, cuando se
    construyen candidatos, entonces las primeras se funden en uno (enlace simple, orden de
    muestra) y las segundas quedan separadas; los dos lados del pseudo-eje de una franja se
    funden."""
    report = _report(_record("r1", "AUSENTE_EN_FUENTE", _vp(300.0)))
    # 60 muestras de 5 m. Rachas 0-7 (40 m) y 10-17 (40 m): hueco de 2 muestras = 10 m -> se funden.
    # Racha 30-37: a 60 m de la anterior -> aparte.
    apoya = set(range(0, 8)) | set(range(10, 18)) | set(range(30, 38))
    readings = {_key(): [_reading(PARCELA, _verdicts(60, apoya))]}
    first, second = build_cut_candidates(report, readings)
    assert GAP_M == 10.0
    assert first.stretch.lines[0][0] == pytest.approx((0.0, 0.0))
    assert first.stretch.lines[-1][-1] == pytest.approx((90.0, 0.0))
    assert len(first.stretch.lines) == 2  # dos rachas fundidas, no unidas por el hueco
    assert second.stretch.lines[0][0] == pytest.approx((150.0, 0.0))

    # Hueco justo por encima de GAP_M (3 muestras = 15 m): no se funden.
    apart = set(range(0, 8)) | set(range(11, 19))
    assert (
        len(build_cut_candidates(report, {_key(): [_reading(PARCELA, _verdicts(60, apart))]})) == 2
    )

    # Franja de 100 x 20: los dos lados del pseudo-eje distan menos de 10 m: un candidato.
    strip = Geometry(rings=(((0.0, 0.0), (100.0, 0.0), (100.0, 20.0), (0.0, 20.0)),), srid=25830)
    n = len(trail_samples(strip))
    strip_report = _report(_record("r2", "AUSENTE_EN_FUENTE", strip, trail_id="VP-S"))
    strip_readings = {_key("VP-S"): [_reading(PARCELA, ["apoya"] * n)]}
    assert len(build_cut_candidates(strip_report, strip_readings)) == 1


def test_ca7_racha_corta_se_descarta_y_25_m_se_conserva() -> None:
    """Dada una racha de longitud (suma de pesos) < `MIN_LENGTH_M` (25 m), cuando se construyen
    candidatos, entonces se descarta; una de exactamente 25 m se conserva."""
    assert MIN_LENGTH_M == 25.0
    report = _report(_record("r1", "AUSENTE_EN_FUENTE", _vp()))
    assert (
        build_cut_candidates(report, {_key(): [_reading(PARCELA, _verdicts(40, set(range(4))))]})
        == ()
    )
    kept = build_cut_candidates(report, {_key(): [_reading(PARCELA, _verdicts(40, set(range(5))))]})
    assert len(kept) == 1
    assert {m.name: m.value for m in kept[0].evidence}["longitud_tramo_m"] == 25.0


def test_ca8_apoyo_fuera_de_la_zona_base_no_forma_racha() -> None:
    """Dada una muestra con veredicto `apoya` fuera de la zona de discrepancia base (en `SOLAPE`,
    a más de `ZONE_MATCH_M` de la zona; o de un trazado sin registro base), cuando se construyen
    candidatos, entonces no forma racha. Una señal con todo `sin_dato` o `no_apoya` no genera
    candidato, y `sin_dato` no resta a las demás señales."""
    assert ZONE_MATCH_M == 0.05
    shape = _vp()
    zone = _line((100.0, 0.0), (200.0, 0.0))  # solo la mitad derecha (muestras 20..39)
    report = _report(_record("r1", "SOLAPE", shape, zone=zone))
    # Apoya en 0..39: solo cuentan las de la zona (20..39).
    (candidate,) = build_cut_candidates(report, {_key(): [_reading(PARCELA, ["apoya"] * 40)]})
    assert candidate.stretch.lines[0][0] == pytest.approx((100.0, 0.0))
    assert {m.name: m.value for m in candidate.evidence}["longitud_tramo_m"] == 100.0
    # Apoya solo fuera de la zona: nada.
    outside = _verdicts(40, set(range(0, 20)))
    assert build_cut_candidates(report, {_key(): [_reading(PARCELA, outside)]}) == ()
    # Trazado sin registro base: nada.
    assert build_cut_candidates(report, {_key("OTRO"): [_reading(PARCELA, ["apoya"] * 40)]}) == ()

    full = _report(_record("r2", "AUSENTE_EN_FUENTE", shape))
    for verdict in ("sin_dato", "no_apoya"):
        none = _reading(PARCELA, [verdict] * 40)
        assert build_cut_candidates(full, {_key(): [none]}) == ()
    # `sin_dato` de una señal no resta a la otra.
    with_nodata = build_cut_candidates(
        full,
        {
            _key(): [
                _reading(PARCELA, ["apoya"] * 40),
                _reading(VISIBILIDAD, ["sin_dato"] * 40),
            ]
        },
    )
    alone = build_cut_candidates(full, {_key(): [_reading(PARCELA, ["apoya"] * 40)]})
    assert with_nodata[0].confidence == alone[0].confidence
    assert [s.signal.identifier for s in with_nodata[0].signals] == ["parcela_no_camino"]


def test_ca9_combinacion_confianza_y_condiciones() -> None:
    """Dadas dos señales que concurren en un tramo, cuando se calcula la confianza
    `round(d·(1−Π(1−w_s·f_s)),3)`, entonces es mayor que con una sola, nunca baja al añadir una
    señal y nunca supera `d`; `d` es la mayor confianza de los registros base que tocan el
    candidato; `conditions` solo lista las condiciones con alguna señal que apoya, en el orden
    fijo del ADR; `SignalSupport` registra `support_fraction` y `no_data_fraction` a 3 decimales
    y solo las señales con `f_s` > 0."""
    shape = _vp()
    report = _report(
        _record("r1", "AUSENTE_EN_FUENTE", shape, confidence=0.5),
        _record("r2", "AUSENTE_EN_FUENTE", shape, confidence=0.8),
        _record("r3", "SOLAPE", shape, zone=_line((0.0, 0.0), (10.0, 0.0)), confidence=0.99),
    )
    parcela = _reading(PARCELA, _verdicts(40, set(range(10, 30))))
    ortofoto = _reading(
        VISIBILIDAD,
        [("apoya" if 10 <= i < 20 else "sin_dato" if i < 30 else "no_apoya") for i in range(40)],
    )
    one = build_cut_candidates(report, {_key(): [parcela]})[0]
    both = build_cut_candidates(report, {_key(): [parcela, ortofoto]})[0]
    only_ortho = build_cut_candidates(report, {_key(): [ortofoto]})[0]
    # r3 solo cubre las 2 primeras muestras: no toca el candidato (muestras 10..29). d = 0,8.
    assert one.discrepancy_ids == ("r1", "r2")
    assert one.confidence == round(0.8 * 0.6, 3)
    assert both.confidence == round(0.8 * (1 - (1 - 0.6 * 1.0) * (1 - 0.5 * 0.5)), 3)
    assert only_ortho.confidence < both.confidence
    assert one.confidence < both.confidence <= 0.8
    assert both.conditions == ("no_se_distingue", "dentro_de_cierre")
    assert one.conditions == ("dentro_de_cierre",)
    by_id = {s.signal.identifier: s for s in both.signals}
    assert by_id["visibilidad_ortofoto"].support_fraction == 0.5
    assert by_id["visibilidad_ortofoto"].no_data_fraction == 0.5
    assert by_id["parcela_no_camino"].no_data_fraction == 0.0
    assert [s.signal.identifier for s in both.signals] == [
        "parcela_no_camino",
        "visibilidad_ortofoto",
    ]
    # Señal sin ningún apoyo: no aparece.
    quiet = _reading(VISIBILIDAD, ["no_apoya"] * 40)
    assert [
        s.signal.identifier
        for s in build_cut_candidates(report, {_key(): [parcela, quiet]})[0].signals
    ] == ["parcela_no_camino"]


def test_ca10_determinismo_identificador_y_orden() -> None:
    """Dadas las mismas entradas en distinto orden de `readings` o de `report.records`, cuando se
    construyen candidatos, entonces el resultado es idéntico; `candidate_id` es de 16 hex de
    sha256 sobre método+versión, municipio, fuente y trazado A y tramo a 0,01 m, sin marcas de
    tiempo; y los candidatos salen en orden canónico (fuente A, trazado A, primera muestra,
    `candidate_id`)."""
    records = [
        _record("r1", "AUSENTE_EN_FUENTE", _vp(), trail_id="VP-B"),
        _record("r2", "AUSENTE_EN_FUENTE", _vp(), trail_id="VP-A"),
        _record("r3", "AUSENTE_EN_FUENTE", _vp(), trail_id="VP-A", b_kind="ign_red_transporte"),
    ]
    readings = {
        _key("VP-A"): [_reading(PARCELA, _verdicts(40, set(range(0, 8)) | set(range(20, 28))))],
        _key("VP-B"): [_reading(PARCELA, _verdicts(40, set(range(10, 20))))],
    }
    results = []
    for order in itertools.permutations(records):
        for reverse in (False, True):
            ordered = {k: readings[k] for k in sorted(readings, reverse=reverse)}
            results.append(build_cut_candidates(_report(*order), ordered))
    assert all(result == results[0] for result in results)
    ids = [c.candidate_id for c in results[0]]
    assert all(len(i) == 16 and int(i, 16) >= 0 for i in ids)
    assert len(set(ids)) == len(ids) == 3
    got = [(c.subject.trail_id, c.stretch.lines[0][0][0]) for c in results[0]]
    assert [g[0] for g in got] == ["VP-A", "VP-A", "VP-B"]
    assert [g[1] for g in got] == pytest.approx([0.0, 100.0, 50.0])
    # El identificador cambia con el municipio.
    other = dataclasses.replace(_report(records[0]), municipality_code="28099")
    assert (
        build_cut_candidates(other, {_key("VP-B"): readings[_key("VP-B")]})[0].candidate_id
        != results[0][2].candidate_id
    )


def test_ca11_descripcion_con_plantillas_y_sin_palabras_vetadas() -> None:
    """Dado un candidato, cuando se llama a `describe_candidate`, entonces el texto usa las
    plantillas del ADR §11 (base y `parcela_no_camino`), termina en «Indicio a verificar, no es un
    dictamen.» y `banned_words_in` no encuentra ninguna palabra vetada."""
    report, readings = _worked_example()
    text = describe_candidate(build_cut_candidates(report, readings)[0])
    assert text == (
        "Tramo de 80 m de vías pecuarias (IDEM) (2014-01-01) sin equivalente en el camino actual "
        "del IGN. Según Catastro, el 100 % del tramo cae dentro de parcelas que no son camino. "
        "Indicio a verificar, no es un dictamen."
    )
    assert text.endswith("Indicio a verificar, no es un dictamen.")
    assert banned_words_in(text) == ()


def test_ca12_veredictos_de_longitud_distinta_lanzan_value_error() -> None:
    """Dada una `SignalReading` cuyo número de veredictos no coincide con las muestras de
    `trail_samples(A)`, cuando se llama a `build_cut_candidates`, entonces lanza `ValueError` (no
    se descarta en silencio)."""
    report = _report(_record("r1", "AUSENTE_EN_FUENTE", _vp()))
    for wrong in (39, 41, 0):
        with pytest.raises(ValueError):
            build_cut_candidates(report, {_key(): [_reading(PARCELA, ["apoya"] * wrong)]})
