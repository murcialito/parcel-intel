"""Historia #24: confirmar la licencia CC BY 4.0 del servicio `roadlink` del IGN.

Son tests de documentación: comprueban REGISTRY.md y las fixtures grabadas en
tests/fixtures/caminos/. No llaman a red. La consulta real a
api-features.idee.es se hizo el 2026-11-26 y su respuesta está en la fixture.
"""

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "src" / "parcel_intel" / "sources" / "REGISTRY.md"
FIXTURES = REPO / "tests" / "fixtures" / "caminos"
COLECCION = FIXTURES / "ign_apifeatures_roadlink_collection.json"
LICENCIA_PDF = FIXTURES / "ign_licencia_condiciones_uso.pdf"
LICENCIA_TXT = FIXTURES / "ign_licencia_condiciones_uso.txt"
LICENCIA_URL = "https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf"
ATRIBUCION = "Obra derivada de IGR-RT 2026 CC-BY 4.0 Instituto Geográfico Nacional"
CITA_LICENCIA = "conlleva la aceptación por el usuario de una licencia CC-BY 4.0"
CITA_ART4 = (
    "tendrá carácter libre y gratuito, siempre que se mencione el origen y propiedad "
    "de los datos, con el alcance y forma que autorice la licencia de uso correspondiente"
)


def _seccion() -> str:
    texto = REGISTRY.read_text(encoding="utf-8")
    inicio = texto.index("## Red de transporte del IGN — roadlink, licencia (historia #24)")
    fin = texto.index("## Resumen de fuentes no verificadas", inicio)
    return texto[inicio:fin]


def _fila_resumen() -> str:
    texto = REGISTRY.read_text(encoding="utf-8")
    return next(
        linea
        for linea in texto.splitlines()
        if linea.startswith("| Red de transporte del IGN (`roadlink`")
    )


@pytest.mark.integration
def test_ca1_licencia_citada_en_registry_con_fecha_y_fixture() -> None:
    """Dado el servicio `roadlink` cuando se consultan los metadatos de la colección
    (`/collections/roadlink`, enlace `rel: license`) y la normativa citada entonces
    `REGISTRY.md` incluye la cita textual y la URL que lo cubren, con fecha de lectura,
    y el estado pasa de `asumido` a `confirmado` (o a `bloqueado` con el motivo si no
    se puede confirmar). [integración: consulta real; se guarda el JSON de la colección
    como fixture]"""
    coleccion = json.loads(COLECCION.read_text(encoding="utf-8"))
    licencias = [enlace for enlace in coleccion["links"] if enlace["rel"] == "license"]
    assert [enlace["href"] for enlace in licencias] == [LICENCIA_URL]
    assert LICENCIA_PDF.exists()

    # Las citas se comprueban contra la transcripción del PDF grabado, no solo contra
    # REGISTRY.md: así el registro no puede citar algo que el documento no dice.
    texto_licencia = LICENCIA_TXT.read_text(encoding="utf-8")
    assert CITA_LICENCIA in texto_licencia
    assert CITA_ART4 in texto_licencia

    seccion = _seccion()
    assert LICENCIA_URL in seccion
    assert "2026-11-26" in seccion
    assert "CC-BY 4.0" in seccion
    assert CITA_LICENCIA in seccion
    assert CITA_ART4 in seccion
    assert "`confirmado`" in _fila_resumen()
    assert "`asumido`" not in _fila_resumen()


def test_ca2_texto_de_atribucion_fijado_en_registry() -> None:
    """Dado el resultado `confirmado` cuando se actualiza el registro entonces
    `REGISTRY.md` fija el texto exacto de atribución («Obra derivada de …») que deberá
    mostrar el visor junto a la capa."""
    seccion = _seccion()
    assert seccion.count(ATRIBUCION) >= 1
    # La fila del resumen repite la atribución para quien solo lea la tabla.
    assert ATRIBUCION in _fila_resumen()


def test_ca3_fila_roadlink_refleja_estado_y_conclusion() -> None:
    """Dado el resumen de fuentes cuando se actualiza entonces la fila de `roadlink`
    refleja el nuevo estado y la conclusión (publicar / interno)."""
    fila = _fila_resumen()
    assert "CC BY 4.0 (`confirmado`" in fila
    assert "**Publicar**" in fila
    assert "**Interno**" not in fila
