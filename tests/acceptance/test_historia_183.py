"""Criterios de aceptación de la historia #183: la red asfaltada del IGN cuenta como
contraparte en `discrepancias` y nunca como sujeto (ADR 0050).

Fixtures:

- `tests/fixtures/asfaltado/entrada/` — SINTÉTICAS (ver su LEEME.md): municipio 28997,
  vías VP-A…VP-E, para CA1–CA4, CA7, CA10 y CA11.
- `tests/fixtures/road_network/roadlink_paved_recorte_municipio_<ine>.json` — RECORTES
  reales de la consulta `paved` (ver `tests/road_layer_fixtures.py`), para CA5, CA6 y CA12.

Adaptación del diseño, anotada en la PR: el diseño esperaba que el `AUSENTE`/`SOLAPE` de
VP-D (asfaltado paralelo a 20 m) se mantuviera. Al pasar la fixture por el pipeline
(Bloque 0), VP-D no da ningún registro: la contraparte a 20 m está dentro del radio de
búsqueda (33,54 m) y fuera de la tolerancia (11,18 m), así que `compare_trail` da un
`DESPLAZAMIENTO`, que el par vía → IGN no conserva (`kinds_kept`), y el inverso (IGN →
vía) no se evalúa porque el asfaltado es solo contraparte. Es el mismo trato que un tramo
sin asfaltar a 20 m, salvo que este no genera el `DESPLAZAMIENTO` con sujeto asfaltado.
CA10 se comprueba tal como está escrito y con VP-E (sin asfaltar a 20 m), que conserva su
`DESPLAZAMIENTO` con o sin red asfaltada.
"""

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from shapely.geometry import LineString

from parcel_intel.adapters.discrepancy_files import GeoJsonDiscrepancyReportReader
from parcel_intel.application.cut_signals import CadastralParcelSignalProvider
from parcel_intel.application.detect_cut_candidates import DetectCutCandidatesUseCase
from parcel_intel.cli import main
from parcel_intel.domain.cut_method import BASE_COUNTERPARTS, CUT_METHOD
from tests.cut_signal_support import ORDINARY, Boundaries, ParcelsPort, Sink, parcel, rect

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).parents[2]
ASFALTADO = ROOT / "tests" / "fixtures" / "asfaltado" / "entrada"
INE = "28997"
PAVED_IDS = {"900000000001", "900000000003", "900000000004"}
UNPAVED_IDS = {"900000000002", "900000000005"}
TOLERANCE_VIA_IGN_M = 11.18


def _run_cli(argv: list[str]) -> int:
    old = sys.argv
    sys.argv = ["parcel_intel.cli.main", *argv]
    try:
        with pytest.raises(SystemExit) as exit_info:
            main.main()
    finally:
        sys.argv = old
    code = exit_info.value.code
    assert isinstance(code, int)
    return code


def _discrepancias(entrada: Path, salida: Path, ine: str = INE) -> int:
    return _run_cli(
        ["discrepancias", "--municipio", ine, "--entrada", str(entrada), "--salida", str(salida)]
    )


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _records(path: Path) -> list[tuple[str, str, str, str]]:
    """(tipo, fuente_a, fuente_b, id del sujeto) de cada registro del fichero."""
    return [
        (
            feature["properties"]["tipo"],
            feature["properties"]["fuente_a"],
            feature["properties"]["fuente_b"],
            feature["properties"]["trazados"][0]["id"],
        )
        for feature in _load(path)["features"]
    ]


def _copy_input(tmp_path: Path) -> Path:
    entrada = tmp_path / "entrada"
    shutil.copytree(ASFALTADO, entrada)
    return entrada


def _empty_paved(entrada: Path) -> None:
    path = entrada / "camino_asfaltado" / f"{INE}.geojson"
    document = _load(path)
    document["features"] = []
    path.write_text(json.dumps(document), encoding="utf-8")


@pytest.fixture
def salida(tmp_path: Path) -> Path:
    out = tmp_path / "salida"
    assert _discrepancias(ASFALTADO, out) == 0
    return out


def test_ca1_trazado_sobre_asfalto_no_genera_indicio(salida: Path) -> None:
    """CA1. Dado un trazado de vía pecuaria cuyo recorrido coincide (≤ el umbral de solape
    vigente) con un tramo `paved` de la red del IGN y sin tramo `unpaved`, cuando se ejecuta
    `discrepancias`, entonces no genera registro publicable por ausencia/solape contra
    `ign_red_transporte`."""
    for folder in ("publicable", "interno"):
        records = _records(salida / folder / f"{INE}.geojson")
        assert not [
            r
            for r in records
            if r[3] == "VP-A"
            and r[2] == "ign_red_transporte"
            and r[0] in {"AUSENTE_EN_FUENTE", "SOLAPE"}
        ]
        assert all(r[3] != "VP-A" for r in records)


def test_ca2_trazado_sobre_camino_sin_asfaltar_sin_regresion(tmp_path: Path, salida: Path) -> None:
    """CA2. Dado un trazado que coincide solo con un tramo `unpaved`, cuando se ejecuta
    `discrepancias`, entonces el resultado es el mismo que antes (sin regresión)."""
    entrada = _copy_input(tmp_path)
    _empty_paved(entrada)
    before = tmp_path / "antes"
    assert _discrepancias(entrada, before) == 0

    def about_b(path: Path) -> list[tuple[str, str, str, str]]:
        return [r for r in _records(path) if "VP-B" in r or r[3] == "900000000002"]

    assert about_b(salida / "interno" / f"{INE}.geojson") == []
    assert about_b(before / "interno" / f"{INE}.geojson") == []
    # Y las fixtures de #32 (con la red asfaltada vacía) dan los mismos ficheros que su oráculo:
    # lo comprueban sin cambios los tests de #32, #94 y #96.


def test_ca3_solo_se_senala_la_parte_sin_contraparte(salida: Path) -> None:
    """CA3. Dado un trazado cuya parte bajo asfalto es parcial, cuando se ejecuta
    `discrepancias`, entonces solo se señala la parte sin contraparte (asfaltada o no), con
    el mismo criterio de longitud mínima que ya usa el ADR 0030."""
    features = [
        f
        for f in _load(salida / "publicable" / f"{INE}.geojson")["features"]
        if f["properties"]["trazados"][0]["id"] == "VP-C"
    ]
    assert [f["properties"]["tipo"] for f in features] == ["SOLAPE"]
    zone_x = [x for x, _ in features[0]["geometry"]["coordinates"]]
    # Oráculo del pipeline (Bloque 0): zona de x = 450610 a 451000.
    assert (min(zone_x), max(zone_x)) == (450610.0, 451000.0)
    # Contraste con shapely: primer punto del eje a más de la tolerancia del par del tramo
    # asfaltado (de 450000 a 450600, a 2 m del eje). La zona empieza en la muestra anterior.
    paved = LineString([(450000.0, 4437002.0), (450600.0, 4437002.0)])
    first_uncovered = next(
        x / 10 for x in range(4500000, 4510001) if paved.distance(_point(x / 10)) > 11.18
    )
    assert first_uncovered == pytest.approx(450611.0, abs=0.1)
    assert min(zone_x) == pytest.approx(first_uncovered, abs=5.0)  # paso de muestreo: 5 m
    medidas = features[0]["properties"]["medidas"]
    assert medidas["tolerancia_par_m"] == TOLERANCE_VIA_IGN_M
    assert medidas["paso_muestreo_m"] == 5.0


def _point(x: float) -> Any:
    from shapely.geometry import Point

    return Point(x, 4437000.0)


def test_ca4_candidatos_con_la_misma_contraparte(tmp_path: Path, salida: Path) -> None:
    """CA4. Dado el método de candidatos a corte (ADR 0039), cuando se calcula la
    discrepancia base, entonces usa la misma contraparte (asfaltada + sin asfaltar) y los
    candidatos de Colmenar no cambian salvo por la parte bajo asfalto.

    Encadena `discrepancias` → `DetectCutCandidatesUseCase` con la señal de Catastro sobre
    un doble (una parcela ordinaria SINTÉTICA que cubre todo): el único candidato es la
    parte de VP-C sin contraparte; VP-A (bajo asfalto) no da ninguno. Los candidatos reales
    de Colmenar se miden en local (CA13)."""
    assert BASE_COUNTERPARTS == {"ign_red_transporte"}
    assert CUT_METHOD.identifier == "candidato_corte"
    assert CUT_METHOD.version == 1

    def candidates(discrepancy_dir: Path) -> list[Any]:
        port = ParcelsPort([parcel(ORDINARY, rect(449000, 4434000, 452000, 4440000))])
        provider = CadastralParcelSignalProvider(
            lambda _code: port, Boundaries((449000, 4434000, 452000, 4440000)), 900.0
        )
        use_case = DetectCutCandidatesUseCase(
            GeoJsonDiscrepancyReportReader(discrepancy_dir / "interno"), [provider], Sink()
        )
        return list(use_case.execute(INE).candidates)

    with_paved = candidates(salida)
    assert [c.subject.trail_id for c in with_paved] == ["VP-C"]
    xs = [x for part in with_paved[0].stretch.lines for x, _ in part]
    assert min(xs) >= 450600.0  # solo la parte sin contraparte
    assert max(xs) == pytest.approx(451000.0, abs=5.0)

    entrada = _copy_input(tmp_path)
    _empty_paved(entrada)
    sin_asfalto = tmp_path / "sin_asfalto"
    assert _discrepancias(entrada, sin_asfalto) == 0
    without_paved = candidates(sin_asfalto)
    assert sorted(c.subject.trail_id for c in without_paved) == ["VP-A", "VP-C", "VP-D"]


def test_ca7_ficheros_anteriores_sin_asfaltado_fallan_con_mensaje(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA7. Dados los ficheros derivados anteriores (sin asfaltado), cuando se ejecuta
    `discrepancias`, entonces falla con un mensaje claro que pide regenerar la capa, en vez
    de dar resultados silenciosamente distintos."""
    entrada = _copy_input(tmp_path)
    shutil.rmtree(entrada / "camino_asfaltado")
    out = tmp_path / "salida"

    assert _discrepancias(entrada, out) == 1

    err = capsys.readouterr().err
    assert f"FALLO {INE}" in err
    assert str(entrada / "camino_asfaltado" / f"{INE}.geojson") in err
    assert "regenera con `camino-actual-municipios`" in err
    assert not (out / "interno" / f"{INE}.geojson").exists()
    assert not (out / "publicable" / f"{INE}.geojson").exists()


def test_ca10_un_tramo_asfaltado_nunca_es_sujeto(tmp_path: Path, salida: Path) -> None:
    """CA10. Dado un tramo `paved` del IGN paralelo a una vía pecuaria a 20 m (fuera de la
    tolerancia del par, 11,18 m, y dentro de su radio de búsqueda, 33,54 m), cuando se
    ejecuta `discrepancias`, entonces ningún registro tiene como sujeto (fuente A) un tramo
    asfaltado —ni `DESPLAZAMIENTO` ni otro tipo— y los registros cuyo sujeto es un tramo sin
    asfaltar son los mismos que con la capa asfaltada vacía. Los tramos asfaltados solo
    sirven de contraparte."""
    records = _records(salida / "interno" / f"{INE}.geojson")
    assert all(r[3] not in PAVED_IDS for r in records)

    entrada = _copy_input(tmp_path)
    _empty_paved(entrada)
    empty = tmp_path / "vacia"
    assert _discrepancias(entrada, empty) == 0

    def unpaved_subject(path: Path) -> list[dict[str, Any]]:
        return [
            f
            for f in _load(path)["features"]
            if f["properties"]["trazados"][0]["id"] in UNPAVED_IDS
        ]

    for folder in ("interno", "publicable"):
        with_paved = unpaved_subject(salida / folder / f"{INE}.geojson")
        without = unpaved_subject(empty / folder / f"{INE}.geojson")
        assert with_paved == without
        # VP-E: el tramo sin asfaltar a 20 m sigue dando su DESPLAZAMIENTO.
        assert [(f["properties"]["tipo"], f["properties"]["trazados"][1]["id"]) for f in with_paved] == [
            ("DESPLAZAMIENTO", "VP-E")
        ]


def _mutate(entrada: Path, folder: str, change: Any) -> Path:
    path = entrada / folder / f"{INE}.geojson"
    document = _load(path)
    change(document)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _second_municipality(entrada: Path) -> None:
    """Copia 28997 como 28996 (sin cambios) para comprobar que el lote sigue."""
    for folder in ("vias_pecuarias", "camino_actual", "camino_asfaltado"):
        document = _load(entrada / folder / f"{INE}.geojson")
        document["properties"]["municipio"] = "28996"
        (entrada / folder / "28996.geojson").write_text(json.dumps(document), encoding="utf-8")


def _set_surface(value: str) -> Any:
    def change(document: dict[str, Any]) -> None:
        document["properties"]["superficie"] = value
        for feature in document["features"]:
            feature["properties"]["superficie"] = value

    return change


def _swap(entrada: Path) -> Path:
    """Intercambia los dos ficheros de 28997 (28996 queda bien)."""
    actual = entrada / "camino_actual" / f"{INE}.geojson"
    asfaltado = entrada / "camino_asfaltado" / f"{INE}.geojson"
    text_actual, text_asfaltado = actual.read_bytes(), asfaltado.read_bytes()
    actual.write_bytes(text_asfaltado)
    asfaltado.write_bytes(text_actual)
    return actual


def _duplicate_id(entrada: Path) -> Path:
    def change(document: dict[str, Any]) -> None:
        document["features"][0]["id"] = "900000000002"  # el id de un tramo sin asfaltar

    return _mutate(entrada, "camino_asfaltado", change)


def _paved_without_unpaved(entrada: Path) -> Path:
    path = entrada / "camino_actual" / f"{INE}.geojson"
    path.unlink()
    return path


@pytest.mark.parametrize(
    "case",
    [
        lambda e: _mutate(e, "camino_actual", _set_surface("paved")),
        lambda e: _mutate(e, "camino_asfaltado", _set_surface("unpaved")),
        _swap,
        _duplicate_id,
        _paved_without_unpaved,
    ],
    ids=["paved-en-camino_actual", "unpaved-en-camino_asfaltado", "intercambiados",
         "id-repetido", "asfaltado-sin-camino_actual"],
)
def test_ca11_ficheros_incoherentes_fallan_nombrando_el_fichero_y_el_lote_sigue(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], case: Any
) -> None:
    """CA11. Dados los directorios intercambiados (un fichero con `superficie: "paved"` en
    `camino_actual/` o uno con `superficie: "unpaved"` en `camino_asfaltado/`), un mismo
    `id_tramo` en los dos ficheros, o el fichero asfaltado sin el fichero sin asfaltar,
    cuando se ejecuta `discrepancias`, entonces ese municipio falla con un mensaje que nombra
    el fichero y el lote sigue (como el CA8 de #32). Sin ninguno de los dos ficheros, la
    fuente consta como `AUSENTE`, como hoy."""
    entrada = _copy_input(tmp_path)
    _second_municipality(entrada)
    bad_path = case(entrada)
    out = tmp_path / "salida"

    code = _run_cli(
        ["discrepancias", "--municipio", INE, "--municipio", "28996",
         "--entrada", str(entrada), "--salida", str(out)]
    )

    assert code == 1
    err = capsys.readouterr().err
    assert f"FALLO {INE}" in err
    assert str(bad_path) in err
    assert not (out / "interno" / f"{INE}.geojson").exists()
    assert (out / "interno" / "28996.geojson").is_file()  # el lote sigue


def test_ca11_sin_ninguno_de_los_dos_ficheros_la_fuente_consta_ausente(tmp_path: Path) -> None:
    """CA11 (última frase). Sin ninguno de los dos ficheros, la fuente consta como
    `AUSENTE`, como hoy."""
    entrada = _copy_input(tmp_path)
    shutil.rmtree(entrada / "camino_actual")
    shutil.rmtree(entrada / "camino_asfaltado")
    out = tmp_path / "salida"

    assert _discrepancias(entrada, out) == 0

    layers = {layer["fuente"]: layer for layer in _load(out / "interno" / f"{INE}.geojson")["properties"]["capas"]}
    assert layers["ign_red_transporte"]["estado"] == "ausente"
