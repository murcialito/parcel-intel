"""Validador del conjunto de validación de caminos cerrados (`docs/validacion/casos.json`).

Historia #51. Solo stdlib: es herramienta de prueba, no lógica de producto, así que vive en
`tests/` y no en `src/`. Las historias #52, #53 y #54 reutilizan `validar_casos` sin duplicarlo.

Reglas que hace cumplir (ver `docs/validacion/README.md`): formato fijo de campos, fuente
rastreable y ningún dato de titularidad ni referencia catastral en los textos del caso.
"""

import datetime
import math
import re

CAMPOS_OBLIGATORIOS: tuple[str, ...] = (
    "id",
    "fuente_url",
    "fuente_tipo",
    "fecha_consulta",
    "municipio",
    "ambito",
    "tramo_descripcion",
    "cierre_fecha_aproximada",
)
CAMPOS_OPCIONALES: tuple[str, ...] = ("tramo_linea", "sintetico")

FUENTES_TIPO: frozenset[str] = frozenset({"prensa", "asociación", "resolución", "otra"})
AMBITOS: frozenset[str] = frozenset({"hito", "comunidad"})
MUNICIPIOS_HITO: frozenset[str] = frozenset(
    {
        "Colmenar de Oreja",
        "Aranjuez",
        "Chinchón",
        "Belmonte de Tajo",
        "Villaconejos",
        "Villarejo de Salvanés",
        "Valdelaguna",
    }
)

# Fragmentos de nombre de campo que delatan titularidad o referencia catastral.
_FRAGMENTOS_PROHIBIDOS: tuple[str, ...] = ("propietar", "titular", "catastral", "refcat")

_PATRON_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_PATRON_FECHA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PATRON_CIERRE = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")
# Referencia catastral de 14 caracteres (p. ej. 99043A90100001) o de 20 (…0000AQ).
_PATRON_REF_CATASTRAL = re.compile(
    r"(?<![0-9A-Za-z])[0-9]{5}[A-Z][0-9]{8}(?:[0-9]{4}[A-Z]{2})?(?![0-9A-Za-z])"
)
# Forma societaria como palabra suelta en mayúsculas.
_PATRON_SOCIEDAD = re.compile(r"(?<![\w.])(?:S\.L\.U\.|S\.L\.|S\.A\.|SL|SA)(?!\w)")


def validar_casos(datos: object) -> list[str]:
    """Devuelve los errores de un conjunto de casos (lista vacía si es válido).

    `datos` es el JSON ya parseado: un objeto con la clave `casos`, una lista de casos.
    """
    if not isinstance(datos, dict):
        return ["el fichero debe ser un objeto JSON con la clave 'casos'"]
    errores = [f"clave de primer nivel no permitida: '{c}'" for c in datos if c != "casos"]
    casos = datos.get("casos")
    if not isinstance(casos, list):
        return [*errores, "'casos' debe ser una lista"]
    ids_vistos: set[str] = set()
    for posicion, caso in enumerate(casos, start=1):
        errores.extend(_validar_caso(caso, posicion, ids_vistos))
    return errores


def _validar_caso(caso: object, posicion: int, ids_vistos: set[str]) -> list[str]:
    if not isinstance(caso, dict):
        return [f"caso #{posicion}: debe ser un objeto"]
    et = _etiqueta(caso, posicion)
    errores: list[str] = []

    for campo in CAMPOS_OBLIGATORIOS:
        if campo not in caso:
            errores.append(f"{et}: falta el campo obligatorio '{campo}'")
    for clave in caso:
        if clave not in CAMPOS_OBLIGATORIOS and clave not in CAMPOS_OPCIONALES:
            errores.append(_error_campo_no_permitido(clave, et))

    for campo in CAMPOS_OBLIGATORIOS:
        if campo in caso and _texto(caso[campo]) is None:
            errores.append(f"{et}: '{campo}' debe ser texto no vacío")

    errores.extend(_errores_de_valores(caso, et, ids_vistos))

    if "tramo_linea" in caso:
        errores.extend(_errores_tramo_linea(caso["tramo_linea"], et))
    if "sintetico" in caso and not isinstance(caso["sintetico"], bool):
        errores.append(f"{et}: 'sintetico' debe ser true o false")
    return errores


def _errores_de_valores(caso: dict[object, object], et: str, ids_vistos: set[str]) -> list[str]:
    """Reglas sobre los valores de texto: solo se aplican cuando el campo ya es texto."""
    errores: list[str] = []

    ident = _texto(caso.get("id"))
    if ident is not None:
        if _PATRON_ID.match(ident) is None:
            errores.append(f"{et}: 'id' no cumple ^[a-z0-9][a-z0-9-]*$")
        elif ident in ids_vistos:
            errores.append(f"{et}: 'id' duplicado '{ident}'")
        ids_vistos.add(ident)

    url = _texto(caso.get("fuente_url"))
    if url is not None and not url.startswith("https://"):
        errores.append(f"{et}: 'fuente_url' debe empezar por https://")

    tipo = _texto(caso.get("fuente_tipo"))
    if tipo is not None and tipo not in FUENTES_TIPO:
        errores.append(
            f"{et}: 'fuente_tipo' no válido: debe ser prensa, asociación, resolución u otra"
        )

    fecha = _texto(caso.get("fecha_consulta"))
    if fecha is not None and not _fecha_iso_valida(fecha):
        errores.append(f"{et}: 'fecha_consulta' debe ser una fecha AAAA-MM-DD válida")

    ambito = _texto(caso.get("ambito"))
    if ambito is not None and ambito not in AMBITOS:
        errores.append(f"{et}: 'ambito' no válido: debe ser hito o comunidad")
    municipio = _texto(caso.get("municipio"))
    if ambito == "hito" and municipio is not None and municipio not in MUNICIPIOS_HITO:
        errores.append(f"{et}: 'municipio' '{municipio}' no pertenece a los 7 del ámbito")

    cierre = _texto(caso.get("cierre_fecha_aproximada"))
    if cierre is not None and not _fecha_cierre_valida(cierre):
        errores.append(f"{et}: 'cierre_fecha_aproximada' debe ser AAAA, AAAA-MM o AAAA-MM-DD")

    for clave, valor in caso.items():
        if clave == "fuente_url":
            continue  # la única cadena que puede llevar una URL con cualquier contenido
        for texto in _textos(valor):
            if _PATRON_REF_CATASTRAL.search(texto):
                errores.append(f"{et}: el campo '{clave}' contiene una referencia catastral")
            if _PATRON_SOCIEDAD.search(texto):
                errores.append(f"{et}: el campo '{clave}' contiene un nombre de sociedad")
    return errores


def _errores_tramo_linea(valor: object, et: str) -> list[str]:
    if not isinstance(valor, list) or len(valor) < 2:
        return [f"{et}: 'tramo_linea' debe ser una lista de al menos 2 puntos [x, y]"]
    errores: list[str] = []
    puntos: list[tuple[float, float]] = []
    for indice, crudo in enumerate(valor, start=1):
        punto = _punto(crudo)
        if punto is None:
            errores.append(f"{et}: el punto {indice} de 'tramo_linea' no es un par [x, y] numérico")
            continue
        x, y = punto
        if not (300000 <= x <= 600000 and 4400000 <= y <= 4500000):
            errores.append(
                f"{et}: el punto {indice} de 'tramo_linea' está fuera del rango de EPSG:25830"
                " para Madrid"
            )
        puntos.append(punto)
    if not errores and puntos[0] == puntos[-1]:
        errores.append(f"{et}: 'tramo_linea' es un polígono cerrado; debe ser una línea abierta")
    return errores


def _etiqueta(caso: dict[object, object], posicion: int) -> str:
    ident = _texto(caso.get("id"))
    return f"caso '{ident}'" if ident is not None else f"caso #{posicion}"


def _error_campo_no_permitido(clave: object, et: str) -> str:
    nombre = str(clave)
    if any(fragmento in nombre.lower() for fragmento in _FRAGMENTOS_PROHIBIDOS):
        return (
            f"{et}: campo prohibido '{nombre}': no se admiten datos de titularidad"
            " ni referencias catastrales"
        )
    return f"{et}: campo no permitido '{nombre}'"


def _texto(valor: object) -> str | None:
    if isinstance(valor, str) and valor.strip():
        return valor
    return None


def _textos(valor: object) -> list[str]:
    if isinstance(valor, str):
        return [valor]
    if isinstance(valor, list):
        return [texto for item in valor for texto in _textos(item)]
    return []


def _numero_finito(valor: object) -> bool:
    return isinstance(valor, int | float) and not isinstance(valor, bool) and math.isfinite(valor)


def _punto(valor: object) -> tuple[float, float] | None:
    if not isinstance(valor, list) or len(valor) != 2:
        return None
    x, y = valor[0], valor[1]
    if not (_numero_finito(x) and _numero_finito(y)):
        return None
    return float(x), float(y)


def _fecha_iso_valida(texto: str) -> bool:
    if _PATRON_FECHA_ISO.match(texto) is None:
        return False
    try:
        datetime.date.fromisoformat(texto)
    except ValueError:
        return False
    return True


def _fecha_cierre_valida(texto: str) -> bool:
    coincidencia = _PATRON_CIERRE.match(texto)
    if coincidencia is None:
        return False
    anio, mes, dia = coincidencia.group(1, 2, 3)
    if dia is not None:
        return _fecha_iso_valida(f"{anio}-{mes}-{dia}")
    if mes is not None:
        return 1 <= int(mes) <= 12
    return True
