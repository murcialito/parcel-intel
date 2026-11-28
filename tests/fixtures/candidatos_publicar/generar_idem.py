"""Caso SINTÉTICO de dos ventanas con los vuelos de Madrid (historia #208, CA13). Nada es real.

Encadena los productores reales: `imagenes-comparacion` (`build_comparison_use_case`, con
el despachador por vuelo) sobre un fichero de candidatos con un tramo de 600 m (dos
ventanas: 1024 px y 576 px), y después `publicar-candidatos` (CLI) con la medición de la
fixture de #170. El `http_get` falso responde:

- IGN: un JPEG «con contenido» (0,03 bytes/píxel) para todos los vuelos;
- IDEM `CM_1975`: la tesela real no blanca de #207 en las dos ventanas;
- IDEM `CM_1991`: la misma tesela en la primera ventana y el PNG blanco real de #206
  (`tesela_1956_fuera_cobertura_z18.png`) en la segunda.

Así la primera ventana publica siete imágenes y la segunda seis, con `1991` omitida.

Desde #315 la publicación lee las capas sintéticas de `capas/` y una cobertura histórica
vacía, y la feature lleva su tabla de convergencia (`convergencia`).

Regenera la fixture del visor `tests/fixtures/site/candidatos_comparacion_idem_28043.geojson`
(el fichero publicado tal cual, lección de #178):

    uv run python -m tests.fixtures.candidatos_publicar.generar_idem
"""

import dataclasses
import json
import math
import tempfile
from pathlib import Path

from parcel_intel.adapters.comparison_files import read_stretches
from parcel_intel.adapters.cut_candidate_files import GeoJsonCutCandidateWriter
from parcel_intel.cli import main
from parcel_intel.domain.candidate_review import candidate_fingerprint
from parcel_intel.domain.cut_candidate import CutCandidate
from tests.fixtures.candidatos_publicar import generar
from tests.fixtures.candidatos_revision import generar as revision

ROOT = Path(__file__).resolve().parents[3]
INE = revision.INE
IDEM_FIXTURES = ROOT / "tests" / "fixtures" / "idem_vuelos"
IDEM_REAL_PNG = (IDEM_FIXTURES / "tesela_1975_colmenar_z18.png").read_bytes()
IDEM_BLANK_PNG = (IDEM_FIXTURES / "tesela_1956_fuera_cobertura_z18.png").read_bytes()
IDEM_LAYER_1975 = "fotosAereasHistoricas_1970-1979_orto-1975-ed50"
IDEM_LAYER_1991 = "fotosAereasHistoricas_1990-1999_orto-1991-ed50"
SECOND_WINDOW_BBOX = "460364,4438356,460652,4438644"
SITE_FIXTURE = ROOT / "tests" / "fixtures" / "site" / "candidatos_comparacion_idem_28043.geojson"
_JPEG = b"\xff\xd8"


def two_window_candidate() -> CutCandidate:
    """Tramo de 600 m (`460000,4438500 → 460600,4438500`): dos ventanas (#172 CA13)."""
    return revision.make_candidate(
        "via_pecuaria_oficial",
        "VP-SINT-MADRID",
        (((460000.0, 4438500.0), (460600.0, 4438500.0)),),
        0.8,
        0.5,
    )


class FakeServers:
    """`http_get` falso del IGN y de la IDEM; registra cada llamada."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls.append((url, dict(params)))
        if url == generar.IDEM_WMS_URL:
            if params["layers"] == IDEM_LAYER_1991 and params["bbox"] == SECOND_WINDOW_BBOX:
                return IDEM_BLANK_PNG
            return IDEM_REAL_PNG
        pixels = int(params["width"]) * int(params["height"])
        return _JPEG + b"\x00" * math.ceil(0.03 * pixels)


def write_inputs(base: Path, http: FakeServers | None = None) -> Path:
    """Candidatos, revisión (aprobado vigente) y manifiesto (productor real) en `base`."""
    candidate = two_window_candidate()
    report = dataclasses.replace(revision.report(), candidates=(candidate,))
    GeoJsonCutCandidateWriter(base / "candidatos").write(report)
    (base / "curated" / INE).mkdir(parents=True)
    review = {
        "candidate_id": candidate.candidate_id,
        "review": "aprobado",
        "reviewed_by": revision.REVIEWER,
        "reviewed_at": revision.REVIEWED_AT,
        "candidate_sha256": candidate_fingerprint(candidate),
    }
    (base / "curated" / INE / "revision.json").write_text(
        json.dumps({"municipio": INE, "revisiones": [review]}), encoding="utf-8"
    )
    use_case = main.build_comparison_use_case(
        base / "cache",
        base / "comparacion",
        offline=False,
        http_get=http or FakeServers(),
        today=lambda: generar.COMPARISON_DATE,
        sleep=lambda seconds: None,
    )
    use_case.execute(INE, read_stretches(base / "candidatos" / f"{INE}.geojson", INE))
    return base


def publish_args(base: Path, site: Path) -> list[str]:
    return [
        "publicar-candidatos",
        "--municipio",
        INE,
        "--medicion",
        str(generar.DIRECTORY / "medicion.json"),
        "--entrada",
        str(base / "candidatos"),
        "--curated",
        str(base / "curated"),
        "--comparacion",
        str(base / "comparacion"),
        "--salida",
        str(site),
        # #315: capas sintéticas de la fixture de #170 y sin cobertura histórica.
        "--capas",
        str(generar.DIRECTORY / "capas"),
        "--curated-historico",
        str(base / "sin_curated_historico"),
        "--cache-historico",
        str(base / "sin_cache_historico"),
    ]


def published_text() -> str:
    """El fichero publicado del caso, generado en un temporal."""
    with tempfile.TemporaryDirectory() as tmp:
        base = write_inputs(Path(tmp) / "entradas")
        site = Path(tmp) / "site"
        parsed = main._build_parser().parse_args(publish_args(base, site))
        code = parsed.func(parsed)
        assert code == 0, code
        return (site / "candidatos" / f"{INE}.geojson").read_text(encoding="utf-8")


def main_() -> None:
    SITE_FIXTURE.write_text(published_text(), encoding="utf-8")


if __name__ == "__main__":
    main_()
