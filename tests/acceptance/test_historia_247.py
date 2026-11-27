"""Historia #247: leer el RDPH y la licencia del IGN de la capa de cauces en REGISTRY (sin red)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

REGISTRY = Path(__file__).resolve().parents[2] / "src" / "parcel_intel" / "sources" / "REGISTRY.md"
INICIO = "#### Licencia de la capa de cauces y zona de servidumbre (historia #247"


def _seccion() -> str:
    texto = REGISTRY.read_text(encoding="utf-8")
    assert INICIO in texto
    resto = texto.split(INICIO, 1)[1]
    return resto.split("**Endpoint real:**", 1)[0]


def test_ca1_licencia_ign_confirmada_con_cita_y_veredicto() -> None:
    """Dado el PDF de licencia del IGN, cuando se lee entero, entonces REGISTRY.md pasa la licencia
    de la capa de cauces de `asumido` a `confirmado` con cita literal de las condiciones y dice si
    permite publicar una capa derivada (con qué atribución y condiciones)."""
    s = _seccion()
    assert "https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf" in s
    assert "`confirmado`" in s
    assert "«Cuando el usuario licenciado genere una obra derivada" in s
    assert "«Obra derivada de <identificador del producto>" in s
    assert "SÍ permite publicar una capa derivada" in s
    assert "2026-11-27" in s


def test_ca2_citas_trla_y_rdph() -> None:
    """Dado el texto consolidado del art. 6 del TRLA y el articulado del RDPH sobre la zona de
    servidumbre, cuando se leen en el BOE, entonces REGISTRY.md recoge las citas literales
    (artículo, redacción, enlace consolidado y fecha de consulta): anchura, desde dónde se mide y
    qué usos enumera."""
    s = _seccion()
    assert "https://www.boe.es/buscar/act.php?id=BOE-A-2001-14276" in s
    assert "https://www.boe.es/buscar/act.php?id=BOE-A-1986-10638" in s
    assert "a) A una zona de servidumbre de cinco metros de anchura" in s
    assert "Protección del ecosistema fluvial y del dominio público hidráulico" in s
    assert "Paso público peatonal y para el desarrollo de los servicios de vigilancia" in s
    assert "Varado y amarre de embarcaciones" in s
    assert "redacción anterior" in s
    assert "pesca fluvial" not in s.split("redacción anterior")[0]
    assert "no enumeran el tránsito general" not in s
    assert "los terrenos que lindan con los cauces" in s
    assert "desde qué línea exacta" in s


def test_ca3_canales_leidos_o_no_leidos_documentados() -> None:
    """Dado un canal que no se pudo leer (PDF o BOE), cuando se documenta, entonces se anota cuál y
    por qué, y no se da por «no hay»."""
    s = _seccion()
    assert "`WebFetch` no lo decodifica" in s
    assert "Ningún canal quedó sin leer" in s
    assert "scne.es/productos.html" in s
    assert "pendiente" in s


def test_ca4_desbloqueo_documentado() -> None:
    """Dado que la licencia no permite redistribuir derivados o no queda claro, cuando se
    documenta, entonces se deja un comentario en #196 mencionando a @murcialito; si sí lo permite,
    se anota en REGISTRY.md y no hace falta comentario."""
    s = _seccion()
    assert "Estado de desbloqueo (CA4)" in s
    assert "no hace falta comentario en #196" in s


def test_ca5_coherencia_del_texto_de_la_ficha() -> None:
    """Dado el texto de la ficha aprobado por el fundador, cuando se compara con las citas,
    entonces REGISTRY.md anota si es coherente con lo leído, sin modificarlo."""
    s = _seccion()
    ficha = (
        "Zona de servidumbre aproximada de la margen de un cauce (art. 6 TRLA), calculada a partir "
        "del eje del cauce de la capa del IGN. Es una aproximación, no un deslinde."
    )
    assert ficha in s
    assert "**coherente** con lo leído" in s
