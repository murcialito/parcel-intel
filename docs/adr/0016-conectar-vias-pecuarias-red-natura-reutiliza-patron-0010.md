# ADR 0016 — Conectar vías pecuarias/Red Natura 2000 al informe: se reutiliza el patrón de ADR 0010 (reafirmado por ADR 0013), sin desviaciones

- Estado: aceptada
- Fecha: 2026-10-16

## Contexto

La historia 0016 conecta las dos fuentes ya aisladas y verificadas en las historias 0014 (`LivestockTrailAdapter`/`LivestockTrailPort`, ADR 0014) y 0015 (`ProtectedAreaAdapter`/`ProtectedAreaPort`, ADR 0015) al mismo informe HTML que las historias 0010 y 0013 ya extendieron para las ocho fuentes anteriores. Verificado contra el código real antes de decidir nada:

- `LivestockTrailPort.get_nearby_livestock_trails(geometry, margin_m) -> list[LivestockTrail]` (`ports/livestock_trail.py`) y `ProtectedAreaPort.get_nearby_protected_areas(geometry, margin_m) -> list[ProtectedArea]` (`ports/protected_area.py`) **nunca lanzan** para "sin afección": lista vacía es el resultado real y mayoritario para ambas (confirmado en el docstring de cada port y en `LivestockTrailAdapter`/`ProtectedAreaAdapter`, que devuelven `[]` sin excepción cuando `parse_wfs_*` no encuentra features). Ninguna de las dos se comporta como `LandClassificationPort` (que sí lanza `NoLandClassificationFoundError`, ADR 0011) — ambas se comportan exactamente como `WatercoursePort` (ADR 0012/0013): `None` solo si falla la red/parsing, tupla vacía es un resultado legítimo y distinto.
- `GenerateEnrichedParcelReportUseCase._safe[T]` (`application/generate_enriched_report.py`) ya es genérico y ya captura `except Exception` sin distinguir tipos — basta, sin modificar su firma, para las dos fuentes nuevas: el valor de éxito es `tuple(port.get_...(geometry, margin_m))`, la misma forma ya usada para `watercourses`. No hace falta ninguna variante de `_safe_notices` (reservada a BOE/BOCM, que aplican `filter_by_title`).
- `domain/livestock_trail.py` y `domain/protected_area.py` ya existen completos desde las historias 0014/0015, con todos los campos que esta historia necesita mostrar (`trail_type`/`name`/`area_m2`/`length_m`; `plan_code`/`plan_name`/`zone_code`/`zone_name`) — no se añade ni se modifica ningún tipo de dominio.
- `adapters/reports/html.py` ya tiene el patrón de tres estados por sección (`_render_bulletin_section`/`_render_watercourse_section`: `None` → "no disponible", tupla vacía → "sin resultados", tupla con elementos → listado) — exactamente la distinción que piden `livestock_trails` y `protected_areas`.
- `LivestockTrailAdapter.DEFAULT_MARGIN_M` y `ProtectedAreaAdapter.DEFAULT_MARGIN_M` son ambos `2.0`, mismo valor y mismo criterio (salvaguarda de punto flotante, no umbral de negocio) ya documentado para IDEM/cauces/inundación.

No hay ninguna forma de dato nueva ni incompatible con lo que ya modelan `domain/report.py`, `application/generate_enriched_report.py` o `adapters/reports/html.py`. A diferencia de las historias 0011/0012 (formas de dato nuevas que obligaron a diseñar), y de forma aún más simple que la historia 0013 (que sí tuvo que razonar sobre `NoLandClassificationFoundError` cayendo en `except Exception`), aquí las dos fuentes nuevas son el caso más simple posible: ambas con la misma semántica exacta que `watercourses`, sin ninguna excepción de negocio que considerar. No hay nada que diseñar de nuevo, solo componer.

## Decisión

**Se reutiliza, sin desviaciones, exactamente el patrón ya fijado por el ADR 0010 y reafirmado por el ADR 0013** para las dos fuentes nuevas:

1. `EnrichedParcelReport` gana dos campos nuevos (`livestock_trails: tuple[LivestockTrail, ...] | None`, `protected_areas: tuple[ProtectedArea, ...] | None`), cada uno con su docstring documentando que `None` solo ocurre por fallo de red y que la tupla vacía es un resultado legítimo — mismo nivel de detalle que `watercourses`.
2. `GenerateEnrichedParcelReportUseCase` recibe `livestock_trail_port: LivestockTrailPort` y `protected_area_port: ProtectedAreaPort` por constructor y los resuelve con el `_safe[T]` ya existente, sin modificarlo: `self._safe(lambda: tuple(self._livestock_trail_port.get_nearby_livestock_trails(geometry, LIVESTOCK_TRAIL_MARGIN_M)))` y análogo para `protected_area_port`.
3. Dos constantes nuevas de margen (`LIVESTOCK_TRAIL_MARGIN_M = 2.0`, `PROTECTED_AREA_MARGIN_M = 2.0`), duplicadas deliberadamente de `LivestockTrailAdapter.DEFAULT_MARGIN_M`/`ProtectedAreaAdapter.DEFAULT_MARGIN_M`, con la misma nota ya escrita para `WATERCOURSE_MARGIN_M`/`FLOOD_HAZARD_MARGIN_M`.
4. `api/main.py` instancia `LivestockTrailAdapter()` y `ProtectedAreaAdapter()` dentro de `get_parcel_report`, junto a los ocho adapters ya existentes — ninguna clase concreta se instancia en otro lugar (ADR 0003, sin cambios).
5. `adapters/reports/html.py` añade dos funciones de render (`_render_livestock_trail_section`, `_render_protected_area_section`), siguiendo literalmente la forma de `_render_watercourse_section` (tres ramas: `None` → "no disponible", tupla vacía → "sin resultados", tupla con elementos → listado de texto). Ninguna dibuja `Geometry` sobre el SVG.
6. **Copy de los tres estados — resuelve la pregunta abierta 1 de la historia:** mismo estilo `"<Sección> (<Proveedor>) no disponible."` ya usado por `land_classifications`/`watercourses` para la rama `None` (en vez del texto sin proveedor inicialmente esbozado en el borrador de este ADR — alineado aquí con lo que el código implementa de verdad, para que este documento no afirme un texto distinto del real):
   - Vías pecuarias: `None` → `"Vías pecuarias (IDEM) no disponible."`; tupla vacía → `"Sin vías pecuarias cercanas."`; con elementos, cada fila muestra `name`, `trail_type`, `municipality_name`, y `area_m2`/`length_m` reales (formateados en m²/m), seguidos de una nota aparte explícita de que no son la anchura legal (ADR 0014).
   - Red Natura 2000: `None` → `"Espacios protegidos Red Natura 2000 (IDEM) no disponible."`; tupla vacía → `"Sin espacios protegidos Red Natura 2000 cercanos."`; con elementos, cada fila muestra `plan_code`/`plan_name` y `zone_code`/`zone_name` (los cuatro campos reales, no solo los dos nombres).
7. **Sin indicador visual especial para el posible solape con `land_classifications` — resuelve la pregunta abierta 3 de la historia:** se lista cada `ProtectedArea` como fila de texto plano, sin ningún elemento de UI nuevo (badge, color, icono) — mismo criterio de simplicidad ya aplicado en el ADR 0013 para el solape de municipios en clasificación de suelo.
8. **Verificación del endpoint HTTP con la referencia urbana del fundador (`REFCAT-RETIRADA`) — resuelve la pregunta abierta 2:** se intenta sin cambios de código; si el endpoint no la resuelve por cualquier motivo ajeno a esta historia, se documenta como limitación conocida y la verificación end-to-end queda satisfecha solo con Villaconejos `REFCAT-RETIRADA` — tal como la propia historia ya lo deja como salida válida.

No se crea ningún `except` nuevo en `ports/errors.py` (ninguna de las dos fuentes lo necesita), no se modifica `_safe`, y no se instancia ningún adapter concreto fuera de `api/main.py`.

## Alternativas consideradas

Ninguna: igual que el ADR 0013, el patrón de conexión ya está fijado y probado por el ADR 0010 sobre cuatro fuentes y reafirmado sobre tres más por el ADR 0013, con las dos mismas distinciones de estado que estas dos fuentes nuevas necesitan (`None`/tupla vacía, idéntico a `watercourses`). No hay ninguna forma de dato nueva que justifique explorar una alternativa; forzar variedad de diseño sin un consumidor real que la motive repetiría el patrón de sobre-diseño que el ADR 0010 ya rechazó explícitamente.

## Consecuencias

- `domain/report.py`: `EnrichedParcelReport` pasa de 8 a 10 campos evidenciales (más `report`). Sigue importando solo tipos de `domain/`.
- `application/generate_enriched_report.py`: 2 parámetros nuevos en el constructor, 2 constantes de margen nuevas, 2 llamadas a `_safe` ya existente. Sigue sin importar ningún adapter concreto.
- `adapters/reports/html.py`: 2 funciones de render nuevas, mismo patrón de `_render_watercourse_section`. Ninguna sección dibuja geometría sobre el SVG.
- `api/main.py`: 2 adapters más instanciados por petición, 0 cambios de composition root fuera de este archivo.
- No se introduce ningún proveedor third-party nuevo (IDEM ya tenía su ADR de entrada en 0011, reutilizado por ambos adapters vía el mismo workspace `Zonas`); el coste de salida no cambia respecto a lo ya documentado en los ADR 0014/0015: desconectar cualquiera de las dos sigue siendo tan barato como dejar de instanciar su adapter en `api/main.py`.
- Riesgo residual: igual que el ADR 0010/0013 ya señalaron, `except Exception` genérico en `_safe` también silenciaría un bug de programación real dentro de `LivestockTrailAdapter`/`ProtectedAreaAdapter` igual que un fallo de red esperado — mismo riesgo ya aceptado, sin mitigación nueva en esta historia.
- Con esta historia, las diez fuentes de `REGISTRY.md` con cliente aislado implementado quedan todas conectadas al informe — ninguna queda pendiente de conexión (solo concesiones de agua e inventario municipal de caminos permanecen sin cliente, fuera de alcance de esta historia).
