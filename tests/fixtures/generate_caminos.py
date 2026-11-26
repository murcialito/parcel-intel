"""Generador de las fixtures SINTÉTICAS de Catastro de `tests/fixtures/caminos/catastro_*`.

Historia #46 (anexo del ADR 0033). Reutiliza las plantillas del generador de #45
(`generate_catastro`) para la WFS `cp:CadastralParcel` y añade la de `Consulta_DNPPP`.

Mundo sintético propio, sin ninguna derivación de coordenadas ni referencias reales:
municipio 28043, sector `A`, polígonos reservados `991` y `992` y una ventana de
600×600 m con origen en (469000, 4439000) (EPSG:25830), teselada con 20 rectángulos
sin huecos ni solapes. Cuatro parcelas con número ≥ 9000 hacen de camino (clase `VT`
en DNPPP) y la `…99100001` es la parcela de control (`C-`). `areaValue` (WFS) y `ssp`
(DNPPP) difieren en dos caminos, como en el dato real.

Determinista: sin `random`, sin reloj y sin red. Solo stdlib y sin importar `parcel_intel`.

Uso (lo llama también `python -m tests.fixtures.generate_catastro`):

    uv run python -m tests.fixtures.generate_caminos            # escribe
    uv run python -m tests.fixtures.generate_caminos --check    # compara, no escribe
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

from tests.fixtures.generate_catastro import (
    HEADER_COMMENT,
    Ring,
    SyntheticParcel,
    SyntheticSurface,
    wfs_cp_collection,
)

CAMINOS_DIR = Path(__file__).parent / "caminos"
FILE_PREFIX = "catastro_"

ORIGIN_X = 469000.00
ORIGIN_Y = 4439000.00

WFS_FILE = "catastro_wfsCP_sintetica_rustica_bbox600m.xml"

_LABOR = ("C-", "LABOR O LABRADÍO SECANO")
_VIA = ("VT", "VÍA DE COMUNICACIÓN DE DOMINIO PÚBLICO")


class Dnppp(NamedTuple):
    """Respuesta `Consulta_DNPPP` de una parcela: clase de cultivo, descripción y `ssp`."""

    class_code: str
    description: str
    ssp: int


class Tile(NamedTuple):
    """Rectángulo del teselado: límites relativos al origen (x = Este, y = Norte)."""

    ref: str
    x0: int
    x1: int
    y0: int
    y1: int
    dnppp: Dnppp | None = None

    @property
    def area(self) -> int:
        return (self.x1 - self.x0) * (self.y1 - self.y0)


# Tabla del diseño de la historia #46 (ordenada por referencia).
TILES: tuple[Tile, ...] = (
    Tile("28043A99100001", 0, 145, 0, 145, Dnppp(*_LABOR, 21025)),
    Tile("28043A99100002", 145, 290, 0, 145),
    Tile("28043A99100003", 0, 145, 145, 290),
    Tile("28043A99100004", 145, 290, 145, 290),
    Tile("28043A99100005", 0, 145, 300, 450),
    Tile("28043A99100006", 145, 290, 300, 450),
    Tile("28043A99100007", 0, 145, 450, 600),
    Tile("28043A99100008", 145, 290, 450, 600),
    Tile("28043A99109101", 290, 300, 0, 600, Dnppp(*_VIA, 6011)),
    Tile("28043A99109102", 0, 290, 290, 300, Dnppp(*_VIA, 2900)),
    Tile("28043A99200001", 300, 445, 0, 130),
    Tile("28043A99200002", 300, 445, 130, 260),
    Tile("28043A99200003", 300, 445, 260, 390),
    Tile("28043A99200004", 450, 600, 0, 130),
    Tile("28043A99200005", 450, 600, 130, 260),
    Tile("28043A99200006", 450, 600, 260, 390),
    Tile("28043A99200007", 300, 450, 400, 600),
    Tile("28043A99200008", 450, 600, 400, 600),
    Tile("28043A99209201", 300, 600, 390, 400, Dnppp(*_VIA, 3024)),
    Tile("28043A99209202", 445, 450, 0, 390, Dnppp(*_VIA, 1950)),
)


def dnppp_file_name(tile: Tile) -> str:
    polygon = tile.ref[6:9]
    parcel = int(tile.ref[9:14])
    return f"catastro_dnppp_sintetica_pol{polygon}_parc{parcel}.xml"


def clockwise_ring(tile: Tile) -> Ring:
    """Rectángulo en sentido horario (SO → NO → NE → SE → SO), como el dato real."""
    x0, x1 = ORIGIN_X + tile.x0, ORIGIN_X + tile.x1
    y0, y1 = ORIGIN_Y + tile.y0, ORIGIN_Y + tile.y1
    return ((x0, y0), (x0, y1), (x1, y1), (x1, y0), (x0, y0))


def render_dnppp(reference: str, class_code: str, description: str, ssp: int) -> bytes:
    """Respuesta `Consulta_DNPPP` sintética de una parcela rústica (UTF-8, sin titularidad)."""
    polygon = int(reference[6:9])
    parcel = int(reference[9:14])
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        HEADER_COMMENT,
        '<consulta_dnp xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns="http://www.catastro.meh.es/">',
        "  <control>",
        "    <cudnp>1</cudnp>",
        "    <cucul>1</cucul>",
        "  </control>",
        "  <bico>",
        "    <bi>",
        "      <idbi>",
        "        <cn>RU</cn>",
        "        <rc>",
        f"          <pc1>{reference[:7]}</pc1>",
        f"          <pc2>{reference[7:14]}</pc2>",
        "          <car>0000</car>",
        "          <cc1>Z</cc1>",
        "          <cc2>Z</cc2>",
        "        </rc>",
        "      </idbi>",
        "      <dt>",
        "        <loine>",
        "          <cp>28</cp>",
        "          <cm>43</cm>",
        "        </loine>",
        "        <cmc>43</cmc>",
        "        <np>MADRID</np>",
        "        <nm>COLMENAR DE OREJA</nm>",
        "        <locs>",
        "          <lors>",
        "            <lorus>",
        "              <czc>0</czc>",
        "              <cpp>",
        f"                <cpo>{polygon}</cpo>",
        f"                <cpa>{parcel}</cpa>",
        "              </cpp>",
        "              <npa>PARAJE SINTETICO</npa>",
        "              <cpaj>999</cpaj>",
        "            </lorus>",
        "          </lors>",
        "        </locs>",
        "      </dt>",
        f"      <ldt>Polígono {polygon} Parcela {parcel} PARAJE SINTETICO. "
        "COLMENAR DE OREJA (MADRID)</ldt>",
        "      <debi>",
        "        <luso>Agrario</luso>",
        "        <sfc>0</sfc>",
        "      </debi>",
        "    </bi>",
        "    <lspr>",
        "      <spr>",
        "        <cspr>0</cspr>",
        "        <dspr>",
        f"          <ccc>{class_code}</ccc>",
        f"          <dcc>{description}</dcc>",
        "          <ip>00</ip>",
        f"          <ssp>{ssp}</ssp>",
        "        </dspr>",
        "      </spr>",
        "    </lspr>",
        "  </bico>",
        "</consulta_dnp>",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_all() -> dict[str, bytes]:
    """Contenido de cada fixture de caminos, por nombre de fichero."""
    parcels = [
        SyntheticParcel(
            reference=tile.ref,
            area_m2=tile.area,
            surfaces=(SyntheticSurface(exterior=clockwise_ring(tile)),),
        )
        for tile in TILES
    ]
    files: dict[str, bytes] = {WFS_FILE: wfs_cp_collection(parcels)}
    for tile in TILES:
        if tile.dnppp is not None:
            files[dnppp_file_name(tile)] = render_dnppp(tile.ref, *tile.dnppp)
    return files


def generate(out_dir: Path) -> list[Path]:
    """Escribe los seis ficheros en `out_dir` y devuelve sus rutas ordenadas."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for name, content in sorted(build_all().items()):
        path = out_dir / name
        path.write_bytes(content)
        paths.append(path)
    return paths


def differences(directory: Path, expected: Mapping[str, bytes] | None = None) -> list[str]:
    """Diferencias entre lo versionado y lo generado (solo los `catastro_*` del directorio)."""
    expected = build_all() if expected is None else expected
    problems: list[str] = []
    for name, content in expected.items():
        path = directory / name
        if not path.exists():
            problems.append(f"falta {name}")
        elif path.read_bytes() != content:
            problems.append(f"difiere {name}")
    if directory.exists():
        for path in sorted(directory.glob(f"{FILE_PREFIX}*")):
            if path.name not in expected:
                problems.append(f"sobra {path.name}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Escribe las fixtures; con `--check` solo compara y devuelve 1 si difieren."""
    args = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in args
    if check:
        args.remove("--check")
    directory = CAMINOS_DIR
    if len(args) == 2 and args[0] == "--destino":
        directory = Path(args[1])
        args = []
    if args:
        print(
            "uso: python -m tests.fixtures.generate_caminos [--check] [--destino <dir>]",
            file=sys.stderr,
        )
        return 2
    if check:
        problems = differences(directory)
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    generate(directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
