"""Historia #54: congelar el conjunto de validación (etiqueta, fecha y huella).

Sin red. CA9 es de integración con Actions: aquí solo se comprueba la forma del workflow.
"""

import datetime
import hashlib
import json
import re
from pathlib import Path

import pytest

from tests.validacion.congelacion import (
    ErrorCongelacion,
    calcular_huella,
    comprobar_integridad,
    congelar,
    leer_congelado,
    version_vigente,
)

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "etiquetar-validacion.yml"
FECHA = datetime.date(2026, 12, 1)


def _casos(carpeta: Path, total: int = 10, hito: int = 5) -> Path:
    casos = [
        {
            "id": f"caso-{i}",
            "fuente_url": "https://www.ejemplo.es/noticia",
            "fuente_tipo": "prensa",
            "fecha_consulta": "2026-11-26",
            "municipio": "Colmenar de Oreja" if i < hito else "El Escorial",
            "ambito": "hito" if i < hito else "comunidad",
            "tramo_descripcion": "camino entre dos puntos",
            "cierre_fecha_aproximada": "2019",
        }
        for i in range(total)
    ]
    ruta = carpeta / "casos.json"
    ruta.write_text(json.dumps({"casos": casos}), encoding="utf-8")
    return ruta


def _solo_casos(carpeta: Path) -> bool:
    return sorted(p.name for p in carpeta.iterdir()) == ["casos.json"]


def test_ca1_congelar_devuelve_recuentos_y_huella(tmp_path: Path) -> None:
    """Dado un `casos.json` con 10 casos, 5 de ellos `ambito: hito`, cuando se ejecuta la función
    de congelación (`congelar(casos_path)`), entonces devuelve el recuento total (10), el recuento
    en el ámbito (5) y la huella SHA-256 en hexadecimal de los bytes del fichero."""
    ruta = _casos(tmp_path)
    resultado = congelar(ruta)
    assert (resultado.casos_total, resultado.casos_ambito) == (10, 5)
    assert resultado.sha256 == hashlib.sha256(ruta.read_bytes()).hexdigest()


@pytest.mark.parametrize(("total", "hito", "minimo"), [(9, 5, "10"), (10, 4, "5")])
def test_ca2_por_debajo_del_minimo_falla_sin_escribir(
    tmp_path: Path, total: int, hito: int, minimo: str
) -> None:
    """Dado un `casos.json` con 9 casos, o con 10 casos pero solo 4 `ambito: hito`, cuando se
    ejecuta la congelación, entonces falla con un error que indica qué mínimo no se cumple
    (10 totales / 5 en el ámbito) y no escribe ningún fichero."""
    ruta = _casos(tmp_path, total, hito)
    with pytest.raises(ErrorCongelacion, match="mínimo") as info:
        congelar(ruta, FECHA, tmp_path)
    assert minimo in str(info.value)
    assert _solo_casos(tmp_path)


def test_ca3_casos_invalidos_fallan_con_el_error_del_validador(tmp_path: Path) -> None:
    """Dado un `casos.json` que no pasa el validador de #51 (campo no permitido, referencia
    catastral, `fuente_url` no https…), cuando se ejecuta la congelación, entonces falla con el
    error del validador y no escribe ningún fichero."""
    ruta = _casos(tmp_path)
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    datos["casos"][0]["fuente_url"] = "http://inseguro.es"
    datos["casos"][1]["propietario"] = "x"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(ErrorCongelacion) as info:
        congelar(ruta, FECHA, tmp_path)
    assert "https://" in str(info.value)
    assert "propietario" in str(info.value)
    assert _solo_casos(tmp_path)


def test_ca4_escribe_congelado_con_los_datos_y_la_nota_fija(tmp_path: Path) -> None:
    """Dado un `casos.json` válido, cuando se congela con una fecha dada, entonces se escribe
    `docs/validacion/CONGELADO.md` con: versión (`validacion-v1`), fecha de congelación
    (AAAA-MM-DD), número total de casos, número de casos dentro del ámbito, huella SHA-256 y el
    nombre de la etiqueta de git esperada. No contiene nada más que esos datos y una nota fija:
    "No ajustar umbrales de detección antes de esta fecha; cualquier cambio de casos exige una
    nueva versión con motivo"."""
    ruta = _casos(tmp_path)
    congelar(ruta, FECHA, tmp_path)
    texto = (tmp_path / "CONGELADO.md").read_text(encoding="utf-8")
    leido = leer_congelado(tmp_path / "CONGELADO.md")
    assert (leido.version, leido.fecha) == (1, "2026-12-01")
    assert (leido.casos_total, leido.casos_ambito) == (10, 5)
    assert leido.sha256 == calcular_huella(ruta)
    assert leido.etiqueta == "validacion-v1"
    assert (
        "No ajustar umbrales de detección antes de esta fecha; "
        "cualquier cambio de casos exige una nueva versión con motivo" in texto
    )
    contenido = [linea for linea in texto.splitlines() if linea and not linea.startswith("#")]
    assert len(contenido) == 7  # seis datos + la nota fija, nada más


def test_ca5_integridad_pasa_si_la_huella_coincide(tmp_path: Path) -> None:
    """Dado el repo con `CONGELADO.md` vigente, cuando corre el test de integridad, entonces
    recalcula la huella de `casos.json` y pasa solo si coincide con la declarada en la última
    versión congelada."""
    ruta = _casos(tmp_path)
    congelar(ruta, FECHA, tmp_path)
    assert comprobar_integridad(tmp_path, ruta) == []
    declarada = leer_congelado(tmp_path / "CONGELADO.md")
    texto = (tmp_path / "CONGELADO.md").read_text(encoding="utf-8")
    (tmp_path / "CONGELADO.md").write_text(
        texto.replace(declarada.sha256, "0" * 64), encoding="utf-8"
    )
    assert comprobar_integridad(tmp_path, ruta) != []


def test_ca6_un_byte_distinto_sin_nueva_version_falla(tmp_path: Path) -> None:
    """Dado un `casos.json` modificado después de congelar (un byte distinto) sin un nuevo
    fichero de congelación, cuando corre el test de integridad, entonces falla con un mensaje
    que explica que hay que crear `CONGELADO-v2.md` con el motivo."""
    ruta = _casos(tmp_path)
    congelar(ruta, FECHA, tmp_path)
    ruta.write_bytes(ruta.read_bytes() + b"\n")
    errores = comprobar_integridad(tmp_path, ruta)
    assert any("CONGELADO-v2.md" in e and "motivo" in e for e in errores)


def test_ca7_v2_con_motivo_es_la_vigente_y_sin_motivo_o_salto_falla(tmp_path: Path) -> None:
    """Dado un `CONGELADO-v2.md` (versión 2) con `motivo` no vacío y la huella del `casos.json`
    actual, cuando corre el test de integridad, entonces pasa y trata la v2 como la vigente.
    Dada una v2 sin motivo o con un número de versión que no sigue a la anterior, entonces el
    test falla."""
    ruta = _casos(tmp_path)
    congelar(ruta, FECHA, tmp_path)
    ruta.write_bytes(ruta.read_bytes() + b"\n")
    congelar(ruta, FECHA, tmp_path, version=2, motivo="se corrige la fecha de una fuente")
    assert comprobar_integridad(tmp_path, ruta) == []
    assert version_vigente(tmp_path).version == 2

    v2 = tmp_path / "CONGELADO-v2.md"
    texto = v2.read_text(encoding="utf-8")
    v2.write_text(re.sub(r"^motivo: .*$", "motivo: ", texto, flags=re.M), encoding="utf-8")
    assert comprobar_integridad(tmp_path, ruta) != []

    v2.unlink()
    v3 = texto.replace("version: 2", "version: 3")
    (tmp_path / "CONGELADO-v3.md").write_text(v3, encoding="utf-8")
    assert comprobar_integridad(tmp_path, ruta) != []


def test_ca8_los_minimos_se_recalculan_desde_casos_json(tmp_path: Path) -> None:
    """Dado el test de integridad, cuando se ejecuta, entonces comprueba también que la versión
    vigente cumple los mínimos (10 totales, 5 en el ámbito) recalculándolos desde `casos.json`,
    no solo leyéndolos de `CONGELADO.md`."""
    ruta = _casos(tmp_path, 10, 5)
    congelar(ruta, FECHA, tmp_path)
    # Mismo CONGELADO.md (declara 10/5), pero el fichero real ahora es otro con huella igual no
    # es posible: se reescribe la huella para aislar la comprobación de mínimos.
    ruta = _casos(tmp_path, 9, 5)
    (tmp_path / "CONGELADO.md").write_text(
        (tmp_path / "CONGELADO.md")
        .read_text(encoding="utf-8")
        .replace(leer_congelado(tmp_path / "CONGELADO.md").sha256, calcular_huella(ruta)),
        encoding="utf-8",
    )
    errores = comprobar_integridad(tmp_path, ruta)
    assert any("10 casos totales" in e for e in errores)


@pytest.mark.integration
def test_ca9_el_workflow_etiqueta_solo_con_esos_paths_y_usa_la_version_del_fichero() -> None:
    """Dado un push a `main` que añade o cambia un fichero `docs/validacion/CONGELADO*.md`,
    cuando corre el workflow `etiquetar-validacion.yml`, entonces crea la etiqueta anotada
    `validacion-vN` (N = versión declarada en el fichero) sobre ese commit si no existe, y no
    hace nada si ya existe."""
    texto = WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r"^on:\s*\n\s+push:", texto, flags=re.M)
    assert "branches: [main]" in texto
    assert '- "docs/validacion/CONGELADO*.md"' in texto
    assert texto.count("paths:") == 1
    assert "contents: write" in texto
    assert "git tag -a" in texto
    assert "^version:" in texto  # lee la versión del fichero
    assert "validacion-v$version" in texto
    assert "ya existe" in texto  # no hace nada si la etiqueta existe
