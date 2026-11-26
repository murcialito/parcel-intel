"""Tests unitarios del generador de fixtures sintéticas de Catastro, de sus huellas y del
bloqueo de red (historia #45)."""

import hashlib
import socket
from pathlib import Path

import pytest

from tests.fixtures import generate_catastro as gen
from tests.fixtures.catastro_fingerprints import (
    fingerprints_of_directory,
    normalize_pos_list,
    reference_fingerprints,
    ring_fingerprints,
)
from tests.network_guard import NetworkBlockedError, no_network


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- Generador ---------------------------------------------------------------


def test_rombo_conserva_la_envolvente_exacta_y_esta_cerrado() -> None:
    envelope = (10.0, 20.0, 30.25, 41.5)

    ring = gen.diamond(envelope)

    assert ring[0] == ring[-1]
    assert len(ring) == 5
    xs = [x for x, _ in ring]
    ys = [y for _, y in ring]
    assert (min(xs), min(ys), max(xs), max(ys)) == envelope


def test_rectangulo_cerrado_en_sentido_antihorario() -> None:
    ring = gen.rectangle(0.0, 0.0, 2.0, 1.0)

    assert ring == ((0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (0.0, 1.0), (0.0, 0.0))
    shoelace = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False))
    assert shoelace > 0


def test_poslist_con_dos_decimales_y_count_igual_al_numero_de_puntos() -> None:
    parcel = gen.SyntheticParcel(
        reference="99000A00000001",
        area_m2=1,
        surfaces=(gen.SyntheticSurface(gen.rectangle(1.0, 2.0, 3.0, 4.25)),),
    )

    body = gen.wfs_cp_collection([parcel]).decode("latin-1")

    assert 'count="5"' in body
    assert ">1.00 2.00 3.00 2.00 3.00 4.25 1.00 4.25 1.00 2.00</gml:posList>" in body
    assert 'numberMatched="1" numberReturned="1"' in body


def test_todas_las_fixtures_llevan_el_comentario_tras_la_declaracion() -> None:
    for name, body in gen.build_all().items():
        first, second = body.split(b"\n")[:2]
        assert first.startswith(b"<?xml"), name
        assert b"FIXTURE SINT" in second, name


def test_check_devuelve_1_si_un_fichero_difiere_falta_o_sobra(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gen.main(["--destino", str(tmp_path)]) == 0
    assert gen.main(["--check", "--destino", str(tmp_path)]) == 0

    (tmp_path / "cpmrc_no_encontrada.xml").write_bytes(b"<x/>")
    (tmp_path / "wfsBU_getcapabilities.xml").unlink()
    (tmp_path / "respuesta_original.xml").write_bytes(b"<x/>")
    (tmp_path / gen.README_NAME).write_text("leeme", encoding="utf-8")

    assert gen.main(["--check", "--destino", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "difiere cpmrc_no_encontrada.xml" in err
    assert "falta wfsBU_getcapabilities.xml" in err
    assert "sobra respuesta_original.xml" in err
    assert gen.README_NAME not in err


def test_argumentos_desconocidos_devuelven_2() -> None:
    assert gen.main(["--otra-cosa"]) == 2


def test_referencias_sinteticas_de_la_tabla_cerrada() -> None:
    dense = gen.colmenar_bbox_denso_parcels()
    assert len(dense) == 121
    assert dense[60].reference == gen.REF_COLMENAR_BBOX_DENSO  # celda central de la rejilla
    assert len(dense[60].surfaces) == 2
    assert dense[0].reference == "99043A93800001" and dense[-1].reference == "99043A93800120"
    assert [p.reference for p in gen.parcela_con_edificios_parcels()] == [
        f"99001{nn:02d}ZZ0000S" for nn in range(1, 10)
    ]
    buildings = gen.dense_bbox_buildings()
    assert len(buildings) == 11
    assert sum(1 for b in buildings if len(b.rings) == 2) == 1


# --- Huellas -----------------------------------------------------------------


def test_normalizacion_de_poslist() -> None:
    assert normalize_pos_list(" 1 2.5\n 3.004 4 ") == "1.00 2.50 3.00 4.00"


def test_huellas_de_referencias_de_cpmrc_wfs_y_edificios() -> None:
    cpmrc = gen.cpmrc_found("99043A90100001", 1.0, 2.0, "x")
    parcel = gen.SyntheticParcel(
        reference="99043A90100002",
        area_m2=1,
        surfaces=(gen.SyntheticSurface(gen.rectangle(0.0, 0.0, 1.0, 1.0)),),
    )
    building = gen.SyntheticBuilding(
        reference="9900105ZZ0000S",
        area_m2=1,
        construction_year=2000,
        rings=(gen.rectangle(0.0, 0.0, 1.0, 1.0),),
    )

    assert reference_fingerprints(cpmrc) == {_sha("99043A90100001")}
    assert reference_fingerprints(gen.wfs_cp_collection([parcel])) == {_sha("99043A90100002")}
    assert reference_fingerprints(gen.wfs_bu_collection([building])) == {_sha("9900105ZZ0000S")}


def test_referencia_de_20_caracteres_se_recorta_a_14() -> None:
    xml = b'<r xmlns="http://www.catastro.meh.es/"><localId>99043A901000010000ZZ</localId></r>'

    assert reference_fingerprints(xml) == {_sha("99043A90100001")}


def test_huellas_de_anillos_iguales_con_otra_precision() -> None:
    ring = gen.rectangle(1.0, 2.0, 3.0, 4.0)
    a = gen.wfs_bu_collection(
        [
            gen.SyntheticBuilding(
                reference="9900101ZZ0000S", area_m2=1, construction_year=1, rings=(ring,)
            )
        ]
    )
    texto = (
        '<x xmlns:gml="http://www.opengis.net/gml/3.2"><gml:posList>1 2 3 2 3 4 1 4 1 2'
        "</gml:posList></x>"
    )

    assert ring_fingerprints(a) == ring_fingerprints(texto.encode("utf-8"))


def test_huellas_de_un_directorio(tmp_path: Path) -> None:
    (tmp_path / "a.xml").write_bytes(gen.cpmrc_found("99043A90100001", 1.0, 2.0, "x"))

    result = fingerprints_of_directory(tmp_path)

    assert result["algoritmo"] == "sha256"
    assert result["referencias"] == [_sha("99043A90100001")]
    assert result["anillos"] == []


# --- Bloqueo de red ----------------------------------------------------------


def test_no_network_bloquea_y_restaura() -> None:
    original = socket.create_connection

    with no_network():
        with pytest.raises(NetworkBlockedError):
            socket.getaddrinfo("example.invalid", 80)
        with socket.socket() as sock, pytest.raises(NetworkBlockedError):
            sock.connect(("192.0.2.1", 80))

    assert socket.create_connection is original
