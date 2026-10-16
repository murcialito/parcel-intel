import re

# Confirmado real (REGISTRY.md hallazgo 4): el `text/html` de `GetFeatureInfo`
# es más fiable que el GML crudo, que solo expone `GRAY_INDEX=999.0` -- un
# código específico de esta capa para "sin dato", no un sentinel genérico.
# El HTML, en cambio, etiqueta el valor como "NO DATA" en texto legible.
_DEPTH_RE = re.compile(
    r"Profundidad del agua \(metros\)</td>\s*<td>\s*(.*?)\s*</td>", re.DOTALL
)


def parse_water_depth(html_body: bytes) -> float | None:
    """Extrae la profundidad de agua (metros) de la respuesta `text/html`
    de `GetFeatureInfo`. Devuelve `None` si la celda dice "NO DATA"
    (confirmado real: sin afección en ese punto, no un error).

    Confirmado real (parcela de Villaconejos, capas `MarinaT100`/
    `MarinaT500`): el servicio devuelve el valor numérico con coma como
    separador decimal ("0,000"), no con punto — se normaliza antes de
    `float()`."""
    match = _DEPTH_RE.search(html_body.decode("utf-8"))
    if match is None:
        return None
    value = match.group(1).strip()
    if value == "NO DATA":
        return None
    return float(value.replace(",", "."))
