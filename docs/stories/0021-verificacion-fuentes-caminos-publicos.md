# 0021 — Verificación de fuentes del primer hito de caminos públicos (resolución, frecuencia, licencia, inventarios municipales) — CERRADA 2026-11-25 (dos criterios parciales, ver abajo)

## Historia

Como proyecto abierto que va a **publicar** un mapa de trazados que deberían ser públicos y de candidatos a corte en Colmenar de Oreja y municipios vecinos, quiero saber antes de escribir código qué resolución, qué frecuencia y qué licencia tiene cada fuente de imágenes y cartografía, y si cada municipio del ámbito tiene inventario de caminos publicado, para no diseñar sobre una capa que no distingue un camino, que está desfasada o que no se puede redistribuir.

## Contexto

Cambio de rumbo del 2026-11-25 ([ADR 0021](../adr/0021-cambio-de-rumbo-caminos-publicos-coste-casi-cero.md), [`docs/vision.md`](../vision.md), punto 7): ninguna historia de código del hito empieza hasta cerrar esta. Hasta ahora las licencias de casi todas las fuentes de `REGISTRY.md` estaban `asumido`, lo que era tolerable para informes privados. Para un mapa público, la licencia decide si una capa se puede publicar.

Historia sin código de producción: el entregable es `REGISTRY.md` más las fixtures o capturas de las respuestas reales. Sigue la regla de `LESSONS.md`: solo cuenta como verificado lo comprobado con una petición real. Las páginas de licencia se citan con su URL y la frase exacta que concede o restringe el uso.

## Criterios de aceptación

- [x] **Ámbito.** Lista de municipios colindantes con Colmenar de Oreja obtenida de una fuente geográfica real (no de memoria), con su código INE, separando los de la Comunidad de Madrid de los de otras comunidades.
- [x] **Por cada fuente de la tabla "Estado de partida" de `docs/vision.md`** (vías pecuarias IDEM, Catastro, PNOA actual, PNOA histórico, cartografía histórica IGN, BTN/BCN, PNOA LiDAR, OpenStreetMap): resolución (GSD o escala), frecuencia o fechas reales disponibles en el ámbito, y licencia con URL y cita textual. Cada valor marcado `confirmado` / `asumido` / `bloqueado`.
- [x] Para PNOA actual e histórico: fecha y resolución del vuelo que cubre realmente el ámbito, no la nominal del programa.
- [ ] **Parcial.** Para Catastro: cómo se identifican los caminos y los arroyos en rústico (numeración de parcela, tipo), comprobado con una petición real en el ámbito. Caminos `confirmado` (`9xxx` + `VT`). Arroyos (`HG`) sin comprobar: queda para la historia del mapa.
- [ ] **Parcial.** Para vías pecuarias: fecha o norma de origen de la cartografía y si hay actos de clasificación o deslinde consultables. Norma de origen (Ley 8/1998) y fecha de la ficha (2014) `confirmado`. Órdenes de clasificación y deslindes por municipio sin buscar; el PDF del inventario de 2023 devuelve 404.
- [x] **Inventarios municipales de caminos**: para cada municipio del ámbito, si hay inventario publicado (dónde, formato, año, si está aprobado por pleno o publicado en el BOCM), o constancia de que no se encontró y dónde se buscó.
- [x] Por cada capa, una conclusión explícita: si se puede **publicar** en el mapa, solo **usar internamente**, o **no usar**.
- [x] `docs/vision.md` actualiza la tabla "Estado de partida" con los resultados.
- [x] `uv run pytest`, `uv run mypy`, `uv run ruff check .` y `uv run lint-imports` siguen en verde (no debería cambiar nada de código).

## Fuera de alcance

- Clientes nuevos, adapters o cambios de dominio.
- Construir el conjunto de validación (historia propia).
- Decidir el método de detección de cortes.

## Resultado

Ver `src/parcel_intel/sources/REGISTRY.md`, sección "Fuentes del primer hito de caminos públicos", y la tabla "Estado tras la verificación" de `docs/vision.md`. Quedan `asumido` o `bloqueado`, cada uno con su motivo en el registro:

- La licencia de la red de transporte y del LiDAR del IGN (se asumen bajo la misma orden).
- La ortofoto de 2025 de la Comunidad de Madrid (aparece en el visor, no en el servicio).
- El conteo de OpenStreetMap (Overpass saturado).
- La lectura jurídica de "transformación" en la licencia de Catastro.
