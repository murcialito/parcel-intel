"""Historia #22: entidad común de trazado y conversión de vías pecuarias."""

import dataclasses
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.livestock_trails.adapter import LivestockTrailAdapter
from parcel_intel.adapters.livestock_trails.parsing import parse_wfs_livestock_trails
from parcel_intel.domain import discrepancy_criterion, trail
from parcel_intel.domain.geometry import Geometry, MultiLineGeometry
from parcel_intel.domain.livestock_trail import (
    LivestockTrail,
    UnknownLivestockTrailTypeError,
    livestock_trail_role,
    livestock_trail_to_trail,
)
from parcel_intel.domain.provenance import Provenance, Redistribution
from parcel_intel.domain.trail import InvalidTrailError, Trail
from tests.adapters.livestock_trails.helpers import FIXTURES_DIR, SequenceHttpGetter

pytestmark = pytest.mark.acceptance

_COLMENAR = FIXTURES_DIR / "wfs_cql_colmenar_municipio_completo_15_tramos.xml"
_VILLACONEJOS = FIXTURES_DIR / "wfs_cql_villaconejos_municipio_completo_2_tramos.xml"
_CORDEL = FIXTURES_DIR / "wfs_cql_dstipo_cordel_muestra_comunidad_madrid.xml"
_LICENSE = "CC BY 4.0 Comunidad de Madrid"
_PROVENANCE = Provenance(
    source="idem",
    url="https://idem.comunidad.madrid/geoidem/Zonas/wfs?typenames=Zonas:IDEM_MA_VIAS_PECUARIAS",
    retrieved_at=date(2026, 10, 16),
    license=None,
)
_FORBIDDEN_FIELD_PARTS = (
    "titular",
    "propietario",
    "owner",
    "holder",
    "referencia_catastral",
    "cadastral",
    "parcela",
    "nif",
)


def _real_trails(path: Path, provenance: Provenance = _PROVENANCE) -> list[LivestockTrail]:
    """Tramos reales de una fixture de IDEM, con el parser real y una `Provenance` fija."""
    return [
        LivestockTrail(
            trail_type=raw["trail_type"],
            name=raw["name"],
            municipality_code=raw["municipality_code"],
            municipality_name=raw["municipality_name"],
            trail_code=raw["trail_code"],
            length_m=raw["length_m"],
            area_m2=raw["area_m2"],
            geometry=Geometry(rings=raw["rings"], srid=25830),
            provenance=provenance,
        )
        for raw in parse_wfs_livestock_trails(path.read_bytes())
    ]


def _adapter_trails(path: Path) -> list[LivestockTrail]:
    """Tramos reales tal como los devuelve hoy `LivestockTrailAdapter`, sin red."""
    adapter = LivestockTrailAdapter(http_get=SequenceHttpGetter([path]))
    query = Geometry(rings=(((450000.0, 4430000.0), (450001.0, 4430001.0)),), srid=25830)
    return adapter.get_nearby_livestock_trails(query, margin_m=2.0)


def _by_code(trails: list[LivestockTrail], code: str) -> LivestockTrail:
    return next(t for t in trails if t.trail_code == code)


def test_ca1_conserva_nombre_tipo_geometria_y_procedencia() -> None:
    """Dado un `LivestockTrail` de la fixture real de Colmenar, cuando se convierte a trazado
    común, entonces conserva nombre, tipo, geometría (EPSG:25830) y `Provenance` completa
    (fuente, URL, fecha de descarga, licencia `CC BY 4.0 Comunidad de Madrid`)."""
    source = _by_code(_adapter_trails(_COLMENAR), "2804301")

    converted = livestock_trail_to_trail(source)

    assert converted.name == "Vereda del Cristo"
    assert converted.trail_type == "Vereda"
    assert converted.geometry is source.geometry
    assert converted.geometry.srid == 25830
    assert converted.provenance.source == source.provenance.source == "idem"
    assert converted.provenance.url == source.provenance.url
    assert "Zonas:IDEM_MA_VIAS_PECUARIAS" in converted.provenance.url
    assert converted.provenance.retrieved_at == source.provenance.retrieved_at
    assert converted.provenance.license == _LICENSE


def test_ca2_caracter_informativo_y_origen_via_pecuaria_oficial() -> None:
    """Dado un trazado de vía pecuaria, cuando se consulta su carácter, entonces indica
    "cartografía informativa, no deslinde" y el origen `via_pecuaria_oficial`."""
    converted = livestock_trail_to_trail(_by_code(_real_trails(_COLMENAR), "2804307"))

    assert converted.character == "cartografía informativa, no deslinde"
    assert converted.source == "via_pecuaria_oficial"


def test_ca3_anejo_queda_marcado_como_anejo() -> None:
    """Dado un elemento anejo (Abrevadero, Descansadero), cuando se convierte, entonces queda
    marcado como anejo y no como vía."""
    trails = _real_trails(_COLMENAR)
    abrevadero = livestock_trail_to_trail(_by_code(trails, "280430E"))
    descansadero = livestock_trail_to_trail(_by_code(trails, "280430A"))

    assert abrevadero.trail_type == "Abrevadero"
    assert abrevadero.role == "anejo"
    assert descansadero.trail_type == "Descansadero"
    assert descansadero.role == "anejo"


def test_ca4_sin_campos_de_titularidad_ni_propietario() -> None:
    """El trazado común no contiene ningún campo de titularidad ni de propietario."""
    names = [field.name.lower() for field in dataclasses.fields(Trail)]

    offending = [n for n in names for part in _FORBIDDEN_FIELD_PARTS if part in n]
    assert offending == []


def test_ca5_contratos_en_verde_e_informe_por_parcela_sin_cambios() -> None:
    """Los contratos de `lint-imports` y `mypy` siguen en verde y el informe por parcela
    existente no cambia."""
    # lint-imports y mypy los ejecuta CI; aquí se fija que lo que consume el informe
    # por parcela (entidad y adapter) no cambia.
    assert [f.name for f in dataclasses.fields(LivestockTrail)] == [
        "trail_type",
        "name",
        "municipality_code",
        "municipality_name",
        "trail_code",
        "length_m",
        "area_m2",
        "geometry",
        "provenance",
    ]
    from_adapter = _adapter_trails(_COLMENAR)
    assert len(from_adapter) == 15
    # Historia #36 (CA7): el adapter ya rellena la licencia en origen.
    assert all(t.provenance.license == _LICENSE for t in from_adapter)
    assert all(t.provenance.redistribution is Redistribution.INTERNAL_ONLY for t in from_adapter)


def test_ca6_quince_tramos_reales_diez_vias_cinco_anejos_y_multiparte() -> None:
    """Dados los 15 tramos de `wfs_cql_colmenar_municipio_completo_15_tramos.xml`, cuando se
    convierten todos, entonces los `identifier` son exactamente los 15 `CD_VP` de la fixture,
    sin repetidos, y hay exactamente 10 con `role == "via"` y 5 con `role == "anejo"`. Los
    anejos son, literalmente, `280430A`, `280430B`, `280430C`, `280430D` y `280430E`
    (recuento hecho sobre los `DS_TIPO` de la fixture: 5 cañadas, 3 veredas, 2 coladas,
    3 abrevaderos, 1 descansadero y 1 descansadero-abrevadero). La "Vereda de la Mesa"
    (`CD_VP=2804303`, `MultiSurface` real de 2 polígonos) conserva sus **2** anillos, en el
    mismo orden y con los mismos puntos (lección 0001: caso multi-parte real)."""
    sources = _real_trails(_COLMENAR)
    converted = [livestock_trail_to_trail(t) for t in sources]

    identifiers = [t.identifier for t in converted]
    assert identifiers == [t.trail_code for t in sources]
    assert len(set(identifiers)) == 15
    assert sum(t.role == "via" for t in converted) == 10
    assert sorted(t.identifier for t in converted if t.role == "anejo") == [
        "280430A",
        "280430B",
        "280430C",
        "280430D",
        "280430E",
    ]
    mesa_source = _by_code(sources, "2804303")
    mesa = next(t for t in converted if t.identifier == "2804303")
    assert mesa.name == "Vereda de la Mesa"
    assert isinstance(mesa.geometry, Geometry)
    assert len(mesa.geometry.rings) == 2
    assert mesa.geometry.rings == mesa_source.geometry.rings
    assert mesa.geometry.rings[0] != mesa.geometry.rings[1]


def test_ca7_todos_los_ds_tipo_reales_se_clasifican_y_uno_desconocido_falla() -> None:
    """Dados todos los `DS_TIPO` de las tres fixtures reales con tramos (Colmenar,
    Villaconejos y la muestra de `Cordel`), cuando se clasifican, entonces ninguno falla:
    `Cañada`, `Cordel`, `Vereda` y `Colada` → `via`; `Abrevadero`, `Descansadero` y
    `Descansadero-Abrevadero` → `anejo`. Dado un `DS_TIPO` sintético desconocido (p. ej.
    `"Majada"`), cuando se convierte, entonces lanza `UnknownLivestockTrailTypeError` y el
    mensaje contiene el valor y el `CD_VP`. No se clasifica en silencio."""
    expected = {
        "Cañada": "via",
        "Cordel": "via",
        "Vereda": "via",
        "Colada": "via",
        "Abrevadero": "anejo",
        "Descansadero": "anejo",
        "Descansadero-Abrevadero": "anejo",
    }
    real = [t for path in (_COLMENAR, _VILLACONEJOS, _CORDEL) for t in _real_trails(path)]
    observed = {t.trail_type: livestock_trail_role(t.trail_type, t.trail_code) for t in real}
    assert observed == expected
    assert all(livestock_trail_to_trail(t).role == expected[t.trail_type] for t in real)

    # Sintético: "Majada" no aparece en ninguna fixture real.
    synthetic = dataclasses.replace(real[0], trail_type="Majada", trail_code="2804399")
    with pytest.raises(UnknownLivestockTrailTypeError) as excinfo:
        livestock_trail_to_trail(synthetic)
    assert "Majada" in str(excinfo.value)
    assert "2804399" in str(excinfo.value)


def test_ca8_licencia_ausente_se_rellena_y_otra_licencia_falla() -> None:
    """Dado un `LivestockTrail` con `provenance.license=None` (lo que devuelve hoy el
    adapter), cuando se convierte, entonces el `Trail` lleva
    `license == "CC BY 4.0 Comunidad de Madrid"` y `redistribution == Redistribution.PUBLIC`,
    y `source`, `url` y `retrieved_at` no cambian. Dado uno con otra licencia distinta
    (sintético), cuando se convierte, entonces lanza `InvalidTrailError` y **no** se marca
    `PUBLIC`."""
    # Historia #36 (CA7): el adapter ya devuelve la licencia; se vuelve a `None` a mano
    # para seguir cubriendo el relleno de un tramo sin licencia.
    from_adapter = _by_code(_adapter_trails(_COLMENAR), "2804303")
    assert from_adapter.provenance.license == _LICENSE
    source = dataclasses.replace(
        from_adapter, provenance=dataclasses.replace(from_adapter.provenance, license=None)
    )

    converted = livestock_trail_to_trail(source)

    assert converted.provenance.license == _LICENSE
    assert converted.provenance.redistribution is Redistribution.PUBLIC
    assert converted.provenance.source == source.provenance.source
    assert converted.provenance.url == source.provenance.url
    assert converted.provenance.retrieved_at == source.provenance.retrieved_at

    # Sintético: licencia inventada, distinta de la leída en REGISTRY.md.
    other = dataclasses.replace(
        source, provenance=dataclasses.replace(source.provenance, license="CC BY-NC 4.0")
    )
    with pytest.raises(InvalidTrailError, match="provenance.license"):
        livestock_trail_to_trail(other)
    assert other.provenance.redistribution is Redistribution.INTERNAL_ONLY


def _valid_trail() -> Trail:
    return livestock_trail_to_trail(_by_code(_real_trails(_COLMENAR), "2804301"))


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        # Todos sintéticos: valores inválidos inventados a partir de un trazado real.
        ({"geometry": Geometry(rings=(((0.0, 0.0), (1.0, 1.0)),), srid=4326)}, "geometry"),
        ({"identifier": ""}, "identifier"),
        ({"identifier": "   "}, "identifier"),
        ({"municipality_code": "2804"}, "municipality_code"),
        ({"municipality_code": "28043A"}, "municipality_code"),
        ({"source": "pnoa"}, "source"),
        ({"role": "camino"}, "role"),
        ({"character": ""}, "character"),
        ({"character": "  "}, "character"),
        ({"provenance": dataclasses.replace(_PROVENANCE, license="")}, "provenance.license"),
        ({"provenance": dataclasses.replace(_PROVENANCE, license=None)}, "provenance.license"),
    ],
)
def test_ca9_invariantes_de_trail_nombran_el_campo(changes: dict[str, object], field: str) -> None:
    """Dado un `Trail` construido a mano con geometría en un srid distinto de 25830, con
    `identifier` vacío, con `municipality_code` que no son 5 dígitos, con `source` o `role`
    fuera de su vocabulario, con `character` vacío o con `provenance.license` vacía, cuando
    se construye, entonces lanza `InvalidTrailError` nombrando el campo. Dado un `Trail` con
    `Geometry(rings=(), srid=25830)`, cuando se construye, entonces **sí** se construye (lo
    necesita #31 CA8 para contar trazados vacíos sin descartarlos)."""
    valid = _valid_trail()
    fields = {f.name: getattr(valid, f.name) for f in dataclasses.fields(Trail)} | changes

    with pytest.raises(InvalidTrailError, match=field.replace(".", r"\.")):
        Trail(**fields)


def test_ca9_trail_con_geometria_vacia_se_construye() -> None:
    """Dado un `Trail` con `Geometry(rings=(), srid=25830)`, cuando se construye, entonces
    **sí** se construye (lo necesita #31 CA8 para contar trazados vacíos sin descartarlos)."""
    empty = dataclasses.replace(_valid_trail(), geometry=Geometry(rings=(), srid=25830))

    assert empty.geometry == Geometry(rings=(), srid=25830)
    empty_lines = dataclasses.replace(_valid_trail(), geometry=MultiLineGeometry((), 25830))
    assert empty_lines.geometry == MultiLineGeometry(lines=(), srid=25830)


def test_ca10_un_solo_vocabulario_de_fuentes() -> None:
    """`discrepancy_criterion.SourceKind` y `trail.SourceKind` son el mismo objeto (un solo
    vocabulario de fuentes) y los tests existentes de #14 pasan sin tocarlos."""
    # Los tests de #14 (tests/acceptance/test_historia_14.py, tests/domain/test_discrepancy.py)
    # corren sin cambios en la misma suite.
    assert discrepancy_criterion.SourceKind is trail.SourceKind


def test_ca11_replace_vuelve_a_validar() -> None:
    """Dado un `Trail` convertido, cuando se aplica
    `dataclasses.replace(trail, geometry=<Geometry en otro srid>)`, entonces lanza
    `InvalidTrailError` (la validación corre también en `replace`, que es como #36/#23
    sustituirán la geometría por la de la pieza recortada)."""
    converted = _valid_trail()
    other_srid = Geometry(rings=(((440000.0, 4430000.0), (440010.0, 4430010.0)),), srid=4258)

    with pytest.raises(InvalidTrailError, match="geometry.srid"):
        dataclasses.replace(converted, geometry=other_srid)
