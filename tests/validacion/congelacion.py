"""Congelación del conjunto de validación (`docs/validacion/casos.json`). Historia #54.

Solo stdlib. Es herramienta de prueba, como `casos_schema`, y reutiliza su validador.

La huella es el SHA-256 de los bytes exactos de `casos.json`: cualquier byte distinto la cambia.
Cada congelación vive en un fichero `CONGELADO.md` (v1) o `CONGELADO-v<N>.md` (N >= 2); la versión
vigente es la de número más alto. Formato: líneas `clave: valor` bajo el título.
"""

import datetime
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from tests.validacion.casos_schema import validar_casos

MINIMO_TOTAL = 10
MINIMO_AMBITO = 5
PREFIJO_ETIQUETA = "validacion-v"
NOTA_FIJA = (
    "No ajustar umbrales de detección antes de esta fecha; "
    "cualquier cambio de casos exige una nueva versión con motivo."
)

_CLAVES_BASE: tuple[str, ...] = (
    "version",
    "fecha",
    "casos_total",
    "casos_ambito",
    "sha256",
    "etiqueta",
)
_PATRON_FICHERO = re.compile(r"^CONGELADO(?:-v(\d+))?\.md$")
_PATRON_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ErrorCongelacion(Exception):
    """El conjunto no se puede congelar o el fichero de congelación no es válido."""


@dataclass(frozen=True)
class Congelado:
    version: int
    fecha: str
    casos_total: int
    casos_ambito: int
    sha256: str
    etiqueta: str
    motivo: str | None = None


def calcular_huella(path: Path) -> str:
    """SHA-256 hexadecimal de los bytes exactos del fichero (lectura binaria)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contar_casos(casos: list[dict[str, object]]) -> tuple[int, int]:
    """(total, dentro del ámbito). Los casos `sintetico: true` no cuentan."""
    reales = [c for c in casos if c.get("sintetico") is not True]
    return len(reales), sum(1 for c in reales if c.get("ambito") == "hito")


def nombre_fichero(version: int) -> str:
    return "CONGELADO.md" if version == 1 else f"CONGELADO-v{version}.md"


def etiqueta_de(version: int) -> str:
    return f"{PREFIJO_ETIQUETA}{version}"


def cargar_casos(casos_path: Path) -> list[dict[str, object]]:
    """Lee `casos.json`, lo valida con el validador de #51 y devuelve sus casos."""
    try:
        datos: object = json.loads(casos_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ErrorCongelacion(f"no se puede leer {casos_path.name}: {error}") from error
    errores = validar_casos(datos)
    if errores:
        raise ErrorCongelacion(
            "casos.json no pasa el validador:\n" + "\n".join(f"- {e}" for e in errores)
        )
    assert isinstance(datos, dict)
    casos = datos["casos"]
    assert isinstance(casos, list)
    return [c for c in casos if isinstance(c, dict)]


def errores_de_minimos(total: int, ambito: int) -> list[str]:
    errores: list[str] = []
    if total < MINIMO_TOTAL:
        errores.append(f"no se cumple el mínimo de {MINIMO_TOTAL} casos totales: hay {total}")
    if ambito < MINIMO_AMBITO:
        errores.append(
            f"no se cumple el mínimo de {MINIMO_AMBITO} casos en el ámbito: hay {ambito}"
        )
    return errores


def render_congelado(
    version: int,
    fecha: str,
    total: int,
    ambito: int,
    huella: str,
    motivo: str | None = None,
) -> str:
    lineas = [
        "# Conjunto de validación congelado",
        "",
        f"version: {version}",
        f"fecha: {fecha}",
        f"casos_total: {total}",
        f"casos_ambito: {ambito}",
        f"sha256: {huella}",
        f"etiqueta: {etiqueta_de(version)}",
    ]
    if motivo is not None:
        lineas.append(f"motivo: {motivo}")
    lineas += ["", NOTA_FIJA, ""]
    return "\n".join(lineas)


def leer_congelado(path: Path) -> Congelado:
    """Parsea un fichero de congelación; lanza `ErrorCongelacion` si está mal formado."""
    campos: dict[str, str] = {}
    for linea in path.read_text(encoding="utf-8").splitlines():
        clave, separador, valor = linea.partition(": ")
        if separador and clave in (*_CLAVES_BASE, "motivo"):
            campos[clave] = valor.strip()
    faltan = [c for c in _CLAVES_BASE if c not in campos]
    if faltan:
        raise ErrorCongelacion(f"{path.name}: faltan las claves {', '.join(faltan)}")
    try:
        version = int(campos["version"])
        total = int(campos["casos_total"])
        ambito = int(campos["casos_ambito"])
        datetime.date.fromisoformat(campos["fecha"])
    except ValueError as error:
        raise ErrorCongelacion(f"{path.name}: valor no válido: {error}") from error
    if _PATRON_SHA256.match(campos["sha256"]) is None:
        raise ErrorCongelacion(f"{path.name}: 'sha256' debe ser 64 caracteres hexadecimales")
    return Congelado(
        version=version,
        fecha=campos["fecha"],
        casos_total=total,
        casos_ambito=ambito,
        sha256=campos["sha256"],
        etiqueta=campos["etiqueta"],
        motivo=campos.get("motivo"),
    )


def versiones(directorio: Path) -> list[Congelado]:
    """Todas las congelaciones del directorio, ordenadas por versión.

    Exige que cada fichero declare la versión de su nombre, que las versiones sean
    consecutivas desde 1 y que desde la v2 haya un `motivo` no vacío.
    """
    encontrados: dict[int, Path] = {}
    for fichero in directorio.iterdir():
        coincidencia = _PATRON_FICHERO.match(fichero.name)
        if coincidencia is None:
            continue
        encontrados[int(coincidencia.group(1) or 1)] = fichero
    resultado: list[Congelado] = []
    for numero in sorted(encontrados):
        congelado = leer_congelado(encontrados[numero])
        nombre = encontrados[numero].name
        if congelado.version != numero:
            raise ErrorCongelacion(
                f"{nombre}: declara la versión {congelado.version}, "
                f"pero su nombre es de la {numero}"
            )
        if congelado.etiqueta != etiqueta_de(numero):
            raise ErrorCongelacion(f"{nombre}: la etiqueta debe ser {etiqueta_de(numero)}")
        if numero >= 2 and not (congelado.motivo or "").strip():
            raise ErrorCongelacion(f"{nombre}: desde la versión 2 hace falta un 'motivo' no vacío")
        resultado.append(congelado)
    for posicion, congelado in enumerate(resultado, start=1):
        if congelado.version != posicion:
            raise ErrorCongelacion(
                f"la versión {congelado.version} no sigue a la {posicion - 1}: "
                f"falta {nombre_fichero(posicion)}"
            )
    return resultado


def version_vigente(directorio: Path) -> Congelado:
    """La congelación de número más alto. `ErrorCongelacion` si no hay ninguna."""
    todas = versiones(directorio)
    if not todas:
        raise ErrorCongelacion(f"no hay ningún CONGELADO*.md en {directorio}")
    return todas[-1]


def congelar(
    casos_path: Path,
    fecha: datetime.date | None = None,
    destino: Path | None = None,
    *,
    version: int = 1,
    motivo: str | None = None,
) -> Congelado:
    """Valida `casos.json`, comprueba los mínimos y devuelve el resumen de la congelación.

    Si se da `destino` (directorio) escribe ahí el fichero de la versión; `fecha` es
    entonces obligatoria. Ante cualquier error no escribe nada.
    """
    casos = cargar_casos(casos_path)
    total, ambito = contar_casos(casos)
    errores = errores_de_minimos(total, ambito)
    if errores:
        raise ErrorCongelacion("; ".join(errores))
    if version >= 2 and not (motivo or "").strip():
        raise ErrorCongelacion("desde la versión 2 hace falta un motivo no vacío")
    if destino is not None and fecha is None:
        raise ErrorCongelacion("hace falta una fecha para escribir la congelación")
    resultado = Congelado(
        version=version,
        fecha=fecha.isoformat() if fecha is not None else "",
        casos_total=total,
        casos_ambito=ambito,
        sha256=calcular_huella(casos_path),
        etiqueta=etiqueta_de(version),
        motivo=motivo if version >= 2 else None,
    )
    if destino is not None:
        texto = render_congelado(
            version, resultado.fecha, total, ambito, resultado.sha256, resultado.motivo
        )
        (destino / nombre_fichero(version)).write_text(texto, encoding="utf-8")
    return resultado


def comprobar_integridad(directorio: Path, casos_path: Path) -> list[str]:
    """Errores de integridad del conjunto frente a su última congelación (vacía = íntegro).

    Sin ningún `CONGELADO*.md` solo exige que `casos.json` sea válido.
    """
    try:
        casos = cargar_casos(casos_path)
    except ErrorCongelacion as error:
        return [str(error)]
    try:
        todas = versiones(directorio)
    except ErrorCongelacion as error:
        return [str(error)]
    if not todas:
        return []
    vigente = todas[-1]
    errores: list[str] = []
    if calcular_huella(casos_path) != vigente.sha256:
        errores.append(
            f"casos.json ha cambiado desde la versión {vigente.version}: la huella no coincide. "
            f"Hay que crear {nombre_fichero(vigente.version + 1)} con el motivo del cambio"
        )
    total, ambito = contar_casos(casos)
    errores.extend(errores_de_minimos(total, ambito))
    return errores
