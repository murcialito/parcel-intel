"""Historia #127: señal parcela_no_camino y caso de uso de candidatos a corte.

Geometrías sintéticas, sin red; el oráculo es el ejemplo trabajado del ADR 0039 §4.
"""

import ast
import dataclasses
import logging
import math
from pathlib import Path

import pytest

from parcel_intel.application.cut_signals import (
    CadastralParcelSignalProvider,
    footprint_kind,
    to_footprint,
)
from parcel_intel.application.detect_cut_candidates import DetectCutCandidatesUseCase
from parcel_intel.domain.cut_method import describe_candidate
from parcel_intel.domain.cut_signal_parcel import (
    PARCEL_SIGNAL,
    ParcelFootprint,
    index_footprints,
    read_parcel_signal,
)
from parcel_intel.domain.discrepancy import trail_samples
from parcel_intel.domain.public_card import banned_words_in
from parcel_intel.ports.errors import TruncatedAreaQueryError
from tests.cut_signal_support import (
    INFRASTRUCTURE_HG,
    INFRASTRUCTURE_VT,
    ORDINARY,
    UNREADABLE,
    URBAN,
    Boundaries,
    ParcelsPort,
    ReportSource,
    Sink,
    base_record,
    line,
    parcel,
    rect,
    report_of,
    source,
)

pytestmark = pytest.mark.acceptance

MARGIN = math.hypot(10, 5)
SRC = Path(__file__).resolve().parents[2] / "src" / "parcel_intel"


def _oracle_use_case(
    sink: Sink, port: ParcelsPort | None = None, report: ReportSource | None = None
) -> tuple[DetectCutCandidatesUseCase, ParcelsPort, ReportSource]:
    port = port or ParcelsPort([parcel(ORDINARY, rect(50, -50, 150, 50))])
    report = report or ReportSource(report_of(base_record("r1", line((0.0, 0.0), (200.0, 0.0)))))
    provider = CadastralParcelSignalProvider(
        lambda _code: port, Boundaries((-100, -100, 300, 100)), 900.0
    )
    return DetectCutCandidatesUseCase(report, [provider], sink), port, report


def test_ca1_ejemplo_trabajado_40_veredictos_16_apoyan() -> None:
    """Dado un trazado A de tipo vía pecuaria con eje de (0, 0) a (200, 0), una única huella
    `ordinaria` rectangular x ∈ [50, 150], y ∈ [−50, 50] y una tolerancia del par que da margen
    `hypot(10, 5)` = 11,180 m, cuando se lee la señal, entonces hay 40 veredictos (muestras en
    x = 2,5 … 197,5), `apoya` exactamente en las 16 de x = 62,5 a x = 137,5, y el resto
    `no_apoya`."""
    samples = trail_samples(line((0.0, 0.0), (200.0, 0.0)))
    index = index_footprints([ParcelFootprint(rect(50, -50, 150, 50), "ordinaria")])
    reading = read_parcel_signal(samples, index, MARGIN, [False] * len(samples))
    assert [s.point[0] for s in samples][:2] == [2.5, 7.5] and samples[-1].point[0] == 197.5
    assert len(reading.verdicts) == 40
    apoyan = [samples[i].point[0] for i, v in enumerate(reading.verdicts) if v == "apoya"]
    assert apoyan == pytest.approx([62.5 + 5.0 * k for k in range(16)])
    assert apoyan[-1] == pytest.approx(137.5)
    assert {v for v in reading.verdicts if v != "apoya"} == {"no_apoya"}


def test_ca2_margen_al_borde_de_una_huella_ordinaria() -> None:
    """Dada una muestra dentro de una huella `ordinaria` a menos del margen de su borde, cuando
    se lee, entonces `no_apoya`. A distancia exactamente igual al margen, `apoya`."""
    footprint = [ParcelFootprint(rect(50, -50, 150, 50), "ordinaria")]
    index = index_footprints(footprint)
    near, exact = (
        trail_samples(line((52.5, 0.0), (57.5, 0.0))),
        trail_samples(line((57.5, 0.0), (62.5, 0.0))),
    )
    assert near[0].point == (55.0, 0.0) and exact[0].point == (60.0, 0.0)
    assert read_parcel_signal(near, index, 10.0, [False]).verdicts == ("no_apoya",)
    assert read_parcel_signal(exact, index, 10.0, [False]).verdicts == ("apoya",)


def test_ca3_infraestructura_otra_y_fuera_de_toda_huella_no_apoyan() -> None:
    """Dada una huella `infraestructura` (número ≥ 9000, de cualquier clase) contenida en una
    `ordinaria` y que cubre la muestra, cuando se lee, entonces `no_apoya`. Una muestra fuera de
    toda huella es `no_apoya`, y una dentro de una huella `otra` también."""
    samples = trail_samples(line((0.0, 0.0), (200.0, 0.0)))
    index = index_footprints(
        [
            ParcelFootprint(rect(0, -50, 100, 50), "ordinaria"),
            ParcelFootprint(rect(45, -5, 55, 5), "infraestructura"),
            ParcelFootprint(rect(120, -50, 160, 50), "otra"),
        ]
    )
    verdicts = read_parcel_signal(samples, index, 10.0, [False] * len(samples)).verdicts
    by_x = {s.point[0]: v for s, v in zip(samples, verdicts, strict=True)}
    assert by_x[22.5] == "apoya"
    assert by_x[47.5] == "no_apoya" and by_x[52.5] == "no_apoya"  # enclave
    assert by_x[137.5] == "no_apoya"  # huella otra
    assert by_x[187.5] == "no_apoya"  # fuera de toda huella


def test_ca4_clasificacion_de_parcel_a_huella_sin_referencia() -> None:
    """Dada la clasificación de `Parcel` a `ParcelFootprint`, cuando se prueban rústica < 9000,
    rústica ≥ 9000 de clase `VT`, rústica ≥ 9000 de clase `HG`, referencia urbana y referencia
    ilegible, entonces salen `ordinaria`, `infraestructura`, `infraestructura`, `otra` y `otra`.
    Y `dataclasses.fields(ParcelFootprint)` es exactamente `geometry` y `kind`: no hay campo de
    referencia."""
    refs = [ORDINARY, INFRASTRUCTURE_VT, INFRASTRUCTURE_HG, URBAN, UNREADABLE]
    kinds = [footprint_kind(parcel(r, rect(0, 0, 1, 1))) for r in refs]
    assert kinds == ["ordinaria", "infraestructura", "infraestructura", "otra", "otra"]
    assert to_footprint(parcel(ORDINARY, rect(0, 0, 1, 1))).kind == "ordinaria"
    assert [f.name for f in dataclasses.fields(ParcelFootprint)] == ["geometry", "kind"]


def test_ca5_tesela_sin_datos_da_sin_dato_y_el_resto_se_evalua() -> None:
    """Dada una muestra cuya tesela no se pudo obtener (el port de parcelas falla con el error de
    «sin datos» acordado), cuando se lee, entonces su veredicto es `sin_dato`; el resto de
    muestras se evalúan con normalidad."""
    zone = line((0.0, 0.0), (1800.0, 0.0))
    port = ParcelsPort(
        [parcel(ORDINARY, rect(-100, -50, 2000, 50))],
        fail=lambda t: TruncatedAreaQueryError(t, 2, 1) if t[0] == 900.0 else None,
    )
    provider = CadastralParcelSignalProvider(
        lambda _c: port, Boundaries((0, -100, 1800, 100)), 900.0
    )
    provider.prepare("28043", [zone])
    reading = provider.read(
        "28043", base_record("r", zone).discrepancy.subject, trail_samples(zone)
    )
    assert reading.verdicts[0] == "apoya" and reading.verdicts[-1] == "sin_dato"
    assert reading.verdicts.count("sin_dato") == 180 and reading.verdicts.count("apoya") == 180


def test_ca6_aplica_a_vias_planimetria_y_mtn50_no_a_catastro() -> None:
    """Dado un trazado `catastro_vt`, cuando se consulta `applies_to`, entonces es falso; para
    vía pecuaria, planimetría y MTN50 es verdadero."""
    provider = CadastralParcelSignalProvider(
        lambda _c: ParcelsPort([]), Boundaries((0, 0, 1, 1)), 900.0
    )
    assert provider.signal == PARCEL_SIGNAL
    assert not provider.applies_to("catastro_vt")
    assert provider.applies_to("via_pecuaria_oficial")
    assert provider.applies_to("planimetria_historica")
    assert provider.applies_to("mtn50_historico")


def test_ca7_caso_de_uso_con_el_oraculo() -> None:
    """Dado el oráculo de CA1 como único trazado de un `MunicipalDiscrepancyReport` base
    (`AUSENTE_EN_FUENTE` frente a `ign_red_transporte`, `d` = 0,691) y un
    `CadastralParcelSignalProvider` con un port de parcelas de prueba, cuando se ejecuta
    `DetectCutCandidatesUseCase`, entonces el informe trae un candidato con tramo de (60, 0) a
    (140, 0), `longitud_tramo_m == 80.0`, condición `dentro_de_cierre`, `f_s == 1.0` y
    `confidence == 0.415`; el sink recibe ese informe exactamente una vez y `signals` del informe
    lleva `SignalRunSummary(status="ejecutada")`."""
    sink = Sink()
    use_case, _, _ = _oracle_use_case(sink)
    result = use_case.execute("28043")
    [candidate] = result.candidates
    [stretch] = candidate.stretch.lines  # una sola línea: de (60, 0) a (140, 0)
    assert stretch[0] == pytest.approx((60.0, 0.0)) and stretch[-1] == pytest.approx((140.0, 0.0))
    assert [m.value for m in candidate.evidence if m.name == "longitud_tramo_m"] == [80.0]
    assert candidate.conditions == ("dentro_de_cierre",)
    assert [s.support_fraction for s in candidate.signals] == [1.0]
    assert candidate.confidence == 0.415
    assert sink.written == [result]
    [summary] = result.signals
    assert summary.status == "ejecutada" and summary.signal == PARCEL_SIGNAL


def test_ca8_solo_se_piden_las_teselas_de_las_zonas_base_una_vez() -> None:
    """Dado un informe con registros base de varios trazados, cuando se calculan las teselas a
    pedir, entonces solo se piden las que tocan alguna zona base (rejilla de lado 900 m sobre el
    bbox del término del IGN) y cada una una sola vez, en orden fila a fila desde la esquina SO."""
    report = ReportSource(
        report_of(
            base_record("r1", line((100.0, 100.0), (300.0, 100.0)), "VP-1"),
            base_record("r2", line((2800.0, 950.0), (2900.0, 950.0)), "VP-2"),
            base_record("r3", line((400.0, 200.0), (500.0, 200.0)), "VP-3"),
        )
    )
    port = ParcelsPort([])
    provider = CadastralParcelSignalProvider(lambda _c: port, Boundaries((0, 0, 3000, 1000)), 900.0)
    DetectCutCandidatesUseCase(report, [provider], Sink()).execute("28043")
    assert port.requests == [(0.0, 0.0, 900.0, 900.0), (2700.0, 900.0, 3000.0, 1000.0)]


def test_ca9_todas_las_teselas_fallan_es_sin_datos_y_se_escribe() -> None:
    """Dado que el port de parcelas falla en todas las teselas necesarias, cuando se ejecuta el
    caso de uso, entonces `SignalRunSummary(status="sin_datos", reason=…)`, todos los veredictos
    son `sin_dato`, no hay candidatos y el informe se escribe igualmente. Cualquier otro error se
    propaga."""
    sink = Sink()
    failing = ParcelsPort([], fail=lambda t: TruncatedAreaQueryError(t, 2, 1))
    use_case, _, _ = _oracle_use_case(sink, failing)
    result = use_case.execute("28043")
    [summary] = result.signals
    assert summary.status == "sin_datos" and summary.reason
    assert result.candidates == () and sink.written == [result]

    provider = CadastralParcelSignalProvider(
        lambda _c: failing, Boundaries((-100, -100, 300, 100)), 900.0
    )
    zone = line((0.0, 0.0), (200.0, 0.0))
    provider.prepare("28043", [zone])
    verdicts = provider.read(
        "28043", base_record("r", zone).discrepancy.subject, trail_samples(zone)
    ).verdicts
    assert set(verdicts) == {"sin_dato"}

    boom = ParcelsPort([], fail=lambda _t: RuntimeError("fallo real"))
    other, _, _ = _oracle_use_case(Sink(), boom)
    with pytest.raises(RuntimeError, match="fallo real"):
        other.execute("28043")


def test_ca10_sin_informe_se_registra_y_no_se_llama_a_los_ports(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Dado que `DiscrepancyReportSource` no tiene informe del municipio, cuando se ejecuta,
    entonces se registra «municipio sin capas», el sink no recibe candidatos, no se llama a los
    ports de parcelas y no hay excepción (criterio del ADR 0030 §3)."""
    sink, port = Sink(), ParcelsPort([])
    use_case, _, _ = _oracle_use_case(sink, port, ReportSource(None))
    with caplog.at_level(logging.INFO):
        result = use_case.execute("28043")
    assert "municipio sin capas" in caplog.text
    assert result.candidates == () and sink.written == []
    assert port.requests == []


def test_ca11_dos_ejecuciones_dan_informes_iguales() -> None:
    """Dadas dos ejecuciones con las mismas entradas, cuando se comparan sus informes, entonces
    son iguales (`==`), con candidatos en el orden canónico del ADR 0039 §5."""
    report = report_of(
        base_record("r2", line((0.0, 100.0), (200.0, 100.0)), "VP-2"),
        base_record("r1", line((0.0, 0.0), (200.0, 0.0)), "VP-1"),
    )
    port = ParcelsPort([parcel(ORDINARY, rect(50, -50, 150, 150))])
    first, _, _ = _oracle_use_case(Sink(), port, ReportSource(report))
    second, _, _ = _oracle_use_case(Sink(), port, ReportSource(report))
    a, b = first.execute("28043"), second.execute("28043")
    assert a == b and len(a.candidates) == 2
    assert [c.subject.trail_id for c in a.candidates] == ["VP-1", "VP-2"]


def test_ca12_frase_sin_palabras_vetadas_y_evidencia_sin_parcelas() -> None:
    """Dado el candidato de CA7, cuando `describe_candidate` (H1) genera la frase de
    `parcela_no_camino`, entonces es «Según Catastro, el {porcentaje} % del tramo cae dentro de
    parcelas que no son camino.», no contiene ninguna palabra de `BANNED_WORDS` (comprobado con
    `banned_words_in`) y la evidencia de la señal solo lleva longitudes y fracciones (sin
    geometría de parcela, número de parcelas ni referencias)."""
    use_case, _, _ = _oracle_use_case(Sink())
    [candidate] = use_case.execute("28043").candidates
    text = describe_candidate(candidate)
    assert "Según Catastro, el 100 % del tramo cae dentro de parcelas que no son camino." in text
    assert banned_words_in(text) == ()

    samples = trail_samples(line((0.0, 0.0), (200.0, 0.0)))
    index = index_footprints([ParcelFootprint(rect(50, -50, 150, 50), "ordinaria")])
    reading = read_parcel_signal(samples, index, MARGIN, [False] * len(samples))
    assert {m.unit for m in reading.evidence} <= {"m", "fraccion"}
    for dump in (repr(candidate), repr(reading)):
        assert ORDINARY not in dump and "50.0, -50.0" not in dump
    assert source("via_pecuaria_oficial").kind == candidate.subject.source.kind


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def test_ca13_capas_respetadas() -> None:
    """Dados los ficheros nuevos de dominio, aplicación y ports, cuando se ejecuta
    `uv run lint-imports`, entonces pasa: el dominio no importa nada externo y la aplicación
    solo importa `ports` y `domain`. (El contrato lo ejecuta CI; aquí se comprueba lo mismo
    sobre los ficheros nuevos.)"""
    stdlib = {"math", "collections.abc", "dataclasses", "typing"}
    for path in [SRC / "domain" / "cut_signal_parcel.py"]:
        for name in _imports(path):
            assert name in stdlib or name.startswith("parcel_intel.domain"), (path, name)
    for path in [SRC / "ports" / "cut_candidate_sink.py"]:
        for name in _imports(path):
            assert name == "typing" or name.startswith("parcel_intel.domain"), (path, name)
    for path in [
        SRC / "application" / "cut_signals.py",
        SRC / "application" / "detect_cut_candidates.py",
    ]:
        for name in _imports(path):
            assert (
                name in {"logging", "collections.abc", "typing"}
                or name.startswith(("parcel_intel.domain", "parcel_intel.ports"))
                or name == "parcel_intel.application.cut_signals"
            ), (path, name)
