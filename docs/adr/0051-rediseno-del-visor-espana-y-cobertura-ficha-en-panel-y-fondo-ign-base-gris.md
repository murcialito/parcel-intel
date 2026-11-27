# ADR 0051 — Rediseño del visor: España y cobertura, ficha en panel y fondo IGN-Base gris

- Estado: aceptada
- Fecha: 2026-11-27
- Historia: #185 (rol diseñador, trabajada en local con el fundador). Amplía el ADR 0037 (visor estático con Leaflet). Diseño: [`docs/diseno/rediseno-visor.md`](../diseno/rediseno-visor.md).

## Contexto

El 2026-11-27 el fundador dijo que el visor era pobre: abría en un municipio sin contexto, el popup de un indicio era largo e ilegible y en móvil el mapa tapaba los controles. Pidió ver toda España con los municipios cubiertos resaltados y el resto en gris, mejorar el aspecto y llevar la ficha a un panel (escritorio) o a una hoja inferior (móvil), con un resumen primero y el detalle desplegable. No hay usuarios todavía, así que el cambio puede ser grande.

## Decisión

1. **Sigue Leaflet 1.9.4** (ADR 0037). El visor solo pinta teselas ráster WMTS y GeoJSON de pocos cientos de KB. MapLibre GL obligaría a vendorizar ~800 KB más y a reescribir estilos sin ganar nada visible. `mapa.js` sigue siendo el único módulo que usa `L`.
2. **Dos fondos, del IGN, KVP:** `mapa` (`IGNBase-gris`, «Callejero gris» de `https://www.ign.es/wmts/ign-base`) y `ortofoto` (el PNOA de #85). Verificado el 2026-11-27 con peticiones reales (REGISTRY.md, «WMTS IGN-Base gris»; fixtures en `tests/fixtures/ign_base/`). Licencia `CC BY 4.0 scne.es`. La tabla del SCNE no lista IGN-Base, así que la atribución es la del servicio con el nombre de la capa: `IGNBase-gris CC BY 4.0 scne.es` (NOTICE). Cada fondo lleva en `config.js` sus atribuciones, visibles solo mientras está activo; `crearMapa` pone la del fondo inicial antes de pedir teselas (CA4 de #85).
3. **Vista inicial: España** (`CONFIG.espana`, península y Baleares) con el fondo gris. Al entrar en un municipio se pasa a la ortofoto, salvo que la persona haya elegido fondo; al volver a España, al gris.
4. **Cobertura publicada como fichero propio:** `site/datos/cobertura.geojson` con el contorno de cada municipio con datos (propiedades `ine` y `nombre`, nada más), EPSG:4326, simplificado a 15 m, y su `.procedencia.json`. Lo escribe el comando nuevo `publicar-cobertura` (`PublishCoverageUseCase` + `GeoJsonCoverageSink`) desde la caché cruda de límites del IGN, sin red. Pasa por la puerta `PublishableLayer` (ADR 0028). Pesa 31.542 bytes para los 7 municipios; el sink falla por encima de 200.000.
5. **El adapter de unidades administrativas marca `PUBLIC`.** Los límites del IGN son `CC BY 4.0 ign.es` y «Publicar» en REGISTRY.md desde la historia 0021, pero el adapter dejaba la marca por defecto (`INTERNAL_ONLY`). Publicar exige marcar en el adapter (ADR 0028). Efecto en otras capas: ninguno visible; la capa vacía de vías pecuarias, que toma la procedencia del límite, ya se omite antes de la puerta desde #86.
6. **Gris fuera de cobertura:** un velo (polígono del mundo con un hueco por municipio) en un pane por debajo de las capas, y el contorno de cada municipio cubierto, que al pulsarlo lo abre. A escala de España, donde 7 municipios son unos píxeles, una etiqueta «Primer hito · N municipios» (marcador de Leaflet con un nodo de texto, accesible con teclado) encuadra la zona; se oculta a partir del zoom 9. Los estilos van en `estilos-capas.js` como `COBERTURA`, fuera de `CLAVES`.
7. **Sin popups.** Al pulsar un trazado, `mapa.js` llama a `alPulsar(propiedades, id)` y el controlador manda un modelo de ficha a la vista, que lo pinta en `<aside id="ficha">`: panel lateral en escritorio, hoja inferior ampliable en móvil (< 900 px). Resumen primero (texto validado, confianza y aviso, nunca plegado) y después `<details>`: imágenes de comparación, fuentes (con «Abrir la consulta original» en lugar de la URL entera) y cómo se ha calculado. Los textos validados de #16 y #169 no cambian.
8. **Estado en el enlace:** `?municipio=<ine>&tramo=<id de 16 hex>`, leído y escrito por el módulo puro `enlace.js` y aplicado con `history.replaceState`. Un enlace a un tramo enciende su capa (que nace apagada) solo para mostrarlo. Un tramo que ya no está publicado abre el municipio y lo dice.
9. **Buscador de municipio** como combobox ARIA (`input role="combobox"` + `ul role="listbox"`), sin tildes ni mayúsculas, solo entre los municipios con datos. Sustituye al `<select>`.
10. **Rótulos sobre la ortofoto** (feedback del fundador, 2026-11-27: al entrar en un municipio se perdían los nombres y las carreteras). El fondo `ortofoto` lleva encima la capa transparente `IGNBaseOrto` del mismo servicio, en escala de grises (sus carreteras naranjas se confundían con las vías pecuarias) y por debajo de los trazados. Atribución `IGNBaseOrto CC BY 4.0 scne.es` (REGISTRY.md, NOTICE).
11. **Atribución en móvil con una hoja abierta** (revisión de la PR): la ficha y la hoja de capas tapan el pie del mapa, así que cada una repite en su pie fijo (fuera de la zona que se desplaza) la misma lista de atribuciones visibles que el control del mapa. Con la hoja de capas plegada se ve la del mapa.
12. **Tokens nuevos** en `site/css/tokens.css` y en el original de `docs/design-system/`: `--map-mapa-filter` (en oscuro atenúa el mapa gris sin invertirlo: invertido quedaba demasiado oscuro, feedback del fundador), `--capa-cobertura` y `--capa-cobertura-velo`.

### Decisiones de producto a revisar con el fundador

- Pasar solo a ortofoto al entrar en un municipio (y a gris al volver a España).
- La atribución completa sigue sobre el mapa también en móvil (no se movió a la hoja de capas).
- El tema sigue al sistema; no hay conmutador claro/oscuro.
- Tolerancia de 15 m de los contornos y zoom 9 para cambiar la etiqueta por los contornos.
- Las filas de indicios y tramos conservan el nombre completo validado («… (no son un dictamen)»); las de vías pecuarias y camino actual se acortan.
- El resumen de la medición de los tramos se pliega en «Cómo se ha medido» y queda a la vista «revisado a mano» (feedback del fundador: ver todas las capas a la vez).
- Opacidad del velo: 0,22 en claro y 0,28 en oscuro.

## Consecuencias

- Los tests de #85, #95, #114, #115, #165, #166, #171 y #178 que fijaban el `<select>`, los popups o el marcado viejo se reescriben para comprobar lo mismo sobre la estructura nueva. Las invariantes (aviso, palabras vetadas, nada catastral, atribución visible, capas apagadas, rutas existentes) siguen probadas.
- El visor pide `datos/cobertura.geojson` al arrancar. Si falla, sigue sin velo y lo dice en el panel; no es un error de capa.
- `cobertura.geojson` es obra derivada (reproyectada y simplificada) del límite del IGN y lleva `CC BY 4.0 ign.es` sin «Obra derivada de…»: el formato del SCNE para unidades administrativas sigue «pendiente de verificar» en NOTICE desde #35. Queda para una historia aparte.
- Cada municipio nuevo del índice necesita volver a ejecutar `publicar-cobertura`; el test de #185 comprueba que la cobertura publicada y el índice tienen los mismos municipios.
