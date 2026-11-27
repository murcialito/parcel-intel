"""Historia #257: cauces de IDEE de un municipio, paginados y cacheados, con licencia."""

import json
from datetime import date
from pathlib import Path

import pytest

from parcel_intel.adapters.hydrography.adapter import (
    ATTRIBUTION_PREFIX,
    LICENSE,
    MAX_PAGES,
    HydrographyAdapter,
)
from parcel_intel.adapters.hydrography.client import WATERCOURSE_URL, default_http_getter
from parcel_intel.adapters.raw_cache import CachedRawFetcher
from parcel_intel.domain.provenance import Redistribution
from parcel_intel.ports.errors import WatercourseDownloadError

pytestmark = pytest.mark.acceptance

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "dph"
_PAGE1 = _FIXTURES / "features_watercourse_aranjuez_con_datos_reales.json"
_PAGE2 = _FIXTURES / "features_watercourse_aranjuez_pagina2_sintetica.json"
_BBOX = (430000.0, 4428000.0, 445000.0, 4440000.0)
_SRID = 25830
_DAY = date(2026, 11, 27)


class _PagedGetter:
    """Sirve la página 1 sin `offset` y la 2 con `offset=10`; cuenta las llamadas."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        assert url == WATERCOURSE_URL
        self.calls.append(dict(params))
        return (_PAGE2 if params.get("offset") == "10" else _PAGE1).read_bytes()


def _fetcher(getter: _PagedGetter, cache: Path, offline: bool = False) -> CachedRawFetcher:
    return CachedRawFetcher(
        getter, cache, lambda: _DAY, sleep=lambda _s: None, min_interval_s=0.0, offline=offline
    )


def test_ca1_se_siguen_las_paginas_next_sin_duplicados(tmp_path: Path) -> None:
    """Dada una respuesta grabada con enlace `next` (dos páginas), cuando se descarga un
    bbox, entonces se siguen las páginas hasta el final y se devuelven los cauces de
    todas, sin duplicados por `id`."""
    getter = _PagedGetter()
    adapter = HydrographyAdapter(fetcher=_fetcher(getter, tmp_path), today=lambda: _DAY)

    watercourses = adapter.get_watercourses_in_bbox(_BBOX, _SRID)

    assert len(getter.calls) == 2
    assert getter.calls[1]["offset"] == "10"
    # 10 de la página 1 + 1 nuevo de la página 2 (el otro repite un id de la 1).
    assert len(watercourses) == 11
    # La página 2 repite el id ...2776328 (ya en la 1): 10 + 2 - 1 repetido = 11.
    assert "Arroyo sintetico de la pagina 2" in [w.name for w in watercourses]


def test_ca2_cada_pagina_queda_en_cache_con_sha256_y_fecha_sin_sobrescribir(
    tmp_path: Path,
) -> None:
    """Dado un bbox municipal y la caché vacía, cuando se descarga con red simulada,
    entonces cada página queda en `data/raw/hydrography/` con su sha256 y fecha, y no
    se sobrescribe si ya existe."""
    getter = _PagedGetter()
    cache = tmp_path / "hydrography"
    first = HydrographyAdapter(fetcher=_fetcher(getter, cache), today=lambda: _DAY)
    first.get_watercourses_in_bbox(_BBOX, _SRID)

    sidecars = sorted(cache.rglob("*.json"))
    assert len(sidecars) == 2
    for sidecar in sidecars:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        assert meta["retrieved_at"] == _DAY.isoformat()
        assert len(meta["sha256"]) == 64
    bodies_before = {p: p.read_bytes() for p in cache.rglob("*.body")}

    # Otro día y otra respuesta: la caché no se toca y no se vuelve a llamar.
    other = CachedRawFetcher(
        getter, cache, lambda: date(2027, 1, 1), sleep=lambda _s: None, min_interval_s=0.0
    )
    HydrographyAdapter(fetcher=other).get_watercourses_in_bbox(_BBOX, _SRID)

    assert len(getter.calls) == 2
    assert {p: p.read_bytes() for p in cache.rglob("*.body")} == bodies_before


def test_ca3_sin_red_repite_el_resultado_y_falla_si_falta_una_pagina(tmp_path: Path) -> None:
    """Dada la caché ya llena, cuando se descarga con `--sin-red`, entonces devuelve los
    mismos cauces sin llamar a la red; si falta una página, falla con error claro y no
    devuelve parcial."""
    getter = _PagedGetter()
    online = HydrographyAdapter(fetcher=_fetcher(getter, tmp_path), today=lambda: _DAY)
    first = online.get_watercourses_in_bbox(_BBOX, _SRID)
    calls = len(getter.calls)

    offline = HydrographyAdapter(fetcher=_fetcher(getter, tmp_path, offline=True))
    second = offline.get_watercourses_in_bbox(_BBOX, _SRID)

    assert second == first
    assert len(getter.calls) == calls

    # Se borra la página 2 de la caché: el resultado ya no puede ser parcial.
    page2_sidecar = next(
        p for p in tmp_path.rglob("*.json") if "offset" in json.loads(p.read_text())["params"]
    )
    page2_sidecar.unlink()
    with pytest.raises(WatercourseDownloadError, match="no cacheada"):
        offline.get_watercourses_in_bbox(_BBOX, _SRID)


def test_ca4_la_procedencia_lleva_fuente_url_fecha_y_licencia(tmp_path: Path) -> None:
    """Dado un cauce descargado, cuando se lee su procedencia, entonces lleva fuente,
    URL, fecha de descarga y licencia `CC BY 4.0` (constante del adapter, con atribución
    «Obra derivada de»), no `None`. El comportamiento por parcela existente no cambia
    (tests actuales en verde)."""
    getter = _PagedGetter()
    adapter = HydrographyAdapter(fetcher=_fetcher(getter, tmp_path), today=lambda: _DAY)

    watercourse = adapter.get_watercourses_in_bbox(_BBOX, _SRID)[0]

    provenance = watercourse.provenance
    assert provenance.source == "idee-watercourse"
    assert provenance.url.startswith(WATERCOURSE_URL + "?")
    assert "bbox=430000.0%2C4428000.0%2C445000.0%2C4440000.0" in provenance.url
    assert provenance.retrieved_at == _DAY
    assert provenance.license == LICENSE
    assert provenance.license is not None
    assert "CC BY 4.0" in provenance.license
    assert ATTRIBUTION_PREFIX in provenance.license
    assert provenance.redistribution is Redistribution.PUBLIC


def test_ca5_supera_el_maximo_de_paginas_y_falla(tmp_path: Path) -> None:
    """Dado un bbox, cuando se supera un máximo de páginas fijado (p. ej. 50), entonces
    falla en lugar de iterar sin fin."""
    assert MAX_PAGES == 50
    calls: list[dict[str, str]] = []

    def endless(url: str, params: dict[str, str]) -> bytes:
        calls.append(dict(params))
        offset = int(params.get("offset", "0")) + 10
        body = json.loads(_PAGE1.read_bytes())
        for link in body["links"]:
            if link["rel"] == "next":
                link["href"] = f"{WATERCOURSE_URL}?offset={offset}&limit=10"
        return json.dumps(body).encode("utf-8")

    adapter = HydrographyAdapter(http_get=endless, today=lambda: _DAY)

    with pytest.raises(WatercourseDownloadError, match="más de 50 páginas"):
        adapter.get_watercourses_in_bbox(_BBOX, _SRID)

    assert len(calls) == MAX_PAGES


@pytest.mark.integration
@pytest.mark.red
def test_ca6_aranjuez_real_se_descarga_cachea_y_se_repite_sin_red(tmp_path: Path) -> None:
    """[integración] Dado Aranjuez, cuando se descargan los cauces reales de IDEE y se
    cachean, entonces hay al menos uno y la segunda ejecución `--sin-red` da el mismo
    resultado."""
    online = CachedRawFetcher(default_http_getter, tmp_path, lambda: _DAY)
    first = HydrographyAdapter(fetcher=online).get_watercourses_in_bbox(_BBOX, _SRID)
    assert len(first) >= 1

    offline = CachedRawFetcher(default_http_getter, tmp_path, lambda: _DAY, offline=True)
    second = HydrographyAdapter(fetcher=offline).get_watercourses_in_bbox(_BBOX, _SRID)

    assert second == first
