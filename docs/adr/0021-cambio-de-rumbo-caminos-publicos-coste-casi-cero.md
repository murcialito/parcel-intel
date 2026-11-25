# ADR 0021 — Cambio de rumbo: caminos públicos como fase 1, proyecto abierto sin ánimo de lucro y coste de funcionamiento casi cero

- Estado: aceptada
- Fecha: 2026-11-25

## Contexto

Hasta la historia 0020 el producto era un informe de due diligence por referencia catastral para compradores de inmuebles (rústico como tesis comercial, pisos como segunda fase, caminos públicos como tercera). El fundador cambia el rumbo del proyecto:

1. Los caminos públicos pasan a ser la fase 1. El rústico para compradores queda como posible fase posterior. Pisos sale del alcance.
2. El proyecto pasa a ser sin ánimo de lucro y de código abierto: sin clientes, precios ni cuentas de pago. Solo se plantearía cobrar o pedir aportaciones si hubiera costes reales de funcionamiento, y el diseño debe buscar que el coste sea casi cero.
3. Los usuarios son asociaciones de defensa de caminos, senderistas, ciclistas, ganaderos y ayuntamientos pequeños.
4. El primer hito (Colmenar de Oreja y municipios vecinos) es un mapa de trazados que deberían ser públicos, los candidatos a corte y un visor web sencillo.
5. La validación pasa a ser un conjunto de caminos cerrados ya documentados públicamente, que el sistema debe señalar sin ayuda.
6. Se mantienen tres principios: indicios y nunca ilegalidades, no nombrar a propietarios, y aprobación humana de las reglas propuestas por IA.
7. Antes de programar hay que verificar la resolución, la frecuencia y la licencia de cada fuente, y si los municipios tienen inventario de caminos.

## Decisión

1. **Se reutiliza el motor y no se borra nada.** Los clientes de Catastro, PNOA (actual e histórico) y vías pecuarias, PostGIS, el evaluador determinista de reglas y el flujo de autoría con revisión humana se mantienen. Los clientes que no aportan al hito (IDEM `UsoDelSuelo`, BOE, BOCM, Sentinel-2, cauces/inundación, Red Natura 2000) se quedan en el repositorio, en pausa, con sus tests en verde.
2. **La unidad de análisis pasa de la parcela al municipio.** Se procesa por lotes ("municipio → trazados y candidatos") en lugar de "referencia catastral → informe bajo petición".
3. **Se publica en estático por defecto.** El visor sirve ficheros pregenerados y no consulta PostGIS ni ninguna API propia. Cualquier componente con coste recurrente (backend, almacenamiento de fotos de avisos, servicio de pago) necesita un ADR propio con una estimación de coste antes de diseñarse.
4. **Ningún LLM en una consulta de usuario.** El LLM (DeepSeek, detrás de la interfaz única ya existente) solo trabaja fuera de línea: autoría de reglas con revisión humana y, si hace falta, textos que se generan una vez y se publican ya revisados.
5. **No entra titularidad.** Ningún dato de titularidad entra en el sistema ni sale en ninguna vista.
6. **La licencia de redistribución decide si una capa se publica.** Una capa cuya licencia no permita la redistribución ni la obra derivada puede usarse internamente, pero no sale en el mapa público.
7. **Verificar antes de programar.** Ninguna historia de código del hito empieza antes de cerrar la historia de verificación de fuentes (resolución, frecuencia y licencia con cita textual; inventarios municipales de caminos).

## Consecuencias

- `docs/vision.md` queda reescrito. La versión anterior se conserva en git.
- `CLAUDE.md` incorpora las reglas de coste casi cero, de no titularidad, de licencia de publicación y la restricción del LLM a uso fuera de línea.
- El composition root actual (`api/` de informe bajo petición) deja de ser el camino principal. La forma del nuevo punto de entrada por lotes y del artefacto estático la decide el arquitecto en la historia correspondiente, con su propio ADR.
- Quedan abiertas: la licencia del código y de los datos derivados, si el mapa muestra la referencia catastral de la finca afectada, el método de detección de cortes y el alojamiento del mapa estático.
- Los riesgos "responsabilidad legal antes de cobrar un informe" y "financiar la digitalización de boletines y planeamiento" dejan de ser bloqueantes porque no se cobra y no hay boletines en el hito. Los sustituye el riesgo de que un candidato publicado se lea como acusación o permita identificar a un propietario de forma indirecta.
