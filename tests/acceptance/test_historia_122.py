"""Historia #122: comando `imagenes-comparacion` por municipio (ADR 0042 §5).

Las fixtures de ventana son las reales de #124 (448 px: AMS, SIGPAC y PNOA2023 y la blanca
de PNOA2010). Donde un vuelo no tiene fixture propia (PNOA2009, PNOA2017) se sirve la de
PNOA2023 como imagen sintética de relleno: los criterios miran el manifiesto, no los píxeles.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import requests

from parcel_intel.adapters.comparison_files import (
    JsonComparisonManifestWriter,
    ManifestTooLargeError,
    read_stretches,
)
from parcel_intel.application.build_municipal_comparisons import MunicipalWindowLimitError
from parcel_intel.cli import main
from parcel_intel.domain.comparison_image import (
    COMPARISON_POLICY,
    DECLARED_GAPS,
    MAX_WINDOWS_PER_MUNICIPALITY,
)
from parcel_intel.domain.public_card import BANNED_WORDS, banned_words_in
from tests.adapters.pnoa.helpers import FIXTURES_DIR, LayerFixtureHttpGet

pytestmark = pytest.mark.acceptance

INE = "28043"
X0, Y0 = 470000, 4440000
CRS = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::25830"}}
OK_LAYERS = {
    "AMS_1956-1957": FIXTURES_DIR / "window_224_ams.jpg",
    "SIGPAC": FIXTURES_DIR / "window_224_sigpac.jpg",
    "PNOA2009": FIXTURES_DIR / "window_224_pnoa2023.jpg",
    "PNOA2017": FIXTURES_DIR / "window_224_pnoa2023.jpg",
    "PNOA2023": FIXTURES_DIR / "window_224_pnoa2023.jpg",
}
BLANK = FIXTURES_DIR / "window_224_pnoa2010_blanca.jpg"
CADASTRAL_REFERENCE = re.compile(r"\b\d{7}[A-Z]{2}\d{4}[A-Z](?:\d{4}[A-Z]{2})?\b", re.IGNORECASE)


def _feature(stretch_id: str, x: int, y: int, length: int) -> dict[str, object]:
    return {
        "type": "Feature",
        "properties": {"id": stretch_id},
        "geometry": {"type": "LineString", "coordinates": [[x, y], [x + length, y]]},
    }


def _write_stretches(path: Path, features: Sequence[dict[str, object]], crs: object = CRS) -> Path:
    collection: dict[str, object] = {"type": "FeatureCollection", "features": list(features)}
    if crs is not None:
        collection["crs"] = crs
    path.write_text(json.dumps(collection), encoding="utf-8")
    return path


def _populate(
    cache: Path,
    out: Path,
    tramos: Path,
    layers: dict[str, Path] | None = None,
) -> LayerFixtureHttpGet:
    """Ejecuta el lote «con red» (doble) para poblar la caché con fecha 2026-11-26."""
    http = LayerFixtureHttpGet(layers or OK_LAYERS)
    use_case = main.build_comparison_use_case(
        cache,
        out,
        offline=False,
        http_get=http,
        today=lambda: date(2026, 11, 26),
        sleep=lambda _s: None,
    )
    requests_ = read_stretches(tramos, INE)
    use_case.execute(INE, requests_)
    return http


def _run(tramos: Path, cache: Path, out: Path, *extra: str) -> int:
    args = main._build_parser().parse_args(
        [
            "imagenes-comparacion",
            "--municipio",
            INE,
            "--tramos",
            str(tramos),
            "--cache",
            str(cache),
            "--salida",
            str(out),
            *extra,
        ]
    )
    code: int = args.func(args)
    return code


def _manifest(out: Path) -> Any:
    loaded: Any = json.loads((out / f"{INE}.json").read_text(encoding="utf-8"))
    return loaded


def test_ca1_solo_desde_la_cache_sin_red(tmp_path: Path) -> None:
    """CA1. Dado un municipio con un fichero de tramos y una caché cruda ya poblada, cuando se
    ejecuta `imagenes-comparacion --municipio <ine> --tramos <fichero> --sin-red`, entonces
    escribe `data/derived/comparacion/<ine>.json` solo desde la caché, sin red."""
    tramos = _write_stretches(tmp_path / "t.geojson", [_feature("a" * 16, X0, Y0, 80)])
    _populate(tmp_path / "raw", tmp_path / "poblado", tramos)
    out = tmp_path / "comparacion"
    assert _run(tramos, tmp_path / "raw", out, "--sin-red") == 0
    assert (out / f"{INE}.json").is_file()
    # El valor por defecto de --salida es la ruta del criterio.
    parsed = main._build_parser().parse_args(
        ["imagenes-comparacion", "--municipio", INE, "--tramos", "x"]
    )
    assert parsed.salida == Path("data/derived/comparacion")
    assert parsed.cache == Path("data/raw")


def test_ca2_el_manifiesto_trae_los_campos_del_adr(tmp_path: Path) -> None:
    """CA2. Dado un tramo generado, cuando se lee el manifiesto, entonces cada imagen trae
    `franja`, `vuelo`, `periodo`, `resolucion_m`, `atribucion` («Obra derivada de …», cadena
    del ADR §3), `sha256`, `bytes` y `procedencia` con `fuente`, `url` (canónica, la misma de
    la caché), `fecha_descarga`, `licencia` y `redistribucion`; cada ventana trae `bbox`,
    `srid`, `ancho_px`, `alto_px`, `trazo_px` y `omitidas`; el manifiesto trae `municipio`,
    `politica` (id y versión) y `huecos` (1957–1997)."""
    tramos = _write_stretches(tmp_path / "t.geojson", [_feature("a" * 16, X0, Y0, 80)])
    http = _populate(tmp_path / "raw", tmp_path / "out", tramos)
    manifest = _manifest(tmp_path / "out")
    assert manifest["municipio"] == INE
    assert manifest["politica"] == {
        "id": COMPARISON_POLICY.identifier,
        "version": COMPARISON_POLICY.version,
    }
    huecos = manifest["huecos"]
    assert isinstance(huecos, list)
    assert [(h["desde"], h["hasta"]) for h in huecos] == [(1957, 1997)]
    assert len(huecos) == len(DECLARED_GAPS)
    tramo = manifest["tramos"][0]
    assert tramo["id"] == "a" * 16
    (ventana,) = tramo["ventanas"]
    assert ventana["bbox"] == [469928, 4439888, 470152, 4440112]
    assert (ventana["srid"], ventana["ancho_px"], ventana["alto_px"]) == (25830, 448, 448)
    assert ventana["trazo_px"] == [[[144.0, 224.0], [304.0, 224.0]]]
    assert ventana["omitidas"] == []
    imagenes = ventana["imagenes"]
    assert [i["franja"] for i in imagenes] == [
        "1956-1957",
        "1997-2003",
        "2006-2011",
        "2014-2020",
        "reciente",
    ]
    for imagen in imagenes:
        assert imagen["atribucion"].startswith("Obra derivada de ")
        assert imagen["sha256"] and imagen["bytes"] > 0
        assert {"vuelo", "periodo", "resolucion_m"} <= set(imagen)
        procedencia = imagen["procedencia"]
        assert procedencia["fuente"] == "pnoa-historico"
        assert procedencia["fecha_descarga"] == "2026-11-26"
        assert procedencia["licencia"] == "CC BY 4.0"
        assert procedencia["redistribucion"] == "publicable"
    assert imagenes[0]["atribucion"] == (
        "Obra derivada de Orto-AMS 1956-1957 CC-BY 4.0 ejercito.defensa.gob.es"
    )
    # La URL del manifiesto es la canónica de la caché: una petición real la reproduciría.
    urls = {i["procedencia"]["url"] for i in imagenes}
    assert len(urls) == 5
    assert all(url.startswith("https://www.ign.es/wms/pnoa-historico?") for url in urls)
    assert len(http.calls) == 5


def test_ca3_tope_de_ventanas_antes_de_pedir_nada(tmp_path: Path) -> None:
    """CA3. Dado un municipio cuyos tramos suman más de `MAX_WINDOWS_PER_MUNICIPALITY` (400)
    ventanas, cuando se ejecuta, entonces sale con 1 **antes de pedir nada** y no escribe
    nada; y si el manifiesto serializado pasara de 3.000.000 bytes, sale con 1 sin
    escribir."""
    n = MAX_WINDOWS_PER_MUNICIPALITY + 1
    features = [_feature(f"{i:016x}", X0 + 1000 * i, Y0, 80) for i in range(n)]
    tramos = _write_stretches(tmp_path / "t.geojson", features)
    out = tmp_path / "out"
    http = LayerFixtureHttpGet(OK_LAYERS)
    use_case = main.build_comparison_use_case(
        tmp_path / "raw", out, offline=False, http_get=http, sleep=lambda _s: None
    )
    with pytest.raises(MunicipalWindowLimitError):
        use_case.execute(INE, read_stretches(tramos, INE))
    assert http.calls == []
    assert not out.exists()
    assert _run(tramos, tmp_path / "raw", out, "--sin-red") == 1
    assert not out.exists()
    assert not (tmp_path / "raw").exists()

    # Segundo tope: el manifiesto de más de 3.000.000 bytes no se escribe.
    one = tmp_path / "uno.geojson"
    _write_stretches(one, [_feature("b" * 16, X0, Y0, 80)])
    _populate(tmp_path / "raw2", tmp_path / "poblado", one)
    base = main.build_comparison_use_case(
        tmp_path / "raw2", tmp_path / "o2", offline=True, sleep=lambda _s: None
    ).execute(INE, read_stretches(one, INE))[0]
    grande = replace(base, windows=base.windows * 2500)
    out2 = tmp_path / "grande"
    with pytest.raises(ManifestTooLargeError):
        JsonComparisonManifestWriter(out2).write(INE, [grande])
    assert not out2.exists()


def test_ca4_un_fallo_no_deja_manifiesto_y_el_anterior_sigue(tmp_path: Path) -> None:
    """CA4. Dado un tramo con alguna franja omitida por `fallo` (p. ej. caché ausente con
    `--sin-red`), cuando se ejecuta, entonces sale con 1 y no deja manifiesto nuevo ni a
    medias (el anterior, si lo hay, sigue igual). Una franja `sin_cobertura` o un tramo
    `tramo_demasiado_largo` **no** son fallo: se escriben y se cuentan en la salida."""
    out = tmp_path / "out"
    tramos = _write_stretches(tmp_path / "t.geojson", [_feature("a" * 16, X0, Y0, 80)])
    # Caché vacía + --sin-red: todas las franjas fallan. Sin manifiesto previo, no hay fichero.
    assert _run(tramos, tmp_path / "vacia", out, "--sin-red") == 1
    assert not (out / f"{INE}.json").exists()
    assert list(out.glob("*.tmp")) == []
    # Con manifiesto previo, queda tal cual.
    out.mkdir()
    previo = out / f"{INE}.json"
    previo.write_text('{"previo": true}\n', encoding="utf-8")
    assert _run(tramos, tmp_path / "vacia", out, "--sin-red") == 1
    assert previo.read_text(encoding="utf-8") == '{"previo": true}\n'

    # sin_cobertura (2009, 2006 y 2011 en blanco) y tramo largo no son fallo.
    mixto = _write_stretches(
        tmp_path / "m.geojson",
        [_feature("a" * 16, X0, Y0, 80), _feature("c" * 16, X0, Y0 + 5000, 2000)],
    )
    blancos = {**OK_LAYERS, "PNOA2009": BLANK, "PNOA2006": BLANK, "PNOA2011": BLANK}
    _populate(tmp_path / "raw", tmp_path / "poblado", mixto, blancos)
    assert _run(mixto, tmp_path / "raw", out, "--sin-red") == 0
    tramos_json = _manifest(out)["tramos"]
    por_id = {t["id"]: t for t in tramos_json}
    assert por_id["c" * 16]["estado"] == "tramo_demasiado_largo"
    assert por_id["c" * 16]["ventanas"] == []
    (ventana,) = por_id["a" * 16]["ventanas"]
    assert ventana["omitidas"] == [
        {
            "franja": "2006-2011",
            "motivo": "sin_cobertura",
            "probados": [2009, 2006, 2011],
            "tipo_error": None,
        }
    ]


def test_ca4_la_salida_cuenta_omisiones(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CA4 (salida). Una franja `sin_cobertura` o un tramo `tramo_demasiado_largo` se
    cuentan en la salida."""
    mixto = _write_stretches(
        tmp_path / "m.geojson",
        [_feature("a" * 16, X0, Y0, 80), _feature("c" * 16, X0, Y0 + 5000, 2000)],
    )
    blancos = {**OK_LAYERS, "PNOA2009": BLANK, "PNOA2006": BLANK, "PNOA2011": BLANK}
    _populate(tmp_path / "raw", tmp_path / "poblado", mixto, blancos)
    capsys.readouterr()
    assert _run(mixto, tmp_path / "raw", tmp_path / "out", "--sin-red") == 0
    salida = capsys.readouterr().out
    assert "a" * 16 + ": generada; 1 ventanas, 4 imágenes, 1 omisiones (sin_cobertura=1)" in salida
    assert "c" * 16 + ": tramo_demasiado_largo; 0 ventanas" in salida


def test_ca5_ni_el_nombre_ni_el_contenido_identifican(tmp_path: Path) -> None:
    """CA5. Dado el resultado, cuando se inspeccionan el nombre del fichero y su contenido,
    entonces solo llevan el id opaco del tramo (16 hexadecimales), el código INE y los
    vuelos; ninguna referencia catastral, nombre de finca, paraje ni persona (test que busca
    la forma de referencia catastral y las palabras de `BANNED_WORDS`). Un fichero de tramos
    con un id de otra forma o con geometría fuera de EPSG:25830 hace salir con 1."""
    tramos = _write_stretches(tmp_path / "t.geojson", [_feature("0123456789abcdef", X0, Y0, 80)])
    _populate(tmp_path / "raw", tmp_path / "out", tramos)
    (fichero,) = (tmp_path / "out").iterdir()
    assert fichero.name == f"{INE}.json"
    texto = fichero.read_text(encoding="utf-8")
    assert CADASTRAL_REFERENCE.search(texto) is None
    assert banned_words_in(texto) == ()
    assert BANNED_WORDS  # el test no es vacuo
    assert '"nombre"' not in texto
    assert "0123456789abcdef" in texto

    cache, out = tmp_path / "raw", tmp_path / "salida"
    malos = {
        "id": _write_stretches(tmp_path / "id.geojson", [_feature("28043A001", X0, Y0, 80)]),
        "id_mayuscula": _write_stretches(
            tmp_path / "idm.geojson", [_feature("ABCDEF0123456789", X0, Y0, 80)]
        ),
        "sin_crs": _write_stretches(
            tmp_path / "sc.geojson", [_feature("a" * 16, X0, Y0, 80)], crs=None
        ),
        "otro_crs": _write_stretches(
            tmp_path / "oc.geojson",
            [_feature("a" * 16, X0, Y0, 80)],
            crs={"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
        ),
        "grados": _write_stretches(
            tmp_path / "gr.geojson",
            [_feature("a" * 16, -3, 40, 1)],  # lon/lat con crs 25830
        ),
    }
    for nombre, ruta in malos.items():
        assert _run(ruta, cache, out, "--sin-red") == 1, nombre
    assert not out.exists()


def test_ca6_mismo_lote_mismos_bytes(tmp_path: Path) -> None:
    """CA6. Dado el mismo lote ejecutado dos veces con la misma caché, entonces el
    manifiesto es idéntico byte a byte (JSON con claves ordenadas, UTF-8, fecha tomada del
    sidecar de la caché)."""
    tramos = _write_stretches(
        tmp_path / "t.geojson",
        [_feature("b" * 16, X0, Y0 + 3000, 300), _feature("a" * 16, X0, Y0, 80)],
    )
    _populate(tmp_path / "raw", tmp_path / "primero", tramos)
    assert _run(tramos, tmp_path / "raw", tmp_path / "segundo", "--sin-red") == 0
    assert _run(tramos, tmp_path / "raw", tmp_path / "tercero", "--sin-red") == 0
    primero = (tmp_path / "primero" / f"{INE}.json").read_bytes()
    assert (tmp_path / "segundo" / f"{INE}.json").read_bytes() == primero
    assert (tmp_path / "tercero" / f"{INE}.json").read_bytes() == primero
    texto = primero.decode("utf-8")
    assert json.loads(texto)  # UTF-8 válido
    assert texto.index('"id": "a' + "a" * 15) < texto.index('"id": "b' + "b" * 15)
    # La fecha es la del sidecar (2026-11-26), no la del día de la lectura.
    assert '"fecha_descarga": "2026-11-26"' in texto


@pytest.mark.integration
@pytest.mark.red
def test_ca7_integracion_tramo_real_corto(tmp_path: Path) -> None:
    """CA7. [integración] Dado un tramo real corto del ámbito, cuando se ejecuta con red,
    entonces se cachean en `data/raw/` las cinco franjas (o sus omisiones `sin_cobertura`) y
    el manifiesto apunta a URL que devuelven los mismos sha256; nada se escribe en `site/`."""
    tramos = _write_stretches(tmp_path / "t.geojson", [_feature("a" * 16, X0, Y0, 80)])
    cache, out = tmp_path / "raw", tmp_path / "out"
    assert _run(tramos, cache, out) == 0
    assert list(cache.rglob("*.body"))
    (ventana,) = _manifest(out)["tramos"][0]["ventanas"]
    franjas = {i["franja"] for i in ventana["imagenes"]} | {
        o["franja"] for o in ventana["omitidas"] if o["motivo"] == "sin_cobertura"
    }
    assert franjas == {"1956-1957", "1997-2003", "2006-2011", "2014-2020", "reciente"}
    for imagen in ventana["imagenes"]:
        respuesta = requests.get(
            imagen["procedencia"]["url"],
            timeout=60,
            headers={"User-Agent": "parcel-intel-verificacion/0.1"},
        )
        respuesta.raise_for_status()
        assert hashlib.sha256(respuesta.content).hexdigest() == imagen["sha256"]
    assert not Path("site/datos/comparacion").exists()


def test_ca8_el_comando_figura_en_claude_md() -> None:
    """CA8. Dado el cambio, entonces el comando figura en `CLAUDE.md`, y `ruff`, `mypy`,
    `lint-imports` y `pytest` siguen en verde, con un test de aceptación por criterio en
    `tests/acceptance/test_historia_122.py`."""
    texto = (Path(__file__).parents[2] / "CLAUDE.md").read_text(encoding="utf-8")
    assert "imagenes-comparacion --municipio" in texto
    assert "--tramos" in texto
