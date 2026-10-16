from parcel_intel.adapters.flood_hazard.parsing import parse_water_depth
from tests.adapters.flood_hazard.helpers import FIXTURES_DIR


def test_no_data_real_devuelve_none() -> None:
    html = (FIXTURES_DIR / "wms_getfeatureinfo_colmenar_rustica_t100_margin2m.html").read_bytes()

    assert parse_water_depth(html) is None


def test_no_data_real_villaconejos_fluvial_t10() -> None:
    html = (
        FIXTURES_DIR / "wms_getfeatureinfo_villaconejos_rustica_fluvialt10_margin2m.html"
    ).read_bytes()

    assert parse_water_depth(html) is None


def test_valor_real_con_coma_decimal_villaconejos_marina_t100() -> None:
    # Capturado real tras conectar esta fuente al informe (historia 0013):
    # la parcela de Villaconejos SÍ tiene un valor numérico real en las
    # capas MarinaT100/MarinaT500 ("0,000", separador de coma, no "NO
    # DATA") -- confirma con datos reales el riesgo residual que había
    # quedado documentado como hipotético en la historia 0012 (el formato
    # numérico real nunca se había observado todavía en ese momento).
    html = (
        FIXTURES_DIR
        / "wms_getfeatureinfo_villaconejos_rustica_marinat100_margin2m_valor_real_coma.html"
    ).read_bytes()

    assert parse_water_depth(html) == 0.0


def test_valor_numerico_hipotetico_con_punto_decimal_se_parsea_a_float() -> None:
    # HTML construido a mano: confirma que un valor con punto decimal (en
    # vez de la coma confirmada real arriba) también se parsea bien, por
    # si el servicio llega a devolver alguna vez ese formato.
    html = b"""<html><body><table class="featureInfo"><tbody>
    <tr><td>Profundidad del agua (metros)</td><td>1.25</td></tr>
    </tbody></table></body></html>"""

    assert parse_water_depth(html) == 1.25
