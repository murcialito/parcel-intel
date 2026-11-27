"""Historia #216: verificar la fuente de recintos SIGPAC de la Comunidad de Madrid.

Historia solo de documentación: el resultado vive en `src/parcel_intel/sources/REGISTRY.md`
(sección «SIGPAC de la Comunidad de Madrid»). Estos tests comprueban que el registro recoge
lo que la verificación dejó probado, contra las fixtures de `tests/fixtures/sigpac/` (la
cabecera del DBF, el `.prj`, los extractos de feed, ficha y términos FEGA) y de
`tests/fixtures/livestock_trails/` (los 15 tramos de Colmenar). Sin red.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

RAIZ = Path(__file__).resolve().parents[2]
REGISTRY = (RAIZ / "src/parcel_intel/sources/REGISTRY.md").read_text(encoding="utf-8")
TITULO_SECCION = (
    "## SIGPAC de la Comunidad de Madrid: recintos, atributos, licencia y uso (historia #216)"
)
SECCION = REGISTRY.split(TITULO_SECCION, 1)[1].split("\n## Resumen de fuentes no verificadas", 1)[0]
FIXTURES = RAIZ / "tests" / "fixtures" / "sigpac"


def _campos_dbf() -> list[tuple[str, str, int, int]]:
    """Nombre, tipo, longitud y decimales de cada campo de la cabecera del DBF (stdlib)."""
    cab = (FIXTURES / "recinto_dbf_cabecera.bin").read_bytes()
    campos = []
    pos = 32
    while cab[pos] != 0x0D:
        nombre = cab[pos : pos + 11].split(b"\x00")[0].decode("latin-1")
        campos.append((nombre, chr(cab[pos + 11]), cab[pos + 16], cab[pos + 17]))
        pos += 32
    return campos


def test_ca1_registro_lista_campos_tipos_y_usos_reales() -> None:
    """CA1. Dado el ZIP de 28043 descargado a una carpeta nueva, cuando se leen sus atributos
    (con `-I`), entonces el registro lista cada campo con su tipo y valores reales de uso
    (códigos de uso: tierra arable, pastos, viales, etc.) y cómo aparecen en él los caminos y
    las vías pecuarias."""
    campos = _campos_dbf()
    assert len(campos) == 20
    for nombre, _tipo, _longitud, _decimales in campos:
        assert nombre in SECCION, nombre
    tipos = {nombre: tipo for nombre, tipo, _longitud, _decimales in campos}
    assert tipos["USO_SIGPAC"] == "C"
    assert tipos["DN_INITIAL"] == "D"
    for codigo, descripcion in [
        ("TA", "Tierras arables"),
        ("PR", "Pasto arbustivo"),
        ("PS", "Pastizal"),
        ("CA", "Viales"),
    ]:
        assert f"| {codigo} |" in SECCION or f"**{codigo}**" in SECCION, codigo
        assert descripcion in SECCION, descripcion
    # Cómo aparecen caminos y vías pecuarias: el cruce de control queda anotado.
    assert "SIGPAC no tiene código para vías pecuarias" in SECCION
    assert "3.188 vértices" in SECCION


def test_ca2_registro_dice_si_hay_campos_de_titularidad() -> None:
    """CA2. Dado el mismo fichero, cuando se buscan campos de titular, declarante o similares,
    entonces el registro dice explícitamente si existen; si existen, se anota que **no
    entrarán en el sistema** (se descartan al leer)."""
    patrones = ("TITULAR", "DECLARANT", "PROPIET", "NIF", "DNI", "NOMBRE", "OWNER")
    for nombre, _tipo, _longitud, _decimales in _campos_dbf():
        assert not any(p in nombre.upper() for p in patrones), nombre
    assert "No existe ningún campo de titular" in SECCION


def test_ca3_citas_textuales_y_licencia_asumida() -> None:
    """CA3. Dado el texto íntegro de `<rights>` del feed, el aviso legal de la ficha y el
    Acuerdo del FEGA (si se puede leer), cuando se comparan, entonces el registro cita
    textualmente cada uno y concluye si se puede redistribuir; si no es concluyente, lo marca
    `asumido` y no `confirmado`."""
    feed = (FIXTURES / "feed_derechos_extracto.txt").read_text(encoding="utf-8")
    fega_feed = (
        "Según el Acuerdo de Distribución del FEGA, O.A. por el que se aprueban los criterios "
        "de acceso, formatos de entrega y condiciones."
    )
    pac = (
        "tienen por objeto facilitar al agricultor la cumplimentación de su solicitud "
        "de ayudas a la PAC"
    )
    assert fega_feed in feed
    assert fega_feed in SECCION
    assert pac in SECCION
    ficha = (FIXTURES / "ficha_datos_gob_extracto.txt").read_text(encoding="utf-8")
    cc_by = "https://creativecommons.org/licenses/by/4.0/legalcode.es"
    assert cc_by in ficha
    assert cc_by in SECCION
    terminos = (FIXTURES / "terminos_fega_hvd_extracto.txt").read_text(encoding="utf-8")
    cita_hvd = "tienen la consideración de datos específicos de alto valor"
    assert cita_hvd in terminos
    assert cita_hvd in SECCION
    assert "Fuente de los datos: FONDO ESPAÑOL DE GARANTÍA AGRARIA O.A." in SECCION
    # No concluyente por el Acuerdo del FEGA no leído: la licencia queda `asumido`.
    assert "`asumido`" in SECCION
    assert "no es concluyente" in SECCION


def test_ca4_vias_pecuarias_poligono_sin_anchura_legal() -> None:
    """CA4. Dado el polígono de la capa #36 (`IDEM_MA_VIAS_PECUARIAS`), cuando se comprueba,
    entonces el registro confirma que trae el **polígono** de la franja (ya confirmado: hallazgo
    3 de REGISTRY.md) y que **no hay campo de anchura legal**; la anchura oficial para la pista
    2 sale de `NM_AREA / NM_LONG` o de una tabla por tipo, y se documenta cuál es viable."""
    fixture_tramos = "tests/fixtures/livestock_trails/"
    fixture_tramos += "wfs_cql_colmenar_municipio_completo_15_tramos.xml"
    gml = (RAIZ / fixture_tramos).read_text(encoding="utf-8")
    assert "gml:Polygon" in gml or "gml:MultiSurface" in gml
    assert "LineString" not in gml
    assert "No hay campo de anchura legal" in SECCION
    assert "NM_AREA / NM_LONG" in SECCION
    # Tabla por tipo: topes legales de la Ley 3/1995, art. 4, y viabilidad documentada.
    assert "75 metros" in SECCION
    assert "37,5 metros" in SECCION
    assert "20 metros" in SECCION
    assert "Viable para #200" in SECCION


def test_ca5_reproyeccion_a_25830_anotada() -> None:
    """CA5. Dado que el fichero va en EPSG:4258, cuando se mide el solape con vías pecuarias,
    entonces el registro anota la reproyección a EPSG:25830 necesaria."""
    prj = (FIXTURES / "recinto.prj").read_text(encoding="latin-1")
    assert "GCS_ETRS_1989" in prj
    assert "EPSG:4258 → EPSG:25830" in SECCION
    assert "reproyectar" in SECCION
