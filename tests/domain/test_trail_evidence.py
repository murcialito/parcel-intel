import pytest

from parcel_intel.domain.georeferencing import AffineTransform
from parcel_intel.domain.trail_evidence import (
    PNOA_EVIDENCE_ATTRIBUTION,
    EvidenceLayout,
    band_radius_m,
    evidence_layout,
    layer_attributions,
)
from tests.adapters.evidence.helpers import make_trail, make_unit

# x = 466000 + 2·col ; y = 4440000 − 2·row (2 m/px, sin giro)
PLAIN = AffineTransform(a=466000.0, b=2.0, c=0.0, d=4440000.0, e=0.0, f=-2.0)


def test_trazado_pequeno_recorte_y_ventana_calculados_a_mano() -> None:
    # bbox (1000,800)-(1100,900) ± 200 → recorte (800,600)-(1300,1100): 500 × 500, step 1.
    # Esquinas: x 467600…468600, y 4437800…4438800 → ventana 1000 × 1000 m a 500 px.
    layout = evidence_layout(make_unit(PLAIN), make_trail((1000, 800), (1100, 900)))
    assert layout == EvidenceLayout(
        crop=(800, 600, 1300, 1100),
        step=1,
        panel_width_px=500,
        panel_height_px=500,
        window=(467600, 4437800, 468600, 4438800),
        pnoa_width_px=500,
        pnoa_height_px=500,
    )


def test_trazado_cerca_del_borde_se_acota_a_la_imagen() -> None:
    # bbox (50,40)-(120,100): 50−200 y 40−200 salen negativos → 0; 120+200 = 320, 100+200 = 300.
    # Esquinas: x 466000…466640, y 4439400…4440000 → 640 × 600 m; 320 px → alto 300.
    layout = evidence_layout(make_unit(PLAIN), make_trail((50, 40), (120, 100)))
    assert layout.crop == (0, 0, 320, 300)
    assert layout.step == 1
    assert (layout.panel_width_px, layout.panel_height_px) == (320, 300)
    assert layout.window == (466000, 4439400, 466640, 4440000)
    assert (layout.pnoa_width_px, layout.pnoa_height_px) == (320, 300)


def test_recorte_mayor_de_800_px_reduce_por_un_escalon_entero() -> None:
    # bbox (100,100)-(1900,200): x 0…2100, y 0…400 → 2100 × 400; step = ceil(2100/800) = 3;
    # panel 700 × 134 (400/3 = 133,3). Ventana x 466000…470200, y 4439200…4440000 (4200 × 800 m);
    # alto de PNOA = ceil(800 · 700 / 4200) = ceil(133,3) = 134.
    layout = evidence_layout(make_unit(PLAIN), make_trail((100, 100), (1900, 200)))
    assert layout.crop == (0, 0, 2100, 400)
    assert layout.step == 3
    assert (layout.panel_width_px, layout.panel_height_px) == (700, 134)
    assert layout.window == (466000, 4439200, 470200, 4440000)
    assert (layout.pnoa_width_px, layout.pnoa_height_px) == (700, 134)


def test_la_ventana_es_la_envolvente_entera_de_las_cuatro_esquinas() -> None:
    # x = 466000,4 + 2·col + 0,1·row ; y = 4440000,6 − 2·row. Recorte (800,600)-(1300,1100):
    # x(800,600) = 467660,4 · x(1300,1100) = 468710,4 → suelo 467660, techo 468711;
    # y(·,600) = 4438800,6 · y(·,1100) = 4437800,6 → suelo 4437800, techo 4438801.
    # 1051 × 1001 m a 500 px → alto = ceil(1001 · 500 / 1051) = ceil(476,2) = 477.
    skewed = AffineTransform(a=466000.4, b=2.0, c=0.1, d=4440000.6, e=0.0, f=-2.0)
    layout = evidence_layout(make_unit(skewed), make_trail((1000, 800), (1100, 900)))
    assert layout.window == (467660, 4437800, 468711, 4438801)
    assert (layout.pnoa_width_px, layout.pnoa_height_px) == (500, 477)


def test_el_suelo_y_el_techo_de_los_vertices_fraccionarios() -> None:
    # bbox (100,100.6)-(200.2,300): suelo 100/100, techo 201/300 → ± 200 → (0,0)-(401,500).
    layout = evidence_layout(make_unit(PLAIN), make_trail((100.0, 100.6), (200.2, 300.0)))
    assert layout.crop == (0, 0, 401, 500)


def test_recorte_fuera_de_la_imagen_lanza_error() -> None:
    unit = make_unit(PLAIN, width_px=100, height_px=100)
    with pytest.raises(ValueError, match="fuera de la imagen"):
        evidence_layout(unit, make_trail((900, 900), (950, 950)))


def test_banda_de_dos_veces_el_loo_y_atribuciones() -> None:
    unit = make_unit(PLAIN, loo_rmse_m=6.5)
    assert band_radius_m(unit) == 13.0
    attributions = layer_attributions(unit)
    assert attributions == (
        "Obra derivada de Planimetrías 1870-1950 CC-BY 4.0 "
        "© Instituto Geográfico Nacional de España",
        PNOA_EVIDENCE_ATTRIBUTION,
    )
    assert PNOA_EVIDENCE_ATTRIBUTION == "Obra derivada de PNOA 2023 CC-BY 4.0 scne.es"
