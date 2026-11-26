"""Historia #121: caso de uso de imágenes de comparación de un tramo (ADR 0042)."""

import dataclasses
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.application.build_comparison_images import BuildComparisonImagesUseCase
from parcel_intel.domain.comparison_image import (
    COMPARISON_POLICY,
    COMPARISON_SLOTS,
    DECLARED_GAPS,
    FLIGHTS,
    ComparisonImage,
    ComparisonWindow,
    DegenerateStretchError,
    StretchComparison,
    StretchRequest,
    comparison_windows,
    stretch_pixels,
)
from parcel_intel.domain.geometry import MultiLineGeometry
from parcel_intel.domain.orthophoto import HistoricalVintage, Orthophoto, OrthophotoWindow
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.ports.errors import OrthophotoNotCoveredError

pytestmark = pytest.mark.acceptance

X0, Y0 = 470000.0, 4440000.0
SID = "0123456789abcdef"
REGISTRY = Path(__file__).parents[2] / "src/parcel_intel/sources/REGISTRY.md"

Line = tuple[tuple[float, float], ...]


def _line(length: float, x0: float = X0) -> Line:
    return ((x0, Y0), (x0 + length, Y0))


def _stretch(*lines: Line) -> MultiLineGeometry:
    return MultiLineGeometry(lines=tuple(lines), srid=25830)


def _request(*lines: Line) -> StretchRequest:
    return StretchRequest(SID, "28043", _stretch(*lines))


class FakePort:
    def __init__(
        self,
        not_covered: set[HistoricalVintage] | None = None,
        fail: dict[HistoricalVintage, Exception] | None = None,
    ) -> None:
        self.not_covered = not_covered or set()
        self.fail = fail or {}
        self.calls: list[tuple[OrthophotoWindow, HistoricalVintage]] = []

    def get_orthophoto_window(
        self, window: OrthophotoWindow, vintage: HistoricalVintage
    ) -> Orthophoto:
        self.calls.append((window, vintage))
        if vintage in self.fail:
            raise self.fail[vintage]
        if vintage in self.not_covered:
            raise OrthophotoNotCoveredError(vintage)
        return Orthophoto(
            image=b"\xff\xd8" + str(vintage).encode(),
            vintage=vintage,
            provenance=Provenance(
                "pnoa-historico",
                f"https://wms/{vintage}",
                date(2026, 11, 26),
                "CC BY 4.0",
                Redistribution.PUBLIC,
            ),
        )


def test_ca1_cinco_imagenes_en_orden_con_procedencia_y_huecos() -> None:
    """Dado un tramo de una sola ventana y un doble del port que devuelve imagen para todos
    los vuelos, cuando se ejecuta el caso de uso, entonces devuelve 5 imágenes en el orden de
    `COMPARISON_SLOTS`, cada una con franja, vuelo, periodo, resolución, atribución «Obra
    derivada de <cadena SCNE del ADR §3>», sha256, bytes y la `Provenance` que dio el port, y
    el resultado lleva `DECLARED_GAPS` (1957–1997) y `COMPARISON_POLICY`."""
    result = BuildComparisonImagesUseCase(FakePort()).execute(_request(_line(80)))
    assert result.status == "generada"
    assert len(result.windows) == 1
    images = result.windows[0].images
    assert [i.slot for i in images] == [
        "1956-1957",
        "1997-2003",
        "2006-2011",
        "2014-2020",
        "reciente",
    ]
    assert [s.name for s in COMPARISON_SLOTS] == [i.slot for i in images]
    assert [i.vintage for i in images] == ["AMS_1956-1957", "SIGPAC", 2009, 2017, 2023]
    first, last = images[0], images[-1]
    assert first.period == "1956-1957"
    assert first.resolution_m == 0.5
    assert first.attribution == (
        "Obra derivada de Orto-AMS 1956-1957 CC-BY 4.0 ejercito.defensa.gob.es"
    )
    assert last.attribution == "Obra derivada de PNOA 2023 CC-BY 4.0 scne.es"
    assert last.resolution_m == 0.25
    assert first.byte_size == len(b"\xff\xd8AMS_1956-1957")
    assert len(first.sha256) == 64
    assert first.provenance.url == "https://wms/AMS_1956-1957"
    assert first.provenance.redistribution is Redistribution.PUBLIC
    assert result.gaps == DECLARED_GAPS
    assert (DECLARED_GAPS[0].from_year, DECLARED_GAPS[0].to_year) == (1957, 1997)
    assert result.policy == COMPARISON_POLICY
    assert result.windows[0].omitted == ()


def test_ca2_vuelo_sin_cobertura_prueba_el_siguiente() -> None:
    """Dado un doble que lanza `OrthophotoNotCoveredError` para `2009` y `2006` y devuelve
    imagen para `2011`, cuando se ejecuta, entonces la franja `2006-2011` trae la imagen de
    2011 y el doble recibió las peticiones en el orden 2009, 2006, 2011; y si tampoco cubre
    2011, la franja sale en `omitted` con motivo `sin_cobertura` y `tried == (2009, 2006,
    2011)`."""
    port = FakePort(not_covered={2009, 2006})
    result = BuildComparisonImagesUseCase(port).execute(_request(_line(80)))
    slot = [i for i in result.windows[0].images if i.slot == "2006-2011"]
    assert [i.vintage for i in slot] == [2011]
    assert [v for _, v in port.calls if v in (2009, 2006, 2011)] == [2009, 2006, 2011]

    port2 = FakePort(not_covered={2009, 2006, 2011})
    omitted = BuildComparisonImagesUseCase(port2).execute(_request(_line(80))).windows[0].omitted
    assert len(omitted) == 1
    assert omitted[0].slot == "2006-2011"
    assert omitted[0].reason == "sin_cobertura"
    assert omitted[0].tried == (2009, 2006, 2011)
    assert omitted[0].error_type is None


def test_ca3_fallo_no_prueba_alternativas() -> None:
    """Dado un doble que lanza otra excepción (p. ej. `ConnectionError`) para `SIGPAC`,
    cuando se ejecuta, entonces la franja `1997-2003` sale con motivo `fallo` y el nombre del
    tipo de error, **no** se pide `OLISTAT`, y las otras cuatro franjas se devuelven."""
    port = FakePort(fail={"SIGPAC": ConnectionError("secreto")})
    window = BuildComparisonImagesUseCase(port).execute(_request(_line(80))).windows[0]
    assert [o.slot for o in window.omitted] == ["1997-2003"]
    assert window.omitted[0].reason == "fallo"
    assert window.omitted[0].error_type == "ConnectionError"
    assert window.omitted[0].tried == ("SIGPAC",)
    assert "OLISTAT" not in [v for _, v in port.calls]
    assert len(window.images) == 4


ORACLES = [
    (80, [(469928, 4439888, 470152, 4440112, 448)]),
    (300, [(469942, 4439792, 470358, 4440208, 832)]),
    (
        1000,
        [
            (469949, 4439744, 470461, 4440256, 1024),
            (470364, 4439744, 470876, 4440256, 1024),
            (470771, 4439856, 471059, 4440144, 576),
        ],
    ),
]


def _tuples(windows: tuple[OrthophotoWindow, ...] | None) -> list[tuple[int, ...]]:
    assert windows is not None
    return [(w.min_x, w.min_y, w.max_x, w.max_y, w.width_px) for w in windows]


def test_ca4_oraculos_del_adr() -> None:
    """Dados los tramos de la tabla de oráculos del ADR §2 (80 m, 300 m, 1000 m, 2000 m,
    multiparte separado), cuando se calculan sus ventanas con `comparison_windows`, entonces
    salen exactamente esos bbox enteros y tamaños en píxeles; el de 2000 m da
    `tramo_demasiado_largo`, sin ventanas y sin ninguna llamada al port."""
    for length, expected in ORACLES:
        windows = comparison_windows(_stretch(_line(length)))
        assert _tuples(windows) == expected
        assert windows is not None
        assert all(w.width_px == w.height_px for w in windows)
    multi = comparison_windows(_stretch(_line(50), _line(50, X0 + 3000)))
    assert _tuples(multi) == [
        (469913, 4439888, 470137, 4440112, 448),
        (472913, 4439888, 473137, 4440112, 448),
    ]
    assert comparison_windows(_stretch(_line(2000))) is None
    port = FakePort()
    result = BuildComparisonImagesUseCase(port).execute(_request(_line(2000)))
    assert result.status == "tramo_demasiado_largo"
    assert result.windows == ()
    assert port.calls == []
    assert result.gaps == DECLARED_GAPS


def test_ca5_todo_punto_de_todas_las_partes_dentro_con_margen() -> None:
    """Dado un tramo multiparte, cuando se calculan sus ventanas, entonces todo punto
    densificado (paso 5 m) de **todas** las partes cae dentro de alguna ventana a ≥ 49 m de
    su borde (no solo la primera parte; lección 0001)."""
    lines: tuple[Line, ...] = (
        ((X0, Y0), (X0 + 333.3, Y0 + 77.7), (X0 + 500.5, Y0 + 300.1)),
        ((X0 + 3000.2, Y0 - 40.4), (X0 + 3200.9, Y0 + 90.6)),
        ((X0 - 2000.0, Y0 + 5000.0), (X0 - 1900.0, Y0 + 5100.0)),
    )
    windows = comparison_windows(_stretch(*lines))
    assert windows is not None
    for line in lines:
        for (ax, ay), (bx, by) in zip(line, line[1:], strict=False):
            n = int(max(abs(bx - ax), abs(by - ay)) / 5) + 1
            for i in range(n + 1):
                x, y = ax + (bx - ax) * i / n, ay + (by - ay) * i / n
                assert any(
                    min(x - w.min_x, w.max_x - x, y - w.min_y, w.max_y - y) >= 49 for w in windows
                ), (x, y)


@pytest.mark.parametrize(
    "lines",
    [(), (((X0, Y0),),), (((X0, Y0), (X0, Y0)),)],
)
def test_ca6_tramo_degenerado(lines: tuple[Line, ...]) -> None:
    """Dado un tramo con `lines=()`, con una sola parte de un punto o con una parte de dos
    puntos iguales, cuando se ejecuta, entonces lanza `DegenerateStretchError` y el doble no
    recibió ninguna petición."""
    port = FakePort()
    with pytest.raises(DegenerateStretchError):
        BuildComparisonImagesUseCase(port).execute(_request(*lines))
    assert port.calls == []


def test_ca7_pixeles_del_trazado() -> None:
    """Dado el tramo de 80 m del oráculo, cuando se calculan los píxeles del trazado,
    entonces son `((144.0, 224.0), …, (304.0, 224.0))` en una ventana de 448×448; y en un
    multiparte cada parte da su propia lista de píxeles."""
    stretch = _stretch(_line(80))
    (window,) = comparison_windows(stretch) or ()
    assert (window.width_px, window.height_px) == (448, 448)
    assert stretch_pixels(stretch, window) == (((144.0, 224.0), (304.0, 224.0)),)
    multi = _stretch(_line(50), _line(50, X0 + 3000))
    windows = comparison_windows(multi)
    assert windows is not None
    px = stretch_pixels(multi, windows[0])
    assert len(px) == 2
    assert px[0][0] == (round((X0 - windows[0].min_x) / 0.5, 1), 224.0)


@pytest.mark.parametrize(
    "stretch_id",
    ["", "0123456789ABCDEF", "28043A0010000100", "28043A001000010000XX", "0123456789abcde"],
)
def test_ca8_id_invalido(stretch_id: str) -> None:
    """Dado un `StretchRequest` con un id que no son 16 hexadecimales en minúscula (vacío,
    con forma de referencia catastral de 14 o 20 caracteres, con mayúsculas), un municipio
    que no son 5 dígitos o un `srid` distinto de 25830, cuando se construye, entonces lanza
    `ValueError`."""
    with pytest.raises(ValueError):
        StretchRequest(stretch_id, "28043", _stretch(_line(80)))


def test_ca8_municipio_y_srid_invalidos_y_campos_exactos() -> None:
    """... un municipio que no son 5 dígitos o un `srid` distinto de 25830 ... y un test fija
    la lista exacta de `dataclasses.fields` de `StretchRequest`, `ComparisonImage`,
    `ComparisonWindow` y `StretchComparison`, sin ningún campo de titularidad, referencia
    catastral ni nombre."""
    for code in ("2804", "280431", "abcde", ""):
        with pytest.raises(ValueError):
            StretchRequest(SID, code, _stretch(_line(80)))
    with pytest.raises(ValueError):
        StretchRequest(SID, "28043", MultiLineGeometry(lines=(_line(80),), srid=4326))

    def names(cls: type) -> list[str]:
        return [f.name for f in dataclasses.fields(cls)]

    assert names(StretchRequest) == ["stretch_id", "municipality_code", "stretch"]
    assert names(ComparisonImage) == [
        "slot",
        "vintage",
        "period",
        "resolution_m",
        "attribution",
        "sha256",
        "byte_size",
        "provenance",
    ]
    assert names(ComparisonWindow) == ["window", "stretch_px", "images", "omitted"]
    assert names(StretchComparison) == [
        "stretch_id",
        "municipality_code",
        "policy",
        "status",
        "windows",
        "gaps",
    ]


def test_ca9_determinista_y_orden_de_partes() -> None:
    """Dado el mismo tramo dos veces con el mismo doble, cuando se ejecuta, entonces los
    resultados son iguales (`==`), y en otro orden de partes el orden de ventanas sigue el
    de las partes de entrada."""
    a, b = _line(50), _line(50, X0 + 3000)
    r1 = BuildComparisonImagesUseCase(FakePort()).execute(_request(a, b))
    r2 = BuildComparisonImagesUseCase(FakePort()).execute(_request(a, b))
    assert r1 == r2
    swapped = BuildComparisonImagesUseCase(FakePort()).execute(_request(b, a))
    assert [w.window for w in swapped.windows] == [w.window for w in reversed(r1.windows)]


def test_ca10_atribuciones_literales_en_el_registro() -> None:
    """Dado `FLIGHTS`, cuando se compara con `REGISTRY.md`, entonces cada cadena de
    atribución del ADR §3 aparece literal en el registro (test de coherencia)."""
    text = REGISTRY.read_text(encoding="utf-8")
    assert len(FLIGHTS) == 10
    for flight in FLIGHTS.values():
        assert flight.attribution in text, flight.attribution


def test_ca11_este_fichero_cubre_cada_criterio() -> None:
    """Dado el cambio, entonces `lint-imports`, `mypy`, `ruff check .` y `pytest` siguen en
    verde (lo ejecuta CI), con un test de aceptación por criterio en este fichero."""
    nombres = {n.split("_")[1] for n in globals() if n.startswith("test_ca")}
    assert nombres == {f"ca{k}" for k in range(1, 12)}
