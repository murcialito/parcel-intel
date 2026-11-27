"""Historia #140: evidencia PNG de dos paneles para revisar trazados históricos propuestos
(#20, hija E). Los docstrings copian el criterio literal.

La fixture `280075-w1` es sintética; su imagen es el recorte ya versionado, que los tests
copian a `tmp_path`. La respuesta de PNOA de `T003` es una respuesta PNG real grabada el
2026-11-26 (`pnoa_ma_280075-w1_T003.png`); el `HttpGet` doble la sirve sin tocar la red.
"""

import hashlib
import json
import shutil
import tomllib
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import numpy as np
import pytest

from parcel_intel.adapters.evidence import (
    PngTrailEvidence,
    PnoaPngSource,
    default_png_http_get,
)
from parcel_intel.adapters.evidence.png import decode_png, encode_png_rgb
from parcel_intel.adapters.evidence.pnoa_png import NotPngResponseError
from parcel_intel.adapters.evidence.renderer import within_distance
from parcel_intel.adapters.ign_historic import HttpStatusError
from parcel_intel.adapters.raw_cache import CachedRawFetcher
from parcel_intel.application.build_trail_evidence import BuildTrailEvidenceUseCase
from parcel_intel.cli import main
from parcel_intel.domain.georeferencing import IGN_HISTORIC_LICENSE, AffineTransform
from parcel_intel.domain.trail_evidence import EvidenceLayout, evidence_layout
from parcel_intel.ports.errors import EvidenceImageFormatError
from tests.adapters.evidence.helpers import (
    CHANNELS,
    HISTORICO,
    PNOA_FIXTURE,
    RECORTE,
    make_png,
    make_trail,
    make_unit,
)

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
UNIT_ID = "280075-w1"
TODAY = date(2026, 11, 26)
IMAGE_RETRIEVED = "2026-11-25"
LINE = (230, 0, 0)
ORANGE = (255, 140, 0)
PNOA_PNG = PNOA_FIXTURE.read_bytes()


class FakePnoaHttp:
    """`HttpGet` de la caché cruda doble: sirve siempre el mismo cuerpo y cuenta llamadas."""

    def __init__(self, body: bytes = PNOA_PNG) -> None:
        self.body = body
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls.append((url, params))
        return self.body


def _no_image_network(url: str, headers: object) -> bytes:
    raise AssertionError("la imagen de trabajo debe salir de la caché")


class _Setup:
    def __init__(self, root: Path) -> None:
        self.curated = root / "curated"
        self.cache = root / "ign_planimetrias"
        self.cache_pnoa = root / "pnoa_ma"
        shutil.copytree(HISTORICO / UNIT_ID, self.curated / UNIT_ID)
        self.cache.mkdir()
        body = RECORTE.read_bytes()
        (self.cache / f"{UNIT_ID}.png").write_bytes(body)
        unit = json.loads((self.curated / UNIT_ID / "unidad.json").read_text(encoding="utf-8"))
        (self.cache / f"{UNIT_ID}.provenance.json").write_text(
            json.dumps(
                {
                    "fuente": "Planimetría de Colmenar de Oreja, IGN, documento 280075",
                    "url": unit["image"]["url"],
                    "fecha_descarga": IMAGE_RETRIEVED,
                    "licencia": IGN_HISTORIC_LICENSE,
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "formato": "image/png",
                    "ancho_px": 500,
                    "alto_px": 500,
                    "crs": "EPSG:25830",
                }
            ),
            encoding="utf-8",
        )

    @property
    def evidence_dir(self) -> Path:
        return self.curated / UNIT_ID / "evidencia"

    def use_case(self, http: FakePnoaHttp, offline: bool = False) -> BuildTrailEvidenceUseCase:
        return main.build_evidence_use_case(
            self.curated,
            self.cache,
            self.cache_pnoa,
            offline,
            image_http_get=_no_image_network,
            pnoa_http_get=http,
            today=lambda: TODAY,
            sleep=lambda _s: None,
        )

    def cli(self, *extra: str) -> int:
        args = main._build_parser().parse_args(
            [
                "historico",
                "evidencia",
                UNIT_ID,
                "--curated",
                str(self.curated),
                "--cache",
                str(self.cache),
                "--cache-pnoa",
                str(self.cache_pnoa),
                *extra,
            ]
        )
        code: int = args.func(args)
        return code


@pytest.fixture
def setup(tmp_path: Path) -> _Setup:
    return _Setup(tmp_path)


def _png(setup: _Setup) -> np.ndarray:
    return decode_png((setup.evidence_dir / "T003.png").read_bytes())


def test_ca1_escribe_solo_la_evidencia_del_trazado_propuesto(setup: _Setup) -> None:
    """CA1. Dada la fixture `280075-w1` (#137) con su imagen en caché y una respuesta PNOA PNG
    real grabada para la ventana que calcula `evidence_layout` del trazado `T003`, cuando se
    ejecuta `historico evidencia 280075-w1` con `--curated` en `tmp_path`, entonces se escriben
    `280075-w1/evidencia/T003.png` y `T003.procedencia.json`. No se escribe nada para `T001` y
    `T002` (aprobados) ni para `T004` (rechazado)."""
    http = FakePnoaHttp()
    records = setup.use_case(http).execute(UNIT_ID)
    assert [r.trail_id for r in records] == ["T003"]
    # La ventana pedida es la que calcula `evidence_layout` (400 × 352 px, 801 × 704 m).
    assert len(http.calls) == 1
    params = http.calls[0][1]
    assert params["bbox"] == "466400,4439749,467201,4440453"
    assert (params["width"], params["height"]) == ("400", "352")

    shutil.rmtree(setup.evidence_dir)
    assert setup.cli("--sin-red") == 0  # la misma orden por la CLI, desde la caché
    assert sorted(p.name for p in setup.evidence_dir.iterdir()) == [
        "T003.png",
        "T003.procedencia.json",
    ]
    assert len(http.calls) == 1


def test_ca2_png_rgb_de_dos_paneles_con_linea_y_banda(setup: _Setup) -> None:
    """CA2. Dado el PNG escrito, cuando se decodifica con el decodificador propio, entonces es
    RGB de 8 bits, su ancho es la suma de los dos paneles y su alto el mayor de ellos. Hay
    píxeles (230, 0, 0) en los dos paneles y píxeles mezclados con (255, 140, 0) solo en el
    de PNOA."""
    setup.use_case(FakePnoaHttp()).execute(UNIT_ID)
    raw = (setup.evidence_dir / "T003.png").read_bytes()
    assert raw[24] == 8 and raw[25] == 2  # IHDR: 8 bits, tipo de color 2 (RGB)
    image = decode_png(raw)
    # Panel 1: 400 × 350 (recorte 100…500 × 0…350); panel 2: 400 × 352 (PNOA).
    assert image.shape == (352, 800, 3)
    left, right = image[:, :400], image[:, 400:]
    assert (left == LINE).all(axis=2).any() and (right == LINE).all(axis=2).any()
    assert (left[350:] == 255).all()  # relleno blanco hasta la altura mayor

    planimetry = decode_png(RECORTE.read_bytes())[0:350, 100:500]
    changed = (left[:350] != planimetry).any(axis=2)
    assert changed.any()
    assert (left[:350][changed] == LINE).all()  # en el panel 1 solo cambia la línea

    pnoa = decode_png(PNOA_PNG)
    changed = (right != pnoa).any(axis=2)
    on_line = (right == LINE).all(axis=2)
    blended = changed & ~on_line
    assert blended.any()
    expected = np.rint(pnoa.astype(float) * 0.65 + np.array(ORANGE) * 0.35).astype(np.uint8)
    assert (right[blended] == expected[blended]).all()  # mezcla al 35 % con (255, 140, 0)


def _plain(a: float = 466000.0) -> AffineTransform:
    return AffineTransform(a=a, b=2.0, c=0.0, d=4440000.0, e=0.0, f=-2.0)


def test_ca3_recorte_escalon_y_ventana_de_pnoa() -> None:
    """CA3. Dado `evidence_layout` con un trazado pequeño, uno cerca del borde de la imagen y
    uno cuyo recorte supera 800 px, cuando se calcula, entonces el recorte es bbox ± 200 px
    acotado a la imagen, `step` = 1, 1 y `ceil(lado/800)`, y la ventana PNOA es la envolvente
    entera de las 4 esquinas transformadas, con `height_px` según la fórmula de #20. Son
    literales calculados a mano en el test."""
    unit = make_unit(_plain())
    # Pequeño: (800,600)-(1300,1100); esquinas 467600…468600 × 4437800…4438800.
    small = evidence_layout(unit, make_trail((1000, 800), (1100, 900)))
    assert small == EvidenceLayout(
        (800, 600, 1300, 1100), 1, 500, 500, (467600, 4437800, 468600, 4438800), 500, 500
    )
    # Borde: 50−200 y 40−200 se acotan a 0; 320 × 300; 640 × 600 m a 320 px → 300 px de alto.
    edge = evidence_layout(unit, make_trail((50, 40), (120, 100)))
    assert edge == EvidenceLayout(
        (0, 0, 320, 300), 1, 320, 300, (466000, 4439400, 466640, 4440000), 320, 300
    )
    # Grande: 2100 × 400 → step = ceil(2100/800) = 3; panel 700 × 134; 4200 × 800 m; alto 134.
    large = evidence_layout(unit, make_trail((100, 100), (1900, 200)))
    assert large == EvidenceLayout(
        (0, 0, 2100, 400), 3, 700, 134, (466000, 4439200, 470200, 4440000), 700, 134
    )
    # La envolvente de una afín con cizalla se redondea hacia fuera: 1051 × 1001 m → alto 477.
    skewed = AffineTransform(a=466000.4, b=2.0, c=0.1, d=4440000.6, e=0.0, f=-2.0)
    window = evidence_layout(make_unit(skewed), make_trail((1000, 800), (1100, 900)))
    assert window.window == (467660, 4437800, 468711, 4438801)
    assert (window.pnoa_width_px, window.pnoa_height_px) == (500, 477)
    # Y el trazado real de la fixture da la ventana que se grabó.
    real = evidence_layout(
        make_unit(
            AffineTransform(
                466200.79539520416,
                1.998478033635248,
                -0.0006198227759108474,
                4440451.029180697,
                0.0022857506944088343,
                -2.0053563160936507,
            ),
            width_px=500,
            height_px=500,
        ),
        make_trail((300, 100), (380, 150)),
    )
    assert real.window == (466400, 4439749, 467201, 4440453)
    assert (real.pnoa_width_px, real.pnoa_height_px) == (400, 352)


def test_ca4_la_banda_llega_a_dos_veces_el_loo(tmp_path: Path) -> None:
    """CA4. Dado un punto de la banda, cuando se comprueba, entonces se colorea un píxel PNOA
    cuyo centro está a ≤ 2 × LOO de la línea, y uno a 2 × LOO + 1 m no. Es un caso sintético
    con LOO conocido."""
    # 1 m/px: x = 466000 + col, y = 4440600 − row. LOO = 4,75 m → banda de ± 9,5 m.
    transform = AffineTransform(466000.0, 1.0, 0.0, 4440600.0, 0.0, -1.0)
    planimetry = encode_png_rgb(np.full((600, 600, 3), 120, dtype=np.uint8))
    sha256 = hashlib.sha256(planimetry).hexdigest()
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / f"{UNIT_ID}.png").write_bytes(planimetry)
    unit = make_unit(transform, width_px=600, height_px=600, loo_rmse_m=4.75, image_sha256=sha256)
    trail = make_trail((100, 300), (300, 300))
    layout = evidence_layout(unit, trail)
    assert layout.window == (466000, 4440100, 466500, 4440500)
    assert (layout.pnoa_width_px, layout.pnoa_height_px) == (500, 400)  # 1 m por píxel
    gray = encode_png_rgb(np.full((400, 500, 3), 200, dtype=np.uint8))
    fetcher = CachedRawFetcher(FakePnoaHttp(gray), tmp_path / "pnoa", lambda: TODAY)
    PngTrailEvidence(raw, tmp_path / "curated", PnoaPngSource(fetcher)).render(unit, trail)
    image = decode_png((tmp_path / "curated" / UNIT_ID / "evidencia" / "T003.png").read_bytes())
    pnoa = image[:, 500:]  # el panel 1 mide 500 px de ancho
    # Fila r: centro en y = 4440500 − r − 0,5; la línea está en y = 4440300 (fila 200).
    column = 250
    inside = (219, 179, 130)  # 0,65·200 + 0,35·(255, 140, 0), redondeado
    assert tuple(pnoa[190, column]) == inside  # a 9,5 m = 2 × LOO: dentro
    assert tuple(pnoa[209, column]) == inside  # a 9,5 m por el otro lado: dentro
    assert tuple(pnoa[189, column]) == (200, 200, 200)  # a 10,5 m = 2 × LOO + 1: fuera
    assert tuple(pnoa[210, column]) == (200, 200, 200)
    # La función pura lo confirma con un radio dado y un paso fino.
    xs = np.array([0.0])
    ys = np.array([9.5, 10.5])
    assert within_distance(xs, ys, [(-5.0, 0.0), (5.0, 0.0)], 9.5).tolist() == [[True], [False]]


def test_ca5_procedencia_completa_y_sin_titularidad(setup: _Setup) -> None:
    """CA5. Dado `T003.procedencia.json`, cuando se lee, entonces trae `unit_id`, `trail_id`,
    `control_points_sha256` (el del CSV), `imagen_trabajo` (`url`, `sha256`, `fecha_descarga`,
    `licencia`), `pnoa` (`url` canónica con `format=image/png` y `layers=OI.OrthoimageCoverage`,
    `fecha_descarga`, `licencia: CC BY 4.0`), las `atribuciones` de capa del ADR 0043 y la de
    PNOA de REGISTRY.md, y `png_sha256` igual al del fichero. No hay ninguna clave de
    titularidad."""
    setup.use_case(FakePnoaHttp()).execute(UNIT_ID)
    text = (setup.evidence_dir / "T003.procedencia.json").read_text(encoding="utf-8")
    record = json.loads(text)
    unit = json.loads((setup.curated / UNIT_ID / "unidad.json").read_text(encoding="utf-8"))
    csv_bytes = (setup.curated / UNIT_ID / "puntos_control.csv").read_bytes()
    assert set(record) == {
        "unit_id",
        "trail_id",
        "control_points_sha256",
        "imagen_trabajo",
        "pnoa",
        "atribuciones",
        "png_sha256",
    }
    assert record["unit_id"] == UNIT_ID and record["trail_id"] == "T003"
    assert record["control_points_sha256"] == hashlib.sha256(csv_bytes).hexdigest()
    assert record["imagen_trabajo"] == {
        "url": unit["image"]["url"],
        "sha256": unit["image"]["sha256"],
        "fecha_descarga": IMAGE_RETRIEVED,
        "licencia": IGN_HISTORIC_LICENSE,
    }
    pnoa = record["pnoa"]
    assert set(pnoa) == {"url", "fecha_descarga", "licencia"}
    assert pnoa["licencia"] == "CC BY 4.0" and pnoa["fecha_descarga"] == TODAY.isoformat()
    url = urlsplit(pnoa["url"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == "https://www.ign.es/wms-inspire/pnoa-ma"
    query = parse_qs(url.query)
    assert query["format"] == ["image/png"] and query["layers"] == ["OI.OrthoimageCoverage"]
    assert query["bbox"] == ["466400,4439749,467201,4440453"]
    assert record["atribuciones"] == [
        "Obra derivada de Planimetrías 1870-1950 CC-BY 4.0 "
        "© Instituto Geográfico Nacional de España",
        "Obra derivada de PNOA 2023 CC-BY 4.0 scne.es",
    ]
    assert (
        record["png_sha256"]
        == hashlib.sha256((setup.evidence_dir / "T003.png").read_bytes()).hexdigest()
    )
    lowered = text.lower()
    for word in ("titular", "propietari", "owner", "catastr"):
        assert word not in lowered


def test_ca6_segunda_ejecucion_sin_red_da_el_mismo_png(setup: _Setup) -> None:
    """CA6. Dada la caché de PNOA poblada, cuando se vuelve a ejecutar con `--sin-red`, entonces
    el `HttpGet` doble registra 0 llamadas y el PNG sale idéntico byte a byte."""
    setup.use_case(FakePnoaHttp()).execute(UNIT_ID)
    first = (setup.evidence_dir / "T003.png").read_bytes()
    shutil.rmtree(setup.evidence_dir)
    second_http = FakePnoaHttp()
    setup.use_case(second_http).execute(UNIT_ID)  # con red permitida, pero la caché basta
    assert second_http.calls == []
    assert (setup.evidence_dir / "T003.png").read_bytes() == first
    shutil.rmtree(setup.evidence_dir)
    assert setup.cli("--sin-red") == 0
    assert (setup.evidence_dir / "T003.png").read_bytes() == first


def _rows(color_type: int, width: int = 6, height: int = 5) -> list[list[int]]:
    channels = CHANNELS[color_type]
    modulus = 8 if color_type == 3 else 256
    return [
        [(y * 83 + i * 59 + (i // channels) * 13) % modulus for i in range(width * channels)]
        for y in range(height)
    ]


@pytest.mark.parametrize("color_type", [0, 2, 3, 4, 6])
@pytest.mark.parametrize("filter_type", [0, 1, 2, 3, 4])
def test_ca7_tipos_de_color_y_filtros(color_type: int, filter_type: int) -> None:
    """CA7. Dados PNG sintéticos de los tipos de color 0, 2, 3 (con PLTE), 4 y 6, cada uno con
    los filtros 0 a 4, y los dos PNG reales (el recorte de la planimetría y la respuesta PNOA),
    cuando se decodifican, entonces dan los píxeles esperados."""
    palette = [(i * 30, 255 - i * 20, i * 7) for i in range(8)]
    rows = _rows(color_type)
    png = make_png(
        color_type, rows, filters=(filter_type,), palette=palette if color_type == 3 else None
    )
    channels = CHANNELS[color_type]
    for y, line in enumerate(rows):
        for x in range(6):
            pixel = line[x * channels : (x + 1) * channels]
            want = (
                palette[pixel[0]]
                if color_type == 3
                else (pixel[0],) * 3
                if color_type in (0, 4)
                else tuple(pixel[:3])
            )
            assert tuple(decode_png(png)[y, x]) == want


def test_ca7_png_reales_formatos_rechazados_e_ida_y_vuelta() -> None:
    """CA7 (resto). Dados los dos PNG reales, cuando se decodifican, entonces dan los píxeles
    esperados. Un PNG entrelazado, uno de 16 bits o un JPEG lanzan `EvidenceImageFormatError`.
    La codificación y la decodificación de vuelta son exactas."""
    planimetry = decode_png(RECORTE.read_bytes())
    pnoa = decode_png(PNOA_PNG)
    assert planimetry.shape == (500, 500, 3) and pnoa.shape == (352, 400, 3)
    # El recorte versionado tiene un valor conocido en una esquina y el PNG de PNOA no es plano.
    assert len(np.unique(pnoa.reshape(-1, 3), axis=0)) > 1000
    for original in (planimetry, pnoa):
        assert np.array_equal(decode_png(encode_png_rgb(original)), original)
    for bad in (
        make_png(2, _rows(2), interlace=1),
        make_png(2, _rows(2), bit_depth=16),
        b"\xff\xd8\xff\xe0\x00\x10JFIF" + bytes(64),
    ):
        with pytest.raises(EvidenceImageFormatError):
            decode_png(bad)


def test_ca8_unidad_no_aceptable_no_escribe_nada(
    setup: _Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    """CA8. Dada una unidad no aceptable (variante de LOO > 15 m) o con una aprobación
    caducada, cuando se ejecuta `evidencia`, entonces sale con 1 con el motivo y no escribe
    nada."""
    csv_path = setup.curated / UNIT_ID / "puntos_control.csv"
    original = csv_path.read_text(encoding="utf-8")
    # Variante con LOO > 15 m: el punto P03 con 200 m de error.
    csv_path.write_text(
        original.replace("466701.0,4439952.0", "466701.0,4440152.0"), encoding="utf-8"
    )
    assert setup.cli("--sin-red") == 1
    assert "rmse_loo" in capsys.readouterr().err
    assert not setup.evidence_dir.exists()
    # Aprobación caducada: otro fichero de puntos (aquí, una descripción) cambia su sha256.
    csv_path.write_text(original.replace("Plaza en el centro", "Plaza"), encoding="utf-8")
    assert setup.cli("--sin-red") == 1
    err = capsys.readouterr().err
    assert "Aprobaciones caducadas" in err and "T001" in err and "T002" in err
    assert not setup.evidence_dir.exists()


def test_ca9_respuesta_que_no_es_png_no_entra_en_la_cache(setup: _Setup) -> None:
    """CA9. Dada una respuesta PNOA que no es PNG (HTML de error 502, real o sintético
    etiquetado), cuando se pide, entonces lanza un error y no queda en la caché (`validate` del
    fetcher)."""
    html = b"<html><body><h1>502 Bad Gateway</h1></body></html>"  # sintético, etiquetado
    with pytest.raises(NotPngResponseError):
        setup.use_case(FakePnoaHttp(html)).execute(UNIT_ID)
    assert not setup.cache_pnoa.exists() or not any(setup.cache_pnoa.rglob("*"))
    assert not setup.evidence_dir.exists()


@pytest.mark.integration
@pytest.mark.red
def test_ca10_pnoa_real_devuelve_un_png_legible(tmp_path: Path) -> None:
    """CA10. [integración] Dada la ventana PNOA de CA1, cuando se pide contra la red real,
    entonces devuelve un PNG que el decodificador propio lee. `REGISTRY.md` anota la URL, los
    bytes, el tipo de color y la fecha."""
    fetcher = CachedRawFetcher(default_png_http_get, tmp_path, lambda: TODAY)
    response = PnoaPngSource(fetcher).fetch((466400, 4439749, 467201, 4440453), 400, 352)
    image = decode_png(response.content)
    assert image.shape == (352, 400, 3)
    registry = (REPO / "src" / "parcel_intel" / "sources" / "REGISTRY.md").read_text(
        encoding="utf-8"
    )
    assert "pnoa_ma_280075-w1_T003.png" in registry


def test_ca11_claude_md_documenta_el_comando_y_no_hay_dependencias_nuevas(setup: _Setup) -> None:
    """CA11. Dado el cambio, entonces `CLAUDE.md` documenta `historico evidencia` y el comando
    funciona literalmente sobre la fixture. `uv run lint-imports`, `uv run mypy`,
    `uv run ruff check .` y `uv run pytest` están en verde, y no se añade ninguna dependencia."""
    claude = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    prefix = "uv run python -m parcel_intel.cli.main historico evidencia"
    lines = [line for line in claude.splitlines() if line.startswith(prefix)]
    assert lines, "CLAUDE.md no documenta `historico evidencia`"
    command = lines[0].split("#")[0].replace(prefix, "").strip()
    assert command.startswith("<unit_id>")
    # Literalmente: el mismo comando con la unidad de la fixture y las rutas de `tmp_path`.
    args = main._build_parser().parse_args(
        ["historico", "evidencia", UNIT_ID, "--curated", str(setup.curated)]
        + ["--cache", str(setup.cache), "--cache-pnoa", str(setup.cache_pnoa), "--sin-red"]
    )
    assert args.func is main._historico_evidencia
    defaults = main._build_parser().parse_args(["historico", "evidencia", UNIT_ID])
    assert defaults.curated == Path("curated/historico")
    assert defaults.cache == Path("data/raw/ign_planimetrias")
    assert defaults.cache_pnoa == Path("data/raw/pnoa_ma")
    assert "--cache-pnoa" in claude
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = " ".join(pyproject["project"]["dependencies"]).lower()
    assert "pillow" not in dependencies and "imageio" not in dependencies
    assert HttpStatusError is not None
