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
| WFS Buildings | `https://ovc.catastro.meh.es/INSPIRE/wfsBU.aspx` | `confirmado` (cerrado en la historia 0002). `GetFeature` real con `typenames=bu:Building` y bbox pequeño (±100-200 m) centrado en un centroide de `Consulta_CPMRC`: funciona igual que `CadastralParcel` (fixture `wfsBU_colmenar_dense_bbox.xml`, edificios reales con geometría, superficie `officialArea` y rango de fecha de construcción). **Detalle no documentado en `GetCapabilities`:** aunque se pide `typenames=bu:Building`, el elemento devuelto en la respuesta real usa el prefijo `bu-ext2d:Building` (espacio de nombres `bu-ext2d`, no `bu`) — el parsing debe buscar por nombre local del elemento (`Building`), no asumir el prefijo de la petición. |
| REST `Consulta_DNPPP` (datos no protegidos por polígono/parcela rústica) | `http://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCCallejero.asmx/Consulta_DNPPP` | `confirmado`. Petición real `Provincia=MADRID&Municipio=COLMENAR DE OREJA&Poligono=1&Parcela=1` → fixture `dnppp_colmenar_pol1_parc1.xml`. Devuelve referencia catastral completa (`REFCAT-RETIRADA`), paraje (`CANTERAS`), uso (`Agrario`) y clase (`LABOR O LABRADÍO SECANO`). Confirma además el código de municipio Catastro para Colmenar de Oreja: `28043`. |
| REST `Consulta_CPMRC` (coordenadas por municipio + referencia catastral) | `http://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCCoordenadas.asmx/Consulta_CPMRC` | **Bloqueado** (`asumido`, no `confirmado`). Probado con la referencia rústica de 20 caracteres obtenida arriba → error `"LA REFERENCIA CATASTRAL DEBE SER DE 14 POSICIONES"` (fixture `cpmrc_colmenar.xml`). Este servicio solo acepta el formato compacto urbano de 14 caracteres, no el formato rústico completo polígono/parcela de 20. |

**Hallazgo pendiente — RESUELTO en la historia 0002 (2026-10-15):** ninguno de los mecanismos de filtrado por atributo que expone este WFS funciona. Se probaron los tres candidatos anotados tras la historia 0001:

- **(a) `resourceId=ES.SDGC.CP.<localId>` con el `localId` INSPIRE de 14 caracteres** (confirmado por deducción: `pc1(7)+pc2(7)` sin `car`+checksum — p. ej. para `REFCAT-RETIRADA` → `REFCAT-RETIRADA`). **No funciona**: sin bbox, el servicio ignora `resourceId` y devuelve un conjunto por defecto de 83 features ajeno a la petición (fixture `wfsCP_getfeature_by_resourceid.xml`, idéntico byte a byte al intento fallido de `CQL_FILTER` sin bbox de la historia 0001).
- **(b) `Filter` OGC estándar vía POST** en vez de `CQL_FILTER` por GET. **No funciona**: el servicio anuncia soporte POST en `GetCapabilities`, pero ignora por completo el cuerpo XML de la petición — con `REQUEST` solo en el cuerpo devuelve `"The parameter REQUEST can't be null"`; añadiéndolo también en la query string, devuelve `"At least one of the parameters TYPENAMES and RESOURCEID must be present in KVP-encoded Ad hoc queries"`, es decir, procesa la petición como KVP (GET) e ignora el body POST entero (fixture `wfsCP_getfeature_post_filter2.xml`).
- **(c, variante real) Combinar el servicio REST de coordenadas con una búsqueda espacial de radio pequeño** — **confirmado como el método correcto, mejor que lo anticipado por la historia 0001.** Cadena verificada con evidencia real, para dos parcelas rústicas de los dos municipios del MVP más una tercera parcela adicional:
  1. **Normalizar** cualquier referencia catastral a su forma compacta de 14 caracteres: `pc1(7) + pc2(7)`, descartando `car` (4) y el checksum (2) del formato completo de 20. Para `REFCAT-RETIRADA` → `REFCAT-RETIRADA`.
  2. **`Consulta_CPMRC`** (`http://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCCoordenadas.asmx/Consulta_CPMRC?Provincia=<provincia>&Municipio=<municipio>&RC=<refcat-14-caracteres>&SRS=EPSG:25830`) con la referencia de 14 caracteres (no la de 20 — con 20 caracteres este mismo servicio falla con `"LA REFERENCIA CATASTRAL DEBE SER DE 14 POSICIONES"`, fixture `cpmrc_colmenar.xml`) **sí devuelve un centroide real** en el `SRS` pedido. Confirmado para:
     - Colmenar de Oreja, Polígono 1 Parcela 1 (`REFCAT-RETIRADA`) → `xcen=467588.74, ycen=4442023.74` (fixture `cpmrc_colmenar_14char.xml`).
     - Villaconejos, Polígono 1 Parcela 1 (`REFCAT-RETIRADA`) → `xcen=454720.29, ycen=4441476.87` (fixture `cpmrc_villaconejos_14char.xml`).
     - Colmenar de Oreja, parcela adicional del núcleo urbano (`REFCAT-RETIRADA`) → `xcen=456886.92, ycen=4436932.98` (fixture `cpmrc_colmenar_urbano_14char.xml`).
  3. **`GetFeature` del WFS con un bbox pequeño** (±100-200 m) centrado en ese centroide, en `EPSG:25830`, devuelve un puñado de parcelas (no las 600+ de un bbox mayor); la parcela buscada está entre ellas y se identifica del lado del cliente comparando `nationalCadastralReference` con la referencia de 14 caracteres. Confirmado exacto para las dos rústicas: `REFCAT-RETIRADA` aparece como primer resultado (área 901 m², fixture `wfsCP_colmenar_rustica_por_centroide.xml`) y `REFCAT-RETIRADA` aparece en el resultado de Villaconejos (fixture `wfsCP_villaconejos_rustica_por_centroide.xml`).
  4. **Nota de rendimiento:** el servicio limita cada `GetFeature` a un área máxima de, aproximadamente, 1 km² por petición (bboxes de 1200m×1200m devuelven `"Area of extension out of limits"`; 1000m×1000m funciona) — irrelevante para este método porque el bbox final es pequeño por diseño (centrado en un centroide ya conocido), pero documentado porque descarta cualquier estrategia que dependa de bboxes grandes.
  5. **Conclusión operativa para el adapter (historia 0002, Bloque 3):** el cliente de Catastro debe implementarse como dos llamadas encadenadas — `Consulta_CPMRC` (centroide) seguido de `GetFeature` con bbox pequeño (match por referencia) — nunca como un único `GetFeature` filtrado, porque el filtrado por atributo no existe en este servicio.

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

Re-verificado el 2026-10-15 **en detalle** para la historia 0008 (ingesta diaria con filtro por texto) — la pasada original de la historia 0001 solo confirmó que el endpoint responde; esta pasada inspecciona el esquema exacto del JSON (necesario antes de fijar cualquier `TypedDict` de parsing, siguiendo la lección registrada tras la historia 0001) y hace peticiones reales nuevas para los casos de error.

- **Protocolo:** REST/JSON (API de datos abiertos, sumario diario).
- **Autenticación:** ninguna.
- **Cabecera obligatoria:** `Accept: application/json`. **Hallazgo nuevo:** sin esta cabecera (p. ej. con el `Accept: */*` por defecto de `curl`), el servicio responde `400 Bad Request` con cuerpo XML (`"No soportado ningún mime type de la cabecera Accept."`) **incluso para un día con sumario real** — no es un detalle opcional de negociación de contenido, es un requisito duro para obtener JSON en absoluto. No documentado en ningún `GetCapabilities` ni autodescripción; solo se descubrió con la petición real.
- **Formato de respuesta:** JSON en el caso de éxito (`200`, con la cabecera anterior). **XML en todos los casos de error** (`400`, `404`), igual con `Accept: application/json` puesto — el servicio ignora el `Accept` pedido al fallar y siempre devuelve XML de error. Un cliente que solo intente `json.loads` en cualquier respuesta sin mirar antes el código de estado HTTP fallaría al parsear el cuerpo de un día sin sumario.
- **CRS:** no aplica (fuente no geoespacial).
- **Licencia:** no verificada explícitamente en esta pasada (`asumido`).
- **Estado:** `confirmado` para la obtención del sumario diario (esquema exacto incluido) y para los códigos de error de "sin sumario"/"fecha inválida"; `asumido` para el filtrado por municipio (sigue sin existir ningún parámetro server-side).

**Endpoint y casos de estado, todos verificados con petición real (2026-10-15):**

| Caso | Petición | Resultado real |
| --- | --- | --- |
| Día con sumario | `GET /datosabiertos/api/boe/sumario/20261015` con `Accept: application/json` | `200 OK`, `Content-Type: application/json`, cuerpo JSON completo → fixture ya existente `sumario_hoy.json` (247 KB). |
| Día sin sumario (fin de semana: domingo 2026-10-11) | igual, con `Accept: application/json` | `404 Not Found`, `Content-Type: application/xml`, cuerpo `<response><status><code>404</code><text>La información solicitada no existe</text></status><data/></response>`. |
| Día futuro sin sumario publicado todavía (2027-12-31) | igual | `404 Not Found`, mismo cuerpo XML que el caso anterior — el servicio no distingue "fin de semana/festivo" de "fecha futura": ambos son el mismo código y el mismo mensaje. Un solo tipo de error basta para los dos. |
| Fecha con formato de calendario inválido (`20261332`, día/mes fuera de rango) enviada tal cual al servidor | igual | `400 Bad Request`, `Content-Type: application/xml`, cuerpo `<response><status><code>400</code><text>El parámetro fecha no cumple el formato.</text></status><data/></response>` — confirma que el servidor también valida, pero el AC de la historia exige que el cliente nunca llegue a mandar esta petición (validación de formato antes de red). |

**Esquema exacto del sumario (confirmado inspeccionando `sumario_hoy.json` campo a campo, no solo "se abre y tiene secciones"):**

```
data.sumario.metadatos.publicacion        = "BOE"
data.sumario.metadatos.fecha_publicacion  = "20261015"
data.sumario.diario[0].numero             = "256"
data.sumario.diario[0].sumario_diario.identificador     = "BOE-S-2026-256"
data.sumario.diario[0].sumario_diario.url_pdf.texto     = URL del PDF del sumario completo
data.sumario.diario[0].seccion            = lista de 7 secciones el 2026-10-15 (p. ej. "1"/"I. Disposiciones generales", "3"/"III. Otras disposiciones", "5A"/"V. Anuncios. - A. Contratación del Sector Público"...)
  seccion[i].codigo, seccion[i].nombre
  seccion[i].departamento                 = lista de departamentos... o UN SOLO DICCIONARIO si solo hay un departamento esa sección ese día (confirmado real: la sección "5C" del 2026-10-15 trae `departamento` como dict, no como lista de 1 elemento)
    departamento[j].codigo, departamento[j].nombre
    departamento[j].epigrafe              = lista de epígrafes, O un solo dict si hay uno solo, O AUSENTE del todo
    departamento[j].item                  = disposiciones directamente bajo el departamento, SIN epígrafe intermedio — confirmado real en la mayoría de ministerios el 2026-10-15 (18 de los casos reales de la fixture no tienen "epigrafe", solo "item" directo bajo "departamento")
    departamento[j].texto.item            = **CUARTA variante, no detectada en la pasada anterior de este registro**: en la sección "5C" (Anuncios particulares) del `20261015`, el departamento "ANUNCIOS PARTICULARES" no trae `item` ni `epigrafe` directamente, sino un objeto `texto` que a su vez contiene `item` (lista). Encontrado al implementar la historia 0008 comparando el recuento real de disposiciones (166) contra el recuento que daban solo las tres variantes documentadas aquí hasta ahora (menos de 166) — el recorrido de parsing debe comprobar también `departamento.texto.item`, no solo `departamento.item` y `departamento.epigrafe[].item`.
      epigrafe[k].nombre
      epigrafe[k].item                    = lista de disposiciones, O un solo dict si hay una sola (confirmado real: epígrafe "Autos" trae varias; otros epígrafes de un solo ítem traen dict)
        item.identificador   = p. ej. "BOE-A-2026-21445" (disposiciones) o "BOE-B-..." (anuncios, confirmado en secciones de Anuncios)
        item.titulo          = título completo de la disposición
        item.control          = presente en algunos ítems, ausente en otros (confirmado: 80 con, sin sobre el resto de los 166 ítems reales del día, cifra corregida tras encontrar la cuarta variante de anidamiento — ver nota abajo) — campo opcional, no fiable como requerido
        item.url_pdf.texto   = URL del PDF de la disposición individual
        item.url_html        = URL de la versión HTML
        item.url_xml         = URL de la versión XML
```

**Hallazgo crítico para el parsing (no un detalle menor):** el JSON de BOE viene de una conversión XML→JSON que colapsa cualquier elemento repetible a un `dict` suelto (no a una lista de un elemento) cuando solo aparece una vez ese día, en al menos tres niveles distintos de anidamiento (`departamento`, `epigrafe`, `item`) — y además `epigrafe` puede estar completamente ausente cuando las disposiciones cuelgan directamente de `departamento`, o sustituido por un `texto.item` intermedio (cuarta variante, ver arriba). Cualquier parsing que asuma siempre `list` en estos campos fallará con `AttributeError`/`TypeError` en un día real cualquiera, no solo en un caso de borde teórico: el propio día de verificación (`20261015`) ya ejercita las **cuatro** variantes a la vez. Un recuento que solo cubra tres de las cuatro variantes (como ocurrió en la primera pasada de esta historia, antes de encontrar `departamento.texto.item`) pierde disposiciones reales completas — en ese caso, toda la sección de Anuncios particulares — sin ningún error visible — la lista resultante simplemente queda incompleta en silencio. Recuento final verificado tras cubrir las cuatro variantes: **166** disposiciones reales ese día (no 164, cifra provisional de una pasada anterior de este mismo registro antes de encontrar la cuarta variante).

**Verificación real del filtro por texto sobre el sumario del `20261015` (166 disposiciones reales en total, tras recorrer las cuatro variantes de anidamiento anteriores):** búsqueda insensible a mayúsculas/tildes de `"colmenar"` → **0 coincidencias**; `"villaconejos"` → **0 coincidencias** (ninguna disposición de ese día menciona ninguno de los dos municipios del MVP en el título, resultado real, no forzado); `"madrid"` → **14 coincidencias** (término genérico real que sí aparece, útil como caso de prueba "sí hay coincidencias" sin depender de que los municipios del MVP aparezcan por casualidad).

**Filtrado por municipio:** sigue sin existir ningún parámetro server-side de búsqueda por municipio o texto libre (confirmado, no solo asumido: no hay ningún parámetro de query documentado ni descubierto en esta pasada) — hace falta descargar el sumario diario completo y filtrar client-side sobre el título de cada disposición. Mirar el PDF del cuerpo cuando el título no basta queda fuera de alcance de la historia 0008 (ver ADR 0008): es una decisión a tomar solo si aparece evidencia real de falso negativo, no por adelantado.

---

## BOCM

Re-verificado en profundidad el 2026-10-15 para la historia 0009 (la pasada original de la historia 0001 solo confirmaba que los dos endpoints RSS respondían, sin esquema exacto) — ver [ADR 0009](../../../docs/adr/0009-cliente-bocm-reutiliza-bulletinnotice-xml-por-disposicion-sin-pdf.md). **Dos afirmaciones de la pasada anterior resultaron incorrectas, no solo incompletas**, corregidas aquí con petición real: (1) `sumarios.rss` no es "el boletín del día sin fecha", es una ventana rodante de los últimos 20 boletines con fecha real por entrada; (2) el texto completo y el título real de cada disposición **no** están solo en el PDF — existe un XML estructurado hermano del PDF, público y sin autenticación.

- **Protocolo:** RSS 2.0 para el índice (`sumarios.rss`, `boletines.rss`) + XML propio (`<documento>`) por disposición individual, descubierto como hermano del PDF, no enlazado desde el RSS.
- **Autenticación:** ninguna, en ningún endpoint.
- **Formato de respuesta:** RSS/XML para los índices; XML (`Content-Type: text/xml;charset=UTF-8`) para cada disposición.
- **CRS:** no aplica.
- **Licencia:** no verificada explícitamente (`asumido`).
- **Estado:** `confirmado`.

**Endpoints verificados:**

| Endpoint | URL | Verificación |
| --- | --- | --- |
| RSS de sumarios | `https://www.bocm.es/sumarios.rss` | `confirmado`. Petición real → fixture `sumarios.rss`. **20 `<item>`**, uno por boletín (no por disposición): `<title>` ("Boletín Nº 246 del 15 Octubre 2026"), `<link>` (a `boletin-completo/BOCM-{AAAAMMDD}/{numero}`), `<pubDate>` **ISO 8601 sin huso horario** (`2026-10-15T00:00:00` — no RFC 822 pese a que el RSS 2.0 lo exige; usar `datetime.fromisoformat`, no `email.utils.parsedate`), `<guid>`, `dc:creator`. El `<pubDate>` coincide exactamente con la fecha nominal del boletín y tiene huecos reales en los días sin publicación (fines de semana: 11 y 4 de octubre, 27 de septiembre de 2026, todos domingos, ausentes de los 20 `<item>`). El `<description>` de cada `<item>` es HTML escapado con el listado de disposiciones de ese boletín: solo trae identificador (`BOCM-20261015-1`, ...) + enlace a PDF/EPUB — **nunca un título descriptivo**. |
| RSS de boletines | `https://www.bocm.es/boletines.rss` | `confirmado`. Petición real → fixture `boletines.rss`. También 20 `<item>`, pero estructura distinta: `<title>` = "BOCM - Nº 246" (sin fecha), `<pubDate>` **RFC 822 real** pero es la fecha de creación del nodo en el CMS, no la fecha nominal del boletín (verificado real: el boletín "Nº 246", nominalmente del 15 de octubre, tiene aquí `pubDate` del **14** de octubre a las 11:54 — desajuste de un día real, no teórico), `<guid>` con formato `"965320 at https://www.bocm.es"` (ID de nodo Drupal, no URL). **No se usa para resolver "día → boletín" por este desajuste de fecha** — `sumarios.rss` es la fuente elegida para eso. |
| XML de una disposición individual | `https://www.bocm.es/boletin/CM_Orden_BOCM/{AAAA}/{MM}/{DD}/BOCM-{AAAAMMDD}-{n}.xml` (misma ruta que el PDF, solo cambia la extensión — confirmado mediante el `encoding` JSON-LD de la página HTML de la disposición, que lista HTML/XML/PDF/EPUB como representaciones del mismo recurso) | `confirmado`. Petición real a `BOCM-20261015-1.xml` → `200 OK`. Esquema: `<documento><metadatos>` con `identificador`, `origen_legislativo`, `departamento`, `rango` (p. ej. "ORDEN"), `fecha_publicacion`, `fecha_disposicion`, `titulo` (**texto completo real**, no truncado), `diario`, `diario_numero`, `seccion` (código romano + nombre en una sola cadena, p. ej. `"I.  COMUNIDAD DE MADRID"`, `"III. ADMINISTRACIÓN LOCAL AYUNTAMIENTOS"`), `url_html`/`url_xml`/`url_json_ld`/`url_pdf`/`url_epub`; `<analisis>` con `seccion`/`apartado`/`organismo`/`tipo_disposicion`; `<texto>` con el cuerpo íntegro. **Verificado real sobre las 80 disposiciones reales del boletín Nº 246 (15 de octubre de 2026), descubiertas vía el `<description>` de `sumarios.rss`: 80/80 peticiones exitosas, 0 errores de red o de parsing.** |

**Recuento real de disposiciones del día de verificación:** **80** (boletín Nº 246, 15 de octubre de 2026), extraídas del `<description>` de `sumarios.rss` por regex sobre el patrón `<a href="/{slug}">BOCM-{día}-{n}</a>` + enlace a PDF, confirmado 80/80 sin pérdidas.

**Verificación real del filtro por texto sobre el `<titulo>` real (no el identificador) de las 80 disposiciones del `20261015`:** búsqueda insensible a mayúsculas/tildes de `"colmenar"` → **1 coincidencia real** (`BOCM-20261015-32`: "Convenio de colaboración... entre la Agencia de Ciberseguridad de la Comunidad de Madrid y el Ayuntamiento de Colmenar de Oreja..." — es el municipio del MVP, no un falso positivo de otro "Colmenar"); `"villaconejos"` → **0 coincidencias**; `"madrid"` → **38 coincidencias** (término genérico real, confirma el camino "sí hay resultados"). A diferencia de BOE (0/0 el mismo día), BOCM sí produjo una coincidencia real para uno de los dos municipios del MVP.

**Filtrado por municipio:** igual que BOE, no hay ningún parámetro server-side de búsqueda — hace falta descargar el índice del día y, por cada disposición, su XML, y filtrar client-side sobre `<titulo>`. **El parsing de PDF no hace falta en ningún caso**: queda descartado, no diferido — confirmado real que el XML hermano del PDF (mismo path, solo cambia la extensión) ya trae título completo y texto íntegro sin tocar el PDF. Esto corrige explícitamente la nota de la pasada anterior de este mismo registro ("el texto completo de cada disposición solo está en PDF"), que era incorrecta.

---

## Sentinel-2 L2A

Verificado el 2026-10-15, **fuera de la pasada original de la historia 0001** (no estaba en su alcance) — añadido justo antes de la historia 0007 (cliente de Sentinel-2), siguiendo la lección registrada de nunca construir un cliente sobre un endpoint sin petición real.

- **Protocolo:** STAC API (búsqueda `POST /search`) + descarga directa de bandas como GeoTIFF en la nube optimizado (COG) vía HTTPS.
- **Autenticación:** ninguna.
- **Formato de respuesta:** JSON (STAC Item/FeatureCollection) para la búsqueda; `image/tiff; application=geotiff; profile=cloud-optimized` para las bandas.
- **CRS:** cada escena viene en su propio huso UTM (p. ej. `EPSG:32630` para el huso 30N que cubre Madrid) — **no** en EPSG:25830 nativo; el adapter tendrá que reproyectar o al menos registrar el CRS real devuelto, no asumir 25830.
- **Licencia:** no verificada explícitamente en esta pasada (`asumido`); datos Copernicus/Sentinel son de acceso abierto por política de la UE, pero falta la cita textual exacta.
- **Estado:** `confirmado`.

| Endpoint | URL | Verificación |
| --- | --- | --- |
| Catálogo STAC (Earth Search, Element84, AWS) | `https://earth-search.aws.element84.com/v1` | `confirmado`. Raíz del catálogo → fixture `stac_root.json`. Colección `sentinel-2-l2a` confirmada en `/collections` entre varias otras (`sentinel-2-l1c`, `landsat-c2-l2`, etc.). |
| Búsqueda STAC | `https://earth-search.aws.element84.com/v1/search` (POST, body JSON con `collections`, `bbox`, `datetime`, `limit`) | `confirmado`. Búsqueda real sobre bbox de Colmenar de Oreja (`[-3.40, 40.09, -3.37, 40.12]`), rango `2026-09-01/2026-10-15` → fixture `stac_search_colmenar.json`. Devuelve 3 escenas reales, la más reciente `S2B_30TVK_20261014_0_L2A` (14 de octubre de 2026, **un día antes de esta verificación** — confirma que el catálogo está al día), con `eo:cloud_cover` ≈ 0.17%. |
| Banda roja (B04) y NIR (B08), como asset COG | `https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/<path-por-escena>/B04.tif` / `.../B08.tif` (URL exacta viene en `assets.red.href` / `assets.nir.href` de cada item STAC) | `confirmado`. `HEAD` real contra el `B04.tif` de la escena anterior → `200 OK`, bucket S3 público (`sentinel-cogs`), sin credenciales. `Accept-Ranges: bytes` confirmado — permite lectura por ventana (recortar solo el entorno de la parcela) sin descargar el GeoTIFF completo, relevante para el adapter de NDVI que construirá la historia 0007. |

**Nota para la historia 0007 (cliente de Sentinel-2):** el NDVI se calcula como `(NIR - RED) / (NIR + RED)` a partir de las bandas `nir` (B08, 10 m) y `red` (B04, 10 m) del mismo item STAC — ambas confirmadas disponibles aquí. La búsqueda por fecha/bbox funciona vía POST con cuerpo JSON (no vía querystring GET), a diferencia de los demás servicios REST ya verificados en este registro.

---

## Resumen de fuentes no verificadas en esta pasada

Fuera de alcance de la historia 0001 (ver sección "Fuera de alcance" de `docs/stories/0001-registro-fuentes.md`): SNCZI/dominio público hidráulico, vías pecuarias, Red Natura 2000, concesiones de agua, inventario municipal de caminos. Quedan para una iteración posterior del registro, cuando las historias de reglas/afecciones las necesiten.
