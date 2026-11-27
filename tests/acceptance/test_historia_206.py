"""Historia #206: verificar los vuelos históricos de la Comunidad de Madrid (1956, 1975, 1991).

Historia de documentación y fixtures: la verificación con red se hizo una vez y quedó escrita
en `REGISTRY.md` y grabada en `tests/fixtures/idem_vuelos/`. Estos tests no llaman a red: leen
las fixtures (CA7) y comprueban que `REGISTRY.md` y `NOTICE` recogen lo que cada criterio exige.
Que lo escrito sea cierto lo verifica el revisor contra las peticiones reales (fecha y hora UTC
anotadas en `REGISTRY.md`).
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from parcel_intel.adapters.evidence.png import decode_png

pytestmark = pytest.mark.acceptance

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "idem_vuelos"
REGISTRY = (ROOT / "src" / "parcel_intel" / "sources" / "REGISTRY.md").read_text(encoding="utf-8")
NOTICE = (ROOT / "NOTICE").read_text(encoding="utf-8")
LESSONS = (ROOT / "docs" / "lessons" / "LESSONS.md").read_text(encoding="utf-8")

CAPAS = {
    1956: "fotosAereasHistoricas_1950-1959_1956-CT-50cm-mosaico",
    1975: "fotosAereasHistoricas_1970-1979_orto-1975-ed50",
    1991: "fotosAereasHistoricas_1990-1999_orto-1991-ed50",
}
ATRIBUCION = (
    "Información geográfica de la Comunidad de Madrid. "
    "Acceso público y gratuito en CC BY 4.0 Comunidad de Madrid ."
)
MUNICIPIOS = (
    "Aranjuez",
    "Belmonte de Tajo",
    "Colmenar de Oreja",
    "Chinchón",
    "Valdelaguna",
    "Villaconejos",
    "Villarejo de Salvanés",
)


def _seccion() -> str:
    inicio = REGISTRY.index("## Vuelos históricos de la Comunidad de Madrid")
    fin = REGISTRY.index("\n## ", inicio + 5)
    return REGISTRY[inicio:fin]


def _gris(nombre: str) -> np.ndarray:
    pixeles = decode_png((FIXTURES / nombre).read_bytes())
    return pixeles.astype(float).mean(axis=2)


def test_ca1_capas_tilematrixset_formato_y_plantilla_anotados() -> None:
    """CA1. [integración] Dado el `GetCapabilities` WMTS de la IDEM, cuando se leen las capas de
    los tres vuelos, entonces `REGISTRY.md` anota, por vuelo, el identificador de capa, el
    `TileMatrixSet` (CRS), el tamaño de tesela, el rango de niveles, el formato y si hay plantilla
    REST o solo KVP. Se guarda la fixture del `GetCapabilities` (o el extracto relevante) en
    `tests/fixtures/idem_vuelos/`."""
    seccion = _seccion()
    for capa in CAPAS.values():
        assert capa in seccion
    for dato in ("EPSG3857", "VGCM:epsg:25830", "256 × 256", "0 a 20", "image/png", "KVP"):
        assert dato in seccion
    assert "Plantilla REST**: **no**" in seccion
    assert (FIXTURES / "capabilities_wmts_extracto.xml").stat().st_size > 0


def test_ca2_teselas_de_colmenar_peticion_codigo_y_nivel_anotados() -> None:
    """CA2. [integración] Dado cada vuelo (1956, 1975, 1991), cuando se pide una tesela real al
    nivel de zoom que da 0,5 m sobre Colmenar de Oreja, entonces `REGISTRY.md` registra la
    petición (URL con plantilla, fecha y hora UTC, `User-Agent` genérico), el código HTTP, el
    `Content-Type` y el tamaño, y se guarda una fixture de esa tesela en
    `tests/fixtures/idem_vuelos/`. Se comprueba que la imagen **no está en blanco** (varianza de
    píxeles o histograma, método anotado) y se dice el nivel de zoom y la resolución en metros por
    píxel resultante."""
    seccion = _seccion()
    for dato in (
        "TILEMATRIX=18",
        "User-Agent: paso-comun-verificacion",
        "2026-11-27",
        "image/png",
        "0,457 m por píxel",
        "Método de «no está en blanco»",
    ):
        assert dato in seccion
    for anyo in CAPAS:
        assert (FIXTURES / f"tesela_{anyo}_colmenar_z18.png").is_file()
        assert f"| {anyo} | 15:" in seccion


def test_ca3_tabla_municipio_por_vuelo_con_los_siete() -> None:
    """CA3. [integración] Dado cada uno de los 7 municipios del ámbito (los de
    `publicar-cobertura --ambito`), cuando se pide una tesela al nivel de 0,5 m sobre un punto de
    su término, entonces `REGISTRY.md` tiene una tabla municipio × vuelo con `con imagen` /
    `en blanco` / `error` y el motivo; la cobertura parcial se describe tal cual y no se
    generaliza a partir de un solo punto. Solo se guardan como fixtures las teselas de Colmenar de
    Oreja (CA2); del resto basta la tabla."""
    seccion = _seccion()
    for municipio in MUNICIPIOS:
        fila = next(linea for linea in seccion.splitlines() if linea.startswith(f"| {municipio} "))
        assert fila.count("con imagen") == 3
    assert "No se generaliza" in seccion
    assert "Un punto por municipio" in seccion
    guardadas = {p.name for p in FIXTURES.glob("tesela_*.png")}
    assert guardadas == {
        "tesela_1956_colmenar_z18.png",
        "tesela_1975_colmenar_z18.png",
        "tesela_1991_colmenar_z18.png",
        "tesela_1956_fuera_cobertura_z18.png",
    }


def test_ca4_licencia_citada_textualmente_con_url_y_fecha() -> None:
    """CA4. [integración] Dado el documento de licencia o la ficha del proveedor de cada vuelo,
    cuando se lee el documento primario (no un resultado de búsqueda), entonces `REGISTRY.md` cita
    **textualmente** la licencia y la atribución, con URL del documento y fecha de lectura, y
    concluye si permite redistribuir la imagen derivada en el visor y en el dossier. Si el
    documento primario no se puede leer, se anota qué canales se intentaron y la licencia queda
    `sin verificar`, sin suponer CC BY 4.0 por lo que diga la issue padre."""
    seccion = _seccion()
    assert ATRIBUCION[:-2] in seccion
    assert "https://idem.comunidad.madrid/recursos_cat_geo/Catalogo/aviso_legal.htm" in seccion
    assert "spacm_vuelo1956_50cm" in seccion
    assert "Documentos primarios leídos el 2026-11-27" in seccion
    assert "imagen derivada en el visor y en el dossier" in seccion
    assert "Canales no leídos" in seccion


def test_ca5_wms_alternativo_probado_y_consecuencia_para_207() -> None:
    """CA5. [integración] Dado el servicio, cuando se prueba una petición por ventana (WMS
    `GetMap` con bbox en EPSG:25830, como el del IGN en #122/#124), entonces `REGISTRY.md` dice si
    existe un WMS/COG alternativo para cada vuelo (probado con una petición real, no solo
    declarado), o que solo hay teselas WMTS, y la consecuencia para el adapter de #207 (mosaico y
    recorte de teselas frente a ventana directa)."""
    seccion = _seccion()
    assert "CRS=EPSG:25830" in seccion
    assert "BBOX=463700,4437200,463828,4437328" in seccion
    assert "Consecuencia para #207" in seccion
    assert "no hace falta mosaico y recorte de teselas" in seccion
    assert "**COG**" in seccion


def test_ca6_fecha_y_cobertura_de_cada_vuelo() -> None:
    """CA6. [integración] Dado cada vuelo, cuando se consulta la ficha del catálogo, entonces
    `REGISTRY.md` anota la fecha real del vuelo (mes y año si se publica; si solo hay año, se
    dice) y si la cobertura del vuelo es parcial en la región, con la fuente de cada dato."""
    seccion = _seccion()
    inicio = seccion.index("### Fecha y cobertura de cada vuelo (CA6)")
    bloque = seccion[inicio:]
    assert bloque.count("solo el año") == 3
    assert "Ninguna ficha publica mes" in bloque
    for ficha in ("spacm_vuelo1956_50cm", "spacm_vuelo1975_50cm", "spacm_vuelo1991_50cm"):
        assert ficha in bloque


def test_ca7_las_fixtures_son_validas_y_no_estan_en_blanco() -> None:
    """CA7. Dadas las fixtures de `tests/fixtures/idem_vuelos/`, cuando se ejecuta un test de
    aceptación sin red, entonces las teselas son imágenes válidas, no están en blanco y la
    fixture de capabilities contiene las tres capas anotadas en CA1."""
    for anyo in CAPAS:
        gris = _gris(f"tesela_{anyo}_colmenar_z18.png")
        assert gris.shape == (256, 256)
        assert float(gris.var()) > 100  # una ortofoto real; en blanco sería 0
        assert len(np.unique(gris.astype(np.uint8))) > 50
        assert (FIXTURES / f"tesela_{anyo}_colmenar_z18.png").stat().st_size < 120_000
    # la tesela fuera de cobertura es la referencia de «en blanco»: el detector la distingue
    fuera = _gris("tesela_1956_fuera_cobertura_z18.png")
    assert float(fuera.var()) < 1
    assert len(np.unique(fuera)) == 1
    capabilities = (FIXTURES / "capabilities_wmts_extracto.xml").read_text(encoding="utf-8")
    for capa in CAPAS.values():
        assert f"<ows:Identifier>{capa}</ows:Identifier>" in capabilities


def test_ca8_notice_y_lecciones() -> None:
    """CA8. Dada la verificación terminada, cuando se revisan `NOTICE` y `LESSONS.md`, entonces
    `NOTICE` incluye la atribución literal de cada vuelo cuya licencia permita redistribución (los
    no verificados o no redistribuibles no entran), y `LESSONS.md` recoge cualquier sorpresa (p.
    ej. 200 con imagen en blanco, `TileMatrixSet` inesperado) o dice en la PR que no hubo
    ninguna."""
    assert ATRIBUCION in NOTICE
    for capa in CAPAS.values():
        assert capa in NOTICE
    assert "Historia #206" in LESSONS


def test_ca9_estado_de_cada_vuelo_para_207_y_208() -> None:
    """CA9. Dado el resultado, cuando se comenta en #207 y #208 (o en su cuerpo vía la PR),
    entonces queda escrito qué vuelos están `confirmado`, `parcial` o `descartado`, para que esas
    historias se desbloqueen con información cierta."""
    seccion = _seccion()
    tabla = seccion[seccion.index("**Estado por vuelo**") : seccion.index("### Capas y teselas")]
    patron = r"^\| (1956|1975|1991) \| `(confirmado|parcial|descartado)` \|"
    estados = re.findall(patron, tabla, re.M)
    assert [anyo for anyo, _ in estados] == ["1956", "1975", "1991"]
