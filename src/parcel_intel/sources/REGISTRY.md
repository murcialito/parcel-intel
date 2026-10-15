# Registro de fuentes

Verificado el 2026-10-15 contra servicios reales (no documentación de terceros). Cada ejemplo de petición/respuesta real está guardado en `tests/fixtures/<fuente>/`. Ver [ADR 0001](../../../docs/adr/0001-sources-es-documentacion-no-capa-de-codigo.md): este archivo es el único contenido permitido en `sources/` — ningún cliente se implementa aquí, solo en `adapters/<proveedor>/`.

Municipios de referencia usados para verificar: Colmenar de Oreja (código Catastro/IDEM: `28043` / `043`) y Villaconejos (código IDEM: `170`), ambos en la Comunidad de Madrid.

---

## Catastro (INSPIRE)

- **Protocolo:** WFS 2.0.0 (geometría) + servicio REST propio de Catastro (consulta no espacial por polígono/parcela).
- **Autenticación:** ninguna.
- **Formato de respuesta:** GML 3.2 / XML (WFS); XML propio (REST).
- **CRS nativo:** parcelas (`cp:CadastralParcel`) — DefaultCRS `EPSG:4326`, pero acepta y devuelve correctamente `EPSG:25830` si se pide explícito vía `srsname` + bbox en esa proyección. Edificios (`bu:Building`, `bu:BuildingPart`, `bu:OtherConstruction`) — DefaultCRS ya es `EPSG:25830` nativo.
- **Licencia:** "No conditions apply" (WFS INSPIRE), documentación de licencia en `https://www.catastro.hacienda.gob.es/webinspire/documentos/Licencia_en.pdf`.
- **Estado:** `confirmado` (parcial — ver hallazgo pendiente abajo).

**Endpoints verificados:**

| Endpoint | URL base | Verificación |
| --- | --- | --- |
| WFS Cadastral Parcels | `https://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx` | `confirmado`. `GetCapabilities` → fixture `wfsCP_getcapabilities.xml`. `GetFeature` con bbox real en EPSG:25830 sobre Colmenar de Oreja → fixture `wfsCP_getfeature_colmenar_bbox.xml`, devuelve parcela real (`nationalCadastralReference=REFCAT-RETIRADA`) con geometría GML en EPSG:25830. |
| WFS Buildings | `https://ovc.catastro.meh.es/INSPIRE/wfsBU.aspx` | `confirmado` solo para `GetCapabilities` (fixture `wfsBU_getcapabilities.xml`, confirma feature types y CRS nativo 25830). **No se hizo un `GetFeature` real sobre edificios en esta pasada** — queda `asumido` que funciona igual que `CadastralParcel`; verificar en la historia 0002. |
| REST `Consulta_DNPPP` (datos no protegidos por polígono/parcela rústica) | `http://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCCallejero.asmx/Consulta_DNPPP` | `confirmado`. Petición real `Provincia=MADRID&Municipio=COLMENAR DE OREJA&Poligono=1&Parcela=1` → fixture `dnppp_colmenar_pol1_parc1.xml`. Devuelve referencia catastral completa (`REFCAT-RETIRADA`), paraje (`CANTERAS`), uso (`Agrario`) y clase (`LABOR O LABRADÍO SECANO`). Confirma además el código de municipio Catastro para Colmenar de Oreja: `28043`. |
| REST `Consulta_CPMRC` (coordenadas por municipio + referencia catastral) | `http://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCCoordenadas.asmx/Consulta_CPMRC` | **Bloqueado** (`asumido`, no `confirmado`). Probado con la referencia rústica de 20 caracteres obtenida arriba → error `"LA REFERENCIA CATASTRAL DEBE SER DE 14 POSICIONES"` (fixture `cpmrc_colmenar.xml`). Este servicio solo acepta el formato compacto urbano de 14 caracteres, no el formato rústico completo polígono/parcela de 20. |

**Hallazgo pendiente (bloqueante para la historia 0002):** no se encontró, en esta pasada, un método que resuelva de forma fiable "referencia catastral rústica (20 caracteres) → geometría exacta de esa parcela". Se probó filtrar `GetFeature` de `wfsCP.aspx` con `CQL_FILTER=nationalCadastralReference='REFCAT-RETIRADA'`: el filtro **no se aplicó** — el servicio devolvió 83 resultados no filtrados y en `EPSG:4326` por defecto, ignorando también el `srsname` pedido (fixture `wfsCP_getfeature_by_refcat.xml`). La vía que sí funcionó (bbox espacial) no parte de una referencia catastral, sino de coordenadas ya conocidas. Candidatos a investigar en la historia 0002: (a) `GetFeature` con `resourceId=ES.SDGC.CP.<localId>` usando el `gml:id`/`inspireId.localId` INSPIRE, cuyo formato de 14 caracteres no coincide trivialmente con la referencia rústica de 20 caracteres y requiere mapeo; (b) `Filter` OGC estándar vía POST en vez de `CQL_FILTER` (que es sintaxis GeoServer, no garantizada por este servicio); (c) usar el dato de superficie/parcela del REST `Consulta_DNPPP` junto con una búsqueda espacial aproximada.

---

## IDEM — Comunidad de Madrid (planeamiento urbanístico)

- **Protocolo:** WMS 1.3.0 y WFS 2.0.0 sobre el mismo servicio.
- **Autenticación:** ninguna.
- **Formato de respuesta:** `GetFeatureInfo` → texto plano clave=valor; WFS `GetFeature` → GML 3.2.
- **CRS nativo:** `EPSG:25830` (coincide exactamente con el CRS de almacenamiento del proyecto, sin reproyección). También acepta `EPSG:4326`, pero en WMS 1.3.0 el orden de ejes del bbox es `lat,lon` (no `lon,lat`) — fuente de errores si no se tiene en cuenta.
- **Licencia:** no verificada explícitamente en esta pasada (`asumido`); el nombre del portal (IDEM, Infraestructura de Datos Espaciales de Madrid) sugiere datos abiertos, pero falta confirmar el texto de licencia exacto.
- **Estado:** `confirmado`.
- **Cobertura de Colmenar de Oreja y Villaconejos:** **confirmada explícitamente**, con dato real, no supuesto.

**Endpoints verificados:**

| Endpoint | URL base | Verificación |
| --- | --- | --- |
| WMS (servicio "UsoDelSuelo", nombre que **no** refleja su contenido completo — incluye las capas de planeamiento `VPLA_*`, no solo uso de suelo medioambiental) | `https://idem.comunidad.madrid/geoidem/UsoDelSuelo/wms` | `confirmado`. `GetCapabilities` → fixture `wms_usodelsuelo_getcapabilities.xml`. Capa relevante: `VPLA_V_CLASIFICACION_REF_25` ("Clasificación del suelo en Planeamiento Urbanístico Refundido 2025", fecha de referencia 31/12/2025). `GetFeatureInfo` real sobre el centro de Colmenar de Oreja → fixture `getfeatureinfo_colmenar_real.txt`, devuelve `CD_MUNICIPIO=043`, `DS_MUNICIPIO=COLMENAR DE OREJA`, `DS_CLASIF_GEN=Suelo Urbano`. Mismo resultado sobre Villaconejos → fixture `getfeatureinfo_villaconejos_real.txt`, `CD_MUNICIPIO=170`, `DS_MUNICIPIO=VILLACONEJOS`. |
| WFS (mismo servicio, vectorial) | `https://idem.comunidad.madrid/geoidem/UsoDelSuelo/wfs` | `confirmado`. `GetCapabilities` → fixture `wfs_usodelsuelo_getcapabilities.xml`, confirma `DefaultCRS=EPSG:25830` nativo para `VPLA_V_CLASIFICACION_REF_25`. `GetFeature` con `CQL_FILTER=DS_MUNICIPIO='COLMENAR DE OREJA'` → fixture `wfs_getfeature_colmenar_clasificacion.xml`: **el filtro sí se aplicó correctamente** (52 polígonos de clasificación de suelo para el municipio, geometría GML real en EPSG:25830) — a diferencia de Catastro, donde el mismo tipo de filtro no funcionó. |

**Nota para la historia de cliente de planeamiento:** existen múltiples capas de clasificación versionadas (`VPLA_V_CLASIFICACION`, `..._MODIF`, `..._REF_19`, `..._REF_23`, `..._REF_25`); `VPLA_V_CLASIFICACION_REF_25` es la más reciente (datos a 31/12/2025) y la que debe usarse por defecto.

---

## PNOA — ortofoto actual e histórica (IGN/CNIG)

- **Protocolo:** WMS 1.3.0 (dos servicios separados: actual e histórico).
- **Autenticación:** ninguna.
- **Formato de respuesta:** `image/jpeg` (GetMap); XML (GetCapabilities).
- **CRS nativo:** `EPSG:25830` entre los CRS soportados (ambos servicios).
- **Licencia:** no verificada explícitamente con cita textual en esta pasada (`asumido` CC-BY 4.0 / licencia IGN estándar, pendiente confirmar enlace exacto).
- **Estado:** `confirmado`.

**Endpoints verificados:**

| Endpoint | URL base | Verificación |
| --- | --- | --- |
| WMS actual | `https://www.ign.es/wms-inspire/pnoa-ma` | `confirmado`. `GetCapabilities` → fixture `wms_pnoa_actual_getcapabilities.xml`. Capa: `OI.OrthoimageCoverage`. `GetMap` real sobre Colmenar de Oreja (bbox EPSG:25830) → fixture `getmap_colmenar_actual.jpg`, imagen JPEG 512×512 real recibida. |
| WMS histórico | `https://www.ign.es/wms/pnoa-historico` | `confirmado`. `GetCapabilities` → fixture `wms_pnoa_historico_getcapabilities.xml`. Capas anuales `PNOA2004` a `PNOA2024`, más vuelos anteriores (`AMS_1956-1957`, `Interministerial_1973-1986`, `Nacional_1981-1986`). `GetMap` real con capa `PNOA2004` sobre el mismo bbox de Colmenar de Oreja → fixture `getmap_colmenar_2004.jpg`, imagen JPEG real recibida. |

**Implicación para el módulo de datación:** la serie histórica real empieza en 1956 y tiene cobertura anual completa desde 2004 — mejor granularidad de la que asumía `docs/vision.md` ("~cada pocos años").

---

## BOE

- **Protocolo:** REST/JSON (API de datos abiertos, sumario diario).
- **Autenticación:** ninguna (al menos para esta consulta puntual).
- **Formato de respuesta:** JSON.
- **CRS:** no aplica (fuente no geoespacial).
- **Licencia:** no verificada explícitamente en esta pasada (`asumido`).
- **Estado:** `confirmado` para la obtención del sumario diario; `asumido` para el filtrado por municipio.

**Endpoint verificado:**

| Endpoint | URL | Verificación |
| --- | --- | --- |
| Sumario diario | `https://boe.es/datosabiertos/api/boe/sumario/{AAAAMMDD}` | `confirmado`. Petición real para `20261015` → fixture `sumario_hoy.json` (JSON completo, 247 KB, incluye secciones, enlaces a PDF de cada disposición). |

**Filtrado por municipio:** no se encontró ningún parámetro server-side de búsqueda por municipio o texto libre en esta pasada — `asumido` que hace falta descargar el sumario diario completo y filtrar client-side sobre el texto de cada entrada (título o, si no basta, el PDF de la disposición). Pendiente revisar si `https://www.boe.es/datosabiertos` documenta un endpoint de búsqueda aparte del sumario diario.

---

## BOCM

- **Protocolo:** RSS 2.0 (sumario + listado de boletines). **No existe una vía estructurada (API/JSON) más allá del RSS** — confirmado, no asumido: se buscó explícitamente y no se encontró.
- **Autenticación:** ninguna.
- **Formato de respuesta:** RSS/XML; cada ítem enlaza a un PDF por disposición individual (el texto completo de cada disposición solo está en PDF o en la página HTML de la disposición, no en el RSS).
- **CRS:** no aplica.
- **Licencia:** no verificada explícitamente en esta pasada (`asumido`).
- **Estado:** `confirmado`.

**Endpoints verificados:**

| Endpoint | URL | Verificación |
| --- | --- | --- |
| RSS de sumarios | `https://www.bocm.es/sumarios.rss` | `confirmado`. Petición real → fixture `sumarios.rss`. Devuelve el boletín del día (`Nº 246, 15 octubre 2026`) con enlace a cada disposición individual y su PDF (p. ej. `https://www.bocm.es/boletin/CM_Orden_BOCM/2026/10/15/BOCM-20261015-1.PDF`). |
| RSS de boletines | `https://www.bocm.es/boletines.rss` | `confirmado`. Petición real → fixture `boletines.rss`. Lista los últimos 20 boletines publicados. |

**Filtrado por municipio:** igual que BOE, no hay parámetro server-side — habría que descargar cada PDF/disposición y buscar el municipio en el texto. A diferencia de BOE (JSON estructurado), aquí el contenido real de cada disposición exige parsing de PDF, no solo de XML/JSON — mayor coste de implementación esperado para el pipeline de boletines en Madrid frente a lo que `docs/vision.md` asumía genéricamente para "BORM" en la fase de Murcia.

---

## Resumen de fuentes no verificadas en esta pasada

Fuera de alcance de la historia 0001 (ver sección "Fuera de alcance" de `docs/stories/0001-registro-fuentes.md`): SNCZI/dominio público hidráulico, vías pecuarias, Red Natura 2000, concesiones de agua, inventario municipal de caminos. Quedan para una iteración posterior del registro, cuando las historias de reglas/afecciones las necesiten.
