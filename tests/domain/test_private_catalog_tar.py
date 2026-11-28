"""Tests unitarios de los miembros de `tar` del catálogo de datos privados (historia #320)."""

import json

import pytest

from parcel_intel.domain.private_catalog import (
    ExtractedMember,
    local_record,
    parse_catalog,
    record_members,
    safe_member_path,
)
from tests.fixtures.private_data.tar_partes import MEMBERS, TAR_ID, mundo_tar, sha256


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("a.gml", "a.gml"),
        ("dir/a.gml", "dir/a.gml"),
        ("./dir/a.gml", "dir/a.gml"),
        ("dir/", "dir"),
        ("dir/sub/a.gml", "dir/sub/a.gml"),
    ],
)
def test_ruta_de_miembro_valida_se_normaliza(name: str, expected: str) -> None:
    assert safe_member_path(name) == expected


@pytest.mark.parametrize(
    "name",
    ["", ".", "..", "../fuera", "a/../../fuera", "a/./b", "a//b", "/abs", "a\\b", "c:x", "a\x00b"],
)
def test_ruta_de_miembro_hostil_se_rechaza_sin_repetirla(name: str) -> None:
    with pytest.raises(ValueError) as error:
        safe_member_path(name)
    assert len(name) <= 3 or name not in str(error.value)


def test_registro_con_miembros_ordena_por_ruta_y_se_lee_de_vuelta(tmp_path_factory) -> None:  # type: ignore[no-untyped-def]
    store, _ = mundo_tar(tmp_path_factory.mktemp("mundo"))
    document = store.read_catalogs()[0]
    entry = parse_catalog(document).entries[0]
    members = [
        ExtractedMember(name, sha256(data), len(data))
        for name, data in sorted(MEMBERS.items(), reverse=True)
    ]
    record = local_record(entry, {"nota": "x"}, members)
    stored = json.loads(record)["miembros"]
    assert [m["ruta"] for m in stored] == sorted(MEMBERS)
    assert record_members(record) == tuple(sorted(members, key=lambda m: m.path))
    assert entry.entry_id == TAR_ID
    assert local_record(entry, {"nota": "x"}, members) == record


def test_registro_sin_miembros_o_con_miembros_malos_no_vale() -> None:
    assert record_members(b"no es json") is None
    assert record_members(b'{"entrada": {}}') is None
    good = {"ruta": "a/b", "sha256": "0" * 64, "tamano_bytes": 1}
    assert record_members(json.dumps({"miembros": [good]}).encode()) is not None
    for bad in (
        {**good, "ruta": "../x"},
        {**good, "sha256": "zz"},
        {**good, "tamano_bytes": -1},
        {**good, "tamano_bytes": True},
        "texto",
    ):
        assert record_members(json.dumps({"miembros": [bad]}).encode()) is None
