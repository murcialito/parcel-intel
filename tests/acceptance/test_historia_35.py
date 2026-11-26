"""Historia #35: límites municipales del IGN y caché cruda inmutable."""

import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.ign_admin_units import IgnAdministrativeUnitsAdapter
from parcel_intel.adapters.ign_admin_units.client import default_http_getter
from parcel_intel.adapters.ign_admin_units.parsing import parse_administrative_units
from parcel_intel.adapters.raw_cache import CachedRawFetcher, RawCacheMissError
from parcel_intel.domain.geometry import Geometry, point_in_any_ring
from parcel_intel.domain.municipality import MunicipalBoundary
from parcel_intel.ports.errors import (
    IncompleteWfsResponseError,
    MunicipalBoundaryNotFoundError,
)

pytestmark = pytest.mark.acceptance

FIXTURE = Path(__file__).parents[1] / "fixtures" / "caminos" / "ign_au_ambito_7_municipios.xml"
CATASTRO_FIXTURES = Path(__file__).parents[1] / "fixtures" / "catastro"
AMBITO = ("28043", "28013", "28052", "28019", "28170", "28180", "28157")
SEARCH_BBOX = (39.98, -3.62, 40.22, -3.15)
D1 = date(2026, 11, 26)
D2 = date(2027, 1, 15)


class _Http:
    def __init__(self, body: bytes | None = None) -> None:
        self.body = FIXTURE.read_bytes() if body is None else body
        self.calls = 0

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls += 1
        return self.body


class _NoNetwork:
    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        raise AssertionError("no debe llamarse a la red")


def _adapter(
    http: _Http | _NoNetwork, cache_dir: Path, today: date = D1, offline: bool = False
) -> IgnAdministrativeUnitsAdapter:
    fetcher = CachedRawFetcher(
        http, cache_dir, lambda: today, sleep=lambda _: None, offline=offline
    )
    return IgnAdministrativeUnitsAdapter(SEARCH_BBOX, fetcher=fetcher)


def _boundaries(tmp_path: Path, codes: tuple[str, ...] = AMBITO) -> list[MunicipalBoundary]:
    return _adapter(_Http(), tmp_path).get_municipal_boundaries(codes)


def test_ca1_siete_limites_en_orden_con_procedencia(tmp_path: Path) -> None:
    """Dada la fixture recortada de la respuesta real del IGN, cuando se piden los 7 códigos
    INE del ámbito, entonces se obtienen 7 `MunicipalBoundary` en el orden pedido, cada uno con
    su código INE, su nombre (p. ej. "Colmenar de Oreja"), geometría en EPSG:25830 con un
    anillo y `Provenance` con fuente, URL completa de la petición, fecha de descarga y licencia
    `CC BY 4.0 ign.es`. Titulcia (28147), presente en la fixture pero no pedida, no aparece."""
    boundaries = _boundaries(tmp_path)

    assert [b.ine_code for b in boundaries] == list(AMBITO)
    assert [b.name for b in boundaries] == [
        "Colmenar de Oreja",
        "Aranjuez",
        "Chinchón",
        "Belmonte de Tajo",
        "Villaconejos",
        "Villarejo de Salvanés",
        "Valdelaguna",
    ]
    for b in boundaries:
        assert b.geometry.srid == 25830
        assert len(b.geometry.rings) == 1
        assert b.provenance.source == "ign_unidades_administrativas"
        assert b.provenance.retrieved_at == D1
        assert b.provenance.license == "CC BY 4.0 ign.es"
        url = b.provenance.url
        assert url.startswith("https://www.ign.es/wfs-inspire/unidades-administrativas?")
        assert "typeNames=au%3AAdministrativeUnit" in url
        assert "bbox=39.98%2C-3.62%2C40.22%2C-3.15%2Curn%3Aogc%3Adef%3Acrs%3AEPSG%3A%3A4258" in url
    assert "28147" not in {b.ine_code for b in boundaries}
    assert "Titulcia" not in {b.name for b in boundaries}

    # Se respeta el orden pedido, no el de la respuesta.
    reordered = _adapter(_Http(), tmp_path / "otra").get_municipal_boundaries(("28170", "28043"))
    assert [b.ine_code for b in reordered] == ["28170", "28043"]


def _centroid(fixture: str) -> tuple[float, float]:
    root = ET.fromstring((CATASTRO_FIXTURES / fixture).read_bytes())
    values = {
        el.tag.rsplit("}", 1)[-1]: float(el.text or "")
        for el in root.iter()
        if el.tag.rsplit("}", 1)[-1] in ("xcen", "ycen")
    }
    return values["xcen"], values["ycen"]


def test_ca2_centroides_catastrales_caen_en_su_municipio(tmp_path: Path) -> None:
    """Dados los límites reproyectados de Colmenar de Oreja y Villaconejos, cuando se comprueban
    los centroides catastrales de la parcela REFCAT-RETIRADA (`467588.74, 4442023.74`) y de la
    REFCAT-RETIRADA (`454720.29, 4441476.87`), ambos en EPSG:25830 y tomados de las fixtures
    `Consulta_CPMRC`, entonces el primero cae dentro de Colmenar y fuera de Villaconejos, y el
    segundo al revés. Así se detectaría un cambio de ejes lat/lon."""
    by_code = {b.ine_code: b.geometry for b in _boundaries(tmp_path)}
    colmenar, villaconejos = by_code["28043"], by_code["28170"]

    # Desde la historia #45 las fixtures `Consulta_CPMRC` son SINTÉTICAS: el centroide
    # es el centro de la envolvente conservada de cada parcela (99043A90100001 y
    # 99170A90100001), a pocos metros de los centroides que cita el criterio.
    c_colmenar = _centroid("cpmrc_colmenar_14char.xml")
    c_villaconejos = _centroid("cpmrc_villaconejos_14char.xml")
    assert c_colmenar == (467582.54, 4442024.38)
    assert c_villaconejos == (454690.61, 4441488.64)

    assert point_in_any_ring(c_colmenar, colmenar.rings)
    assert not point_in_any_ring(c_colmenar, villaconejos.rings)
    assert point_in_any_ring(c_villaconejos, villaconejos.rings)
    assert not point_in_any_ring(c_villaconejos, colmenar.rings)


def _vertices(geometry: Geometry) -> set[tuple[float, float]]:
    return {point for ring in geometry.rings for point in ring}


def test_ca3_vertices_compartidos_siguen_identicos_tras_reproyectar(tmp_path: Path) -> None:
    """Dados los límites de Colmenar de Oreja y Villaconejos, que en EPSG:4258 comparten 38
    vértices exactos (REGISTRY.md), cuando se reproyectan, entonces siguen compartiendo 38
    vértices idénticos en EPSG:25830. Garantiza que la partición no deja huecos ni solapes."""
    units = {u["ine_code"]: u for u in parse_administrative_units(FIXTURE.read_bytes())["units"]}
    raw = {
        code: {point for ring in units[code]["rings"] for point in ring}
        for code in ("28043", "28170")
    }
    assert len(raw["28043"] & raw["28170"]) == 38

    by_code = {b.ine_code: b.geometry for b in _boundaries(tmp_path)}
    shared = _vertices(by_code["28043"]) & _vertices(by_code["28170"])
    assert len(shared) == 38


def test_ca4_cache_sin_red_con_otro_reloj_da_el_mismo_resultado(tmp_path: Path) -> None:
    """Dada una respuesta ya guardada en la caché cruda, cuando se vuelve a pedir en modo sin
    red y con un reloj que devuelve otra fecha, entonces el resultado es idéntico al primero,
    incluido `retrieved_at`, que es la fecha de la descarga original, y no se llama a la red.
    En modo sin red y sin entrada se lanza `RawCacheMissError`, y una entrada existente nunca se
    sobrescribe."""
    http = _Http()
    first = _adapter(http, tmp_path, today=D1).get_municipal_boundaries(AMBITO)
    assert http.calls == 1
    files_before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

    second = _adapter(_NoNetwork(), tmp_path, today=D2, offline=True).get_municipal_boundaries(
        AMBITO
    )
    assert second == first
    assert all(b.provenance.retrieved_at == D1 for b in second)

    # Una entrada existente nunca se sobrescribe, aunque la red devolviera otra cosa.
    other = _Http(FIXTURE.read_bytes().replace(b"Colmenar de Oreja", b"Otro nombre"))
    third = _adapter(other, tmp_path, today=D2).get_municipal_boundaries(AMBITO)
    assert other.calls == 0
    assert third == first
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == files_before

    # Sin entrada y sin red: error explícito, sin llamar a la red.
    with pytest.raises(RawCacheMissError):
        _adapter(_NoNetwork(), tmp_path / "vacia", offline=True).get_municipal_boundaries(AMBITO)


def test_ca5_codigo_ausente_lanza_error_sin_lista_parcial(tmp_path: Path) -> None:
    """Dado un código INE que no está en la respuesta (p. ej. 28079), cuando se piden límites
    que lo incluyen, entonces se lanza `MunicipalBoundaryNotFoundError` con ese código y no se
    devuelve ninguna lista parcial."""
    with pytest.raises(MunicipalBoundaryNotFoundError) as excinfo:
        _boundaries(tmp_path, ("28043", "28079", "28170"))

    assert excinfo.value.missing_codes == ("28079",)
    assert "28079" in str(excinfo.value)


def test_ca6_number_matched_distinto_de_features_lanza_error(tmp_path: Path) -> None:
    """Dada una respuesta WFS con `numberMatched` distinto del número de features parseadas
    (fixture sintética, etiquetada como tal), cuando se procesa, entonces se lanza
    `IncompleteWfsResponseError`."""
    # Fixture SINTÉTICA: la real con numberMatched="8" reescrito a "9" (hay 8 features).
    synthetic = FIXTURE.read_bytes().replace(b'numberMatched="8"', b'numberMatched="9"')
    assert synthetic != FIXTURE.read_bytes()

    with pytest.raises(IncompleteWfsResponseError) as excinfo:
        _adapter(_Http(synthetic), tmp_path).get_municipal_boundaries(AMBITO)

    assert (excinfo.value.number_matched, excinfo.value.number_parsed) == (9, 8)
    # Una respuesta truncada no llega a la caché inmutable.
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]


@pytest.mark.integration
def test_ca7_integracion_wfs_real_devuelve_los_7_sin_huecos(tmp_path: Path) -> None:
    """[integración] Dado el WFS real del IGN, cuando se piden los 7 códigos del ámbito con el
    bbox del hito, entonces se obtienen los 7, sin huecos y con `numberMatched` igual a las
    features parseadas."""
    fetcher = CachedRawFetcher(default_http_getter, tmp_path, lambda: D1)
    adapter = IgnAdministrativeUnitsAdapter(SEARCH_BBOX, fetcher=fetcher)

    boundaries = adapter.get_municipal_boundaries(AMBITO)

    assert [b.ine_code for b in boundaries] == list(AMBITO)
    assert all(len(b.geometry.rings) == 1 for b in boundaries)
    # La guarda de numberMatched se aplica al descargar: si no coincidiera, habría lanzado.
    body = next(tmp_path.rglob("*.body")).read_bytes()
    parsed = parse_administrative_units(body)
    assert parsed["number_matched"] == len(parsed["units"])
