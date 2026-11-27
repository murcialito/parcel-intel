"""Piezas comunes de la revisión humana — historia #168, ADR 0047.

La revisión humana (trazados digitalizados, unidades georreferenciadas y
candidatos a corte) firma con un usuario de GitHub. El patrón vive solo aquí,
para que las tres revisiones acepten exactamente los mismos nombres. Solo stdlib.
"""

import re

GITHUB_USER_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
"""Usuario de GitHub: alfanumérico y guiones, de 1 a 39 caracteres, sin empezar por guion."""


def is_github_user(value: object) -> bool:
    """`True` si `value` es texto y cumple entero `GITHUB_USER_RE`."""
    return isinstance(value, str) and GITHUB_USER_RE.fullmatch(value) is not None
