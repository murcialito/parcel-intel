"""Historia #296: guía para crear el repo privado `paso-comun-datos` y subir la copia del
Catastro histórico de Colmenar (28043), con el catálogo inicial.

Historia solo de documentación. Los tests leen `docs/guias/repo-privado-datos.md` y
`REGISTRY.md` y comprueban las frases, el orden de los pasos, el JSON de ejemplo (que se
parsea y se valida contra los campos obligatorios del ADR 0055 §3) y la ausencia de patrones
de token, rutas del usuario y referencias catastrales. No llaman a red.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
GUIA = REPO / "docs" / "guias" / "repo-privado-datos.md"
REGISTRY = REPO / "src" / "parcel_intel" / "sources" / "REGISTRY.md"
INICIO_DATOS = "## Datos internos: copia en el repo privado (ADR 0055)"
INICIO_CATASTRO = "## Catastro histórico de rústica (Sede Electrónica, historia #287)"

# Referencia catastral de finca (14 o 20 posiciones): no debe aparecer en la guía.
REF_CATASTRAL = re.compile(r"\b\d{7}[A-Z]{2}\d{4}[A-Z]\b|\b\d{7}[A-Z]{2}\d{4}[A-Z]\d{4}[A-Z]{2}\b")
# Patrones de token de GitHub y de claves privadas.
SECRETO = re.compile(r"ghp_|github_pat_|gho_|ghs_|ghu_|AKIA[0-9A-Z]{12}|BEGIN [A-Z ]*PRIVATE KEY")
# Rutas absolutas del portátil del fundador.
RUTA_USUARIO = re.compile(r"/home/|/Users/|[A-Za-z]:\\")
# Campos de titularidad prohibidos en el catálogo (ADR 0055 §3).
TITULARIDAD = re.compile(r"(?i)titular|propietari|\bnif\b|\bdni\b|nombre_persona")
CAMPOS_OBLIGATORIOS = {
    "id",
    "fuente",
    "url",
    "fecha_descarga",
    "licencia",
    "publicable",
    "restricciones_uso",
    "sha256",
    "tamano_bytes",
    "almacen",
    "formato",
    "destino",
    "procedencia",
}
PRODUCTOS_28043 = {
    "ac": "Avance catastral",
    "tp": "Topográfico Parcelario",
    "1r": "1.ª renovación",
    "2r": "2.ª renovación",
    "3r": "3.ª renovación",
}
PLACEHOLDER = "a rellenar por el fundador"


def _guia() -> str:
    return GUIA.read_text(encoding="utf-8")


def _registro() -> str:
    return REGISTRY.read_text(encoding="utf-8")


def _seccion(texto: str, inicio: str) -> str:
    i = texto.index(inicio)
    fin = texto.find("\n## ", i + len(inicio))
    return texto[i : fin if fin != -1 else len(texto)]


def _seccion_guia(prefijo: str) -> str:
    """Texto de la sección de la guía cuyo título empieza por `prefijo` (hasta el siguiente ##)."""
    texto = _guia()
    i = texto.index(f"\n## {prefijo}") + 1
    fin = texto.find("\n## ", i + 3)
    return texto[i : fin if fin != -1 else len(texto)]


def _bloques_json() -> list[dict[str, Any]]:
    """Los bloques ```json de la guía que son JSON válido (la plantilla de 28013 usa marcadores)."""
    bloques = re.findall(r"```json\n(.*?)\n```", _guia(), flags=re.DOTALL)
    validos = []
    for bloque in bloques:
        try:
            validos.append(json.loads(bloque))
        except json.JSONDecodeError:
            continue
    return validos


def _catalogo() -> dict[str, Any]:
    catalogos = [b for b in _bloques_json() if "entradas" in b]
    assert len(catalogos) == 1
    return catalogos[0]


def test_ca1_pasos_en_orden_con_condiciones_previas_repo_y_releases() -> None:
    """Dado `docs/guias/repo-privado-datos.md`, cuando el fundador lo sigue, entonces cubre en
    este orden: (0) las dos condiciones previas del ADR §5 (comprobar que `PROJECT_TOKEN` es
    clásico con solo `public_repo` y `project`, sin `repo`, y que la App de Claude está con
    «Only select repositories» sin `paso-comun-datos`), (1) crear el repo **privado**
    `paso-comun-datos` sin colaboradores, forks, deploy keys ni secrets y comprobar que es
    privado y que solo él tiene acceso, (2) comprobar si las releases inmutables están
    disponibles en su plan para un repo personal privado y activarlas si lo están (anotando el
    resultado en el README del repo privado), (3) la comprobación previa del CA2, (4) calcular
    los sha256, (5) subir cada `.7z` como adjunto de una release de etiqueta
    `catastro-historico-28043-20261127` (borrador → adjuntar → publicar) respetando los 2 GiB por
    fichero, (6) subir a git `procedencia/`, `catalogo/` y `README.md`."""
    texto = _guia()
    marcas = [
        "## 0. ",
        "## 1. ",
        "## 2. ",
        "## 3. ",
        "## 4. ",
        "## 5. ",
        "## 6. ",
        "## 7. ",
    ]
    posiciones = [texto.index(m) for m in marcas]
    assert posiciones == sorted(posiciones)

    cero = _seccion_guia("0. ")
    assert "public_repo" in cero and "`project`" in cero and "sin `repo`" in cero
    assert "Only select repositories" in cero and "paso-comun-datos" in cero

    uno = _seccion_guia("1. ")
    assert "gh repo create murcialito/paso-comun-datos --private" in uno
    assert "sin colaboradores" in uno.lower() or "collaborators" in uno
    assert "isPrivate" in uno
    assert "collaborators" in uno and "keys" in uno and "actions/secrets" in uno
    assert "forks" in uno

    dos = _seccion_guia("2. ")
    assert "releases inmutables" in dos.lower()
    assert "README del repo privado" in dos or "README" in dos

    tres = _seccion_guia("3. ")
    assert "7z l" in tres

    cuatro = _seccion_guia("4. ")
    assert "sha256sum" in cuatro

    cinco = _seccion_guia("5. ")
    assert "catastro-historico-28043-20261127" in cinco
    assert "--draft" in cinco and "gh release upload" in cinco and "--draft=false" in cinco
    assert "2 GiB" in tres or "2 GiB" in cinco

    seis = _seccion_guia("6. ")
    assert "procedencia/" in seis and "catalogo/" in seis and "README.md" in seis


def test_ca2_comprobacion_previa_sin_extraer_nombres_prohibidos_y_procedencia() -> None:
    """Dado el mismo documento, cuando se lee la comprobación previa a la subida, entonces pide
    listar el contenido de cada `.7z` sin extraerlo (p. ej. `7z l`) y comprobar que no hay ninguno
    de estos nombres o patrones: «Hoja de Características», «Relación de Propietarios», «Ficha
    parcelaria», `.xls`/`.xlsx`/`.csv`/`.txt` de relación de titulares, y que solo hay PDF de
    cartografía; también que el sha256 de cada fichero coincide con el de su `.procedencia.json`,
    y que, si no existe procedencia (los ficheros se bajaron a mano), la crea antes con fuente,
    URL, fecha de descarga y licencia."""
    tres = _seccion_guia("3. ")
    assert "7z l" in tres
    assert "sin extraerlo" in tres or "sin extraer" in tres
    for nombre in ("Hoja de Características", "Relación de Propietarios", "Ficha parcelaria"):
        assert nombre in tres, nombre
    for extension in (".xls", ".xlsx", ".csv", ".txt"):
        assert extension in tres, extension
    assert "PDF" in tres
    assert "procedencia" in tres and "fuente" in tres and "fecha_descarga" in tres
    assert "licencia" in tres and "url" in tres.lower()

    cuatro = _seccion_guia("4. ")
    assert "sha256sum" in cuatro
    assert "procedencia" in cuatro
    assert "coincidir" in cuatro


def test_ca3_catalogo_de_ejemplo_con_esquema_y_plantilla_28013() -> None:
    """Dado el mismo documento, cuando se lee el catálogo inicial, entonces trae un
    `catalogo/catastro_historico.json` de ejemplo con el esquema 1 del ADR §3 y una entrada por
    producto de 28043 (AC, TP, 1R, 2R, 3R) con `id` `catastro-historico-28043-<producto>-20261127`,
    `municipio_ine`, `url` (Sede Electrónica de Catastro, descarga con Cl@ve), `fecha_descarga`
    `2026-11-27`, `licencia` (la resolución con su URL), `publicable: false`, `restricciones_uso`
    (las tres de arriba), `almacen` de tipo `release`, `formato: fichero`, `destino`
    `raw/catastro_historico/28043/<producto>.7z`, `procedencia` y `sustituido_por: null`; los
    `sha256` y `tamano_bytes` van como «a rellenar por el fundador». Incluye además la plantilla
    del lote de 28013 con fecha y sha256 «a rellenar». **Sin referencias catastrales de fincas ni
    nombres de personas.**"""
    catalogo = _catalogo()
    assert catalogo["esquema"] == 1
    assert catalogo["fuente"] == "catastro_historico"
    entradas = catalogo["entradas"]
    assert len(entradas) == 5

    por_producto = {}
    for entrada in entradas:
        assert CAMPOS_OBLIGATORIOS <= set(entrada), entrada["id"]
        assert not TITULARIDAD.search(json.dumps(entrada)), entrada["id"]
        codigo = entrada["id"].split("-")[3]
        por_producto[codigo] = entrada
    assert set(por_producto) == set(PRODUCTOS_28043)

    for codigo, entrada in por_producto.items():
        assert entrada["id"] == f"catastro-historico-28043-{codigo}-20261127"
        assert entrada["municipio_ine"] == "28043"
        assert entrada["producto"] == PRODUCTOS_28043[codigo]
        assert "sedecatastro.gob.es" in entrada["url"] and "Cl@ve" in entrada["url"]
        assert entrada["fecha_descarga"] == "2026-11-27"
        assert "23-03-2011" in entrada["licencia"]
        assert "resoluciondgc20110323_tfs.pdf" in entrada["licencia"]
        assert entrada["publicable"] is False
        assert len(entrada["restricciones_uso"]) == 3
        assert entrada["almacen"]["tipo"] == "release"
        assert entrada["almacen"]["etiqueta"] == "catastro-historico-28043-20261127"
        assert entrada["formato"] == "fichero"
        assert entrada["destino"] == f"raw/catastro_historico/28043/{codigo.upper()}.7z"
        assert entrada["procedencia"].startswith("procedencia/catastro_historico/")
        assert entrada["sustituido_por"] is None
        assert entrada["sha256"] == PLACEHOLDER
        assert entrada["tamano_bytes"] == PLACEHOLDER

    plantilla = _seccion_guia("Plantilla del lote de Aranjuez")
    assert "28013" in plantilla
    assert PLACEHOLDER in plantilla
    assert "catastro-historico-28013-" in plantilla
    assert "fecha_descarga" in plantilla and "sha256" in plantilla


def test_ca4_verificacion_posterior_y_inmutabilidad() -> None:
    """Dado el mismo documento, cuando se lee la verificación posterior, entonces dice cómo
    descargar cada adjunto a un directorio nuevo y comparar su sha256 con el del catálogo (con la
    salida esperada), y recuerda que lo subido es inmutable: una versión nueva es un fichero nuevo
    con `id` y procedencia propios y a la vieja solo se le rellena `sustituido_por`."""
    siete = _seccion_guia("7. ")
    assert "gh release download" in siete
    assert "mkdir" in siete and "nuevo" in siete
    assert "sha256sum -c" in siete
    assert "catalogo/catastro_historico.json" in siete
    for adjunto in ("ac", "tp", "1r", "2r", "3r"):
        assert f"catastro-historico-28043-{adjunto}-20261127.7z: OK" in siete, adjunto

    reglas = _seccion_guia("Reglas de inmutabilidad")
    assert "inmutable" in reglas.lower() or "Solo se añade" in reglas
    assert "sustituido_por" in reglas
    assert "id" in reglas and "procedencia" in reglas
    assert "nuevo" in reglas or "nueva" in reglas


def test_ca5_registro_enlaza_la_guia_sin_datos_reales() -> None:
    """Dado `REGISTRY.md`, cuando se lee la sección «Datos internos: copia en el repo privado (ADR
    0055)», entonces la línea «Estado» sigue diciendo que no se ha subido nada y añade que la guía
    existe (`docs/guias/repo-privado-datos.md`) y que se actualizará a «copia hecha el <fecha>»
    cuando el fundador lo confirme; **sin URL de acceso, sin sha256 reales y sin presentar como
    hecho lo que no ha ocurrido**. La sección «Catastro histórico de rústica» enlaza a la guía sin
    repetirla."""
    registro = _registro()
    datos = _seccion(registro, INICIO_DATOS)
    estado = [ln for ln in datos.splitlines() if ln.startswith("Estado a ")]
    assert len(estado) == 1
    assert "todavía no se ha subido nada" in estado[0]
    assert "docs/guias/repo-privado-datos.md" in estado[0]
    assert "copia hecha el <fecha>" in estado[0]
    assert "github.com/murcialito/paso-comun-datos" not in datos
    assert not re.search(r"\b[0-9a-f]{64}\b", datos)
    # La ruta relativa del enlace debe apuntar a la guía real.
    enlace = re.search(r"\]\(([^)]*repo-privado-datos\.md)\)", estado[0])
    assert enlace is not None
    assert (REGISTRY.parent / enlace.group(1)).resolve() == GUIA.resolve()

    catastro = _seccion(registro, INICIO_CATASTRO)
    assert "repo-privado-datos.md" in catastro
    assert "gh release" not in catastro
    assert not re.search(r"\b[0-9a-f]{64}\b", catastro)


def test_ca6_guia_sin_secretos_rutas_de_usuario_ni_referencias_catastrales() -> None:
    """Dado el documento, cuando se lee entero, entonces no contiene secretos ni tokens, ni rutas
    del portátil del fundador (solo rutas relativas a `data/`), ni referencias catastrales ni
    nombres de personas."""
    texto = _guia()
    assert not SECRETO.search(texto)
    assert not RUTA_USUARIO.search(texto)
    assert not REF_CATASTRAL.search(texto)
    assert "data/raw/catastro_historico/28043/" in texto
    for bloque in _bloques_json():
        assert not REF_CATASTRAL.search(json.dumps(bloque))
        assert not TITULARIDAD.search(json.dumps(bloque))


def test_ca7_ningun_agente_ejecuta_la_guia_y_el_comprobador_queda_fuera() -> None:
    """Dado el documento, cuando se lee, entonces dice explícitamente que ningún agente ni workflow
    del repo público ejecuta esta guía ni usa `gh` contra el repo privado, y que el comprobador
    local de sha256 y de titularidad no está en alcance."""
    texto = _guia().lower()
    assert "ningún agente ni workflow del repo público" in texto
    assert "usa `gh` contra el repo privado" in texto
    assert "comprobador local de sha256 y de titularidad no está en alcance" in texto
