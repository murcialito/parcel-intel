"""Historia #43: NOTICE de atribuciones por capa y ADR de licencias.

Son tests de documentación y coherencia: leen `NOTICE`, `docs/vision.md`,
`docs/adr/` y `src/parcel_intel/sources/REGISTRY.md`. No llaman a red.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
NOTICE = REPO / "NOTICE"
VISION = REPO / "docs" / "vision.md"
ADR_DIR = REPO / "docs" / "adr"
REGISTRY = REPO / "src" / "parcel_intel" / "sources" / "REGISTRY.md"

LICENCIA_IGN = "https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf"


def _seccion_notice(titulo: str) -> str:
    """Texto de una sección `## titulo` de NOTICE, hasta el siguiente `## `."""
    lineas = NOTICE.read_text(encoding="utf-8").splitlines()
    inicio = lineas.index(f"## {titulo}")
    resto = lineas[inicio + 1 :]
    fin = next((i for i, linea in enumerate(resto) if linea.startswith("## ")), len(resto))
    return "\n".join(resto[:fin])


def _filas_resumen_registry() -> list[list[str]]:
    """Filas de la tabla «Resumen» de REGISTRY.md (sección de fuentes del primer hito)."""
    lineas = REGISTRY.read_text(encoding="utf-8").splitlines()
    inicio = lineas.index("### Resumen") + 1
    filas: list[list[str]] = []
    for linea in lineas[inicio:]:
        if linea.startswith("#"):
            break
        es_cabecera = linea.startswith("| Fuente") or linea.startswith("| ---")
        if linea.startswith("| ") and not es_cabecera:
            celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
            filas.append(celdas)
    return filas


# Prefijo de la celda «Fuente» en REGISTRY.md → texto que NOTICE debe usar para esa fuente.
# Cada fuente marcada «Publicar» en el Resumen del registro debe tener una entrada aquí.
FUENTES_PUBLICABLES = {
    "PNOA ortofoto actual": "PNOA",
    "PNOA histórico": "PNOA",
    "Planimetrías / minutas del IGN": "Planimetrías",
    "Primera edición del MTN50": "MTN50",
    "Red de transporte del IGN": "Red de transporte",
    "Vías pecuarias (IDEM)": "Vías pecuarias",
    # Historia #187 (ADR 0060): texto literal de la legislación citada, del BOE.
    "BOE": "Boletín Oficial del Estado",
}


def test_ca1_notice_lista_fuentes_publicables_con_licencia_url_y_atribucion() -> None:
    """Dado el repo, cuando se lee `NOTICE` en la raíz, entonces lista cada fuente marcada
    «Publicar» en REGISTRY.md (IGN/CNIG: red de transporte, unidades administrativas, PNOA,
    planimetrías, MTN50; vías pecuarias IDEM) con su licencia, su URL de licencia y su texto
    de atribución tal como figura en REGISTRY.md (o "pendiente de verificar" si el registro no
    lo trae completo)."""
    texto = NOTICE.read_text(encoding="utf-8")
    publicables = _seccion_notice("Fuentes que pueden publicarse")
    registry = REGISTRY.read_text(encoding="utf-8")

    # Las cuatro familias que nombra el criterio.
    for familia in ("Red de transporte", "unidades administrativas", "PNOA", "Vías pecuarias"):
        assert familia in publicables, familia

    # URL de licencia del IGN/CNIG, la misma que cita REGISTRY.md.
    assert LICENCIA_IGN in publicables
    assert LICENCIA_IGN in registry

    # Textos de atribución exactos, tal como figuran en REGISTRY.md.
    atribuciones = [
        "Obra derivada de IGR-RT 2026 CC-BY 4.0 Instituto Geográfico Nacional",
        "Obra derivada de Planimetrías 1870-1950 CC-BY 4.0 "
        "© Instituto Geográfico Nacional de España",
        "Obra derivada de Primera edición MTN50 1875-1968 CC-BY 4.0 "
        "© Instituto Geográfico Nacional de España",
        "CC BY 4.0 scne.es",
        "CC BY 4.0 ign.es",
        "CC BY 4.0 Comunidad de Madrid",
    ]
    for atribucion in atribuciones:
        assert atribucion in publicables, atribucion
        assert atribucion in registry, f"no consta en REGISTRY.md: {atribucion}"

    # Lo que no se ha verificado queda marcado, no inventado.
    assert "pendiente de verificar" in publicables
    assert "pendiente de verificar" in texto


def test_ca2_notice_declara_catastro_interno_y_osm_fuera_del_mapa() -> None:
    """Dado `NOTICE`, cuando se lee la sección de fuentes no publicadas, entonces declara que
    Catastro (INSPIRE) es solo de uso interno y que sus capas derivadas no se publican hasta
    tener consulta jurídica, y que OpenStreetMap (ODbL) no entra en el mapa."""
    no_publicadas = _seccion_notice("Fuentes no publicadas")
    assert "Catastro (INSPIRE)" in no_publicadas
    assert "uso interno" in no_publicadas
    assert "consulta jurídica" in no_publicadas
    assert "OpenStreetMap (ODbL)" in no_publicadas
    assert "no entra en el mapa" in no_publicadas


def test_ca3_notice_distingue_licencia_de_codigo_y_de_datos_sin_titularidad() -> None:
    """Dado `NOTICE`, cuando se lee, entonces distingue la licencia del código (Apache-2.0) de
    la de los datos derivados publicados (CC BY 4.0) y no menciona a ningún propietario ni
    dato de titularidad."""
    texto = NOTICE.read_text(encoding="utf-8")
    licencias = _seccion_notice("Licencias")
    assert "Apache License 2.0" in licencias
    assert "CC BY 4.0" in licencias
    assert "Código" in licencias
    assert "Datos derivados publicados" in licencias
    minusculas = texto.lower()
    assert "propietari" not in minusculas
    assert "titular" not in minusculas


def test_ca4_vision_licencia_de_datos_resuelta_y_exclusiones_reflejadas() -> None:
    """Dado `docs/vision.md`, cuando se lee la sección de decisiones abiertas, entonces la
    licencia de datos derivados figura como resuelta (CC BY 4.0, 2026-11-25) y las filas de
    Catastro y OSM reflejan "no se publica por ahora"."""
    lineas = VISION.read_text(encoding="utf-8").splitlines()
    inicio = lineas.index("**Decisiones abiertas:**")
    fin = lineas.index("## Convenciones (sin cambios)")
    seccion = lineas[inicio:fin]
    prefijo = "- [ ] Licencia de los datos derivados"
    pendientes = [linea for linea in seccion if linea.startswith(prefijo)]
    resueltas = [linea for linea in seccion if linea.startswith(prefijo.replace("[ ]", "[x]"))]
    assert pendientes == []
    assert len(resueltas) == 1
    assert "CC BY 4.0" in resueltas[0]
    assert "2026-11-25" in resueltas[0]

    filas = [linea for linea in lineas if linea.startswith("| Catastro INSPIRE")]
    filas += [linea for linea in lineas if linea.startswith("| OpenStreetMap")]
    assert len(filas) == 2
    for fila in filas:
        assert "no se publica por ahora" in fila, fila


def test_ca5_adr_licencias_registra_las_tres_decisiones() -> None:
    """Dado `docs/adr/`, cuando se lista, entonces existe el ADR 0035
    (`0035-licencias-codigo-y-datos-publicados-notice.md`) que registra las tres decisiones
    (Apache-2.0, CC BY 4.0 con atribución por capa en la procedencia, exclusiones de Catastro
    y OSM) con su fecha, sin proponer decisiones nuevas. El test busca el fichero por el sufijo
    `licencias-codigo-y-datos-publicados-notice.md`, no por el número, para no romperse si el
    número vuelve a colisionar."""
    adrs = sorted(ADR_DIR.glob("*-licencias-codigo-y-datos-publicados-notice.md"))
    assert len(adrs) == 1, "debe existir exactamente un ADR de licencias por sufijo"
    texto = adrs[0].read_text(encoding="utf-8")
    assert "Apache-2.0" in texto
    assert "CC BY 4.0" in texto
    assert "atribución" in texto
    assert "Catastro" in texto
    assert "OpenStreetMap" in texto
    assert "2026-11-25" in texto


def test_ca6_coherencia_registry_publicar_frente_a_notice() -> None:
    """Dado un test de coherencia, cuando se ejecuta, entonces falla si una fuente marcada
    "Publicar" en REGISTRY.md no aparece en `NOTICE` o si `NOTICE` nombra Catastro como
    publicable."""
    publicables_notice = _seccion_notice("Fuentes que pueden publicarse")
    publicar = [fila[0] for fila in _filas_resumen_registry() if fila[4].startswith("**Publicar**")]

    # Cada fuente «Publicar» del registro tiene su entrada mapeada y aparece en NOTICE.
    asignadas: dict[str, str] = {}
    for nombre in publicar:
        prefijos = [p for p in FUENTES_PUBLICABLES if nombre.startswith(p)]
        assert len(prefijos) == 1, f"fuente «Publicar» sin mapear en este test: {nombre}"
        asignadas[nombre] = FUENTES_PUBLICABLES[prefijos[0]]
    assert set(FUENTES_PUBLICABLES) == {
        next(p for p in FUENTES_PUBLICABLES if n.startswith(p)) for n in publicar
    }
    for nombre, token in asignadas.items():
        assert token in publicables_notice, f"«{nombre}» no aparece en NOTICE"

    # Catastro nunca es publicable.
    assert "Catastro" not in publicables_notice
