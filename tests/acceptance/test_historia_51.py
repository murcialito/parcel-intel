"""Historia #51: formato y validador del conjunto de validación (casos.json).

Son tests de documento y validador: leen `docs/validacion/casos.json` y llaman a
`validar_casos` sobre casos sintéticos construidos aquí. No llaman a red.

Cada test de rechazo parte de un caso válido y rompe un solo aspecto, para no pasar
por la razón equivocada.
"""

import copy
import json
from pathlib import Path

import pytest

from tests.validacion.casos_schema import validar_casos

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
CASOS = REPO / "docs" / "validacion" / "casos.json"

CAMPOS_OBLIGATORIOS = (
    "id",
    "fuente_url",
    "fuente_tipo",
    "fecha_consulta",
    "municipio",
    "ambito",
    "tramo_descripcion",
    "cierre_fecha_aproximada",
)


def _caso_valido() -> dict[str, object]:
    return {
        "id": "caso-valido-1",
        "fuente_url": "https://www.ejemplo.es/articulo-camino",
        "fuente_tipo": "prensa",
        "fecha_consulta": "2026-11-26",
        "municipio": "Colmenar de Oreja",
        "ambito": "hito",
        "tramo_descripcion": (
            "camino entre la carretera de Ocaña y el arroyo del Soto, paraje Las Eras"
        ),
        "cierre_fecha_aproximada": "2019-05",
    }


def _con(caso: dict[str, object], **cambios: object) -> dict[str, object]:
    nuevo = copy.deepcopy(caso)
    nuevo.update(cambios)
    return nuevo


def _doc(*casos: dict[str, object]) -> dict[str, object]:
    return {"casos": list(casos)}


def test_ca1_fichero_real_no_devuelve_errores() -> None:
    """Dado `docs/validacion/casos.json` tal como está en el repo, cuando se ejecuta el
    validador, entonces no devuelve errores. (El fichero arranca con `{"casos": []}` o con
    un único caso sintético con `"sintetico": true`; ese caso se ignora en los recuentos de
    #52/#53.)"""
    datos: object = json.loads(CASOS.read_text(encoding="utf-8"))
    assert validar_casos(datos) == []


def test_ca2_campo_obligatorio_ausente_nombra_campo_e_id() -> None:
    """Dado un caso al que le falta cualquiera de los campos obligatorios `id`,
    `fuente_url`, `fuente_tipo`, `fecha_consulta`, `municipio`, `ambito`,
    `tramo_descripcion`, `cierre_fecha_aproximada`, cuando se valida, entonces el error
    nombra el campo ausente y el `id` (o la posición) del caso."""
    for campo in CAMPOS_OBLIGATORIOS:
        caso = _caso_valido()
        del caso[campo]
        errores = validar_casos(_doc(caso))
        assert len(errores) >= 1, campo
        # Sin `id` el caso se localiza por su posición (caso #1); con `id`, por el id.
        localizador = "caso #1" if campo == "id" else "caso-valido-1"
        assert any(campo in e and localizador in e for e in errores), (campo, errores)


def test_ca3_campo_fuera_de_lista_es_error_y_nombra_titularidad() -> None:
    """Dado un caso con un campo fuera de la lista permitida (los obligatorios más los
    opcionales `tramo_linea` y `sintetico`), cuando se valida, entonces es error, y el
    mensaje es explícito si el campo es `propietario`, `titular` o `referencia_catastral`
    (o variantes como `refcat`, `ref_catastral`)."""
    for campo in ("propietario", "titular", "referencia_catastral", "refcat", "ref_catastral"):
        errores = validar_casos(_doc(_con(_caso_valido(), **{campo: "dato"})))
        assert len(errores) == 1, (campo, errores)
        assert campo in errores[0]
        assert "titularidad" in errores[0] and "prohibido" in errores[0], errores[0]

    errores_otro = validar_casos(_doc(_con(_caso_valido(), notas="texto libre")))
    assert len(errores_otro) == 1
    assert "notas" in errores_otro[0]
    assert "prohibido" not in errores_otro[0]


def test_ca4_referencia_catastral_o_sociedad_en_texto_es_error_sin_falsos_positivos() -> None:
    """Dado un caso cuyo texto (cualquier valor de cadena salvo `fuente_url`) contiene una
    referencia catastral (14 o 20 caracteres alfanuméricos con el patrón de Catastro, p. ej.
    `99043A90100001` o `99043A901000010000AQ`) o un patrón de sociedad (`S.L.`, `S.A.`,
    `S.L.U.`, `SL`, `SA` como palabra suelta en mayúsculas), cuando se valida, entonces es
    error. Un caso con una descripción neutra normal ("camino entre X e Y, paraje Z") no
    genera falsos positivos."""
    assert validar_casos(_doc(_caso_valido())) == []

    textos_con_dato = [
        "camino entre la finca de 99043A90100001 y el arroyo",
        "camino entre la finca de 99043A901000010000AQ y el arroyo",
        "cerrado por Promociones Ejemplo S.L.",
        "cerrado por Promociones Ejemplo S.A.",
        "cerrado por Promociones Ejemplo S.L.U.",
        "cerrado por Promociones Ejemplo SL",
        "cerrado por Promociones Ejemplo SA",
    ]
    for texto in textos_con_dato:
        errores = validar_casos(_doc(_con(_caso_valido(), tramo_descripcion=texto)))
        assert len(errores) >= 1, texto
        assert any("caso-valido-1" in e for e in errores), (texto, errores)


def test_ca5_url_no_https_o_fecha_consulta_invalida_es_error() -> None:
    """Dado `fuente_url` que no empieza por `https://` o `fecha_consulta` que no es una fecha
    ISO válida (`AAAA-MM-DD`, p. ej. `2026-02-30` es inválida), cuando se valida, entonces
    es error."""
    assert validar_casos(_doc(_caso_valido())) == []
    for url in ("http://www.ejemplo.es/a", "ftp://ejemplo.es/a", "www.ejemplo.es/a"):
        assert validar_casos(_doc(_con(_caso_valido(), fuente_url=url))) != [], url
    for fecha in ("2026-02-30", "2026/11/26", "26-11-2026"):
        assert validar_casos(_doc(_con(_caso_valido(), fecha_consulta=fecha))) != [], fecha


def test_ca6_valores_fuera_de_enumeracion_o_municipio_fuera_de_ambito_es_error() -> None:
    """Dado `fuente_tipo` fuera de {`prensa`, `asociación`, `resolución`, `otra`}, o `ambito`
    fuera de {`hito`, `comunidad`}, o `ambito: "hito"` con un `municipio` que no es uno de los
    7 del ámbito, cuando se valida, entonces es error."""
    assert validar_casos(_doc(_caso_valido())) == []
    assert validar_casos(_doc(_con(_caso_valido(), fuente_tipo="blog"))) != []
    assert validar_casos(_doc(_con(_caso_valido(), ambito="provincia"))) != []
    assert validar_casos(_doc(_con(_caso_valido(), municipio="Madrid"))) != []
    for tipo in ("prensa", "asociación", "resolución", "otra"):
        assert validar_casos(_doc(_con(_caso_valido(), fuente_tipo=tipo))) == [], tipo
    # Fuera del ámbito del hito, un municipio de la Comunidad de Madrid es válido.
    comunidad = _con(_caso_valido(), ambito="comunidad", municipio="Madrid")
    assert validar_casos(_doc(comunidad)) == []


def test_ca7_id_duplicado_o_con_formato_invalido_es_error() -> None:
    """Dado `id` duplicado entre dos casos, o `id` que no cumple `^[a-z0-9][a-z0-9-]*$`,
    cuando se valida, entonces es error."""
    dos_iguales = _doc(_caso_valido(), _con(_caso_valido(), municipio="Aranjuez"))
    errores = validar_casos(dos_iguales)
    assert any("duplicado" in e and "caso-valido-1" in e for e in errores), errores
    for ident in ("Caso_1", "caso 1", "-caso", "caso.1", "Caso-Mayuscula"):
        assert validar_casos(_doc(_con(_caso_valido(), id=ident))) != [], ident
    assert validar_casos(_doc(_con(_caso_valido(), id="caso-1"))) == []


def test_ca8_cierre_fecha_aproximada_invalida_es_error() -> None:
    """Dado `cierre_fecha_aproximada` que no sea `AAAA`, `AAAA-MM` o `AAAA-MM-DD` válidos,
    cuando se valida, entonces es error."""
    for valido in ("2019", "2019-05", "2019-05-17"):
        assert validar_casos(_doc(_con(_caso_valido(), cierre_fecha_aproximada=valido))) == []
    for invalido in ("19", "2019-13", "2019-02-30", "2019-5", "mayo 2019", "2019/05"):
        errores = validar_casos(_doc(_con(_caso_valido(), cierre_fecha_aproximada=invalido)))
        assert errores != [], invalido


def test_ca9_tramo_linea_valida_o_rechaza_puntos_pocos_fuera_de_rango_o_cerrados() -> None:
    """Dado `tramo_linea` (opcional), cuando es una lista de al menos 2 puntos `[x, y]` con
    números finitos en un rango plausible de EPSG:25830 para Madrid (x entre 300000 y 600000,
    y entre 4400000 y 4500000), entonces es válido; con menos de 2 puntos, valores no
    numéricos o fuera de rango, es error. Un polígono cerrado (primer punto igual al último)
    también es error: es una línea, no una parcela."""
    linea = [[430000, 4450000], [431000, 4451000]]
    assert validar_casos(_doc(_con(_caso_valido(), tramo_linea=linea))) == []

    malos = {
        "un solo punto": [[430000, 4450000]],
        "punto no numérico": [[430000, 4450000], ["431000", 4451000]],
        "x fuera de rango": [[100000, 4450000], [431000, 4451000]],
        "y fuera de rango": [[430000, 4450000], [431000, 9000000]],
        "polígono cerrado": [[430000, 4450000], [431000, 4451000], [430000, 4450000]],
    }
    for motivo, tramo in malos.items():
        errores = validar_casos(_doc(_con(_caso_valido(), tramo_linea=tramo)))
        assert errores != [], motivo
