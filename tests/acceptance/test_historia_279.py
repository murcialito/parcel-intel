"""Historia #279: verificar el catálogo de caminos de Cáceres y Extremadura (validación).

Historia de investigación: el resultado vive en `src/parcel_intel/sources/REGISTRY.md`. CA1 y CA2
exigen el contenido real, que `ide.caceres.es` no sirve a los runners de Actions: se pasan en local.
"""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

RAIZ = Path(__file__).resolve().parents[2]
REGISTRY = (RAIZ / "src/parcel_intel/sources/REGISTRY.md").read_text(encoding="utf-8")
SECCION = REGISTRY.split("## Catálogo de caminos públicos de Cáceres y Extremadura", 1)[1]
URL_GEOJSON = (
    "https://ide.caceres.es/geoserver/sigaytocc/ows?service=WFS&version=1.0.0&request=GetFeature"
    "&typeName=sigaytocc%3Acaminos&outputFormat=application%2Fjson"
)


@pytest.mark.integration
@pytest.mark.red
@pytest.mark.fuera_de_ci
def test_ca1_geojson_descargado_y_registrado() -> None:
    """Dado el recurso GeoJSON del catálogo de Cáceres, cuando se descarga a `data/raw/` (fuera de
    git), entonces se registra en REGISTRY.md con URL, fecha de descarga, sha256, nº de elementos,
    sistema de coordenadas, campos y licencia CC-BY comprobada en la página de origen y no solo en
    la ficha."""
    fichero = RAIZ / "data/raw/caceres_caminos/caminos.geojson"
    if not fichero.exists():
        subprocess.run(
            ["curl", "-sS", "-L", "-A", "parcel-intel-verificacion/0.1", "-o", str(fichero),
             URL_GEOJSON],
            check=True, timeout=300,
        )
    datos = fichero.read_bytes()
    sha = hashlib.sha256(datos).hexdigest()
    n = len(json.loads(datos)["features"])
    assert sha in SECCION, "anotar el sha256 en REGISTRY.md"
    assert f"{n} features" in SECCION, "anotar el nº de features en REGISTRY.md"


def test_ca1_registry_documenta_lo_leido_y_lo_pendiente() -> None:
    """CA1 (parte sin red): REGISTRY.md deja la URL real, la licencia discrepante y qué falta."""
    assert URL_GEOJSON.split("&request")[0] in SECCION or "sigaytocc%3Acaminos" in SECCION
    assert "No se aplican condiciones" in SECCION
    assert "CC-BY" in SECCION
    assert "pendiente-local" in SECCION


@pytest.mark.integration
@pytest.mark.red
@pytest.mark.fuera_de_ci
def test_ca2_registry_responde_si_hay_perdida_de_traza() -> None:
    """Dado el contenido real, cuando se inspeccionan sus campos y geometrías, entonces REGISTRY.md
    dice si existe algún dato de pérdida de traza, cancela u obra de acceso (sí/no, con el campo) o
    si solo hay trazados; sin nombres de personas ni referencias catastrales copiados."""
    assert "pendiente-local" not in SECCION.split("### CA2", 1)[1].split("### CA3", 1)[0], (
        "CA2 sigue pendiente: inspeccionar los campos en local y anotar el resultado"
    )


def test_ca2_hoy_no_se_afirma_que_no_hay() -> None:
    """CA2 (parte sin red): la ausencia en la ficha no se lee como «no hay»."""
    parte = SECCION.split("### CA2", 1)[1].split("### CA3", 1)[0]
    assert "no equivale a «no hay»" in parte


def test_ca3_canales_de_extremadura_con_resultado() -> None:
    """Dado que el catálogo de Extremadura se cita con ~13.000 pérdidas de traza, cuando se buscan
    sus canales (datos.gob.es, Junta de Extremadura/IDEEX, CICTEX, visor.ideex.es), entonces
    REGISTRY.md anota cada canal consultado y su resultado (descargable, solo visor, ilegible) sin
    tratar «ilegible» como «no hay», y la licencia si se encuentra."""
    parte = SECCION.split("### CA3", 1)[1]
    for canal in ("datos.gob.es", "IDEEX", "CICTEX", "visor.ideex.es", "JIIDE"):
        assert canal in parte
    assert "ilegible" in parte and "No equivale a que no existan" in parte
    assert "Licencia de un conjunto de Extremadura" in parte


def test_ca4_conclusion_provisional_y_pendiente_de_comentario() -> None:
    """Dado el resultado, cuando se cierra la historia, entonces un comentario en la issue #271
    concluye una de: «hay verdad de cortes descargable», «solo hay trazados» o «no sirve», con las
    fuentes del método que faltarían allí y su coste. (El comentario lo pone quien cierra CA1/CA2;
    aquí queda la conclusión provisional en REGISTRY.)"""
    parte = SECCION.split("### Conclusión provisional", 1)[1]
    assert "trazados" in parte and "vías pecuarias" in parte and "Catastro VT" in parte


def test_ca5_ningun_fichero_del_catalogo_en_git_ni_en_site() -> None:
    """Dado cualquier hallazgo, entonces no entra ningún fichero de ese catálogo en git ni en
    `site/` en esta historia."""
    salida = subprocess.run(
        ["git", "ls-files", "data", "site"], cwd=RAIZ, capture_output=True, text=True, check=True
    ).stdout.lower()
    assert "caceres" not in salida
