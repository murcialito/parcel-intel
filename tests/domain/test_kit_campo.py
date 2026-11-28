import pytest

from parcel_intel.domain.kit_campo import (
    KitExportError,
    KitGeometry,
    PublishedFeature,
    PublishedLayerFile,
    build_kit_layer,
)

LINE = KitGeometry(lines=(((-3.5, 40.0), (-3.4, 40.1)),))
WARNING = "Esto no es un dictamen."


def card(**overrides: object) -> dict[str, object]:
    properties: dict[str, object] = {
        "etiqueta": "Desplazamiento entre fuentes",
        "texto": "Indicio a verificar: difieren unos 12 m.",
        "aviso": WARNING,
        "confianza": "media",
        "aviso_omision": None,
        "evidencia": [{"fuente": "x", "atribucion": "y"}],
    }
    properties.update(overrides)
    return properties


def file_of(layer: str, properties: dict[str, object], notice: str = "aviso") -> PublishedLayerFile:
    return PublishedLayerFile(
        layer=layer,  # type: ignore[arg-type]
        municipality_code="28043",
        features=(PublishedFeature("f1", LINE, properties),),
        source="fuente",
        license="CC BY 4.0",
        attribution=("Atribución A",),
        notice=notice,
    )


def test_ficha_con_etiqueta_texto_confianza_aviso_y_atribucion() -> None:
    layer = build_kit_layer(file_of("discrepancias", card()))
    tramo = layer.tramos[0]
    assert tramo.name == "Desplazamiento entre fuentes"
    assert "difieren unos 12 m" in tramo.description
    assert "Confianza: media." in tramo.description
    assert WARNING in tramo.description
    assert "Atribución: Atribución A" in tramo.description


def test_aviso_de_omision_se_conserva() -> None:
    layer = build_kit_layer(file_of("discrepancias", card(aviso_omision="Parte se omite.")))
    assert "Parte se omite." in layer.tramos[0].description


def test_trazado_sin_nombre_usa_nombre_por_defecto_y_aviso_de_la_procedencia() -> None:
    layer = build_kit_layer(
        file_of(
            "camino_actual",
            {"nombre": None, "tipo": "x", "fecha_dato": "2017-03-17"},
            "no deslinde",
        )
    )
    assert layer.tramos[0].name == "Camino actual (sin nombre)"
    assert "no deslinde" in layer.tramos[0].description
    assert "2017-03-17" in layer.tramos[0].description


@pytest.mark.parametrize("confianza", [None, "", "muy alta"])
def test_confianza_no_valida_falla(confianza: object) -> None:
    with pytest.raises(KitExportError):
        build_kit_layer(file_of("discrepancias", card(confianza=confianza)))


def test_palabra_vetada_en_la_ficha_falla() -> None:
    with pytest.raises(KitExportError, match="vetadas"):
        build_kit_layer(file_of("discrepancias", card(texto="Es una usurpación.")))


def test_procedencia_sin_aviso_falla() -> None:
    with pytest.raises(KitExportError, match="sin aviso"):
        build_kit_layer(file_of("vias_pecuarias", {"nombre": "a"}, notice="  "))


def test_propiedad_catastral_anidada_falla() -> None:
    with pytest.raises(KitExportError, match="catastral"):
        build_kit_layer(file_of("discrepancias", card(evidencia=[{"referencia_catastral": "x"}])))


def test_capa_sin_elementos_da_capa_vacia() -> None:
    empty = PublishedLayerFile("vias_pecuarias", "28043", (), "f", "l", ("a",), "n")
    assert build_kit_layer(empty).tramos == ()


@pytest.mark.parametrize("layer", ["discrepancias", "candidatos"])
def test_convergencia_se_admite_y_no_se_exporta(layer: str) -> None:
    """#315 (ADR 0057 §8): la tabla de convergencia entra en la lista blanca de las dos
    capas con ficha, pero no pasa a la descripción del tramo."""
    table = {
        "titulo": "Qué fuentes muestran este trazado",
        "filas": [{"fuente": "catastro_vt", "rotulo": "Catastro: vía de comunicación"}],
        "aviso": "Aviso de la tabla.",
    }
    kit = build_kit_layer(file_of(layer, card(convergencia=table)))
    description = kit.tramos[0].description
    for text in ("Qué fuentes", "Catastro: vía", "Aviso de la tabla", "convergencia"):
        assert text not in description
    assert (
        kit.tramos[0].description == build_kit_layer(file_of(layer, card())).tramos[0].description
    )
