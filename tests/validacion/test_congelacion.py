"""Tests unitarios de la congelación del conjunto de validación (historia #54). Sin red."""

import datetime
import hashlib
import json
from pathlib import Path

import pytest

from tests.validacion.congelacion import (
    Congelado,
    ErrorCongelacion,
    calcular_huella,
    comprobar_integridad,
    congelar,
    contar_casos,
    leer_congelado,
    render_congelado,
    version_vigente,
)

FECHA = datetime.date(2026, 12, 1)


def caso(indice: int, ambito: str = "comunidad", **extra: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": f"caso-{indice}",
        "fuente_url": "https://www.ejemplo.es/noticia",
        "fuente_tipo": "prensa",
        "fecha_consulta": "2026-11-26",
        "municipio": "Colmenar de Oreja" if ambito == "hito" else "El Escorial",
        "ambito": ambito,
        "tramo_descripcion": "camino entre dos puntos",
        "cierre_fecha_aproximada": "2019",
    }
    base.update(extra)
    return base


def escribir_casos(carpeta: Path, total: int = 10, hito: int = 5) -> Path:
    casos = [caso(i, "hito" if i < hito else "comunidad") for i in range(total)]
    ruta = carpeta / "casos.json"
    ruta.write_text(json.dumps({"casos": casos}, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def test_huella_es_sha256_de_los_bytes_exactos(tmp_path: Path) -> None:
    ruta = tmp_path / "casos.json"
    ruta.write_bytes(b'{"casos": []}\r\n')
    assert calcular_huella(ruta) == hashlib.sha256(b'{"casos": []}\r\n').hexdigest()


def test_un_byte_distinto_cambia_la_huella(tmp_path: Path) -> None:
    ruta = escribir_casos(tmp_path)
    antes = calcular_huella(ruta)
    ruta.write_bytes(ruta.read_bytes() + b"\n")
    assert calcular_huella(ruta) != antes


def test_contar_casos_ignora_sinteticos() -> None:
    casos = [caso(1, "hito"), caso(2, "hito", sintetico=True), caso(3)]
    assert contar_casos(casos) == (2, 1)


def test_congelar_devuelve_recuentos_y_huella(tmp_path: Path) -> None:
    ruta = escribir_casos(tmp_path)
    resultado = congelar(ruta)
    assert (resultado.casos_total, resultado.casos_ambito) == (10, 5)
    assert resultado.sha256 == calcular_huella(ruta)


def test_congelar_sin_destino_no_escribe(tmp_path: Path) -> None:
    ruta = escribir_casos(tmp_path)
    congelar(ruta, FECHA)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["casos.json"]


@pytest.mark.parametrize(("total", "hito", "fragmento"), [(9, 5, "10"), (10, 4, "5")])
def test_congelar_por_debajo_del_minimo_falla_y_no_escribe(
    tmp_path: Path, total: int, hito: int, fragmento: str
) -> None:
    ruta = escribir_casos(tmp_path, total, hito)
    with pytest.raises(ErrorCongelacion, match="mínimo") as info:
        congelar(ruta, FECHA, tmp_path)
    assert fragmento in str(info.value)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["casos.json"]


def test_los_sinteticos_no_cuentan_para_el_minimo(tmp_path: Path) -> None:
    casos = [caso(i, "hito" if i < 5 else "comunidad") for i in range(9)]
    casos.append(caso(99, "hito", sintetico=True))
    ruta = tmp_path / "casos.json"
    ruta.write_text(json.dumps({"casos": casos}), encoding="utf-8")
    with pytest.raises(ErrorCongelacion, match="10 casos totales"):
        congelar(ruta, FECHA, tmp_path)


def test_congelar_conjunto_invalido_falla_con_el_error_del_validador(tmp_path: Path) -> None:
    casos = [caso(i, "hito" if i < 5 else "comunidad") for i in range(10)]
    casos[0]["fuente_url"] = "http://inseguro.es"
    ruta = tmp_path / "casos.json"
    ruta.write_text(json.dumps({"casos": casos}), encoding="utf-8")
    with pytest.raises(ErrorCongelacion, match="https://"):
        congelar(ruta, FECHA, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["casos.json"]


def test_congelar_json_ilegible_falla(tmp_path: Path) -> None:
    ruta = tmp_path / "casos.json"
    ruta.write_text("{no es json", encoding="utf-8")
    with pytest.raises(ErrorCongelacion):
        congelar(ruta, FECHA, tmp_path)


def test_congelar_con_destino_escribe_v1_y_se_lee_de_vuelta(tmp_path: Path) -> None:
    ruta = escribir_casos(tmp_path)
    resultado = congelar(ruta, FECHA, tmp_path)
    leido = leer_congelado(tmp_path / "CONGELADO.md")
    assert leido == resultado
    assert leido.etiqueta == "validacion-v1"
    assert leido.fecha == "2026-12-01"
    assert leido.motivo is None


def test_congelar_con_destino_exige_fecha(tmp_path: Path) -> None:
    ruta = escribir_casos(tmp_path)
    with pytest.raises(ErrorCongelacion, match="fecha"):
        congelar(ruta, None, tmp_path)


def test_render_solo_lleva_los_datos_y_la_nota_fija() -> None:
    texto = render_congelado(1, "2026-12-01", 10, 5, "a" * 64)
    assert "motivo:" not in texto
    assert "No ajustar umbrales de detección antes de esta fecha" in texto
    contenido = [linea for linea in texto.splitlines() if linea and not linea.startswith("#")]
    assert len(contenido) == 7  # 6 claves + nota fija


def test_integridad_sin_congelado_solo_exige_casos_validos(tmp_path: Path) -> None:
    ruta = escribir_casos(tmp_path, 3, 1)
    assert comprobar_integridad(tmp_path, ruta) == []
    ruta.write_text("{}", encoding="utf-8")
    assert comprobar_integridad(tmp_path, ruta) != []


def test_integridad_pasa_con_huella_vigente(tmp_path: Path) -> None:
    ruta = escribir_casos(tmp_path)
    congelar(ruta, FECHA, tmp_path)
    assert comprobar_integridad(tmp_path, ruta) == []


def test_integridad_falla_si_cambia_un_byte_y_pide_v2(tmp_path: Path) -> None:
    ruta = escribir_casos(tmp_path)
    congelar(ruta, FECHA, tmp_path)
    ruta.write_bytes(ruta.read_bytes() + b" ")
    errores = comprobar_integridad(tmp_path, ruta)
    assert any("CONGELADO-v2.md" in e and "motivo" in e for e in errores)


def test_v2_con_motivo_y_huella_actual_pasa_y_es_la_vigente(tmp_path: Path) -> None:
    ruta = escribir_casos(tmp_path)
    congelar(ruta, FECHA, tmp_path)
    ruta.write_bytes(ruta.read_bytes() + b" ")
    congelar(ruta, FECHA, tmp_path, version=2, motivo="se corrige una fuente")
    assert comprobar_integridad(tmp_path, ruta) == []
    assert version_vigente(tmp_path).version == 2


def test_v2_sin_motivo_falla(tmp_path: Path) -> None:
    ruta = escribir_casos(tmp_path)
    huella = calcular_huella(ruta)
    congelar(ruta, FECHA, tmp_path)
    (tmp_path / "CONGELADO-v2.md").write_text(
        render_congelado(2, "2026-12-02", 10, 5, huella, motivo=""), encoding="utf-8"
    )
    assert any("motivo" in e for e in comprobar_integridad(tmp_path, ruta))
    with pytest.raises(ErrorCongelacion):
        congelar(ruta, FECHA, tmp_path, version=2)


def test_v3_sin_v2_no_sigue_a_la_anterior(tmp_path: Path) -> None:
    ruta = escribir_casos(tmp_path)
    huella = calcular_huella(ruta)
    congelar(ruta, FECHA, tmp_path)
    (tmp_path / "CONGELADO-v3.md").write_text(
        render_congelado(3, "2026-12-02", 10, 5, huella, motivo="x"), encoding="utf-8"
    )
    assert any("no sigue" in e for e in comprobar_integridad(tmp_path, ruta))


def test_version_declarada_distinta_de_la_del_nombre_falla(tmp_path: Path) -> None:
    ruta = escribir_casos(tmp_path)
    congelar(ruta, FECHA, tmp_path)
    (tmp_path / "CONGELADO-v2.md").write_text(
        render_congelado(5, "2026-12-02", 10, 5, calcular_huella(ruta), motivo="x"),
        encoding="utf-8",
    )
    assert comprobar_integridad(tmp_path, ruta) != []


def test_integridad_recalcula_los_minimos_desde_casos_json(tmp_path: Path) -> None:
    ruta = escribir_casos(tmp_path, 9, 5)
    # Un CONGELADO.md que miente: declara 10/5 y la huella correcta de un casos.json de 9.
    (tmp_path / "CONGELADO.md").write_text(
        render_congelado(1, "2026-12-01", 10, 5, calcular_huella(ruta)), encoding="utf-8"
    )
    errores = comprobar_integridad(tmp_path, ruta)
    assert any("10 casos totales" in e for e in errores)


def test_version_vigente_sin_ficheros_falla(tmp_path: Path) -> None:
    with pytest.raises(ErrorCongelacion):
        version_vigente(tmp_path)


def test_leer_congelado_rechaza_huella_mal_formada(tmp_path: Path) -> None:
    ruta = tmp_path / "CONGELADO.md"
    ruta.write_text(render_congelado(1, "2026-12-01", 10, 5, "zz"), encoding="utf-8")
    with pytest.raises(ErrorCongelacion, match="sha256"):
        leer_congelado(ruta)


def test_congelado_es_inmutable() -> None:
    c = Congelado(1, "2026-12-01", 10, 5, "a" * 64, "validacion-v1")
    with pytest.raises(AttributeError):
        c.version = 2  # type: ignore[misc]
