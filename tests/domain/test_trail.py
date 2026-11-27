"""Invariantes de `Trail` (historia #22). Todos los valores son sintéticos."""

import dataclasses
import math
from datetime import date, datetime
from typing import get_args

import pytest

from parcel_intel.domain.geometry import Geometry, LineGeometry, MultiLineGeometry
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.trail import METRIC_SRID, InvalidTrailError, SourceKind, Trail

_PROVENANCE = Provenance(
    source="fuente sintética",
    url="https://example.invalid/trazados",
    retrieved_at=date(2026, 11, 26),
    license="CC BY 4.0",
)


def _trail(**changes: object) -> Trail:
    fields: dict[str, object] = {
        "identifier": "T-1",
        "source": "ign_red_transporte",
        "role": "via",
        "name": None,
        "trail_type": None,
        "municipality_code": "28043",
        "geometry": MultiLineGeometry(lines=(((0.0, 0.0), (10.0, 0.0)),), srid=METRIC_SRID),
        "provenance": _PROVENANCE,
        "data_date": None,
        "character": "nota sintética",
    } | changes
    return Trail(**fields)  # type: ignore[arg-type]


def test_trail_sintetico_multilinea_sin_nombre_se_construye() -> None:
    trail = _trail()

    assert trail.name is None
    assert trail.trail_type is None
    assert isinstance(trail.geometry, MultiLineGeometry)
    assert trail.provenance.redistribution is Redistribution.INTERNAL_ONLY


def test_trail_es_inmutable() -> None:
    trail = _trail()

    with pytest.raises(dataclasses.FrozenInstanceError):
        trail.identifier = "otro"  # type: ignore[misc]


def test_source_kind_tiene_las_cinco_fuentes() -> None:
    assert sorted(get_args(SourceKind)) == [
        "catastro_vt",
        "ign_red_transporte",
        "mtn50_historico",
        "planimetria_historica",
        "via_pecuaria_oficial",
    ]


@pytest.mark.parametrize("source", get_args(SourceKind))
def test_todas_las_fuentes_del_vocabulario_se_aceptan(source: str) -> None:
    assert _trail(source=source).source == source


def test_data_date_con_fecha_se_acepta() -> None:
    assert _trail(data_date=date(1881, 1, 1)).data_date == date(1881, 1, 1)


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"name": ""}, "name"),
        ({"trail_type": "  "}, "trail_type"),
        ({"identifier": 7}, "identifier"),
        ({"municipality_code": 28043}, "municipality_code"),
        ({"data_date": datetime(2026, 1, 1, 12, 0)}, "data_date"),
        ({"data_date": "2026-01-01"}, "data_date"),
        ({"provenance": "idem"}, "provenance"),
        ({"counterpart_only": 1}, "counterpart_only"),
        ({"counterpart_only": "true"}, "counterpart_only"),
        ({"geometry": LineGeometry(points=((0.0, 0.0), (1.0, 1.0)), srid=METRIC_SRID)}, "geometry"),
        ({"geometry": MultiLineGeometry(lines=(), srid=4326)}, "geometry.srid"),
        (
            {"geometry": MultiLineGeometry(lines=(((0.0, 0.0), (math.nan, 1.0)),), srid=25830)},
            "geometry",
        ),
        (
            {"geometry": Geometry(rings=(((0.0, math.inf), (1.0, 1.0)),), srid=25830)},
            "geometry",
        ),
    ],
)
def test_invariantes_sinteticas_nombran_el_campo(changes: dict[str, object], field: str) -> None:
    with pytest.raises(InvalidTrailError, match=field.replace(".", r"\.")):
        _trail(**changes)


def test_geometria_con_partes_de_un_solo_punto_se_acepta() -> None:
    # La entidad no exige segmentos medibles: eso lo decide el consumidor.
    trail = _trail(geometry=MultiLineGeometry(lines=(((1.0, 1.0),),), srid=METRIC_SRID))

    assert trail.geometry == MultiLineGeometry(lines=(((1.0, 1.0),),), srid=METRIC_SRID)


def test_counterpart_only_es_false_por_defecto_y_se_puede_marcar() -> None:
    assert _trail().counterpart_only is False
    assert dataclasses.replace(_trail(), counterpart_only=True).counterpart_only is True


def test_replace_con_campo_invalido_vuelve_a_validar() -> None:
    with pytest.raises(InvalidTrailError, match="municipality_code"):
        dataclasses.replace(_trail(), municipality_code="123")
