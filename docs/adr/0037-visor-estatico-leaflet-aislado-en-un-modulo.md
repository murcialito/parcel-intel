# ADR 0037 — Visor estático con Leaflet aislado en un módulo

- Estado: aceptada
- Fecha: 2026-11-26
- Historia: #85 (feature #82, épica #6)

## Contexto

El primer corte del mapa publica dos capas CC BY 4.0 (vías pecuarias de la Comunidad de Madrid y
camino actual del IGN) como GeoJSON estático en `site/datos/` (#84), en GitHub Pages, sin backend
(ADR 0021: coste casi cero). Hace falta un visor que las dibuje sobre una ortofoto, con la
atribución de cada capa visible junto a los datos (ADR 0035, condiciones del IGN) y el aviso de
que las vías pecuarias son cartografía informativa, no un deslinde.

El fundador fijó en #6/#82: Leaflet copiado en el sitio, sin CDN; dependencia de la librería
aislada en un módulo para poder migrar a MapLibre GL sin tocar HTML ni datos; mapa base PNOA o
IGN-Base por WMTS.

## Decisión

1. **Librería: Leaflet 1.9.4** (última estable el 2026-11-26; la 2.0 está en beta), BSD-2-Clause.
   Se copia `dist/leaflet.js`, `dist/leaflet.css` y `dist/images/` del paquete npm
   `leaflet-1.9.4.tgz` (sha1 `23fae724e282fa25745aff82ca4d394748db7d8d`, comprobado de nuevo
   contra la descarga real al implementar) a `site/vendor/leaflet/`, con su `LICENSE`. Sin CDN,
   sin npm en el repo, sin paso de compilación.
2. **Aislamiento:** solo `site/mapa.js` usa el global `L`. Expone `crearMapa` y un objeto con
   `anadirCapa`, `quitarCapa`, `mostrarCapa`, `encuadrar` y `ponerAtribuciones`. La lógica del visor
   (`controlador.js`) recibe el mapa, la carga de JSON y la vista por inyección y no conoce ni el
   DOM ni Leaflet; `app.js` es el único punto de composición. Un test impide referencias a `L`
   fuera de `mapa.js`.
3. **Mapa base:** WMTS `https://www.ign.es/wmts/pnoa-ma`, capa `OI.OrthoimageCoverage`,
   `GoogleMapsCompatible` (EPSG:3857), JPEG, niveles 0-19, petición KVP (el servicio no ofrece
   REST). Verificado el 2026-11-26 con una tesela real sobre Colmenar de Oreja. Licencia CC BY 4.0
   (documento de condiciones del IGN; `AccessConstraints` = `CC BY 4.0 scne.es`); CORS abierto.
   Atribución, de la tabla de productos del SCNE, sin «Obra derivada de» porque las teselas se
   muestran sin transformar: `PNOA 2023 CC-BY 4.0 scne.es` y
   `MosaicoSentinel2 2018-2026 CC-BY 4.0 ign.es`, siempre visibles. IGN-Base queda como alternativa
   no usada.
4. **Textos públicos:** las atribuciones y el aviso se incrustan en `config.js` e `index.html` y un
   test los compara con `NOTICE`, que es la fuente única. No se generan. Las atribuciones se
   pasan al control de Leaflet escapadas, como texto plano.
5. **Índice:** el visor conoce los municipios por `site/datos/indice.json` (con su
   `.procedencia.json`), que escribe `publicar-capas`.
6. **Pruebas:** comprobaciones estáticas desde pytest y tests de módulo con `node --test` (Node
   de la imagen del runner, sin dependencias nuevas).

## Desviaciones del diseño de la issue

- Se añade `site/vista.js`: la vista (selector, estados de capa, mensajes y ficha del popup) recibe
  el `document` por inyección. Así el requisito «el texto se inserta como texto» (CA6) se prueba en
  Node con un documento falso que prohíbe `innerHTML`, sin tener que importar `app.js`.
- Para cargar los módulos en Node, el test los copia a un directorio temporal con un
  `package.json` `{"type": "module"}` en lugar de renombrarlos a `.mjs`: `app.js` y los tests
  importan con rutas relativas `./x.js`, que el renombrado rompería. `site/` sigue sin
  `package.json`.
- Una capa que el índice no lista se muestra como «sin trazados de esta capa en el municipio»,
  igual que una capa vacía: #84 no publica capas vacías, así que la ausencia en el índice es el
  caso real de capa vacía.
- `indice.json` ya lo genera #84 (ADR 0036); esta historia no toca Python de producción.

## Disparadores para migrar a MapLibre GL

Se reescribe solo `mapa.js` (y se añaden teselas vectoriales) cuando ocurra cualquiera de:

- el volumen obliga a teselas vectoriales (`.pmtiles`): el GeoJSON que hay que descargar para una
  pantalla pasa de unas decenas de MB, o el navegador se resiente al dibujar las capas de un
  municipio en un móvil medio;
- hacen falta estilos dependientes del zoom, rotación o inclinación del mapa;
- Leaflet 1.x deja de recibir correcciones de seguridad (revisar cuando la 2.0 sea estable).

## Coste de funcionamiento

Cero: ficheros estáticos en GitHub Pages y teselas públicas del IGN. Sin backend, sin claves, sin
almacenamiento propio.

## Consecuencias

- La atribución del PNOA lleva el año del vuelo (2023). Cuando el IGN publique un vuelo nuevo
  sobre Madrid (la tabla del SCNE ya lista uno de 2024), el test de integración que compara el año
  servido con el atribuido fallará y habrá que actualizar `NOTICE`, `REGISTRY.md` y `config.js`
  juntos.
- Cambiar de librería no toca `index.html`, `controlador.js`, `config.js` ni los datos.
- Los ES modules exigen servir el sitio por HTTP (Pages lo hace; en local, `python3 -m http.server`).
- El sitio depende de un servicio externo solo para el fondo; si falla, las capas siguen sobre fondo
  neutro.
- Leaflet se actualiza a mano (copiar `dist/`, actualizar versión y sha1 aquí y en `NOTICE`).
- La capa de camino actual de Colmenar pesa ~1 MB; #86 mide el peso total del sitio.
