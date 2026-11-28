"""Historia #227: servir el sitio en pasocomun.org.

Un test por criterio. Todo sin red salvo CA6 (`integration` y `red`).
"""

from __future__ import annotations

import re
import socket
import ssl
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from tests.acceptance.test_historia_115 import URL_PAGES

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
ADR_DIR = ROOT / "docs" / "adr"

SUFIJOS = {
    ".html", ".js", ".mjs", ".css", ".json", ".geojson",
    ".webmanifest", ".svg", ".txt", ".xml",
}  # fmt: skip
_URL_GITHUB = re.compile(r"https?://github\.com/murcialito/paso-comun[^\s\"'<>)]*")
_PAGES = re.compile(r"murcialito\.github\.io", re.IGNORECASE)
_PREFIJO = "/paso-comun/"


def referencias_prohibidas(raiz: Path) -> list[tuple[str, str]]:
    """Ficheros de texto bajo `raiz` que referencian el dominio de Pages antiguo o el prefijo."""
    halladas: list[tuple[str, str]] = []
    for ruta in sorted(raiz.rglob("*")):
        if not ruta.is_file() or ruta.suffix.lower() not in SUFIJOS:
            continue
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        texto = _URL_GITHUB.sub("", texto)
        rel = ruta.relative_to(raiz).as_posix()
        for m in _PAGES.finditer(texto):
            halladas.append((rel, m.group(0)))
        if _PREFIJO in texto:
            halladas.append((rel, _PREFIJO))
    return halladas


def _adr() -> Path:
    candidatos = [
        p for p in sorted(ADR_DIR.glob("*.md"))
        if "- Historia: #227" in p.read_text(encoding="utf-8")
    ]  # fmt: skip
    assert len(candidatos) == 1, candidatos
    return candidatos[0]


def test_ca1_adr_del_dominio() -> None:
    """CA1. Dado el ADR del dominio, cuando se lee, entonces recoge registrador, coste del
    primer año y de renovación (cada uno con fuente y fecha de consulta, o «no verificado»),
    riesgos (caducidad y toma del dominio, toma de Pages sin verificar, datos del titular) con
    su mitigación, qué pasa con la URL antigua y la nota sobre #104."""
    texto = _adr().read_text(encoding="utf-8")
    for esperado in (
        "OVH", "13,99", "7,99", "2026-11-27", "2027-11-27",
        "https://www.ovhcloud.com/es-es/domains/tld/org/",
        "https://rdap.publicinterestregistry.org/rdap/domain/pasocomun.org",
        "caducidad", "transferencia", "verific", "whois", "301", "#104",
    ):  # fmt: skip
        assert esperado in texto, esperado
    numeros = [p.name[:4] for p in ADR_DIR.glob("*.md")]
    assert len(numeros) == len(set(numeros))


class _Metas(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.og: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "meta":
            d = dict(attrs)
            if d.get("property") and d.get("content") is not None:
                self.og[d["property"] or ""] = d["content"] or ""


def _metas(html: str) -> dict[str, str]:
    p = _Metas()
    p.feed(html)
    return p.og


def test_ca2_open_graph_en_el_dominio() -> None:
    """CA2. Dado `site/index.html`, cuando se leen `og:url` y `og:image`, entonces valen
    `https://pasocomun.org/` y `https://pasocomun.org/og-image.png`."""
    og = _metas((SITE / "index.html").read_text(encoding="utf-8"))
    assert og["og:url"] == "https://pasocomun.org/"
    assert og["og:image"] == "https://pasocomun.org/og-image.png"


def test_ca3_url_pages_de_la_historia_115() -> None:
    """CA3. Dado `tests/acceptance/test_historia_115.py`, cuando se ejecuta, entonces
    `URL_PAGES` es `https://pasocomun.org/` y el test pasa."""
    assert URL_PAGES == "https://pasocomun.org/"


def test_ca4_claude_md_menciona_el_dominio() -> None:
    """CA4. Dado `CLAUDE.md`, cuando se lee la cabecera, entonces el sitio figura en
    `https://pasocomun.org/` y menciona el ADR; el repo sigue siendo `murcialito/paso-comun`."""
    cabecera = "\n".join((ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines()[:5])
    assert "https://pasocomun.org/" in cabecera
    assert "murcialito/paso-comun" in cabecera
    assert f"ADR {_adr().name[:4]}" in cabecera
    assert "github.io" not in cabecera


def test_ca5_site_sin_referencias_a_la_url_antigua() -> None:
    """CA5. Dado el contenido de `site/` (HTML, JS, CSS, manifiestos, JSON de índice), cuando un
    test sin red lo recorre, entonces falla si algún fichero referencia `murcialito.github.io` o
    el prefijo `/paso-comun/` (las URLs de `github.com/murcialito/paso-comun` no cuentan)."""
    assert referencias_prohibidas(SITE) == []


def test_ca7_el_escaner_distingue_los_casos(tmp_path: Path) -> None:
    """CA7. Dado un directorio temporal con tres ficheros de texto —uno con
    `https://murcialito.github.io/paso-comun/datos/x.json`, otro con un
    `fetch("/paso-comun/datos/indice.json")` y otro solo con
    `https://github.com/murcialito/paso-comun/issues/16#issuecomment-1`—, cuando se le pasa la
    misma función de escaneo que usa CA5, entonces señala exactamente los dos primeros y no el
    tercero."""
    (tmp_path / "a.txt").write_text("https://murcialito.github.io/paso-comun/datos/x.json")
    (tmp_path / "b.js").write_text('fetch("/paso-comun/datos/indice.json")')
    (tmp_path / "c.txt").write_text(
        "https://github.com/murcialito/paso-comun/issues/16#issuecomment-1"
    )
    rutas = {ruta for ruta, _ in referencias_prohibidas(tmp_path)}
    assert rutas == {"a.txt", "b.js"}


class _SinRedireccion(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def _get(url: str) -> tuple[int, dict[str, str], str]:
    opener = urllib.request.build_opener(
        _SinRedireccion, urllib.request.HTTPSHandler(context=ssl.create_default_context())
    )
    peticion = urllib.request.Request(url, headers={"User-Agent": "paso-comun-tests"})
    try:
        with opener.open(peticion, timeout=30) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), ""


@pytest.mark.integration
@pytest.mark.red
def test_ca6_dominio_sirve_el_visor_y_la_url_antigua_redirige() -> None:
    """CA6. [integración] Dado el dominio ya configurado por el fundador, cuando se pide
    `https://pasocomun.org/`, entonces responde 200 con HTTPS válido y sirve el visor; y
    `https://murcialito.github.io/paso-comun/` redirige (301) a él."""
    try:
        socket.getaddrinfo("pasocomun.org", 443)
    except OSError:
        pytest.skip("pasocomun.org aún no resuelve")
    estado, _, cuerpo = _get("https://pasocomun.org/")
    assert estado == 200
    assert "Paso Común" in cuerpo
    assert _metas(cuerpo)["og:url"] == "https://pasocomun.org/"
    estado, cabeceras, _ = _get("https://murcialito.github.io/paso-comun/")
    assert estado == 301
    destino = {k.lower(): v for k, v in cabeceras.items()}["location"]
    assert destino.startswith("https://pasocomun.org/")
