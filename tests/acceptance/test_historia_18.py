"""Historia #18: ADR de georreferenciación y digitalización con revisión humana.

Es una historia de documentación: los tests leen el ADR nuevo de `docs/adr/` (buscado por
sufijo, no por número, lección de #43) y lo contrastan con los datos de #17
(`tests/fixtures/caminos/planimetrias/`), con la entidad de #19, con `NOTICE` y con
`.github/CODEOWNERS`. No llaman a red.

Nota sobre CA12: el cuerpo de la issue, copiado del repo anterior al migrar (ADR 0040), escribe
las referencias como `murcialito/parcel-intel#20`. Son las mismas issues de este repo (#20 es
la carga de la planimetría de Colmenar y #50 la protección de `curated/**`), así que el ADR las
escribe como `#20`, igual que el resto de `docs/adr/`, y el encabezado se comprueba con esa forma.
"""

import dataclasses
import json
import re
from pathlib import Path

import pytest

from parcel_intel.domain.historic_trail import HistoricTrail, derived_work_attribution
from tests.factories import make_synthetic_historic_trail

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
ADR_DIR = REPO / "docs" / "adr"
PLANIMETRIAS = REPO / "tests" / "fixtures" / "caminos" / "planimetrias"
SUFIJO = "-georreferenciacion-y-digitalizacion-con-revision-humana.md"

ENCABEZADOS = (
    "## Datos de partida",
    "### Imagen de trabajo",
    "### Transformación",
    "### Error",
    "### Registro",
    "### Digitalización y revisión",
    "### Almacenamiento e incertidumbre",
    "### Licencia y publicación",
    "### Herramientas",
    "### Umbrales de producto",
    "## Consecuencias para #19 y #20",
    "## Límites",
)
CADENAS = (
    "EPSG:25830",
    "RMSE",
    "Obra derivada de",
    "propuesto",
    "aprobado",
    "rechazado",
    "curated/historico/",
    "#50",
)
SHA_PLANIMETRIA = "4b356414497cae86e425a062354e174ff2ccedcd21dcaddc9a2677763fe2ae21"
SHA_MTN50 = "0c96eaa15797dcc3617838d3288e432f45a0ecbff60c5fe940ec0ff4bebe7c68"


def _adr_path() -> Path:
    adrs = sorted(ADR_DIR.glob(f"*{SUFIJO}"))
    assert len(adrs) == 1, f"debe existir exactamente un ADR que acabe en {SUFIJO}: {adrs}"
    return adrs[0]


def _adr() -> str:
    return _adr_path().read_text(encoding="utf-8")


def _lineas() -> list[str]:
    return _adr().splitlines()


def _seccion(encabezado: str) -> str:
    """Texto desde la línea que empieza por `encabezado` hasta el siguiente encabezado del
    mismo nivel o superior (`## ` corta siempre; `### ` corta solo una subsección)."""
    lineas = _lineas()
    inicio = next(i for i, linea in enumerate(lineas) if linea.startswith(encabezado))
    nivel = encabezado.split(" ", 1)[0]
    cortes = ("## ",) if nivel == "##" else ("## ", "### ")
    resto = lineas[inicio + 1 :]
    fin = next(
        (i for i, linea in enumerate(resto) if linea.startswith(cortes)),
        len(resto),
    )
    return "\n".join([lineas[inicio], *resto[:fin]])


def _plano(texto: str) -> str:
    """Texto sin saltos de línea ni negritas, para buscar frases partidas al maquetar."""
    return re.sub(r"\s+", " ", texto.replace("**", ""))


def _verificacion() -> dict[str, object]:
    datos = json.loads((PLANIMETRIAS / "verificacion.json").read_text(encoding="utf-8"))
    assert isinstance(datos, dict)
    return datos


def _imagen(clave: str) -> dict[str, object]:
    imagenes = _verificacion()["imagenes"]
    assert isinstance(imagenes, dict)
    imagen = imagenes[clave]
    assert isinstance(imagen, dict)
    return imagen


def _procedencia(nombre: str) -> dict[str, object]:
    datos = json.loads((PLANIMETRIAS / nombre).read_text(encoding="utf-8"))
    assert isinstance(datos, dict)
    return datos


def _filas_datos_de_partida() -> dict[str, list[str]]:
    """Filas de la tabla de "Datos de partida": rótulo → [planimetría, MTN50]."""
    filas: dict[str, list[str]] = {}
    for linea in _seccion("## Datos de partida").splitlines():
        if not linea.startswith("| ") or linea.startswith("| ---"):
            continue
        celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
        if len(celdas) == 3 and celdas[0]:
            filas[celdas[0].replace("**", "")] = celdas[1:]
    return filas


def _decimal(texto: str) -> float:
    return float(texto.replace(",", "."))


def _umbrales_mm() -> tuple[float, float]:
    """(mm de papel del RMSE LOO, mm de papel del residuo máximo), leídos del ADR."""
    texto = _plano(_seccion("### Umbrales de producto"))
    rmse = re.search(r"RMSE LOO ≤ (\d+,\d+) mm × escala", texto)
    residuo = re.search(r"residuo máximo ≤ (\d+,\d+) mm × escala", texto)
    assert rmse is not None and residuo is not None
    return _decimal(rmse.group(1)), _decimal(residuo.group(1))


# --- CA1 -----------------------------------------------------------------


def test_ca1_transformacion_modelo_puntos_fuente_y_alternativas() -> None:
    """CA1. Dado el ADR, cuando se lee la sección de transformación, entonces fija el modelo
    (p. ej. afín/polinómica/spline), el número mínimo de puntos de control, cómo se eligen y de
    qué fuente (PNOA, Catastro actual, hitos estables), y por qué se descartan las
    alternativas."""
    texto = _plano(_seccion("### Transformación"))

    assert "Afín de 6 parámetros por unidad" in texto
    assert "x = a + b·col + c·row ; y = d + e·col + f·row" in texto
    assert "Mínimo 6 retenidos por unidad, en ≥ 3 de los 4 cuadrantes" in texto
    assert "Orden de preferencia: (1) hitos estables" in texto
    assert "La coordenada se lee sobre PNOA" in texto
    assert "Nunca de Catastro" in texto
    assert "envolvente convexa" in texto
    descartadas = texto.split("Alternativas descartadas:", 1)[1]
    for alternativa in ("Helmert", "Polinómica de 2.º orden", "Thin plate spline", "WMS o del ECW"):
        motivo = descartadas.split(alternativa, 1)[1].split("- ", 1)[0]
        assert len(motivo.strip(" *:")) > 20, f"{alternativa} sin motivo de descarte"


# --- CA2 -----------------------------------------------------------------


def test_ca2_error_metrica_umbrales_por_tipo_y_rechazo() -> None:
    """CA2. Dado el ADR, cuando se lee la sección de error, entonces define la métrica (RMSE y
    error máximo sobre puntos de control retenidos), el umbral admitido por tipo de documento
    (planimetría / MTN50) y qué ocurre si se supera (el documento no se carga)."""
    error = _plano(_seccion("### Error"))
    assert "RMSE de ajuste, residuo máximo y RMSE con validación cruzada" in error
    assert "sobre los puntos retenidos" in error
    assert "El error publicado de la unidad, y de cada trazado suyo, es el RMSE LOO" in error
    assert "la unidad no se carga" in error
    assert "no aporta ningún trazado" in error

    umbrales = _plano(_seccion("### Umbrales de producto"))
    assert "Planimetría y MTN50" in umbrales
    rmse_mm, residuo_mm = _umbrales_mm()
    assert (rmse_mm, residuo_mm) == (0.6, 1.4)
    for escala, etiqueta in ((25_000, "1:25.000"), (50_000, "1:50.000")):
        rmse_m = round(rmse_mm * escala / 1000)
        residuo_m = round(residuo_mm * escala / 1000)
        assert f"{etiqueta} → {rmse_m} m / {residuo_m} m" in umbrales


# --- CA3 -----------------------------------------------------------------


def test_ca3_registro_que_se_guarda_y_donde() -> None:
    """CA3. Dado el ADR, cuando se lee la sección de registro, entonces especifica qué se guarda
    por documento (id, URL, fecha de descarga, hash del original, licencia, puntos de control,
    parámetros, error, quién y cuándo) y dónde (crudos inmutables en `data/`, metadatos en el
    modelo de #19)."""
    texto = _plano(_seccion("### Registro"))

    for dato in (
        "`unit_id`, número de documento IGN",
        "URL exacta",
        "fecha de descarga",
        "licencia",
        "sha256",
        "todos los puntos de control",
        "los parámetros a–f",
        "RMSE, residuo máximo, LOO",
        "quién puso los puntos (usuario de GitHub) y cuándo",
    ):
        assert dato in texto, dato
    assert "la imagen, inmutable, en `data/raw/ign_planimetrias/<unit_id>.*`" in texto
    assert "`curated/historico/<unit_id>/`" in texto
    assert "`historic_georeference`, #20" in texto
    assert "`historic_trail` (#19)" in texto
    assert "Git es la fuente de verdad" in texto


# --- CA4 -----------------------------------------------------------------


def test_ca4_flujo_de_revision_estados_aprobador_evidencia_y_publicacion() -> None:
    """CA4. Dado el ADR, cuando se lee la sección de digitalización, entonces describe el flujo
    propuesto → aprobado/rechazado (estados, quién aprueba, qué evidencia se muestra: recorte de
    la imagen original junto al trazado), y que solo los aprobados se publican."""
    texto = _plano(_seccion("### Digitalización y revisión"))

    assert "`propuesto` → `aprobado` | `rechazado`" in texto
    assert "`proposed/approved/rejected`" in texto
    assert "Ningún agente digitaliza ni marca `aprobado`." in texto
    assert "Aprueba un miembro de CODEOWNERS de `curated/**`" in _seccion(
        "### Digitalización y revisión"
    )
    assert "#50" in texto
    assert "El recorte de la imagen de trabajo con el trazado dibujado encima." in texto
    assert "El recorte de PNOA 2023 con el trazado transformado" in texto
    assert "Solo los `aprobado` se transforman, se guardan como `approved` y se publican" in texto
    assert "Rechazar exige `review_note`." in texto

    codeowners = (REPO / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    assert any(
        linea.split()[0] == "curated/**"
        for linea in codeowners.splitlines()
        if linea.strip() and not linea.startswith("#")
    ), "la garantía que cita el ADR (#50) debe existir en CODEOWNERS"


# --- CA5 -----------------------------------------------------------------


def test_ca5_almacenamiento_crs_simplificacion_e_incertidumbre() -> None:
    """CA5. Dado el ADR, cuando se lee la sección de almacenamiento, entonces fija geometría en
    EPSG:25830, la tolerancia de simplificación y cómo se representa la incertidumbre
    posicional del trazado (p. ej. error del documento como atributo) sin presentarla como
    precisión que no tiene."""
    texto = _plano(_seccion("### Almacenamiento e incertidumbre"))

    assert "`LineString` en EPSG:25830, guardada sin simplificar (tolerancia 0)" in texto
    assert "Douglas-Peucker a `min(2 m, LOO/5)`" in texto
    assert "`georeferencing_error_m` = RMSE LOO de la unidad" in texto
    assert "banda de ± 2 × error, no como una línea fina" in texto
    assert "nunca muestra coordenadas con más precisión que el metro" in texto
    assert "georeferencing_error_m" in {f.name for f in dataclasses.fields(HistoricTrail)}


# --- CA6 -----------------------------------------------------------------


def test_ca6_atribucion_por_producto_y_sin_titularidad() -> None:
    """CA6. Dado el ADR, cuando se lee la sección de licencia y publicación, entonces incluye
    el texto de atribución "Obra derivada de …" por producto y confirma que ningún dato de
    titularidad entra en el flujo."""
    texto = _plano(_seccion("### Licencia y publicación"))
    licencia = re.search(r'`license = "([^"]+)"`', texto)
    assert licencia is not None
    planimetria = re.search(r"`(Obra derivada de Planimetría de Colmenar de Oreja[^`]+)`", texto)
    mtn50 = re.search(r"`(Obra derivada de Primera edición MTN50, IGN, hoja 0606[^`]+)`", texto)
    assert planimetria is not None and mtn50 is not None

    # Las cadenas por trazado salen tal cual de `derived_work_attribution` (#19).
    base = make_synthetic_historic_trail()
    casos = (
        ("Planimetría de Colmenar de Oreja, IGN, documento 280075", base.document_date,
         planimetria.group(1)),
        ("Primera edición MTN50, IGN, hoja 0606", base.document_date.replace(year=1881),
         mtn50.group(1)),
    )
    for source, fecha, esperado in casos:
        trail = dataclasses.replace(
            base,
            document_date=fecha,
            provenance=dataclasses.replace(
                base.provenance, source=source, license=licencia.group(1)
            ),
        )
        assert derived_work_attribution(trail) == esperado

    # Las cadenas por capa son las de NOTICE (#43) y de las procedencias de #17.
    notice = (REPO / "NOTICE").read_text(encoding="utf-8")
    for nombre in (
        "planimetria_colmenar_280075.provenance.json",
        "mtn50_0606_chinchon.provenance.json",
    ):
        atribucion = _procedencia(nombre)["atribucion"]
        assert isinstance(atribucion, str)
        assert f"`{atribucion}`" in texto
        assert atribucion in notice
    assert "`Obra derivada de PNOA 2023 CC-BY 4.0 scne.es`" in texto
    assert "Obra derivada de PNOA 2023 CC-BY 4.0 scne.es" in notice

    assert "Ningún dato de titularidad: Catastro no interviene" in texto
    assert "nunca de fincas, casas ni personas" in texto


# --- CA7 -----------------------------------------------------------------


def test_ca7_herramientas_licencia_coste_y_proveedor() -> None:
    """CA7. Dado el ADR, cuando se lee la sección de herramientas, entonces indica qué
    herramientas externas se usan para georreferenciar (solo en adapters/offline), su licencia
    y coste, y justifica que no hay coste recurrente; si hay proveedor nuevo, lo declara como
    tal."""
    texto = _plano(_seccion("### Herramientas"))

    assert "QGIS (GPL-2.0+, gratuito)" in texto
    assert "fuera de línea" in texto
    assert "`domain/` con stdlib" in texto
    assert "Pillow (HPND, gratuita)" in texto
    assert "solo en `adapters/evidence/`" in texto
    assert "Sin proveedor nuevo" in texto
    assert "Sin coste recurrente" in texto


# --- CA8 -----------------------------------------------------------------


def test_ca8_consecuencias_para_19_y_20_sin_ambiguedad() -> None:
    """CA8. Dado el ADR, cuando se contrasta con el diseño de #19 y murcialito/parcel-intel#20,
    entonces enumera las
    consecuencias para ambas (campos de la entidad, ports, migración, formato de entrada de los
    puntos de control) sin ambigüedad."""
    texto = _plano(_seccion("## Consecuencias para #19 y #20"))

    # #19: cada campo citado existe en la entidad fusionada y no se pide ninguno nuevo.
    assert "#19 no cambia." in texto
    campos = {f.name for f in dataclasses.fields(HistoricTrail)}
    citados = {"document_id", "identifier", "georeferencing_error_m", "reviewer"}
    assert citados <= campos
    for campo in citados:
        assert f"`{campo}`" in texto
    assert "`provenance.source` y `provenance.license`" in texto
    assert "`identifier` = `<unit_id>-<trail_id>`" in texto

    # #20: dominio, ports, adapters, migración y formato de los puntos.
    for pieza in (
        "`domain/georeferencing.py`",
        "`ports/errors.py`",
        "`WorkingImagePort`, `CuratedHistoricInputPort` y `GeoreferenceRepositoryPort`",
        "tabla `historic_georeference` con UPSERT por `unit_id`",
        "`load_historic_trails`",
        "`historico ajuste|evidencia|cargar`",
        "`point_id,col,row,x_25830,y_25830,coordinate_source,description,retained,discard_reason`",
        "`control_points_sha256`",
    ):
        assert pieza in texto, pieza


# --- CA9 -----------------------------------------------------------------


def test_ca9_limites_del_metodo_como_indicio() -> None:
    """CA9. Dado el ADR, cuando se lee la sección de límites, entonces declara qué no garantiza
    el método (error de la época, deformación del papel, caminos ya desaparecidos) para que el
    visor lo exprese como indicio."""
    texto = _plano(_seccion("## Límites"))

    assert "no la exactitud del dibujo de la época" in texto
    assert "deformación local del papel" in texto
    assert "puede haber desaparecido" in texto
    assert "Su ausencia hoy no es prueba de corte." in texto
    assert "indicio fechado con su error" in texto
    assert "nunca una prueba, un deslinde ni un dictamen" in texto


# --- CA10 ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("clave", "columna", "procedencia", "escala"),
    [
        ("planimetria_colmenar_280075", 0, "planimetria_colmenar_280075.provenance.json", 25_000),
        ("mtn50_0606_chinchon", 1, "mtn50_0606_chinchon.provenance.json", 50_000),
    ],
)
def test_ca10_datos_de_partida_citan_17_y_aplican_la_viabilidad(
    clave: str, columna: int, procedencia: str, escala: int
) -> None:
    """CA10 (añadido por el arquitecto, precisado el 2026-11-26). Dado
    `tests/fixtures/caminos/planimetrias/verificacion.json` de #17, cuando se lee la sección
    "Datos de partida" del ADR, entonces cita de ahí, para la planimetría 280075 y la hoja MTN50
    0606, el formato, las dimensiones en píxeles, la resolución efectiva (m/píxel), la escala
    del documento y el número de puntos de control candidatos; y aplica la regla de viabilidad
    del documento (resolución efectiva ≤ U/3 y ≥ 6 puntos candidatos identificables). Si un
    documento no la cumple, el ADR lo declara "no georreferenciable con este método" y aplica la
    rama alternativa; no lo deja abierto. El reparto de los puntos (≥ 3 cuadrantes) es una
    condición de la carga de cada unidad, no de la viabilidad del documento, y el ADR dice qué
    pasaría hoy con los puntos de #17."""
    imagen = _imagen(clave)
    prov = _procedencia(procedencia)
    filas = _filas_datos_de_partida()

    def celda(rotulo: str) -> str:
        return filas[rotulo][columna]

    assert celda("Formato") == imagen["formato"] == prov["formato"]
    completa = imagen["imagen_completa_cacheada"]
    assert isinstance(completa, dict)
    pixeles = completa["pixeles"]
    assert isinstance(pixeles, dict)
    assert celda("Píxeles").startswith(f"{pixeles['ancho']} × {pixeles['alto']}")
    assert celda("sha256") == f"`{prov['sha256']}`"
    assert celda("m/píxel del render") == str(completa["metros_por_pixel"]).replace(".", ",")

    resolucion = imagen["resolucion_efectiva"]
    assert isinstance(resolucion, dict)
    nativa = float(resolucion["metros_por_pixel_nativo_estimado"])
    rango = resolucion["rango_m_px"]
    assert isinstance(rango, list)
    peor = max(float(rango[1]), float(completa["metros_por_pixel"]))
    efectiva = max(nativa, float(completa["metros_por_pixel"]))
    assert celda("Resolución efectiva (la peor de las dos)") == (
        f"{_fmt(efectiva)} m/px ({_fmt(peor)} en el peor caso)"
    )
    assert celda("Escala del documento").startswith(f"1:{escala:,}".replace(",", "."))

    candidatos = imagen["puntos_control"]
    resumen = imagen["resumen_puntos_control"]
    assert isinstance(candidatos, list) and isinstance(resumen, dict)
    n_candidatos = len(candidatos)
    assert n_candidatos == resumen["total"]
    assert celda("Puntos candidatos identificables").startswith(str(n_candidatos))
    assert celda("De ellos con coordenada").startswith(str(resumen["con_coordenada"]))

    # Regla de viabilidad recalculada con los umbrales del propio ADR.
    rmse_mm, _ = _umbrales_mm()
    umbral = rmse_mm * escala / 1000
    assert celda("U y U/3") == f"{_fmt(umbral)} m y {_fmt(umbral / 3)} m/px"
    viable = peor <= umbral / 3 and n_candidatos >= 6
    assert viable
    assert celda("Viabilidad").replace("**", "").startswith("Viable con este método")

    texto = _plano(_seccion("## Datos de partida"))
    assert "no de la viabilidad del documento" in texto
    assert "la carga de cualquiera de las dos unidades se rechazaría" in texto
    assert "un solo cuadrante" in texto
    # La rama alternativa para un documento no viable está decidida, no abierta.
    assert "Rama alternativa (documento no viable" in _plano(_seccion("### Imagen de trabajo"))


def _fmt(valor: float) -> str:
    return f"{valor:g}".replace(".", ",")


# --- CA11 ----------------------------------------------------------------


def test_ca11_umbrales_en_subseccion_propia_con_fecha_del_fundador() -> None:
    """CA11 (añadido por el arquitecto). Dados los umbrales numéricos del ADR, cuando se lee,
    entonces aparecen en una subsección propia cuyo título empieza por "Umbrales de producto",
    separada de las decisiones de arquitectura (lección del ciclo 0006–0010), con la fecha de
    aprobación del fundador."""
    titulos = [linea for linea in _lineas() if linea.startswith("### Umbrales de producto")]
    assert titulos == ["### Umbrales de producto (aprobados por el fundador el 2026-11-26)"]

    umbrales = _plano(_seccion("### Umbrales de producto"))
    for cifra in ("0,6 mm", "1,4 mm", "15 m / 35 m", "30 m / 70 m", "≥ 6 retenidos", "25 %"):
        assert cifra in umbrales, cifra
    # Las decisiones de arquitectura remiten a la subsección en vez de repetir las cifras.
    assert "los de \"Umbrales de producto\"" in _plano(_seccion("### Error"))
    for seccion in ("### Transformación", "### Error", "### Registro"):
        assert "15 m" not in _seccion(seccion) and "0,6 mm" not in _seccion(seccion)


# --- CA12 ----------------------------------------------------------------


def test_ca12_adr_unico_con_encabezados_cadenas_y_datos_sin_pendientes() -> None:
    """CA12 (añadido por el arquitecto, precisado el 2026-11-26). Dada la suite, cuando se
    ejecuta `pytest -m acceptance` sin red, entonces `tests/acceptance/test_historia_18.py`
    comprueba que existe exactamente un ADR en `docs/adr/` cuyo nombre acaba en
    `-georreferenciacion-y-digitalizacion-con-revision-humana.md`; que contiene estos
    encabezados literales: `## Datos de partida`, `### Imagen de trabajo`, `### Transformación`,
    `### Error`, `### Registro`, `### Digitalización y revisión`, `### Almacenamiento e
    incertidumbre`, `### Licencia y publicación`, `### Herramientas`, `### Umbrales de
    producto`, `## Consecuencias para #19 y murcialito/parcel-intel#20` y `## Límites`; que contiene
    las cadenas `EPSG:25830`, `RMSE`, `Obra derivada de`, `propuesto`, `aprobado`, `rechazado`,
    `curated/historico/` y `#50`; y que la sección "Datos de partida" (hasta el siguiente
    `## `) no contiene la palabra "pendiente" y sí los dos sha256 de las imágenes completas de
    #17 (`4b356414…` y `0c96eaa1…`, completos)."""
    adr = _adr()
    lineas = adr.splitlines()

    for encabezado in ENCABEZADOS:
        assert any(linea.startswith(encabezado) for linea in lineas), encabezado
    for cadena in CADENAS:
        assert cadena in adr, cadena

    datos = _seccion("## Datos de partida")
    assert "pendiente" not in datos.lower()
    assert SHA_PLANIMETRIA in datos
    assert SHA_MTN50 in datos
    assert _procedencia("planimetria_colmenar_280075.provenance.json")["sha256"] == SHA_PLANIMETRIA
    assert _procedencia("mtn50_0606_chinchon.provenance.json")["sha256"] == SHA_MTN50
