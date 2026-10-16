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


def test_valor_numerico_hipotetico_se_parsea_a_float() -> None:
    # HTML construido a mano, NO capturado de una petición real: las dos
    # parcelas del MVP dieron "NO DATA" en los tres servicios muestreados
    # del Bloque 1 (REGISTRY.md), así que ningún valor numérico de
    # profundidad real llegó a observarse todavía. Este test solo confirma
    # que el parser extrae y convierte el número cuando la celda no es
    # "NO DATA" -- el formato exacto que usa el servicio real para un valor
    # positivo (separador decimal, unidades en la celda) queda sin
    # confirmar contra la red; riesgo residual documentado aquí, a
    # revisar en cuanto una petición real devuelva una profundidad != None.
    html = b"""<html><body><table class="featureInfo"><tbody>
    <tr><td>Profundidad del agua (metros)</td><td>1.25</td></tr>
    </tbody></table></body></html>"""

    assert parse_water_depth(html) == 1.25
