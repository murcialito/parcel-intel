"""Historia #17: acceso, resolución y georreferenciabilidad de planimetrías IGN y MTN50 0606.

Son tests de documentación y de fixtures: no llaman a red. Los PNG se validan leyendo
la cabecera con la biblioteca estándar.
"""

import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "src" / "parcel_intel" / "sources" / "REGISTRY.md"
FIXTURES = REPO / "tests" / "fixtures" / "caminos" / "planimetrias"
RAW = REPO / "data" / "raw" / "ign_planimetrias"
IMAGENES = ["planimetria_colmenar_280075", "mtn50_0606_chinchon"]
ESTADOS = ("`confirmado`", "`asumido`", "`bloqueado`")


def _verificacion() -> dict[str, Any]:
    datos: dict[str, Any] = json.loads((FIXTURES / "verificacion.json").read_text("utf-8"))
    return datos


def _dimensiones_png(ruta: Path) -> tuple[int, int]:
    cabecera = ruta.read_bytes()[:24]
    assert cabecera[:8] == b"\x89PNG\r\n\x1a\n", f"{ruta.name} no es un PNG"
    ancho, alto = struct.unpack(">II", cabecera[16:24])
    return int(ancho), int(alto)


def _seccion() -> str:
    texto = REGISTRY.read_text(encoding="utf-8")
    inicio = texto.index("## Planimetría de Colmenar y MTN50 0606: acceso y georreferenciabilidad")
    fin = texto.index("\n## ", inicio + 5)
    return texto[inicio:fin]


@pytest.mark.integration
@pytest.mark.red
def test_ca1_descarga_con_procedencia_por_imagen() -> None:
    """Dado el servicio de minutas del IGN, cuando se descarga la planimetría de Colmenar de
    Oreja (doc. 280075) y la hoja MTN50 0606, entonces quedan en `data/raw/ign_planimetrias/`
    con un fichero de procedencia por imagen (fuente, URL exacta, fecha de descarga, licencia,
    hash SHA-256, formato y dimensiones en píxeles)."""
    campos = {
        "fuente",
        "url",
        "fecha_descarga",
        "licencia",
        "sha256",
        "formato",
        "ancho_px",
        "alto_px",
    }
    for nombre in IMAGENES:
        # La procedencia viaja en las fixtures: se valida siempre, sin red ni data/.
        prov = json.loads((FIXTURES / f"{nombre}.provenance.json").read_text("utf-8"))
        assert campos <= prov.keys(), f"{nombre}: faltan {campos - prov.keys()}"
        assert prov["url"].startswith("https://www.ign.es/wms/")
        assert "CC BY 4.0" in prov["licencia"]
        assert len(prov["sha256"]) == 64
        # Si la caché local existe, la imagen debe coincidir con su procedencia.
        imagen = RAW / f"{nombre}.png"
        if imagen.exists():
            assert hashlib.sha256(imagen.read_bytes()).hexdigest() == prov["sha256"]
            assert _dimensiones_png(imagen) == (prov["ancho_px"], prov["alto_px"])


def test_ca2_fixtures_validas_y_resolucion_documentada() -> None:
    """Dadas las fixtures grabadas en `tests/fixtures/caminos/planimetrias/` (respuesta de
    metadatos y un recorte o versión reducida de cada imagen, sin red), cuando se leen,
    entonces son imágenes válidas y de cada una consta en un `verificacion.json`: píxeles,
    formato, resolución efectiva (m/píxel sobre el terreno, estimada y con su método) y
    tamaño del original."""
    datos = _verificacion()
    assert (FIXTURES / "cdd_detalle_alti280352_colmenar.html").stat().st_size > 0
    for nombre in IMAGENES:
        img = datos["imagenes"][nombre]
        ruta = FIXTURES / img["fixture"]
        assert hashlib.sha256(ruta.read_bytes()).hexdigest() == img["sha256_fixture"]
        assert _dimensiones_png(ruta) == (img["pixeles"]["ancho"], img["pixeles"]["alto"])
        assert img["formato"] == "image/png"
        res = img["resolucion_efectiva"]
        assert res["metros_por_pixel_nativo_estimado"] > 0
        assert res["metodo"] and res["estado"] in ("confirmado", "asumido")
        assert img["original"]["tamano"]
    assert datos["metodo_resolucion"]


def test_ca3_marco_servicio_y_puntos_de_control() -> None:
    """Dado `verificacion.json`, cuando se consulta cada imagen, entonces declara
    explícitamente: si trae marco, coordenadas o cuadrícula; si el servicio la sirve sin
    georreferenciar o ya reproyectada; y una lista de ≥4 puntos de control reconocibles hoy
    (iglesia, cruce de caminos, puente…), cada uno con descripción y, si se puede, coordenada
    en EPSG:25830 sacada de PNOA o Catastro (o marcado `sin coordenada`). Si no hay ≥4, lo
    dice."""
    datos = _verificacion()
    for nombre in IMAGENES:
        img = datos["imagenes"][nombre]
        for clave in ("marco", "coordenadas", "cuadricula"):
            assert isinstance(img[clave]["presente"], bool), f"{nombre}.{clave}"
            assert img[clave]["detalle"]
        assert img["servicio"]["estado_georreferenciacion"] in (
            "ya reproyectada",
            "sin georreferenciar",
        )
        puntos = img["puntos_control"]
        resumen = img["resumen_puntos_control"]
        assert resumen["total"] == len(puntos)
        assert resumen["cumple_minimo_4"] is (len(puntos) >= 4)
        con_coordenada = 0
        for p in puntos:
            assert p["descripcion"]
            coord = p["coordenada_25830"]
            if coord == "sin coordenada":
                continue
            con_coordenada += 1
            x, y = coord
            # Ámbito de Colmenar de Oreja en ETRS89 / UTM 30N.
            assert 460000 < x < 475000 and 4430000 < y < 4450000, p["id"]
            assert p["fuente_coordenada"].startswith("PNOA")
        assert resumen["con_coordenada"] == con_coordenada


def test_ca4_registry_hallazgos_con_estado_licencia_y_fixtures() -> None:
    """Dado `REGISTRY.md`, cuando se lee la sección nueva "Planimetría de Colmenar y MTN50
    0606: acceso y georreferenciabilidad", entonces recoge cada hallazgo con su estado
    (`confirmado` / `asumido` / `bloqueado`), enlaza las fixtures y repite la licencia y la
    atribución exacta a usar."""
    seccion = _seccion()
    filas = [
        f
        for f in seccion.split("### Hallazgos", 1)[1].split("###", 1)[0].splitlines()
        if f.startswith("| ") and not f.startswith("| ---") and not f.startswith("| Hallazgo")
    ]
    assert len(filas) >= 8
    for fila in filas:
        assert any(e in fila for e in ESTADOS), f"fila sin estado: {fila[:80]}"
    for estado in ESTADOS:
        assert estado in seccion
    assert "tests/fixtures/caminos/planimetrias/" in seccion
    assert "verificacion.json" in seccion
    assert "CC BY 4.0" in seccion
    assert "Obra derivada de Planimetrías 1870-1950 CC-BY 4.0" in seccion
    assert "Obra derivada de Primera edición MTN50 1875-1968 CC-BY 4.0" in seccion
    for nombre in ("cdd_detalle_alti280352_colmenar.html",):
        assert nombre in seccion
        assert (FIXTURES / nombre).exists()


def test_ca5_recomendacion_compara_opciones_y_concluye() -> None:
    """Dado `REGISTRY.md`, cuando se lee la recomendación de método, entonces compara al
    menos dos opciones de georreferenciación (p. ej. transformación afín/polinómica con
    puntos de control manuales frente a servicio ya reproyectado), con coste, precisión
    esperable y esfuerzo humano, y concluye cuál recomienda y si hace falta ADR. Si la imagen
    no se puede obtener o no es georreferenciable, lo declara y propone alternativa; no lo
    deja como "pendiente"."""
    seccion = _seccion()
    recomendacion = seccion.split("### Recomendación de método de georreferenciación", 1)[1]
    cabecera = recomendacion.splitlines()
    tabla = [linea for linea in cabecera if linea.startswith("| ")]
    assert "Coste" in tabla[0] and "Precisión esperable" in tabla[0]
    assert "Esfuerzo humano" in tabla[0]
    opciones = [linea for linea in tabla[2:] if linea.startswith("| **")]
    assert len(opciones) >= 2
    assert "**Recomendación: C.**" in recomendacion
    assert "¿Hace falta ADR?" in recomendacion
    assert "reCAPTCHA" in recomendacion  # declara que la imagen cruda solo se obtiene a mano
    assert "pendiente" not in recomendacion.lower()


def test_ca6_data_no_entra_en_git() -> None:
    """Dada la suite, cuando se ejecuta `pytest -m acceptance` sin red, entonces pasa usando
    solo las fixtures, y `data/` no entra en git."""
    # Ningún fichero de data/ está versionado y la carpeta está ignorada.
    versionados = subprocess.run(
        ["git", "ls-files", "data"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    assert versionados.strip() == ""
    ignorado = subprocess.run(
        ["git", "check-ignore", "data/raw/ign_planimetrias/x.png"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ignorado.returncode == 0
    # Las imágenes completas no se colaron en las fixtures: los recortes son pequeños.
    for png in FIXTURES.glob("*.png"):
        assert png.stat().st_size < 1_000_000, png.name
