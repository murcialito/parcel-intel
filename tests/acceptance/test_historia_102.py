"""Historia #102: ADR de privacidad y moderación de avisos con foto.

Historia solo de documentación. Los tests localizan el ADR por su cabecera (`- Historias: #102`),
nunca por número (lecciones de #43, #136 y #168), leen sus secciones y `docs/vision.md`, y buscan
las frases y cifras que fija el diseño. No llaman a red.
"""

import re
from pathlib import Path

import pytest

from parcel_intel.domain.public_card import banned_words_in

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
ADR_DIR = REPO / "docs" / "adr"
VISION = REPO / "docs" / "vision.md"
CABECERA = "- Historias: #102"

ENCABEZADOS = (
    "Contexto",
    "Decisión",
    "Metadatos de la foto",
    "Personas y matrículas",
    "Contacto",
    "Conservación y borrado",
    "Moderación",
    "Lenguaje del aviso",
    "Base legal",
    "Preguntas al fundador",
    "Restricciones para las historias del flujo de avisos",
    "Consecuencias",
)

PLANTILLAS = ("Confirma", "Desmiente", "No concluyente")


def _adr_paths() -> list[Path]:
    return sorted(
        p
        for p in ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")
        if any(line.startswith(CABECERA) for line in p.read_text(encoding="utf-8").splitlines())
    )


def _adr_path() -> Path:
    paths = _adr_paths()
    assert len(paths) == 1, paths
    return paths[0]


def _adr() -> str:
    return _adr_path().read_text(encoding="utf-8")


def _seccion(titulo: str) -> str:
    texto = _adr()
    marca = f"\n## {titulo}\n"
    inicio = texto.index(marca) + len(marca)
    fin = texto.find("\n## ", inicio)
    return texto[inicio : fin if fin != -1 else len(texto)]


def _sin_saltos(texto: str) -> str:
    return re.sub(r"\s+", " ", texto)


def _plantillas() -> dict[str, str]:
    seccion = _seccion("Lenguaje del aviso")
    resultado: dict[str, str] = {}
    for nombre in PLANTILLAS:
        encontrado = re.search(rf"- \*\*{nombre}\*\*: «([^»]+)»", seccion)
        assert encontrado is not None, nombre
        resultado[nombre] = encontrado.group(1)
    return resultado


def test_encabezados_exactos() -> None:
    """Encabezados `##` exactos del diseño (punto 5), en ese orden."""
    titulos = re.findall(r"^## (.+)$", _adr(), flags=re.MULTILINE)
    assert tuple(titulos) == ENCABEZADOS


def test_ca1_metadatos_se_descartan_y_ubicacion_declarada() -> None:
    """CA1. Dado el ADR de privacidad, cuando se lee la sección de metadatos, entonces fija para
    EXIF qué campos se descartan siempre (GPS, hora, modelo de dispositivo, miniatura incrustada) y
    cómo se obtiene la ubicación del aviso (la declara el usuario sobre el mapa, sobre un indicio
    concreto, no sale de la foto)."""
    seccion = _sin_saltos(_seccion("Metadatos de la foto"))
    assert "Se descartan siempre todos los metadatos" in seccion
    for campo in ("**GPS**", "**fecha y hora**", "Model", "**miniatura incrustada**"):
        assert campo in seccion, campo
    assert "la declara la persona" in seccion
    assert "no sale de la foto" in seccion
    assert "indicio o tramo publicado concreto" in seccion
    assert "sobre el mapa" in seccion
    assert "Nunca se lee el GPS de la foto" in seccion
    assert "El original con metadatos no se guarda nunca" in seccion


def test_ca2_caras_y_matriculas_tapado_manual_sin_reconocimiento() -> None:
    """CA2. Dado el ADR, cuando se lee la sección de personas y matrículas, entonces decide qué se
    hace con caras y matrículas visibles (rechazo en moderación o difuminado) y quién lo aplica,
    sin reconocimiento automático por LLM en consultas de usuario."""
    seccion = _sin_saltos(_seccion("Personas y matrículas"))
    assert "rectángulo opaco" in seccion
    assert "**se rechaza**" in seccion
    assert "**el moderador humano**" in seccion
    assert "Sin reconocimiento automático" in seccion
    assert "ni LLM" in seccion
    assert "consulta del usuario" in seccion


def test_ca3_contacto_minimo_finalidad_quien_lo_ve_nunca_publicado() -> None:
    """CA3. Dado el ADR, cuando se lee la sección de contacto, entonces fija el mínimo de datos de
    contacto (o su ausencia), su finalidad, quién los ve y que no se publican nunca."""
    seccion = _sin_saltos(_seccion("Contacto"))
    assert "El contacto es opcional" in seccion
    assert "solo **un correo electrónico**" in seccion
    assert "Finalidad única" in seccion
    assert "Lo ven solo los moderadores" in seccion
    assert "Nunca se publica" in seccion


def test_ca4_plazos_de_conservacion_y_borrado_a_peticion() -> None:
    """CA4. Dado el ADR, cuando se lee la sección de conservación, entonces fija un plazo máximo
    para fotos sin publicar, para publicadas y para contacto, y cómo se borra a petición del
    autor."""
    seccion = _sin_saltos(_seccion("Conservación y borrado"))
    assert "| Foto sin moderar | 60 días desde su recepción" in seccion
    assert "| Foto rechazada | se borra en 7 días" in seccion
    assert "como máximo 3 años desde la visita" in seccion
    assert "| Contacto | 30 días desde la decisión" in seccion
    assert "como máximo 90 días desde la recepción" in seccion
    assert "a petición del autor" in seccion
    assert "código de aviso" in seccion
    assert "un plazo máximo de un mes" in seccion


def test_ca5_moderacion_humana_lista_y_rechazados() -> None:
    """CA5. Dado el ADR, cuando se lee la sección de moderación, entonces establece que nada se
    publica sin aprobación humana, una lista de comprobación de moderación (sin propietarios, sin
    acusación, sin caras ni matrículas, sin referencia catastral de finca) y qué ocurre con lo
    rechazado."""
    seccion = _sin_saltos(_seccion("Moderación"))
    assert "Nada se publica sin aprobación humana" in seccion
    assert "Ningún agente ni proceso automático aprueba" in seccion
    lista = re.findall(r"- \[ \] ([^\n]+)", _seccion("Moderación"))
    assert len(lista) >= 4
    texto_lista = " ".join(lista)
    for punto in (
        "propietario",
        "lenguaje de acusación",
        "caras ni matrículas",
        "referencia catastral de finca",
    ):
        assert punto in texto_lista, punto
    assert "Lo rechazado no se publica" in seccion
    assert "se borra en 7 días" in seccion


def test_ca6_plantillas_sin_acusacion_pendientes_de_validacion() -> None:
    """CA6. Dado el ADR, cuando se lee la sección de lenguaje, entonces fija las plantillas de texto
    del aviso (confirma, desmiente, no concluyente) sin lenguaje de acusación, marcadas como
    pendientes de validación del fundador."""
    seccion = _seccion("Lenguaje del aviso")
    assert "Pendientes de validación del fundador" in seccion
    plantillas = _plantillas()
    assert set(plantillas) == set(PLANTILLAS)
    for texto in plantillas.values():
        assert texto.startswith("Aviso ciudadano ({mes_anyo}):")
        assert "verific" in texto


def test_ca7_base_legal_con_fuentes_primarias() -> None:
    """CA7. Dado el ADR, cuando se lee la sección de base legal, entonces recoge qué obligaciones
    de protección de datos (RGPD/LOPDGDD) se aplican a los datos que se guardan, citando la fuente
    primaria consultada, y lo que queda como pregunta al fundador."""
    seccion = _sin_saltos(_seccion("Base legal"))
    for url in (
        "https://www.boe.es/buscar/doc.php?id=DOUE-L-2016-80807",
        "https://www.boe.es/buscar/act.php?id=BOE-A-2018-16673",
        "https://www.aepd.es/preguntas-frecuentes/0-conceptos-basicos/FAQ-0002-sobre-la-matricula-de-un-coche",
    ):
        assert url in seccion, url
    assert "RGPD" in seccion and "LOPDGDD" in seccion
    assert "«toda información sobre una persona física identificada o identificable»" in seccion
    assert "«exclusivamente personales o domésticas»" in seccion
    for articulo in ("art. 5.1.c", "art. 6.1.a", "art. 17", "art. 25", "art. 11", "art. 7"):
        assert articulo in seccion, articulo
    assert "pregunta al fundador" in seccion
    assert "no es un dictamen jurídico" in seccion
    # Un canal no leído se dice así (lección de #26).
    assert "paráfrasis" in seccion
    assert "EUR-Lex" in seccion


def test_ca8_coherente_con_claude_md_y_restricciones_r1_r10() -> None:
    """CA8. Dado el ADR, cuando se contrasta con CLAUDE.md, entonces no contradice ningún principio
    y lista las restricciones que heredan las historias de diseño del flujo de avisos."""
    seccion = _seccion("Restricciones para las historias del flujo de avisos")
    numeros = re.findall(r"^- R(\d+)\. ", seccion, flags=re.MULTILINE)
    assert numeros == [str(n) for n in range(1, 11)]
    texto = _sin_saltos(seccion)
    # Principios de CLAUDE.md que las restricciones recogen.
    assert "Nada se publica sin aprobación humana" in texto
    assert "LLM" in texto and "ningún LLM interviene en la recepción ni en la consulta" in texto
    assert "Ningún dato de titularidad ni referencia catastral de finca" in texto
    assert "R9. Un aviso no cambia el estado de un indicio" in texto
    # Ni denuncia ni acusación en el texto propio del ADR fuera de las citas al fundador.
    assert "denunci" not in _sin_saltos(_seccion("Decisión")).lower()


def test_ca9_estado_propuesta_cabecera_unica_y_recomendaciones() -> None:
    """CA9 (añadido por el arquitecto). Dado el ADR, cuando se lee su cabecera y su sección
    «Preguntas al fundador», entonces su estado es `propuesta` (no `aceptada`), la cabecera lleva
    la línea `- Historias: #102`, hay una sola entrada de ADR con ese número en `docs/adr/` y cada
    pregunta abierta lleva la recomendación del arquitecto."""
    path = _adr_path()
    adr = _adr()
    estado = re.search(r"^- Estado: (.+)$", adr, flags=re.MULTILINE)
    assert estado is not None
    assert estado.group(1).startswith("propuesta")
    assert "aceptada" not in estado.group(1)
    assert any(line.startswith(CABECERA) for line in adr.splitlines())
    numero = path.name[:4]
    assert len(list(ADR_DIR.glob(f"{numero}-*.md"))) == 1
    assert adr.startswith(f"# ADR {numero} — ")
    preguntas = re.findall(r"^\d+\. (.+)$", _seccion("Preguntas al fundador"), flags=re.MULTILINE)
    assert len(preguntas) >= 6
    for pregunta in preguntas:
        assert "Recomendación:" in pregunta, pregunta


def test_ca10_plantillas_sin_palabras_vetadas_ni_huecos_personales() -> None:
    """CA10 (añadido por el arquitecto). Dado el texto de las tres plantillas del ADR, cuando se
    pasa por `banned_words_in` de `domain/public_card.py`, entonces no aparece ninguna palabra
    vetada, ni «denuncia» ni «denunciar», y ninguna plantilla tiene huecos para nombre de persona,
    de finca ni referencia catastral (solo `{mes_anyo}`)."""
    plantillas = _plantillas()
    assert len(plantillas) == 3
    for nombre, texto in plantillas.items():
        assert banned_words_in(texto) == (), nombre
        assert "denunci" not in texto.lower(), nombre
        assert re.findall(r"\{([^}]*)\}", texto) == ["mes_anyo"], nombre


def test_ca11_vision_enlaza_el_adr_como_propuesto() -> None:
    """CA11 (añadido por el arquitecto). Dado `docs/vision.md`, cuando se lee la línea de «Avisos
    ciudadanos con foto» de las fases posteriores y la pregunta abierta sobre avisos, entonces
    enlazan al ADR nuevo y dicen que la política de privacidad está propuesta y pendiente de
    validación del fundador."""
    enlace = f"(adr/{_adr_path().name})"
    frase = "política de privacidad y moderación propuesta, pendiente de validación del fundador"
    lineas = VISION.read_text(encoding="utf-8").splitlines()
    fase = [linea for linea in lineas if linea.startswith("- **Avisos ciudadanos con foto**")]
    pregunta = [
        linea
        for linea in lineas
        if linea.startswith("- [ ] Cómo se reciben y moderan los avisos ciudadanos con foto")
    ]
    assert len(fase) == 1 and len(pregunta) == 1
    for linea in (fase[0], pregunta[0]):
        assert enlace in linea
        assert frase in linea
