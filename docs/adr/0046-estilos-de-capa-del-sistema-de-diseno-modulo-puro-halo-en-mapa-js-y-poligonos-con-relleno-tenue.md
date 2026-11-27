# ADR 0046 — Estilos de capa del sistema de diseño: módulo puro, halo en mapa.js y polígonos con contorno y relleno tenue

- Estado: aceptada
- Fecha: 2026-11-27
- Historia: #165 (madre #116, feature #113). Enmienda la interfaz de `mapa.js` del ADR 0037 §2.

## Contexto
El sistema de diseño (`docs/design-system/site/js/estilos-capas.js`) define el estilo de cada capa como halo oscuro + línea, con variantes de tema y de estado (normal, hover, seleccionado), y lo entrega como script global que recibe `L`. El visor (ADR 0037) usa módulos ES y aísla Leaflet en `mapa.js`; `controlador.js` y `config.js` no importan nada. Las vías pecuarias e indicios publicados son polígonos y el sistema de diseño piensa en líneas.

## Decisión
1. `site/estilos-capas.js` es un módulo ES puro con los valores y la aritmética del original (`BASE`, `ESTILOS`, `estilo`), más `RELLENO`, `estiloTrazado` (relleno para polígonos) y `temaDe` (regla de tema). Sin DOM, sin Leaflet, sin globales. Un test lo compara con el original ejecutado en `node:vm`.
2. El dibujo con halo, el hover y la selección única viven en `mapa.js`, que importa `estiloTrazado`. Interfaz: `anadirCapa(id, geojson, { clave | claveDe, orden, alPulsar })` y `ponerTema(tema)`; el resto no cambia.
3. Orden de apilado por pane por capa (`zIndex` 400 + `orden` de `config.js`), independiente del orden de carga.
4. Polígonos: halo y línea sobre el contorno y relleno del color de la línea al 15 % (vías pecuarias) o al 10 % (indicios), +10 puntos al pasar el puntero o seleccionar. A zoom bajo se lee como banda continua; a zoom alto muestra el ancho real.
5. `config.js` describe el estilo como datos (`{ clave }` o `{ porPropiedad, claves, defecto }`); `controlador.js` lo traduce sin imports. Confianza desconocida → nivel `baja`.
6. El tema lo resuelve `app.js` con `temaDe` (data-tema gana; si no, prefers-color-scheme) y lo pasa a `mapa.js`; la ortofoto se atenúa por CSS con `--map-tiles-filter`.

### Umbrales y decisiones de producto a revisar con el fundador
- Opacidad del relleno de polígonos (15 % vías pecuarias, 10 % indicios) y su aumento de 10 puntos en hover y selección: no vienen del sistema de diseño.
- Confianza ausente o desconocida dibujada como `baja` (el nivel menos enfático) en lugar de ocultar el indicio.

## Consecuencias
- Cambiar de librería sigue siendo reescribir solo `mapa.js`; `estilos-capas.js` es independiente de Leaflet y sirve a MapLibre.
- Cada feature se dibuja dos veces (halo y línea): duplica el coste de dibujo; entra en los disparadores de migración del ADR 0037.
- Si cambia `docs/design-system/site/js/estilos-capas.js`, el test del CA1 obliga a actualizar el módulo.
- El trazado histórico (`orden` 20) e indicios ya tienen estilo probado; dibujarlo es añadir la capa a `config.js`.
