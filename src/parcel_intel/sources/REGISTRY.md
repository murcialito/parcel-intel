# Registro de fuentes

Verificado el 2026-10-15 contra servicios reales (no documentación de terceros). Cada ejemplo de petición/respuesta real está guardado en `tests/fixtures/<fuente>/`. Ver [ADR 0001](../../../docs/adr/0001-sources-es-documentacion-no-capa-de-codigo.md): este archivo es el único contenido permitido en `sources/` — ningún cliente se implementa aquí, solo en `adapters/<proveedor>/`.

Municipios de referencia usados para verificar: Colmenar de Oreja (código Catastro/IDEM: `28043` / `043`) y Villaconejos (código IDEM: `170`), ambos en la Comunidad de Madrid.

---

## Catastro (INSPIRE)

- **Protocolo:** WFS 2.0.0 (geometría) + servicio REST propio de Catastro (consulta no espacial por polígono/parcela).
- **Autenticación:** ninguna.
- **Formato de respuesta:** GML 3.2 / XML (WFS); XML propio (REST).
- **CRS nativo:** parcelas (`cp:CadastralParcel`) — DefaultCRS `EPSG:4326`, pero acepta y devuelve correctamente `EPSG:25830` si se pide explícito vía `srsname` + bbox en esa proyección. Edificios (`bu:Building`, `bu:BuildingPart`, `bu:OtherConstruction`) — DefaultCRS ya es `EPSG:25830` nativo.
- **Licencia:** licencia propia de Catastro INSPIRE v1.0 (julio 2016), `https://www.catastro.hacienda.gob.es/webinspire/documentos/Licencia.pdf` — **no** es "No conditions apply" (eso es el campo `Fees` del `GetCapabilities`). Prohíbe difundir la información original sin transformarla. Detalle en la sección "Fuentes del primer hito de caminos públicos" (historia 0021).
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

Re-verificado el 2026-10-16 **en detalle** para la historia 0011 (cliente de clasificación de suelo) — la pasada original de la historia 0001 (dejada arriba hasta ahora) solo confirmó que el servicio responde y que `CQL_FILTER` por municipio filtra correctamente; no probó el filtro espacial `BBOX` (el único que el cliente real puede usar, porque conoce una geometría de parcela, no un nombre de municipio completo), no inspeccionó el esquema completo de campos, no probó ningún caso de solape entre clasificaciones y no probó ningún caso de bbox sin cobertura. Mismo patrón de re-verificación ya aplicado a Sentinel-2 (0007), BOE (0008) y BOCM (0009): **esta pasada encontró que la verificación anterior, además de incompleta, dejó grabada una fixture que no coincidía con lo que el propio texto de `REGISTRY.md` afirmaba** (ver hallazgo 0 abajo) — tercera vez en este proyecto que una re-verificación detecta una discrepancia real entre lo escrito y lo grabado, no solo una laguna.

- **Protocolo:** WMS 1.3.0 y WFS 2.0.0 sobre el mismo servicio.
- **Autenticación:** ninguna.
- **Formato de respuesta:** `GetFeatureInfo` → texto plano clave=valor; WFS `GetFeature` → GML 3.2; `DescribeFeatureType` → XML Schema (XSD).
- **CRS nativo:** `EPSG:25830` (coincide exactamente con el CRS de almacenamiento del proyecto, sin reproyección). También acepta `EPSG:4326`, pero en WMS 1.3.0 el orden de ejes del bbox es `lat,lon` (no `lon,lat`) — fuente de errores si no se tiene en cuenta. **Confirmado en esta pasada:** el filtro espacial `BBOX` del WFS 2.0.0 se codifica como KVP plano `bbox=minx,miny,maxx,maxy,EPSG:25830` (GET, sin necesidad de `srsName` aparte) y el servicio responde con la geometría ya en ese mismo CRS — ninguna reproyección necesaria en el cliente.
- **Licencia:** sigue sin verificarse explícitamente (`asumido`); no es objeto de esta historia (ver "Fuera de alcance" de la historia 0011).
- **Estado:** `confirmado`, con el nivel de detalle de BOE/BOCM.
- **Cobertura de Colmenar de Oreja y Villaconejos:** confirmada explícitamente, con dato real.

**Hallazgo 0 — la fixture grabada en la pasada de la historia 0001 (`wfs_getfeature_colmenar_clasificacion.xml`, ya reemplazada) no coincidía con lo que el texto de `REGISTRY.md` afirmaba sobre ella.** El texto decía "52 polígonos reales devueltos"; el archivo grabado tenía `numberMatched="52" numberReturned="1"` y un único `<wfs:member>` — es decir, la prosa describía correctamente la respuesta real del servicio (confirmado repitiendo la misma petición en esta pasada: `CQL_FILTER=DS_MUNICIPIO='COLMENAR DE OREJA'` sin parámetro de paginación devuelve, en efecto, `numberMatched="52" numberReturned="52"`, 52 `<wfs:member>` reales), pero el archivo guardado como evidencia solo conservó 1 de esos 52 — probablemente truncado al grabar la fixture, no un comportamiento real del servicio (se ha comprobado que el servicio no pagina por defecto: no hay límite de `count`/`maxFeatures` implícito). Fixture corregida y sustituida por `wfs_getfeature_cql_colmenar_municipio_completo.xml` (52/52 reales). Esta historia ya no usa `CQL_FILTER` por municipio como método de consulta del cliente (ver hallazgo 3), pero la fixture queda corregida para que `REGISTRY.md` no vuelva a afirmar algo que su propia evidencia grabada contradecía.

**Hallazgo 1 — `GetFeature` con filtro espacial `BBOX` (KVP, sin `CQL_FILTER`) funciona exactamente igual que con Catastro/PNOA: `bbox=minx,miny,maxx,maxy,EPSG:25830`.** Verificado real sobre el bbox de la parcela rústica `REFCAT-RETIRADA` de Colmenar de Oreja (geometría real tomada de la fixture ya existente `tests/fixtures/catastro/wfsCP_colmenar_rustica_por_centroide.xml`, bbox envolvente `(467550.15, 4442011.35, 467614.92, 4442037.4)` + margen de 2 m aplicado a mano con la misma fórmula que `domain.geometry.bbox_with_margin`) → `GET https://idem.comunidad.madrid/geoidem/UsoDelSuelo/wfs?service=WFS&version=2.0.0&request=GetFeature&typenames=VPLA_V_CLASIFICACION_REF_25&bbox=467548.15,4442009.35,467616.92,4442039.4,EPSG:25830` → `200 OK`, `numberMatched="1" numberReturned="1"` → fixture `wfs_getfeature_bbox_colmenar_rustica_margin2m.xml`. Esa parcela cae dentro de un único polígono de clasificación: `DS_CLASIF_GEN=Suelo No Urbanizable Común`.

**Hallazgo 2 — esquema completo de campos del elemento GML, confirmado con `DescribeFeatureType` real (fixture `wfs_describefeaturetype_clasificacion_ref25.xml`) y cruzado contra los campos realmente poblados en 56 features reales distintas (1 de Colmenar + 3 de Villaconejos/Chinchón + 52 del municipio completo de Colmenar).** El elemento `UsoDelSuelo:VPLA_V_CLASIFICACION_REF_25` trae, además de `DS_CLASIF_GEN`/`DS_MUNICIPIO`/`CD_MUNICIPIO` ya conocidos:

| Campo | Tipo (XSD) | Poblado en los 56 features reales observados | Significado confirmado |
| --- | --- | --- | --- |
| `CDID` | `decimal` | Sí, siempre, valor numérico distinto por feature (p. ej. `116387`) | Identificador interno de fila en el sistema IDEM. Sin significado de negocio confirmado más allá de ser un ID. |
| `CD_UNI` | `string` | Sí, siempre (p. ej. `RF_043_58_CLA_0000036`) | Identificador compuesto interno (`RF_<municipio>_<CD_REUR>_CLA_<secuencial>`). **No es un identificador de norma/ordenanza** — es la clave interna de la unidad de clasificación en el sistema IDEM, no una referencia a un instrumento de planeamiento (PGOU, Normas Subsidiarias) con nombre o fecha de aprobación. |
| `CD_MUNICIPIO` / `DS_MUNICIPIO` | `string` | Sí | Ya conocidos. |
| **`FC_REF`** | **`date`** | Sí, siempre, idéntico en todos los features observados del mismo día de consulta (`2025-06-29`) | **Es la fecha de vigencia/referencia del dato de clasificación** — la pregunta explícita del Bloque 1 sobre "fecha de vigencia" tiene aquí su respuesta: sí existe, es un campo de fecha real (no un string libre), y corresponde a cuándo se fijó la versión `REF_25` de la capa (coincide con la fecha de corte 31/12/2025 ya documentada, aunque el valor real observado, `2025-06-29`, es la fecha de la última actualización de ese polígono concreto dentro de esa versión, no la fecha de corte genérica de la capa completa — matiz real, no asumido). |
| `DS_CLASIF_DET` | `string` | Sí, siempre | Clasificación **más granular** que `DS_CLASIF_GEN` (p. ej. `DS_CLASIF_GEN="Suelo No Urbanizable Común"` con `DS_CLASIF_DET="Suelo no urbanizable común"` casi idéntico en unos casos, pero en otros claramente más específico: `DS_CLASIF_GEN="Suelo No Urbanizable Protegido"` con `DS_CLASIF_DET="Suelo No Urbanizable Especialmente Protegido por su valor naturalístico y en defensa del equilibrio ecológico"`). No mencionado en la verificación de la historia 0001; confirmado real en esta pasada. |
| **`CD_SIGLAS`** | `string` | Sí, siempre (p. ej. `SUBNS`, `SNUP`) | **Es el código corto de clasificación** que pedía el Bloque 1 — confirmado real y distinto por tipo de clasificación (`SUBNS` para "Suelo No Urbanizable Común", `SNUP` para "Suelo No Urbanizable Protegido"). |
| `NM_LONGITUD` | `double` | Sí, siempre | Perímetro real del polígono completo de clasificación, en metros (no de la intersección con ninguna parcela). |
| **`NM_AREA`** | **`double`** | Sí, siempre | **Es la superficie real del polígono completo de clasificación**, en m² — la pregunta del Bloque 1 sobre "superficie del polígono" tiene aquí su respuesta. Es la superficie del polígono de clasificación entero (p. ej. `7.37783026716129E7` m² ≈ 73.8 km² para la mancha de "Suelo No Urbanizable Común" que cubre buena parte del término de Colmenar de Oreja), **no** la superficie de la intersección entre ese polígono y una parcela concreta — ese cálculo de intersección es tarea de la capa de reglas futura, no de este campo. |
| `CD_REUR` | `string` | Sí, siempre (p. ej. `58`, `365`, `65`) | Código numérico corto, consistente con el segmento central de `CD_UNI` (p. ej. `CD_UNI="RF_043_58_..."` con `CD_REUR="58"`). Significado exacto no confirmado más allá de esa composición — ningún campo de texto lo explica y no hay autodescripción fiable que consultar (ver lección sobre no confiar en autodescripción). |
| `GEOMETRY1` | `gml:GeometryPropertyType` | Sí, siempre | Geometría real del polígono (`gml:MultiSurface` de uno o más `gml:Polygon`/`gml:LinearRing`/`gml:posList`, mismo patrón GML 3.2 que Catastro). **A diferencia de Catastro, SÍ tiene anillos interiores (huecos) reales** — ver hallazgo 2.1 más abajo, encontrado durante la implementación del cliente, no durante esta verificación. |
| `DS_NOTAS`, `DS_ADJUNTO`, `DS_NOTAS_REF` | `string` (los tres `nillable`) | **No** — ausentes (vacíos) en los 56 features reales observados, sin una sola excepción | Declarados en el esquema (`DescribeFeatureType`) pero nunca poblados en la práctica real verificada. **No existe ningún campo de identificador de norma/ordenanza con nombre o fecha de aprobación de instrumento de planeamiento** (PGOU, Normas Subsidiarias) en esta capa — se buscó explícitamente y la ausencia se documenta aquí, no se asume. Si ese dato existe en IDEM, estaría en otra capa (fuera de alcance de esta historia, ver "Fuera de alcance" de la historia 0011). |

**Hallazgo 2.1 — los polígonos de IDEM SÍ tienen anillos interiores (huecos) reales, a diferencia de Catastro, descubierto durante la implementación del cliente (no durante la verificación del Bloque 1, que no llegó a inspeccionar `gml:interior`).** La feature `VILLACONEJOS`/`Suelo No Urbanizable Común` de `wfs_getfeature_bbox_villaconejos_rustica_margin2m_solape.xml` tiene 1 `gml:exterior` y **14 `gml:interior`** dentro de un único `gml:Polygon`; la feature de Colmenar (`wfs_getfeature_bbox_colmenar_rustica_margin2m.xml`) tiene 1 exterior y 4 interiores. `domain.geometry.Geometry` declara explícitamente, en su propio docstring, que no modela anillos interiores ("ninguna fuente usada hasta ahora los tiene") — deja de ser cierto con esta fuente. El cliente (`adapters/idem/parsing.py`) resuelve esto tomando solo los anillos `gml:exterior` y descartando los `gml:interior`, documentado en el propio parser; `area_m2` no se ve afectado porque viene directo del campo `NM_AREA` del servidor, no se calcula a partir de los anillos. **Riesgo residual explícito:** cualquier render futuro de estos polígonos (p. ej. un mapa en el informe HTML) dibujará el polígono como macizo, sin sus huecos reales — aceptable para esta historia (cliente aislado, sin conectar a ningún render todavía), pero a revisar si una historia futura conecta `LandClassification.geometry` a cualquier visualización.

**Hallazgo 3 — caso real de solape/colindancia entre clasificaciones distintas, encontrado con el bbox de la parcela rústica `REFCAT-RETIRADA` de Villaconejos (geometría real de `tests/fixtures/catastro/wfsCP_villaconejos_rustica_por_centroide.xml`, margen de 2 m).** `GET .../wfs?...&bbox=454553.78,4441392.86,454827.45,4441584.42,EPSG:25830` → `200 OK`, `numberMatched="3" numberReturned="3"` → fixture `wfs_getfeature_bbox_villaconejos_rustica_margin2m_solape.xml`. Los 3 features reales:

1. `DS_MUNICIPIO=VILLACONEJOS`, `DS_CLASIF_GEN=Suelo No Urbanizable Común` (`CD_SIGLAS=SUBNS`).
2. `DS_MUNICIPIO=VILLACONEJOS`, `DS_CLASIF_GEN=Suelo No Urbanizable Protegido` (`CD_SIGLAS=SNUP`, `DS_CLASIF_DET` menciona valor naturalístico/equilibrio ecológico).
3. `DS_MUNICIPIO=CHINCHÓN` (`CD_MUNICIPIO=052`, municipio distinto, también de la Comunidad de Madrid, colindante con Villaconejos), `DS_CLASIF_GEN=Suelo No Urbanizable Común`.

Es decir, el mismo bbox pequeño (parcela real + 2 m) intersecta **tres polígonos de dos clasificaciones generales distintas y dos municipios distintos**. **Confirmado que esto no es un artefacto del margen**: repitiendo la misma petición con margen `0` (bbox exacto de la parcela, sin ningún margen) se obtiene idéntico resultado (`numberMatched="3"`, mismos tres features) — el solape es real y existe en el dato de origen, no es un efecto de haber ensanchado el bbox de consulta. Responde de forma positiva y con evidencia real la pregunta 1 del Bloque 1 de la historia 0011 (no hizo falta forzar ningún caso sintético).

**Hallazgo 4 — bbox sin cobertura: `200 OK` con `FeatureCollection` vacía, idéntico tanto fuera de la Comunidad de Madrid como fuera de España continental.** Dos peticiones reales:

- Bbox en pleno casco de Toledo (fuera de la Comunidad de Madrid, `EPSG:25830`, `bbox=407900,4413900,408100,4414100,EPSG:25830`) → `200 OK`, `numberMatched="0" numberReturned="0"`, cuerpo `<wfs:FeatureCollection .../>` autocerrado, sin ningún `<wfs:member>` → fixture `wfs_getfeature_bbox_fuera_cobertura_toledo.xml`.
- Bbox en el Atlántico, muy al sur de la península (`bbox=200000,3800000,200100,3800100,EPSG:25830`) → idéntico resultado (`200 OK`, 0 features, mismo cuerpo autocerrado).

**No existe ninguna distinción observable entre "fuera de cobertura del servicio" y "hueco real dentro de la cobertura de la Comunidad de Madrid"**: ambos casos reales probados devuelven exactamente la misma forma de respuesta (`200 OK`, `FeatureCollection` vacía, sin código de error ni campo que lo señale). Documentado explícitamente como respuesta negativa a la pregunta 4 del Bloque 1 — no se puede distinguir porque el servicio no lo distingue, igual que ya se confirmó para BOE (`404` idéntico para "fin de semana" y "fecha futura sin publicar", ADR 0008) y BOCM (mismo criterio, ADR 0009): un único tipo de error basta también aquí.

**Endpoints verificados:**

| Endpoint | URL base | Verificación |
| --- | --- | --- |
| WMS | `https://idem.comunidad.madrid/geoidem/UsoDelSuelo/wms` | `confirmado` (sin cambios frente a la pasada de la historia 0001). `GetFeatureInfo` real sobre Colmenar de Oreja y Villaconejos → fixtures ya existentes `getfeatureinfo_colmenar_real.txt`/`getfeatureinfo_villaconejos_real.txt`. **No se usa como método de consulta del cliente** (ver "Fuera de alcance" de la historia 0011: no devuelve geometría de polígono). |
| WFS — `DescribeFeatureType` | `https://idem.comunidad.madrid/geoidem/UsoDelSuelo/wfs?...&request=DescribeFeatureType&typeName=UsoDelSuelo:VPLA_V_CLASIFICACION_REF_25` | `confirmado`, nuevo en esta pasada. → fixture `wfs_describefeaturetype_clasificacion_ref25.xml`. Esquema completo (14 campos + geometría) cruzado contra features reales — ver hallazgo 2. |
| WFS — `GetFeature` con `BBOX` (método de consulta elegido para el cliente) | `https://idem.comunidad.madrid/geoidem/UsoDelSuelo/wfs?service=WFS&version=2.0.0&request=GetFeature&typenames=VPLA_V_CLASIFICACION_REF_25&bbox=minx,miny,maxx,maxy,EPSG:25830` | `confirmado`, nuevo en esta pasada. Caso de una sola clasificación → fixture `wfs_getfeature_bbox_colmenar_rustica_margin2m.xml` (1 feature). Caso de solape real (2 clasificaciones, 2 municipios) → fixture `wfs_getfeature_bbox_villaconejos_rustica_margin2m_solape.xml` (3 features, ver hallazgo 3). Caso sin cobertura → fixture `wfs_getfeature_bbox_fuera_cobertura_toledo.xml` (0 features, ver hallazgo 4). |
| WFS — `GetFeature` con `CQL_FILTER` por municipio (método **descartado** para el cliente, ver hallazgo 0 y "Fuera de alcance" de la historia 0011) | mismo WFS | `confirmado` que sigue funcionando (52/52 reales, re-verificado) → fixture corregida `wfs_getfeature_cql_colmenar_municipio_completo.xml`, sustituye a la fixture truncada de la historia 0001. No se usa en el cliente porque es impreciso frente a una geometría de parcela concreta (no aísla qué polígono(s) cubren exactamente esa parcela) — el bbox de la parcela sí lo hace. |

**Nota para el cliente de planeamiento (historia 0011):** existen múltiples capas de clasificación versionadas (`VPLA_V_CLASIFICACION`, `..._MODIF`, `..._REF_19`, `..._REF_23`, `..._REF_25`); `VPLA_V_CLASIFICACION_REF_25` es la más reciente (datos a 31/12/2025) y la única verificada en esta pasada — las demás quedan fuera de alcance explícito.

---

## PNOA — ortofoto actual e histórica (IGN/CNIG)

- **Protocolo:** WMS 1.3.0 (dos servicios separados: actual e histórico).
- **Autenticación:** ninguna.
- **Formato de respuesta:** `image/jpeg` (GetMap); XML (GetCapabilities).
- **CRS nativo:** `EPSG:25830` entre los CRS soportados (ambos servicios).
- **Licencia:** CC BY 4.0 (`confirmado`, historia 0021): Orden FOM/2807/2015, `https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf`; `GetCapabilities` declara `CC BY 4.0 scne.es`.
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

## SNCZI / Dominio Público Hidráulico — MITECO

Verificado por primera vez el 2026-10-16, para la historia 0012 — a diferencia de las demás fuentes de este registro, **no existía ninguna pasada previa** (ni siquiera superficial): la historia 0001 dejó esta fuente explícitamente fuera de alcance (ver "Resumen de fuentes no verificadas" al final de este archivo, ahora corregido). El punto de partida de `docs/vision.md` ("WMS/WFS del Ministerio") no se da por cierto en ningún momento: todo lo que sigue viene de peticiones HTTP reales, nunca de la cita de `docs/vision.md` ni de ningún `GetCapabilities` tomado como autoridad por sí solo.

**Resultado, resumido:** la búsqueda encontró **dos servicios reales y funcionales** (uno para cursos de agua/cauces, otro para peligrosidad por inundación) y **un servicio roto en producción** (el gateway legacy del propio MITECO para dominio público hidráulico deslindado/cartográfico, confirmado roto con evidencia reproducible, no asumido). Los dos servicios reales no viven bajo `sig.mapama.gob.es`/`wms.mapama.gob.es` como anticipaba `docs/vision.md`, sino bajo `api-features.idee.es` y `servicios.idee.es` — infraestructura de IDEE/IGN (la misma familia de servicios ya verificada para PNOA en la historia 0006), no de MITECO directamente, aunque el dato en sí es responsabilidad de MITECO/Confederaciones Hidrográficas.

### A) Cursos de agua (cauces) — IDEE, OGC API Features — `confirmado`

- **Cómo se encontró:** ni adivinando URLs ni confiando en `docs/vision.md`. La ruta real fue: (1) confirmar que `sig.mapama.gob.es`/`wms.mapama.gob.es` responden (sí, ambos dan `200` en la raíz) pero no exponen ningún WMS/WFS funcional bajo ningún nombre de capa probado (ver sección C); (2) rastrear la web pública de MITECO (`miteco.gob.es/es/cartografia-y-sig/visores.html`) hasta el catálogo de datos abiertos real, `https://catalogo.datosabiertos.miteco.gob.es/catalogo/` (CKAN), y buscar ahí (`package_search`, API real, no HTML) los datasets "zonas inundables", "cauces", "dominio publico hidraulico" → fixture `ckan_package_show_cauces_dph_deslindado.json`; (3) ese catálogo señala URLs de servicio reales, algunas rotas (sección C) y otras en dominios de IDEE que sí funcionan.
- **Protocolo:** OGC API — Features (REST/JSON, estándar OGC moderno, no WFS clásico). Sin autenticación.
- **Formato de respuesta:** GeoJSON (`application/geo+json` vía `f=json`).
- **CRS:** no tiene un único CRS de almacenamiento expuesto (`storageCrs` ausente en la respuesta de la colección), pero declara soporte explícito de `EPSG:25830` entre sus CRS alternativos (lista completa: `4258, 4326, 3857, 3035, 25828, 25829, 25830, 25831, 32628-32631, CRS84`...) — confirmado real que pedir `crs=http://www.opengis.net/def/crs/EPSG/0/25830` (y el mismo valor en `bbox-crs`) devuelve coordenadas ya en esa proyección, sin reproyección del lado del cliente, mismo patrón que Catastro/PNOA/IDEM.
- **Licencia:** citada explícitamente (a diferencia del resto de fuentes de este registro, donde queda `asumido` sin ningún enlace) — `https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf`, enlazada desde los metadatos de la propia colección (`rel: license`). No se ha descargado ni leído el PDF en esta pasada, así que el contenido exacto de las condiciones queda `asumido`, pero la existencia y URL del documento de licencia sí está `confirmado`.
- **Estado:** `confirmado`.

**Endpoint real:**

| Endpoint | URL | Verificación |
| --- | --- | --- |
| Catálogo de colecciones | `https://api-features.idee.es/collections` | `confirmado`. Lista 38 colecciones reales del tema INSPIRE Hidrografía (`HY-*`) y otros. La colección relevante para "cauce" es `watercourse` (`HY-P Curso de agua`). |
| Esquema de la colección | `https://api-features.idee.es/collections/watercourse/schema?f=json` | `confirmado` → fixture `features_watercourse_schema.json`. Esquema completo con ~30 campos (ver tabla abajo). |
| `items` con filtro espacial `bbox` | `https://api-features.idee.es/collections/watercourse/items?bbox=minx,miny,maxx,maxy&bbox-crs=...EPSG/0/25830&crs=...EPSG/0/25830&f=json` | `confirmado`, probado en tres bbox reales (ver hallazgos 1-3 abajo). |

**Hallazgo 1 — bbox de la parcela rústica real de Colmenar de Oreja (`REFCAT-RETIRADA`, margen 2 m, mismo bbox ya usado por IDEM en la historia 0011): resultado "sin afección", legítimo.** `GET .../items?bbox=467548.15,4442009.35,467616.92,4442039.4&bbox-crs=EPSG:25830&crs=EPSG:25830` → `200 OK`, `numberMatched=0, numberReturned=0` → fixture `features_watercourse_colmenar_rustica_margin2m_sin_afeccion.json`. Ningún curso de agua a menos de 2 m de esta parcela — resultado real, no forzado, coherente con que es una parcela de secano alejada de cualquier río/arroyo cartografiado.

**Hallazgo 2 — bbox de la parcela rústica real de Villaconejos (`REFCAT-RETIRADA`, margen 2 m, mismo bbox que IDEM): resultado POSITIVO real, no un caso de laboratorio.** `GET .../items?bbox=454553.78,4441392.86,454827.45,4441584.42&bbox-crs=EPSG:25830&crs=EPSG:25830` → `200 OK`, `numberMatched=1, numberReturned=1` → fixture `features_watercourse_villaconejos_rustica_margin2m_barranco_montero.json`. El curso de agua encontrado: **`nombre="Barranco del Montero"`**, `id_demarc="ES030"` / `id_demarcd="Tajo"` (**la misma demarcación hidrográfica del Tajo citada textualmente en `docs/vision.md`** como ejemplo de la regla `within_distance` → `requires_authorization`), `ancho_min="1"` (metro), geometría `LineString` real. Esta es la misma parcela que la historia 0011 (IDEM) ya había encontrado en el borde de dos clasificaciones de suelo y dos municipios (Villaconejos/Chinchón) — ahora confirma, además, estar a menos de 2 m de un cauce real con nombre, sentando la base empírica exacta que `docs/vision.md` pedía para la regla de ejemplo.

**Hallazgo 3 — bbox amplio sobre la comarca de Aranjuez (entre Colmenar de Oreja y Villaconejos, por donde pasan el Tajo y el Jarama) para confirmar que el servicio tiene datos reales en profundidad, no solo el caso aislado del hallazgo 2.** `GET .../items?bbox=430000,4428000,445000,4440000&bbox-crs=EPSG:25830&crs=EPSG:25830&limit=10` → `200 OK`, `numberMatched=179` (179 cursos de agua reales en esa comarca) → fixture `features_watercourse_aranjuez_con_datos_reales.json`. Primer feature real: `nombre="Arroyo de Borox"`, `id_demarcd="Tajo"`, `tipo_cursod="Curso natural"`, `persistd="Permanente"`, `ancho_min="5"`/`ancho_max="20"` (metros), `longitud=5700.4` (metros), geometría `LineString` 3D real (con cota Z) de cientos de puntos, `fuented="Instituto Geográfico Nacional"`.

**Esquema de campos confirmado (`features_watercourse_schema.json`, cruzado contra los features reales de los tres hallazgos anteriores):**

| Campo | Tipo | Significado confirmado |
| --- | --- | --- |
| `nombre` | `string` | Nombre propio del curso de agua (p. ej. "Barranco del Montero", "Arroyo de Borox"). Puede venir nulo (`nil_nombre`/`nilreason_nombre` presentes en el esquema para ese caso, no observado en los features reales de esta pasada). |
| `id_demarc` / `id_demarcd` | `string` | Código (`ES030`) y nombre (`Tajo`) de la demarcación hidrográfica — **coincide exactamente con la "Confederación Hidrográfica del Tajo" citada en `docs/vision.md`**. |
| `ancho_min` / `ancho_max` | `string` (numérico) | Anchura mínima/máxima del cauce, en metros. |
| `persist` / `persistd` | `string` (código INSPIRE `WaterPersistenceValue`) / `string` (legible) | Permanente/intermitente (`persistd="Permanente"` en los dos features reales con valor, p. ej.). |
| `orden` / `orden_esq` / `orden_esqd` | `string` | Orden del curso en la jerarquía de la red (p. ej. escala de Pfaffstetter, `orden_esqd="Pfaffstetter"`). |
| `tipo_curso` / `tipo_cursod` | `string` | Natural/artificial (`tipo_cursod="Curso natural"` real). |
| `longitud` | `number` | Longitud total del curso, en metros. |
| `fecha_alta` | `string` (formato `date`) | Fecha de alta del dato en el sistema. |
| `canaliza`, `marea`, `nativeness`, `drainsbasin`, `condicion`/`condiciond`, `fuente`/`fuented`, `situacion`/`situaciond`, `jerarquia`/`jerarquiad`, `origen`/`origend`, `origen_z`/`origen_zd` | varios | Presentes en el esquema y poblados en al menos un feature real de los 179 del hallazgo 3; sin consumidor identificado todavía (ver ADR 0012 para la decisión de qué campos modelar). |
| `hydroid_localid` / `inspireid_localid` | `string` | Identificadores INSPIRE del feature. `inspireid_localid` tiene `x-ogc-role: id` (es el identificador primario de la colección). |
| geometría | `LineString` (2D o 3D, con cota Z real) | **Línea, no polígono** — representa el eje/centro del cauce, no un área. Relevante para el diseño del Bloque 2 (ver ADR 0012): el cálculo de "a menos de 100 m de un cauce" se hace de forma natural como distancia punto-a-línea, no como intersección de polígonos. |

### B) Peligrosidad por inundación (zonas inundables, por periodo de retorno) — IDEE, WMS 1.3.0 raster — `confirmado`, con limitación real de forma (sin geometría de polígono)

- **Protocolo:** WMS 1.3.0 (GeoServer real — el propio servicio revela `http://localhost:8080/geoserver/...` en el `schemaLocation` de sus respuestas `GetFeatureInfo`, confirmando el backend). Sin autenticación.
- **Formato de respuesta:** `image/png` (`GetMap`); `application/vnd.ogc.gml` o `text/html` (`GetFeatureInfo`); XML (`GetCapabilities`).
- **CRS:** soporta explícitamente `EPSG:25830` entre una lista amplia (`CRS:84, EPSG:25828-25831, EPSG:32630, EPSG:3857, EPSG:4230, EPSG:4258, EPSG:4326...`) → fixture `wms_inundaciones_getcapabilities.xml`.
- **Licencia:** no verificada explícitamente con cita textual en esta pasada (`asumido`).
- **Estado:** `confirmado` como servicio real y funcional; **con una limitación real importante** (ver abajo) frente a lo que el Bloque 2 de la historia 0012 esperaba (lista de elementos con geometría poligonal).

**Endpoint real:**

| Endpoint | URL | Verificación |
| --- | --- | --- |
| WMS Peligrosidad por Inundación | `https://servicios.idee.es/wms-inspire/riesgos-naturales/inundaciones` | `confirmado`. `GetCapabilities` real → fixture `wms_inundaciones_getcapabilities.xml`. Capas reales: `NZ.Flood.FluvialT10`, `NZ.Flood.FluvialT100`, `NZ.Flood.FluvialT500` (fluvial, periodos de retorno 10/100/500 años), `NZ.Flood.MarinaT100`, `NZ.Flood.MarinaT500` (costera), `EL.GridCoverage`. |

**Hallazgo 4 — el valor que devuelve `GetFeatureInfo` es una profundidad de agua en metros, en un píxel/punto del raster, NO una entidad poligonal con atributos (nombre de zona, tipo, periodo de retorno como campo).** Confirmado con `INFO_FORMAT=text/html` (más legible que el GML crudo, que solo expone un `GRAY_INDEX` numérico sin etiqueta): la tabla de respuesta real dice literalmente `"Profundidad del agua (metros)"` como cabecera de columna. Sobre la parcela rústica real de Colmenar de Oreja (mismo bbox del hallazgo 1, capa `NZ.Flood.FluvialT100`) → `"NO DATA"` → fixture `wms_getfeatureinfo_colmenar_rustica_t100_margin2m.html` (y su equivalente GML crudo, `wms_getfeatureinfo_colmenar_rustica_t100_margin2m.xml`, con `GRAY_INDEX=999.0` — **`999.0` es el código de "NO DATA" de esta capa, confirmado por la etiqueta legible del `text/html`, no el sentinel genérico de "fuera de cobertura del raster"**, que es un número totalmente distinto, ver hallazgo 5). Sobre Villaconejos (mismo bbox del hallazgo 2, capas `FluvialT10` y `FluvialT100`) → también `"NO DATA"` en ambas → fixtures `wms_getfeatureinfo_villaconejos_rustica_fluvialt10_margin2m.html` / `..._fluvialt100_margin2m.html`. **Sin afección por inundación fluvial en ninguno de los dos municipios de referencia del MVP, para los periodos de retorno probados** — resultado real y legítimo, igual que ya ocurrió con IDEM/BOE en historias anteriores.

**Hallazgo 5 — prueba positiva real de que el servicio SÍ tiene datos cuando existe riesgo real, para no confundir "sin afección en las dos parcelas del MVP" con "el servicio siempre devuelve vacío".** `GetMap` real sobre un bbox amplio que cubre el curso del río Manzanares en Madrid capital (`EPSG:4326`, `bbox=40.38,-3.75,40.48,-3.65`, capa `NZ.Flood.FluvialT100`) → `200 OK`, imagen PNG real de 800×800 con **175 colores distintos** (gradiente de azules clasificando profundidad de inundación) sobre fondo transparente → fixture `wms_getmap_manzanares_t100_real_con_riesgo.png`. Confirma que el servicio renderiza zonas de riesgo reales con clasificación por color donde existen, y que el "NO DATA" de las parcelas del MVP es un resultado genuino de esa ubicación, no un servicio roto o vacío por defecto. (Un intento de localizar con `GetFeatureInfo` el valor exacto de profundidad en un píxel concreto de esa zona azul no acertó la coordenada exacta del píxel dentro del tiempo de esta verificación — no se considera necesario repetirlo: la prueba visual de 175 colores reales ya es evidencia suficiente de que el servicio tiene datos reales en esa zona, y el objetivo de esta prueba era descartar "el servicio está vacío siempre", no medir una profundidad exacta.)

**Limitación real para el diseño del Bloque 2 (ver ADR 0012): este servicio es un raster de profundidad de agua, no una colección de entidades vectoriales con geometría poligonal y atributos (nombre de zona inundable, tipo de zona, periodo de retorno como campo tabular).** `GetFeatureInfo` da un único valor numérico (profundidad) en el punto consultado — no hay "lista de zonas inundables que intersectan el bbox" como sí la hay para IDEM (`LandClassification`, historia 0011) o para los cursos de agua de la sección A de este mismo hallazgo. Esto cumple exactamente el supuesto que la propia historia 0012 (Bloque 2, AC de "método de consulta") anticipó explícitamente: *"salvo que el Bloque 1 documente explícitamente que ningún método disponible devuelve geometría, en cuyo caso se usa el mejor método disponible y esa limitación queda documentada como tal en el adapter"* — es exactamente este caso.

### C) Dominio Público Hidráulico deslindado/cartográfico y Zona de Servidumbre/Policía — MITECO (gateway legacy `wms.mapama.gob.es`) — `bloqueado`

**No se encontró ningún servicio funcional para estas capas específicas, a pesar de usar las URLs reales y oficiales citadas por el propio catálogo de datos abiertos de MITECO** (`https://catalogo.datosabiertos.miteco.gob.es/catalogo/`, dataset "Cauces con DPH deslindado" → fixture `ckan_package_show_cauces_dph_deslindado.json`). Esto no es una URL adivinada ni un nombre de capa supuesto: es la URL que el propio Ministerio publica como el `GetCapabilities` de este servicio.

- **URLs oficiales probadas (citadas literalmente por el catálogo CKAN de MITECO):**
  - `https://wms.mapama.gob.es/sig/Agua/DPHDeslindado?service=wms&request=GetCapabilities` (Cauces con DPH deslindado) → fixture `wms_mapama_dph_deslindado_getcapabilities_roto.xml`.
  - `https://wms.mapama.gob.es/sig/agua/DPHCartografico?service=wms&request=GetCapabilities` (Cauces con DPH cartográfico) → fixture `wms_mapama_dph_cartografico_getcapabilities_roto.xml`.
  - `https://wms.mapama.gob.es/sig/agua/ZI_LaminasQ100?service=wms&request=GetCapabilities` (variante de Zonas Inundables publicada también por MITECO, no solo por IDEE) → fixture `wms_mapama_zi_laminasq100_getcapabilities_roto.xml`.
- **Resultado real, idéntico en las tres:** `200 OK`, `Content-Type: text/xml`, cuerpo:
  ```
  <ServiceExceptionReport version="1.1.1"><ServiceException code="InvalidFormat">
  [ Referencia a objeto no establecida como instancia de un objeto.
    System.NullReferenceException: Referencia a objeto no establecida como instancia de un objeto.
    en _Default.ConstruirServiceArcGISBaseUrl() en ...\wms\wms.aspx.cs:línea 606
    en _Default.Page_Load(...) en ...\wms\wms.aspx.cs:línea 848 ]
  </ServiceException></ServiceExceptionReport>
  ```
  Es decir, **una excepción de referencia nula sin capturar en el backend ASP.NET del propio Ministerio** (traza de pila real, con nombres de fichero/línea reales), no un error de autenticación, de formato de parámetros o de nombre de capa equivocado.
- **Confirmado que el fallo es sistémico, no específico de "Agua" ni de las capas DPH/ZI concretas:** repitiendo exactamente la misma petición (`GetMap` con parámetros completos y válidos: `layers=0&styles=&srs=EPSG:25830&bbox=...&width=256&height=256&format=image/png`) contra una carpeta completamente ajena al dominio hídrico (`/sig/Biodiversidad/LIC/wms.aspx`, Lugares de Interés Comunitario) → **idéntica excepción, mismo `NullReferenceException` en la misma línea de código** → fixture `wms_mapama_biodiversidad_lic_getmap_roto_control.xml`. Esto descarta que el problema sea "nombre de capa incorrecto" o "carpeta Agua mal adivinada": **todo el gateway legacy `wms.mapama.gob.es/sig/*/wms.aspx` está roto en producción**, a fecha de esta verificación (2026-10-16), para cualquier petición que pase de la validación inicial de parámetros (`service=WMS` + `request` reconocido) y llegue a construir la URL base real contra ArcGIS Server.
- **Lo que SÍ se probó antes de llegar a esta conclusión** (para que quede constancia de que no es un primer intento fallido dado por perdido): variaciones de mayúsculas/minúsculas en los parámetros, con/sin `VERSION`, con/sin `FORMAT`, `GetCapabilities` y `GetMap` por separado, `SERVICE=WFS` (confirma mensaje distinto, `"service is not WMS"`, es decir, ese código de validación sí funciona; el `NullReferenceException` solo aparece cuando `SERVICE=WMS` es aceptado y la petición avanza a construir la URL de ArcGIS), HTTP sin TLS (puerto 80 cerrado, no es una vía alternativa), y el catálogo REST nativo de ArcGIS Server en `sig.mapama.gob.es/arcgis/rest/services` (responde, `confirmado` como servicio real, pero solo expone 4 servicios ajenos — `aguaHidroDemarcaciones`, comarcas agrarias/ganaderas, playas — ninguno de dominio público hidráulico ni zonas inundables).
- **Qué significa para el motor de reglas (`within_distance` a `dph_cauce`, citado en `docs/vision.md`):** la geometría exacta del **deslinde legal** del DPH (la línea que separa el cauce de la propiedad privada, con valor jurídico) y de las **zonas de servidumbre (5 m) y policía (100 m)** como capas propias **no están disponibles en ningún servicio en vivo verificado en esta pasada**. El cliente de cursos de agua de la sección A (`watercourse`, geometría de eje/centro del cauce, no el deslinde legal) es la mejor aproximación real disponible — más precisa que nada, pero no idéntica al deslinde legal del DPH (el eje del cauce y el límite de DPH deslindado no son la misma línea; la distancia real sobre la que opera la ley se mide desde el deslinde, no desde el eje). Esta distinción queda documentada explícitamente para que el motor de reglas futuro no asuma que son intercambiables sin más — ver ADR 0012.
- **Decisión de cómo proceder, dejada para el arquitecto** (ver ADR 0012): no se vuelve a intentar este gateway en esta historia; se usa `watercourse` como aproximación documentada para "cauce" en el cliente del Bloque 2, y se deja constancia explícita de que el deslinde legal exacto del DPH y las zonas de servidumbre/policía como capas propias quedan **sin verificar y sin cliente**, candidatas a una historia futura que pruebe, por ejemplo, el geoportal propio de la Confederación Hidrográfica del Tajo (no probado en esta pasada) en vez de este gateway general del Ministerio.

---

## Vías pecuarias — IDEM, Comunidad de Madrid (Red de Vías Pecuarias)

Verificado por primera vez el 2026-10-16, para la historia 0014 — a diferencia de SNCZI/DPH (historia 0012), que tampoco tenía pasada previa pero sí una pista textual verificable (`docs/vision.md` citando "WMS/WFS del Ministerio"), vías pecuarias arrancaba sin ninguna pista más concreta que "cartografía autonómica, cobertura desigual". Las tres pistas del contexto de la historia 0014 se exploraron en este orden: (1) otros servicios del propio dominio IDEM más allá de `UsoDelSuelo` — **aquí se encontró el resultado**, documentado abajo; (2) catálogo CKAN de MITECO y (3) `datos.comunidad.madrid` no llegaron a probarse porque (1) ya dio un resultado positivo y completo, siguiendo el mismo criterio de parada de la historia 0012 (no seguir buscando alternativas una vez hay un servicio real y suficiente para el Bloque 2).

**Cómo se encontró — nunca adivinando el nombre de una carpeta, siempre confirmando contra la red real:** la historia planteaba como candidatos a probar `ViasPecuarias`, `VP` u otro nombre de carpeta "hermano" de `UsoDelSuelo` bajo el mismo GeoServer (`https://idem.comunidad.madrid/geoidem/`). Ninguno de esos nombres es correcto. El método real que funcionó: pedir el `GetCapabilities` **global** del propio GeoServer (`GET https://idem.comunidad.madrid/geoidem/ows?service=wfs&version=2.0.0&request=GetCapabilities`, sin fijar ningún workspace en la ruta) → `200 OK`, 366 KB, lista de capas de **todos** los workspaces del servidor con su nombre `workspace:capa` → fixture `ows_getcapabilities_global_zonas_workspace.xml`. Filtrando esa lista por el patrón `pecuari|vp|vereda|canada|cordel|colada` aparece una única coincidencia real: `Zonas:IDEM_MA_VIAS_PECUARIAS` — el workspace correcto es `Zonas` (genérico, de "Medio Ambiente/Zonas", no `ViasPecuarias` ni `VP` como anticipaba la historia), con prefijo de capa `IDEM_MA_` (Medio Ambiente) compartido con otras ~37 capas del mismo workspace (cotos de caza, montes, embalses, Red Natura 2000 bajo `Zonas:IDEM_MA_RED_NATURA_PLAN` — candidata evidente para una futura historia de descubrimiento, no tocada aquí).

- **Protocolo:** WMS 1.3.0 y WFS 2.0.0 sobre el mismo GeoServer que IDEM/`UsoDelSuelo` (historia 0011), workspace distinto (`Zonas` en vez de `UsoDelSuelo`).
- **Autenticación:** ninguna.
- **Formato de respuesta:** WFS `GetFeature` → GML 3.2/XML (idéntico patrón a `UsoDelSuelo`); `DescribeFeatureType` → XSD.
- **CRS nativo:** `EPSG:25830`, confirmado real — el filtro `bbox=minx,miny,maxx,maxy,EPSG:25830` (mismo KVP que `UsoDelSuelo`, Catastro y PNOA) devuelve la geometría ya en esa proyección (`srsName="urn:ogc:def:crs:EPSG::25830"` explícito en cada `gml:Polygon`/`gml:MultiSurface` real), sin reproyección del cliente.
- **Licencia:** CC BY 4.0 Comunidad de Madrid, declarada en `AccessConstraints` del `GetCapabilities` WMS del workspace `Zonas` (historia 0021, fixture `tests/fixtures/caminos/idem_zonas_wms_getcapabilities.xml`). No hay documento de licencia aparte.
- **Estado:** `confirmado`.
- **Cobertura de Colmenar de Oreja y Villaconejos:** confirmada explícitamente, con dato real — ambos municipios tienen tramos reales en la capa (15 y 2 respectivamente, ver hallazgo 2), aunque ninguno de los dos está a menos de ~2 km de la parcela rústica de referencia del MVP (ver hallazgo 3).

**Endpoints verificados:**

| Endpoint | URL | Verificación |
| --- | --- | --- |
| `GetCapabilities` global (todos los workspaces) | `https://idem.comunidad.madrid/geoidem/ows?service=wfs&version=2.0.0&request=GetCapabilities` | `confirmado`. Método real que reveló el workspace `Zonas` y la capa `IDEM_MA_VIAS_PECUARIAS` — ver "Cómo se encontró" arriba → fixture `ows_getcapabilities_global_zonas_workspace.xml`. |
| `DescribeFeatureType` | `https://idem.comunidad.madrid/geoidem/Zonas/wfs?service=WFS&version=2.0.0&request=DescribeFeatureType&typeName=Zonas:IDEM_MA_VIAS_PECUARIAS` | `confirmado` → fixture `wfs_describefeaturetype_vias_pecuarias.xml`. Esquema completo, 8 campos + geometría — ver hallazgo 1. |
| `GetFeature` con `BBOX` (método elegido para el cliente) | `https://idem.comunidad.madrid/geoidem/Zonas/wfs?service=WFS&version=2.0.0&request=GetFeature&typenames=Zonas:IDEM_MA_VIAS_PECUARIAS&bbox=minx,miny,maxx,maxy,EPSG:25830` | `confirmado`. Caso "sin vía pecuaria cerca" (las dos parcelas reales del MVP, margen 2 m) → fixtures `wfs_getfeature_bbox_colmenar_rustica_margin2m_sin_afeccion.xml` / `wfs_getfeature_bbox_villaconejos_rustica_margin2m_sin_afeccion.xml`, ambas `numberMatched="0"` — ver hallazgo 3. Caso sin cobertura (Toledo) → fixture `wfs_getfeature_bbox_fuera_cobertura_toledo.xml`, también `numberMatched="0"`, idéntico a "sin vía pecuaria cerca" — misma indistinguibilidad ya confirmada para IDEM/`UsoDelSuelo` (hallazgo 4 de esa sección) y DPH. |
| `GetFeature` con `CQL_FILTER` por municipio (usado solo para verificación en profundidad, no es el método elegido para el cliente — mismo criterio que IDEM/`UsoDelSuelo`) | mismo WFS, `CQL_FILTER=DS_MUNI='COLMENAR DE OREJA'` / `'VILLACONEJOS'` | `confirmado`. 15 tramos reales en Colmenar de Oreja → fixture `wfs_cql_colmenar_municipio_completo_15_tramos.xml`; 2 tramos reales en Villaconejos → fixture `wfs_cql_villaconejos_municipio_completo_2_tramos.xml` — ver hallazgo 2. |
| `GetCapabilities` del WMS del workspace `Zonas` | `https://idem.comunidad.madrid/geoidem/Zonas/wms?service=WMS&version=1.3.0&request=GetCapabilities` | `confirmado`, consultado solo para leer el `Title`/`Abstract` de la capa (no se usa como método de consulta del cliente, mismo criterio que IDEM/`UsoDelSuelo`: no da geometría de polígono en `GetFeatureInfo`, no probado en detalle por no ser necesario) → fixture `wms_zonas_getcapabilities.xml`. |

**Hallazgo 1 — esquema completo de campos, confirmado con `DescribeFeatureType` real y cruzado contra los 17 features reales observados (15 de Colmenar + 2 de Villaconejos).** El elemento `Zonas:IDEM_MA_VIAS_PECUARIAS` trae:

| Campo | Tipo (XSD) | Poblado en los 17 features reales | Significado confirmado |
| --- | --- | --- | --- |
| `CD_MUNI` | `string` | Sí, siempre | Código de municipio (p. ej. `28043`, `28170`) — mismo código que Catastro/IDEM `UsoDelSuelo`. |
| `DS_MUNI` | `string` | Sí, siempre | Nombre de municipio. |
| `DS_NOMBRE` | `string` | Sí, siempre | Nombre propio del tramo/elemento (p. ej. `"Cañada de la Alameda"`, `"Vereda del Raso"`, pero también `"Abrevadero"`, `"Descansadero Valle de San Juan"` — ver hallazgo 2 sobre `DS_TIPO`). |
| `CD_VP` | `string` | Sí, siempre | Código corto de la vía pecuaria (p. ej. `2804307` para una cañada; `280430E`, con letra en vez de dígito final, para los elementos anejos tipo abrevadero/descansadero — patrón real, no documentado en ningún sitio, encontrado al inspeccionar los 17 valores). |
| `DS_TRAMO` | `decimal` | Sí, pero **siempre `0`** en los 17 features reales observados (confirmado además con `CQL_FILTER=DS_TRAMO>0` sobre la capa completa de la Comunidad de Madrid: `numberMatched="0"`, ningún tramo de ningún municipio tiene valor distinto de 0) | Campo declarado para numerar sub-tramos de una misma vía pecuaria, **sin ningún uso real observado todavía** — documentado como posible pero no confirmado, no se asume que vaya a aparecer poblado en otro municipio. |
| **`DS_TIPO`** | **`string`** | Sí, siempre | **Es el campo de tipo de vía pedido explícitamente por el Bloque 1 de la historia.** Valores reales observados en los 17 features de Colmenar/Villaconejos: `"Cañada"`, `"Vereda"`, `"Colada"` — **tres de los cuatro tipos legales citados en la historia** (ningún `"Cordel"` en estos dos municipios concretos, pero sí confirmado real en otros municipios de la Comunidad de Madrid: `CQL_FILTER=DS_TIPO='Cordel'` sobre la capa completa → `numberMatched="301"`, p. ej. `"Cordel de las Merinas"` en Aldea del Fresno → fixture `wfs_cql_dstipo_cordel_muestra_comunidad_madrid.xml`). **Además, tres valores reales que NO son ninguno de los cuatro tipos legales de vía pecuaria que anticipaba la historia**: `"Abrevadero"`, `"Descansadero"`, `"Descansadero-Abrevadero"` — elementos anejos a la red (puntos de descanso/abrevado del ganado), geolocalizados en la misma capa con la misma estructura de campos que una cañada/vereda/colada real, no un tipo de vía pecuaria en sí. Documentado explícitamente como hallazgo, no filtrado ni descartado por este registro — decisión de si el cliente los incluye o los excluye queda para el ADR 0014. |
| `NM_LONG` | `double` | Sí, siempre | Longitud real del tramo/elemento, en metros (p. ej. `10492.01` m para "Vereda del Cristo"). |
| `NM_AREA` | `double` | Sí, siempre | Superficie real del polígono del tramo/elemento, en m² (p. ej. `122148.09` m² para "Vereda del Cristo"). **No existe ningún campo explícito de "anchura legal" en el esquema** — ver hallazgo 2 sobre esta ausencia y sobre la relación `NM_AREA`/`NM_LONG`. |
| `GEOMETRY1` | `gml:GeometryPropertyType` (genérico en el XSD) | Sí, siempre | Geometría real del tramo — **siempre `gml:Polygon` o `gml:MultiSurface`** (nunca una línea/curva abierta) — ver hallazgo 3 sobre la forma real. |

**Hallazgo 2 — no existe ningún campo de "anchura legal" en el esquema real, confirmado por ausencia, no asumido.** La historia pedía confirmar explícitamente si existe un campo de anchura legal en metros. El esquema completo (`DescribeFeatureType`, 8 campos + geometría, tabla del hallazgo 1) no tiene ningún campo con ese significado — ni `ANCHO`, ni `ANCHURA`, ni ningún nombre equivalente. Lo que sí existen son `NM_LONG` (longitud) y `NM_AREA` (superficie) del polígono real del tramo, de los que se puede **derivar** una anchura media aproximada (`NM_AREA / NM_LONG`) — comprobado real sobre los 17 features: para los tramos de tipo `"Vereda"` esa anchura derivada sale entre ~9 y ~12 m (p. ej. "Vereda del Cristo": 122148.09/10492.01 ≈ 11.64 m); para los de tipo `"Cañada"` sale entre ~35 y ~38 m (p. ej. "Cañada de la Alameda": 171197.68/4839.01 ≈ 35.38 m); para los de tipo `"Colada"` sale entre ~14 y ~17 m. **Estos valores derivados NO coinciden con las anchuras legales de referencia que cita la propia historia** (vereda ≥ 20,89 m, cañada ≥ 75 m) — son sistemáticamente menores, consistente con el fenómeno real conocido de ocupación/reducción de facto de vías pecuarias frente a su anchura legal original, pero esta discrepancia **se documenta aquí como hallazgo, no se resuelve**: decidir si el cliente expone esta anchura derivada, y si se debe usar en vez de — o además de — la anchura legal de referencia, es una decisión del ADR 0014 y, en última instancia, del motor de reglas futuro (ver "Fuera de alcance" de la historia 0014, que ya anticipaba explícitamente no resolver esta reconciliación).

**Hallazgo 3 — geometría real: polígono (área real, no línea de eje), con un caso real confirmado de multi-parte (`MultiSurface`), sin ningún anillo interior observado.** De los 17 features reales (15 Colmenar + 2 Villaconejos), 16 traen un único `gml:Polygon` con un único `gml:exterior` y **cero `gml:interior`** (a diferencia de IDEM/`UsoDelSuelo`, historia 0011, que sí tiene huecos reales) — el polígono representa la franja/superficie real de la vía pecuaria ya cartografiada con su anchura, no el eje/centro como los cursos de agua de la historia 0012 (`LineString`). **Un feature real, `"Vereda de la Mesa"` (Colmenar de Oreja, `CD_VP=2804303`), trae `gml:MultiSurface` con 2 `gml:surfaceMember`/`gml:Polygon` distintos** — mismo patrón de geometría multi-parte ya conocido en este proyecto para edificios de Catastro con varios cuerpos (historia 0002), nunca antes visto en una fuente IDEM. Esto responde de forma concluyente la pregunta abierta de la historia sobre la forma de la geometría: **es un polígono (franja con anchura ya cartografiada), nunca una línea** — a diferencia de los cursos de agua (historia 0012), y sin el problema de anillos interiores que sí tuvo IDEM/`UsoDelSuelo` (historia 0011). `domain.geometry.Geometry` (anillos exteriores, multi-parte, sin huecos) encaja exactamente con esta forma real sin ningún cambio — ver ADR 0014.

**Hallazgo 4 — bbox real sobre las dos parcelas del MVP: "sin vía pecuaria cerca" en ambas, resultado real y legítimo, no un artefacto del margen de 2 m.** `GET .../wfs?...&bbox=467548.15,4442009.35,467616.92,4442039.4,EPSG:25830` (parcela rústica `REFCAT-RETIRADA` de Colmenar de Oreja, mismo bbox ya usado por IDEM/`UsoDelSuelo` y por cursos de agua) → `200 OK`, `numberMatched="0"` → fixture `wfs_getfeature_bbox_colmenar_rustica_margin2m_sin_afeccion.xml`. `GET .../wfs?...&bbox=454553.78,4441392.86,454827.45,4441584.42,EPSG:25830` (parcela rústica `REFCAT-RETIRADA` de Villaconejos) → idéntico, `numberMatched="0"` → fixture `wfs_getfeature_bbox_villaconejos_rustica_margin2m_sin_afeccion.xml`. **Confirmado que no es un margen demasiado pequeño**: calculando la distancia real desde el centroide de cada parcela (mismos centroides ya usados por Catastro, `Consulta_CPMRC`) hasta el punto más cercano de cada uno de los 17 tramos reales del hallazgo 2 (aproximación por puntos de la polilínea, no por distancia exacta punto-a-polígono), el tramo más cercano a Colmenar de Oreja está a ≈2,39 km (`"Vereda del Cristo"`) y el más cercano a Villaconejos está a ≈2,25 km (`"Vereda del Raso"`) — ambas muy por encima de cualquier margen razonable de punto flotante. Es un resultado real: las dos parcelas de referencia del MVP, elegidas en la historia 0001 por su simplicidad catastral, simplemente no están cerca de ninguna vía pecuaria cartografiada.

**Hallazgo 5 — prueba positiva real de que el servicio sí tiene datos ricos, para no confundir "sin vía pecuaria cerca de las dos parcelas del MVP" con "la capa está vacía o es pobre".** Los municipios completos de Colmenar de Oreja y Villaconejos sí tienen tramos reales (15 y 2 respectivamente, hallazgo 2) y la Comunidad de Madrid completa tiene **1694 features reales** en esta capa (confirmado con `GetFeature&resultType=hits` sin filtro, sin descargar el contenido completo). El `Abstract` real del `GetCapabilities` del WMS (`Title="Red de Vías Pecuarias de la Comunidad de Madrid"`) cita explícitamente la norma de origen: *"Ley 8/1998, de 15 de junio, de Vías Pecuarias de la Comunidad de Madrid"* y confirma textualmente *"el territorio de la Comunidad de Madrid es atravesado por cuatro cañadas reales, además de por gran número de otras vías pecuarias (cordeles, veredas y coladas)"* — cita que confirma independientemente la taxonomía de cuatro tipos ya anticipada por la historia, aunque el campo real (`DS_TIPO`) tenga también los tres valores anejos no legales ya señalados en el hallazgo 1.

---

## Red Natura 2000 y espacios protegidos — IDEM, Comunidad de Madrid (Planes de Gestión)

Verificado en profundidad el 2026-10-16, para la historia 0015, a partir de un hallazgo de pasada de la historia 0014 (`Zonas:IDEM_MA_RED_NATURA_PLAN`, mismo workspace `Zonas` del GeoServer de IDEM ya usado para vías pecuarias) — nunca dado por bueno solo por el nombre de la capa, verificado con el mismo rigor que el resto de fuentes.

**Confirmado con evidencia textual real que es la Red Natura 2000 oficial.** El `Title` real del `GetCapabilities` del WMS del workspace `Zonas` para esta capa dice literalmente: *"Planes de Gestión de Espacios Protegidos Red Natura 2000 de la Comunidad de Madrid"*; el `Abstract` añade *"a escala 1:25.000 del año 2014"* (bilingüe ES/EN, el texto en inglés confirma *"Plans for the Management of Protected Areas of Natura 2000 Network"*) → fixture `wms_zonas_getcapabilities.xml`. Los valores reales del campo `DS_PLAN` citan explícitamente ZEC y ZEPA (ver hallazgo 1) — confirmación independiente, no solo por el nombre de la capa.

- **Protocolo:** WFS 2.0.0 (verificado real para esta capa concreta, no asumido por compartir workspace con vías pecuarias) y WMS 1.3.0, mismo GeoServer de IDEM.
- **Autenticación:** ninguna.
- **Formato de respuesta:** GML 3.2/XML (`GetFeature`), XSD (`DescribeFeatureType`).
- **CRS nativo:** `EPSG:25830`, verificado real para esta capa (`srsName="urn:ogc:def:crs:EPSG::25830"` en la geometría real devuelta, y `<CRS>EPSG:25830</CRS>` en el `GetCapabilities` del WMS) — no asumido por analogía con vías pecuarias/IDEM.
- **Licencia:** no verificada explícitamente con cita textual (`asumido`).
- **Estado:** `confirmado`, con una precisión importante de alcance (ver hallazgo 2).
- **Cobertura de Colmenar de Oreja y Villaconejos:** confirmada explícitamente, con dato real — las tres geometrías probadas (dos parcelas rústicas del MVP y una referencia catastral urbana real) caen dentro de la misma zona de plan de gestión (ver hallazgo 3).

**Endpoints verificados:**

| Endpoint | URL | Verificación |
| --- | --- | --- |
| `DescribeFeatureType` | `https://idem.comunidad.madrid/geoidem/Zonas/wfs?service=WFS&version=2.0.0&request=DescribeFeatureType&typeName=Zonas:IDEM_MA_RED_NATURA_PLAN` | `confirmado` → fixture `wfs_describefeaturetype_red_natura.xml`. Esquema completo, 5 campos + geometría — ver hallazgo 1. |
| `GetFeature` con `BBOX` (método elegido para el cliente) | `https://idem.comunidad.madrid/geoidem/Zonas/wfs?service=WFS&version=2.0.0&request=GetFeature&typenames=Zonas:IDEM_MA_RED_NATURA_PLAN&bbox=minx,miny,maxx,maxy,EPSG:25830` | `confirmado`. Tres geometrías reales probadas, las tres con afección real (ver hallazgo 3) → fixtures `wfs_getfeature_bbox_colmenar_rustica_margin2m.xml`, `wfs_getfeature_bbox_colmenar_urbana_margin2m.xml`, `wfs_getfeature_bbox_villaconejos_rustica_margin2m.xml`. |
| `GetFeature` con `CQL_FILTER=CD_ZONA='A'` (solo para verificación, no es el método del cliente) | mismo WFS | `confirmado`, muestra real de una zona de conservación prioritaria (`numberMatched="38"`) distinta del plan que cubre el MVP → fixture `wfs_cql_cd_zona_a_muestra_jarama_henares.xml` — ver hallazgo 1. |
| `GetFeature&resultType=hits` sin filtro (recuento total) | mismo WFS | `confirmado`. `numberMatched="215"` en toda la Comunidad de Madrid, `numberReturned="0"` (sin descargar contenido) → fixture `wfs_gethits_total_215_comunidad_madrid.xml`. |
| `GetCapabilities` del WMS del workspace `Zonas` | `https://idem.comunidad.madrid/geoidem/Zonas/wms?service=WMS&version=1.3.0&request=GetCapabilities` | `confirmado`, consultado para leer `Title`/`Abstract`/`CRS` de la capa → fixture `wms_zonas_getcapabilities.xml`. |
| Gateway legacy de MITECO (`wms.mapama.gob.es/sig/Biodiversidad/RedNatura2000/wms.aspx`, nombre de carpeta citado por el catálogo de datos abiertos del Ministerio) | — | `bloqueado`, mismo `NullReferenceException` real ya confirmado sistémico en la historia 0012 (DPH) → fixture `wms_mapama_biodiversidad_rednatura_getcapabilities_roto.xml`. No se investiga más allá: ya confirmado en 0012 que todo el gateway `wms.mapama.gob.es/sig/*/wms.aspx` está roto en producción, no es específico de esta capa. |
| Catálogo CKAN de MITECO (`catalogo.datosabiertos.miteco.gob.es`, mismo método que sí funcionó en la historia 0012) | — | **Inconcluso, no `bloqueado`**: fallo de conexión TLS real (`Recv failure: Connection reset by peer`) en 3 intentos repetidos en esta sesión, mientras otros dominios `.gob.es` y servicios ya usados respondieron con normalidad en la misma sesión → fixture `ckan_miteco_red_natura_intento_fallido.txt`. Documentado honestamente como intento real sin resultado concluyente, no como "catálogo roto" (no se puede descartar que sea un fallo transitorio de esta sesión concreta). |
| `sig.mapama.gob.es/arcgis/rest/services` (raíz del catálogo REST de ArcGIS Server, ya confirmado real en la historia 0012) | `https://sig.mapama.gob.es/arcgis/rest/services` | `confirmado` que responde, pero solo expone 4 servicios ajenos (`ElevationsService`, `PrintService`, `SharedService`, `SharedService_3857`) → fixture `arcgis_rest_sig_mapama_root_sin_servicio_rednatura.json`. Ningún servicio de Red Natura 2000 bajo este catálogo, mismo resultado que ya dio este mismo endpoint en la historia 0012. |

**Hallazgo 1 — esquema real, 5 campos + geometría, sin código oficial de sitio Natura 2000 (ES3XXXXXX) como campo propio.** `DescribeFeatureType` confirma: `CD_PLAN` (código corto del plan de gestión, p. ej. `"SE"`, `"JH"`), `DS_PLAN` (nombre completo del plan, texto libre real que SÍ cita ZEC/ZEPA explícitamente — p. ej. *"Plan de Gestión de las Cuencas de los ríos Jarama y Henares (ZEC) y de las Estepas Cerealistas de los ríos Jarama y Henares (ZEPA)"*, o *"Plan de gestión de vegas, cuestas y páramos del sureste de Madrid (ZEC), cortados y cantiles de los ríos Jarama y Manzanares (ZEPA) y carrizales y sotos de Aranjuez (ZEPA)"*), `CD_ZONA` (código corto de la sub-zona dentro del plan, p. ej. `"A"`, `"X"`), `DS_ZONA` (nombre de la sub-zona, p. ej. *"Zona A: Conservación Prioritaria"* o *"Espacio previamente ordenado / zonificado o en el que se ha considerado que no es necesario establecer una zonificación específica"*), `GEOMETRY1`. **Esta capa modela la zonificación de los planes de gestión regionales (agrupan varios espacios Red Natura 2000 bajo un único plan), no el límite oficial de cada sitio individual con su código EU** (`ES3XXXXXX`) — distinción real importante para el diseño del cliente, documentada aquí, no asumida.

**Hallazgo 2 — confirmación de alcance: "planes de gestión zonificados", no "límites oficiales de cada LIC/ZEC/ZEPA individual".** El nombre de la capa (`RED_NATURA_PLAN`, con sufijo `_PLAN`) y el esquema real (campos de plan/zona, no de sitio individual) confirman que esta fuente representa la **zonificación interna de los planes de gestión** aprobados por la Comunidad de Madrid — un plan puede agrupar varios espacios ZEC/ZEPA distintos bajo una única zonificación de gestión (p. ej. el plan `"SE"` agrupa un ZEC y dos ZEPA distintos bajo un único plan territorial). Es una fuente real y oficial de Red Natura 2000 (confirmado, hallazgo textual de arriba), pero **no** es el límite administrativo de cada sitio Natura 2000 individual con su código EU oficial — mismo tipo de distinción de alcance ya documentada para vías pecuarias (anchura real cartografiada vs. anchura legal, historia 0014) y para cauces (eje real vs. deslinde legal del DPH, historia 0012). Cualquier regla futura que necesite el código EU oficial de un sitio Natura 2000 concreto (para citarlo en un hallazgo) debe decidir si esta fuente es suficiente (identifica el plan de gestión aplicable y su zonificación, información real y útil) o si hace falta una fuente complementaria con los límites oficiales por sitio — no resuelto aquí, documentado como decisión futura.

**Hallazgo 3 — las tres geometrías reales probadas (incluida la vivienda real del fundador) caen dentro del mismo plan de gestión, en su zona genérica (no de conservación prioritaria).** `GET .../wfs?...&bbox=467548.15,4442009.35,467616.92,4442039.4,EPSG:25830` (parcela rústica `REFCAT-RETIRADA`, Colmenar de Oreja) → `200 OK`, `numberMatched="1"` → fixture `wfs_getfeature_bbox_colmenar_rustica_margin2m.xml`. `GET .../wfs?...&bbox=458114.6,4436581.5,458146.0,4436630.0,EPSG:25830` (parcela urbana real `REFCAT-RETIRADA`, vivienda real del fundador, Colmenar de Oreja) → idéntico resultado → fixture `wfs_getfeature_bbox_colmenar_urbana_margin2m.xml`. `GET .../wfs?...&bbox=454553.78,4441392.86,454827.45,4441584.42,EPSG:25830` (parcela rústica `REFCAT-RETIRADA`, Villaconejos) → idéntico resultado → fixture `wfs_getfeature_bbox_villaconejos_rustica_margin2m.xml`. **Las tres devuelven el mismo feature real**: `CD_PLAN="SE"` (*"Plan de gestión de vegas, cuestas y páramos del sureste de Madrid..."*), `CD_ZONA="X"` (*"Espacio previamente ordenado/zonificado... no es necesario establecer una zonificación específica"* — la categoría menos restrictiva del esquema de zonificación, distinta de `"Zona A: Conservación Prioritaria"` observada en el hallazgo 1 para otro plan). Resultado real y legítimo, no forzado: confirma que todo el territorio de los dos municipios del MVP (y la vivienda real del fundador) está dentro del área de gestión Red Natura 2000 regional, pero en su categoría de menor restricción, no en una zona de conservación prioritaria.

**Hallazgo 4 — geometría real multi-parte CON anillos interiores reales (huecos), a diferencia de vías pecuarias (historia 0014) y más parecido a IDEM/`UsoDelSuelo` (historia 0011).** La geometría del plan `"SE"` (el feature real que cubre las tres geometrías de prueba) es un `gml:MultiSurface` con **5 `gml:Polygon`/`gml:surfaceMember` reales y 2 `gml:interior` reales** (huecos dentro de alguno de esos 5 polígonos) — confirmado contando explícitamente las etiquetas reales (no solo líneas que las contienen: el XML real viene minificado en una sola línea, `grep -c` sin `-o` habría dado un falso "1" en vez del conteo real; verificado con `grep -o '<gml:interior>' | wc -l`, mismo cuidado que ya exigió la lección de la historia 0011). **Esta fuente sí necesita el mismo patrón de parser que IDEM/`UsoDelSuelo`** (tomar solo `gml:exterior`, descartar `gml:interior`) — nunca asumir, solo porque comparte workspace y técnica de descubrimiento con vías pecuarias, que también comparte su forma de geometría (que resultó ser el caso simple, sin huecos). Cada fuente geoespacial se verifica por sí misma, incluso dentro del mismo servidor.

**Hallazgo 3.1 — CORRECCIÓN del hallazgo 3, encontrada por el arquitecto al diseñar la historia 0018 (motor de reglas, regla de solape): "mismo feature devuelto por `BBOX`" NO equivale a "solape geométrico real" para esta capa concreta.** El hallazgo 3 afirmaba que las tres geometrías de prueba "están dentro" del plan `SE`/`X` basándose solo en que el WFS devolvía el mismo feature para las tres bboxes de consulta. Verificado con geometría real (parsers ya existentes sobre las fixtures ya citadas, cruzado con `shapely` como control independiente, ver `docs/adr/0018-solape-poligono-poligono-vias-pecuarias-red-natura-hallazgo-bbox-laxo.md`): la parcela rústica de Villaconejos (`REFCAT-RETIRADA`) está realmente a **1363.16 m** del polígono real más cercano de la zona; la rústica de Colmenar de Oreja (`REFCAT-RETIRADA`) está a **8329.95 m**. **Ninguna de las dos solapa de verdad.** Causa raíz confirmada: el filtro `BBOX` de OGC Filter Encoding que usa este WFS evalúa la envolvente (bounding box) de la geometría completa del feature, no su geometría real — y el feature `SE`/`X` es un `MultiSurface` de 5 polígonos reales dispersos en un área de ~46×41 km (hallazgo 4), cuya envolvente combinada cubre trivialmente cualquier bbox pequeño dentro de esa región aunque el polígono más próximo esté a más de 1 km. No se ha podido verificar el caso de la vivienda urbana real del fundador (`REFCAT-RETIRADA`) con geometría real porque ninguna fixture del repositorio contiene su geometría catastral — queda pendiente de verificación en vivo contra el servidor real. **Lección para cualquier fuente futura que use un filtro espacial `BBOX` (no `Intersects`) de OGC Filter Encoding**: no asumir que "el WFS devolvió este feature" implica solape/proximidad real, sobre todo si el feature es un `MultiSurface` disperso — confirmarlo siempre con geometría real antes de documentarlo como hallazgo.

---

## Fuentes del primer hito de caminos públicos — resolución, frecuencia y licencia (historia 0021)

Verificado el 2026-11-25 para la [historia 0021](../../../docs/stories/0021-verificacion-fuentes-caminos-publicos.md), tras el cambio de rumbo del [ADR 0021](../../../docs/adr/0021-cambio-de-rumbo-caminos-publicos-coste-casi-cero.md). Cambia la pregunta: ya no basta con "¿responde el endpoint?". Ahora hace falta saber si la capa **distingue un camino**, **de cuándo es** y **si se puede publicar** en un mapa abierto. Fixtures en `tests/fixtures/caminos/` salvo que se indique otra cosa.

Conclusión por capa: **publicar** (puede salir en el mapa público), **interno** (sirve para analizar, pero no se redistribuye tal cual) o **no usar**.

### Ámbito del hito — `confirmado`

`GetFeature` real al WFS INSPIRE de unidades administrativas del IGN (`https://www.ign.es/wfs-inspire/unidades-administrativas`, `au:AdministrativeUnit`, bbox `39.98,-3.62,40.22,-3.15` en EPSG:4258). Como colindante cuenta todo municipio que comparte vértices exactos con el polígono de Colmenar de Oreja. La respuesta completa (27 MB) está en `data/raw/ign_au/`, fuera de git. El resumen derivado está en `ambito_colindantes_colmenar.json`.

| Municipio | INE | Comunidad | Vértices compartidos |
| --- | --- | --- | --- |
| Colmenar de Oreja | 28043 | Madrid | — |
| Aranjuez | 28013 | Madrid | 405 |
| Chinchón | 28052 | Madrid | 124 |
| Belmonte de Tajo | 28019 | Madrid | 57 |
| Villaconejos | 28170 | Madrid | 38 |
| Villarejo de Salvanés | 28180 | Madrid | 22 |
| Valdelaguna | 28157 | Madrid | 5 (linde corta, pero real) |
| Noblejas, Ontígola, Villarrubia de Santiago, Ocaña | 45115, 45123, 45195, 45121 | Castilla-La Mancha | fuera del hito |

### Resumen

| Fuente | Resolución / escala | Fechas o frecuencia en el ámbito | Licencia | Conclusión |
| --- | --- | --- | --- | --- |
| PNOA ortofoto actual (IGN) | 0,25 m | Vuelo de **julio de 2023** (`confirmado`, tres puntos del ámbito). Madrid se vuela cada 3 años: 2011, 2014, 2017, 2020, 2023 → el siguiente debería ser 2026 (`asumido`) | CC BY 4.0 (`confirmado`) | **Publicar**, con atribución |
| PNOA histórico (IGN) | 0,50 m (1956-57, SIGPAC 1997-2003, 2006, 2009); 0,25 m (2011-2023); 1 m (OLISTAT) | Vuelos sobre Colmenar: **1956-57**, 1997-98, 1997-2003, 2006, 2009, 2011, 2014, 2017, 2020, 2023 (`confirmado`). Interministerial (1973-86) y Nacional (1981-86): **sin imagen** en el punto de prueba | CC BY 4.0 (`confirmado`) | **Publicar**, con atribución |
| Planimetrías / minutas del IGN (1870-1950) | Mapas manuscritos, escala de minuta (sin GSD) | **Los 7 municipios del ámbito tienen planimetría** de 1870-1880 (ver tabla). Aranjuez tiene además una de 1943 | CC BY 4.0 (`confirmado` por la Orden FOM/2807/2015, ver más abajo) | **Publicar** como imagen de referencia. Hay que georreferenciarlas: no son vectoriales |
| Primera edición del MTN50 y del MTN25 (IGN) | 1:50.000 y 1:25.000 | Hoja 0606 "Chinchón": MTN50 de 1881, con reediciones en 1934, 1948, 1968, 1975 y 2002. Minuta MTN50 de 1963. MTN25 0606-1 de 1995 (`confirmado`) | CC BY 4.0 (`confirmado`) | **Publicar** |
| Red de transporte del IGN (`roadlink`, OGC API Features) | Vectorial | 53 tramos en una ventana de 3×2 km de Colmenar; **41 sin asfaltar** (caminos). `fecha_alta` entre 2017 y 2026 (`confirmado`) | CC BY 4.0 (`confirmado` en la historia #24, sección «Red de transporte del IGN — roadlink»). Atribución: «Obra derivada de IGR-RT 2026 CC-BY 4.0 Instituto Geográfico Nacional» | **Publicar**, como referencia de "camino actual", con esa atribución junto a la capa |
| Catastro (INSPIRE) | Vectorial | Se actualiza 2 veces al año según la página INSPIRE de Catastro (`asumido`, no comprobado contra datos) | Licencia propia v1.0 de julio de 2016. **No es CC BY** (`confirmado`, ver más abajo) | **Interno**. Solo se puede publicar un producto **transformado**, y nunca con el nombre "cartografía catastral" |
| Vías pecuarias (IDEM) | Polígonos de franja (historia 0014) | Ficha de datos.gob.es con fecha de modificación **2014-11-29**. No consta fecha de digitalización por tramo | CC BY 4.0 Comunidad de Madrid (declarada en el `GetCapabilities` del WMS `Zonas`; ningún documento de licencia aparte) | **Publicar**, con atribución y con el aviso de que es cartografía informativa, no un deslinde |
| PNOA LiDAR | 3.ª cobertura: densidad nominal de 5 puntos/m² (`asumido`, especificación del IGN) | **3.ª cobertura volada en 2024** sobre Colmenar (`confirmado` por la capa `infoExpeditasLIDAR`) | CC BY 4.0 (`asumido`: producto del CNIG cubierto por la orden del IGN, sin cita específica) | **Interno** de momento; su utilidad para detectar cierres está sin demostrar |
| Ortofoto propia de la Comunidad de Madrid (IDEM `srvimagen2`) | 50 cm publicada (original de 30 cm reservado a la Comunidad y los ayuntamientos) | 2019, junio-julio (`confirmado`). El visor de IDEM nombra una capa "2025-CT-25cm" que no aparece en el `GetCapabilities` global (`bloqueado`) | Sin verificar | **No usar** hasta verificarla. Una ortofoto de 2025 a 25 cm sería más reciente que la del PNOA |
| OpenStreetMap | Vectorial, edición continua | Conteo no hecho: Overpass respondió `502`, "at capacity" (`bloqueado` temporalmente) | ODbL, de tipo "compartir igual" (`asumido`, https://www.openstreetmap.org/copyright) | **Interno**, como señal. Publicar mezclado con otras capas obligaría a liberar la base derivada bajo ODbL |

### Detalle de licencias (citas textuales)

- **IGN/CNIG (PNOA, histórico, minutas, MTN, red de transporte, unidades administrativas)** — `https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf` (leído el 2026-11-25). El uso de los productos del ámbito de la Orden FOM/2807/2015 "conlleva la aceptación por el usuario de una licencia CC-BY 4.0". Para una obra derivada, la atribución lleva delante "Obra derivada de", con el formato `Obra derivada de <producto> <fecha> CC-BY 4.0 <atribución>`; el propio documento pone como ejemplo `Obra derivada de PNOA 2010-2013 CC-BY scne.es`. La atribución tiene que verse junto a los datos. Los `GetCapabilities` del PNOA declaran `CC BY 4.0 scne.es`. El de unidades administrativas declara `CC BY 4.0 ign.es`. El WMS de minutas solo exige mencionar «© Instituto Geográfico Nacional de España» para acceder al servicio.
- **Catastro INSPIRE (parcelas, direcciones, edificios)** — `https://www.catastro.hacienda.gob.es/webinspire/documentos/Licencia.pdf`, "Licencia de acceso y uso de los servicios y conjuntos de datos INSPIRE de la Dirección General del Catastro", versión 1.0, julio de 2016. Corrige el "No conditions apply" que figuraba en la sección de Catastro: ese texto es el `Fees` del `GetCapabilities`, no la licencia. Puntos clave:
  - Permite el uso propio y "la elaboración y distribución de nuevos productos de valor añadido" siempre que la información "sea transformada".
  - Prohíbe la difusión de la información original: no puede difundirse "por Internet ni por ningún otro medio sin su previa transformación".
  - Exige que la transformación no altere ni desnaturalice el contenido, y que el producto no se identifique como "cartografía catastral" ni "información catastral".
  - La información distribuida a terceros "carecerá de fehaciencia" y quien la distribuye soporta las reclamaciones de terceros.
  - **Consecuencia:** el mapa no puede servir las parcelas catastrales tal cual. Sí puede publicar una capa propia derivada (p. ej. "trazado de camino inferido", que combina la geometría de las parcelas `VT` con otras fuentes), con un nombre que no la confunda con cartografía catastral. Si basta con simplificar o filtrar para que cuente como "transformación" en el sentido del artículo 21 de la Ley de Propiedad Intelectual es una cuestión jurídica abierta: **consultar antes de publicar**.
- **Vías pecuarias (IDEM)** — el `GetCapabilities` WMS 1.3.0 del workspace `Zonas` (`idem_zonas_wms_getcapabilities.xml`) declara `AccessConstraints` = `CC BY 4.0 Comunidad de Madrid` y `Fees` = `NONE`. La ficha de datos.gob.es (`datosgob_vias_pecuarias_madrid.json`) no trae campo de licencia. El PDF del inventario de vías pecuarias (enero de 2023) que daba la búsqueda web devuelve 404, y su copia indexada lleva el aviso "DATOS CON CARÁCTER EXCLUSIVAMENTE INFORMATIVO". El mapa tiene que repetir ese carácter informativo.

### Catastro — cómo aparecen los caminos en rústico — `confirmado`

`GetFeature` real al WFS de parcelas sobre 600×600 m de rústico en Colmenar (`catastro_wfsCP_colmenar_rustica_bbox600m.xml`, 51 parcelas). Los caminos son **parcelas propias con número 9000 o superior** dentro de cada polígono: `REFCAT-RETIRADA`, `…09007`, `REFCAT-RETIRADA`, `…09004`. `Consulta_DNPPP` sobre cada una (`catastro_dnppp_colmenar_pol*_parc*.xml`) devuelve paraje **"DESCUENTO"**, subparcela de clase **`VT` — "VÍA DE COMUNICACIÓN DE DOMINIO PÚBLICO"** y su superficie (p. ej. 8.604 m² en la 1/9001). La parcela de control 1/1 da en cambio `C-` "LABOR O LABRADÍO SECANO".

- Implicación: el filtro "camino según Catastro" es `parcela ≥ 9000` más la clase `VT`, que se comprueba contra `Consulta_DNPPP` (el WFS no trae el uso).
- Límite: Catastro **no prueba la titularidad** (la propia licencia dice que la información carece de fehaciencia). Un camino que no figura como `9xxx` no queda descartado como público, y al revés.
- Pendiente para la historia del mapa: comprobar si los arroyos salen como `HG` en las mismas parcelas `9xxx`, para no confundirlos con caminos.

### PNOA — vuelos reales sobre el ámbito — `confirmado`

- **Actual**: `GetFeatureInfo` sobre la capa `OI.MosaicElement` de `pnoa-ma`, en tres puntos (Colmenar `467400,4441800,467800,4442200`; zona de Chinchón `457000,4446000,…`; zona de Villarejo `478000,4447000,…`, EPSG:25830). Las tres respuestas dicen "Fecha 2023-07, Resolución 0.25 m, Ortoimagen verdadera NO" (`pnoa_ma_mosaicelement_gfi_*.html`).
- **Histórico**: la capa `infoVuelos` en Colmenar (`pnoa_historico_infovuelos_gfi_colmenar.html`) da la lista de vuelos de la tabla resumen. Las capas `Interministerial_1973-1986` y `Nacional_1981-1986` devuelven un `GetFeatureInfo` vacío y un `GetMap` transparente de 334 bytes en ese punto: **hueco de 1957 a 1997** en el servicio de ortofotos. Las fotografías sin ortorrectificar de esos vuelos podrían estar en la Fototeca del CNIG (sin verificar).
- **Coincide con el `Abstract` del `GetCapabilities` histórico**: la capa `PNOA2023` dice que abarca la Comunidad de Madrid a 25 cm, y la `PNOA2024` no incluye Madrid.

### Planimetrías del IGN por municipio — `confirmado`

`GetFeatureInfo` sobre la capa `Minutas` de `https://www.ign.es/wms/minutas-cartograficas` dentro de cada término (`ign_minutas_gfi_*.html`, `ign_minutas-cartograficas_gfi_Minutas_colmenar.html`). Todas son planimetrías, es decir, mapas manuscritos de trabajos topográficos que suelen dibujar caminos y vías pecuarias.

| Municipio | Fecha | Documento |
| --- | --- | --- |
| Colmenar de Oreja | 1875-08-06 | 280075 |
| Villaconejos | 1874-12-12 | 280264 |
| Chinchón | 1870-01-01 (fecha genérica de la serie) | 281287 |
| Belmonte de Tajo | 1874-05-20 | 280040 |
| Valdelaguna | 1874-05-29 | 280246 |
| Villarejo de Salvanés | 1874-11-21; 1870-01-01 | 280277; 281469 |
| Aranjuez | 1880-04-03; 1943-05-27 | 280027; 280022 |

`GetCapabilities` de `https://www.ign.es/wms/planimetrias` devuelve un error HTML de Tomcat (`bloqueado`); el servicio válido es el de minutas.

### Inventarios municipales de caminos — **ninguno encontrado publicado**

Búsqueda del 2026-11-25 en la web general y en el BOCM indexado, por "inventario de caminos" y por cada municipio del ámbito (Colmenar de Oreja, Villaconejos, Chinchón, Belmonte de Tajo, Valdelaguna, Villarejo de Salvanés, Aranjuez). **No aparece ningún inventario de caminos publicado ni ningún acuerdo de aprobación en el BOCM** para ninguno de los siete.

- Un resultado que la búsqueda atribuía a Chinchón (`BOCM-20230825-31`, desafectación del "camino público del Pedazo") resultó ser de **Chapinería** al leer el PDF: falso positivo descartado.
- Que no aparezca en la web no prueba que no exista. Los caminos públicos deben constar en el **inventario general de bienes** de cada ayuntamiento (Reglamento de Bienes de las Entidades Locales), que rara vez se publica.
- **Siguiente paso, sin coste:** solicitud de acceso a información pública (Ley 19/2013) a cada uno de los siete ayuntamientos, pidiendo el epígrafe de caminos del inventario de bienes y su cartografía, si existe. Es una acción externa en nombre del proyecto: la decide el fundador.
- **Mientras tanto**, el mapa se apoya en vías pecuarias oficiales + Catastro `VT` + planimetrías de 1870-1880 + PNOA de 1956, y lo dice explícitamente en el visor.

---

## Planimetría de Colmenar y MTN50 0606: acceso y georreferenciabilidad

Verificado el 2026-11-25 para la [historia #17](https://github.com/murcialito/parcel-intel/issues/17) (feature #11). Pregunta: ¿se pueden obtener la planimetría de Colmenar de Oreja (doc. 280075, 1875) y la hoja MTN50 0606 (1881) a una resolución útil, y georreferenciarlas? Datos en `tests/fixtures/caminos/planimetrias/` (`verificacion.json`, recortes de 1 km, procedencia de las imágenes completas y ficha del Centro de Descargas). Script puntual: `scripts/verificar_planimetrias.py`. Imágenes completas (ventana de 5×5 km, 2000×2000 px, 2,5 m/px) en `data/raw/ign_planimetrias/`, fuera de git, con su `*.provenance.json` (URL exacta, fecha, SHA-256, licencia).

### Hallazgos

| Hallazgo | Estado | Detalle |
| --- | --- | --- |
| El WMS de minutas y el de primera edición MTN sirven las dos imágenes sin captcha | `confirmado` | `GetMap` en EPSG:25830, PNG. Respuestas de 5×5 km a 2000 px en 10 a 25 s |
| Lo que sirve el WMS es un **mosaico ya reproyectado**, no la imagen cruda | `confirmado` | Las hojas de la planimetría aparecen recortadas, con huecos blancos y desajustes entre sí; la capa trae 13 CRS |
| El WMS devuelve 500/502 con el User-Agent por defecto de `requests`; con uno identificable funciona | `confirmado` | Descarga ya con reintentos en el script (ver `LESSONS.md`) |
| Resolución efectiva de la planimetría ≈ 2,5 m/px (rango 2 a 3) | `asumido` | Estimada por interpolación (método en `verificacion.json`); el original no se ha visto |
| Resolución efectiva del MTN50 ≈ 4 m/px (rango 3 a 5) | `asumido` | Igual |
| El original existe en el Centro de Descargas del CNIG: JPG + ECW, ED50 UTM 30 extendido, escala 25000, por municipio, 11 a 30 MB | `confirmado` (fichas ALTI de Colmenar); `asumido` (PLANI 280075) | Ficha en `cdd_detalle_alti280352_colmenar.html`. El PLANI 280075 no apareció en el listado público |
| La descarga del original pasa por reCAPTCHA v3 (`preAutorizarDescarga`) y un formulario con campo señuelo | `confirmado` | No se automatiza ni se elude: la hace una persona en el navegador |
| Marco, coordenadas y cuadrícula visibles | `confirmado` en el render | Planimetría: sin marco; solo mojones kilométricos; rejilla fina solo en el plano urbano. MTN50: sin marco, sin cuadrícula, sin coordenadas; hay cotas y un vértice geodésico en el casco |
| Puntos de control reconocibles hoy | `asumido` | 6 por imagen (cruce radial norte, iglesia, Plaza Mayor, ermita de San Juan, cementerio, ermita del Cristo); 3 con coordenada leída a ojo en el PNOA (±25 a 30 m), 3 `sin coordenada`. Los 3 con coordenada están a menos de 600 m entre sí: sirven para medir el desajuste local, no para ajustar toda la hoja |
| Desajuste local MTN50 frente a PNOA en el casco | `asumido` | 15 a 60 m a ojo; no medido con rigor |
| Ficha MTN50 0606 en el Centro de Descargas (tamaño, píxeles del original) | `bloqueado` | No se abrió en esta historia; queda para la de georreferenciación |

### Licencia y atribución exacta

CC BY 4.0 por la Orden FOM/2807/2015 y la licencia de uso del IGN (ver "Detalle de licencias", `https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf`), citada también por la ficha del Centro de Descargas. Redistribución permitida con atribución. Usar, junto a la imagen:

- Planimetría: `Obra derivada de Planimetrías 1870-1950 CC-BY 4.0 © Instituto Geográfico Nacional de España`
- MTN50: `Obra derivada de Primera edición MTN50 1875-1968 CC-BY 4.0 © Instituto Geográfico Nacional de España`

### Recomendación de método de georreferenciación

| Opción | Coste | Precisión esperable | Esfuerzo humano |
| --- | --- | --- | --- |
| **A. Usar el mosaico del WMS tal cual**, cacheado a 2,5 m/px | Cero. Una descarga por ventana, reproducible desde `data/raw/` | Heredada de la georreferenciación del IGN: MTN50 1:50.000 (el IGN declara una precisión de 1:50.000 para los datos de las planimetrías), y desajustes visibles entre hojas del mosaico de la planimetría. Orden de decenas de metros | Bajo: solo medir el desajuste |
| **B. Original (JPG + ECW) + transformación afín o polinómica de 2.º orden** con 8 a 10 puntos de control repartidos (QGIS), un fichero por hoja | Cero en dinero. Dependencia de una descarga manual con captcha | RMSE esperable de 5 a 15 m en la planimetría con buenos puntos (estimación, sin medir) | Alto: unas 2 a 4 h por municipio, más la descarga manual |
| **C. Híbrido**: A como base cacheada y reproducible; medir su error con 8 a 10 puntos de control repartidos; pasar a B solo en los términos donde el error pase de ~25 m | Cero | A donde basta, la de A; donde no, la de B | Medio: 2 h de medida por municipio, y B solo donde haga falta |

**Recomendación: C.** La imagen cruda **sí se puede obtener, pero solo a mano** (reCAPTCHA), así que B no puede ser un paso automático de un proceso por lotes. Empezar con A permite digitalizar y medir ya, y deja B como mejora acotada. Si la medida de la historia de georreferenciación sale por encima de ~25 m en un término, la alternativa es B para ese término. Pedir las imágenes al IGN (acción externa, decide el fundador) solo hace falta si el WMS no basta y la descarga manual resulta inviable para los siete municipios.

**¿Hace falta ADR?** Sí, en la historia de georreferenciación: fija el método (WMS cacheado frente a original manual) y la dependencia de un paso humano con captcha. No introduce proveedor nuevo (sigue siendo el IGN).

---

## Vías pecuarias — clasificación y deslinde por municipio (historia #26)

Verificado el 2026-11-25 para la [historia #26](https://github.com/murcialito/parcel-intel/issues/26) (feature #9, pendiente heredada de la historia 0021). Pregunta: para los 7 municipios del ámbito, ¿hay orden de clasificación y deslinde aprobados, y dónde se publican? **Respuesta corta: no se ha podido verificar para ninguno de los 7.** No es que no existan: el canal donde se publican (BOCM) no es consultable por búsqueda desde esta pasada. Las fixtures están en `tests/fixtures/caminos/`.

### Canales consultados — `confirmado`

| Canal | Petición real | Resultado | Fixture |
| --- | --- | --- | --- |
| Buscador de texto del BOCM | `GET https://www.bocm.es/buscador?texto=clasificacion+vias+pecuarias+Colmenar+de+Oreja` | `404`, 12 KB. **No hay endpoint de búsqueda público por URL.** | `bocm_buscador_texto_404.html` |
| RSS de sumarios del BOCM | `https://www.bocm.es/sumarios.rss` (ya documentado en la sección BOCM) | Solo ventana de 20 boletines recientes. **No sirve para búsquedas históricas.** | `tests/fixtures/bocm/sumarios.rss` |
| Catálogo abierto de la Comunidad de Madrid (CKAN) | `package_search?q=deslinde` | **0 resultados.** | `ckan_package_search_deslinde_sin_resultados.json` |
| Catálogo abierto (CKAN) | `package_search?q=clasificacion vias pecuarias` | 1 resultado: "Superficie de terreno forestal por tipo de propiedad" (estadística de superficie). **No es una orden de clasificación.** | `ckan_package_search_clasificacion_vias_pecuarias.json` |
| WFS de IDEM, `GetCapabilities` global | `https://idem.comunidad.madrid/geoidem/ows?service=wfs&version=2.0.0&request=GetCapabilities` | Única capa de vías pecuarias: `Zonas:IDEM_MA_VIAS_PECUARIAS`. Las capas `UsoDelSuelo:VPLA_V_CLASIFICACION*` son **clasificación de suelo** (planeamiento, ver historia 0011), no de vías pecuarias. **No hay capa de deslinde.** | `tests/fixtures/livestock_trails/ows_getcapabilities_global_zonas_workspace.xml` |
| Búsqueda web general | — | **No ejecutada.** El permiso de búsqueda web no estaba concedido en esta sesión. Ninguna afirmación de esta sección se basa en ella. | — |

### Clasificación por municipio — orden, fecha y URL BOCM

Estado de todas las filas: `bloqueado`. Motivo: el archivo del BOCM no se ha escaneado por fecha y no hay buscador accesible. "No encontrada" significa aquí "no localizada por los canales de arriba", no "no existe".

| Municipio | INE | Orden de clasificación | Estado |
| --- | --- | --- | --- |
| Colmenar de Oreja | 28043 | no encontrada | `bloqueado` |
| Aranjuez | 28013 | no encontrada | `bloqueado` |
| Chinchón | 28052 | no encontrada | `bloqueado` |
| Belmonte de Tajo | 28019 | no encontrada | `bloqueado` |
| Villaconejos | 28170 | no encontrada | `bloqueado` |
| Villarejo de Salvanés | 28180 | no encontrada | `bloqueado` |
| Valdelaguna | 28157 | no encontrada | `bloqueado` |

`asumido`: la clasificación de vías pecuarias en la Comunidad de Madrid se aprueba por orden de la Consejería competente en medio ambiente (Ley 8/1998, citada en el `Abstract` del WMS `Zonas`, `wms_zonas_getcapabilities.xml`). Por eso el sitio donde buscarla es el BOCM. La cita exacta de la norma de cada municipio no se ha comprobado.

### Deslinde por municipio — `bloqueado`

| Municipio | Deslinde (orden, fecha, URL, geometría) |
| --- | --- |
| Colmenar de Oreja | sin deslinde publicado (no verificado) |
| Aranjuez | sin deslinde publicado (no verificado) |
| Chinchón | sin deslinde publicado (no verificado) |
| Belmonte de Tajo | sin deslinde publicado (no verificado) |
| Villaconejos | sin deslinde publicado (no verificado) |
| Villarejo de Salvanés | sin deslinde publicado (no verificado) |
| Valdelaguna | sin deslinde publicado (no verificado) |

Lo que sí está `confirmado`: ninguna geometría de deslinde en las fuentes consultadas. La única geometría de vías pecuarias es la cartografía informativa de IDEM (sección "Vías pecuarias — IDEM" arriba), que es polígono de franja sin fecha de deslinde ni campo de estado.

### Conclusiones — `confirmado` salvo que se indique

- **Se puede marcar un tramo como "deslindada" en el mapa?** **No, con lo verificado.** No hay orden de deslinde localizada ni geometría de deslinde descargable. La capa IDEM es informativa (su licencia es CC BY 4.0 y el mapa debe mantener el aviso de carácter informativo, ver sección del 2026-11-25 arriba).
- **Qué falta para poder decidirlo:** (1) escanear el archivo del BOCM por fechas de la serie de clasificaciones y deslindes de la Consejería, o contar con un buscador del BOCM con permiso; (2) pedir la clasificación y deslindes a cada ayuntamiento y a la Dirección General competente (acción externa, la decide el fundador). Esto queda como **historia nueva** si el fundador lo aprueba: investigar el archivo del BOCM tiene coste de red y tiempo que esta historia no cubre.
- **Licencia de una geometría de deslinde, si aparece:** no se puede decidir sin la fuente. Se verificará con la misma disciplina que la licencia de IDEM (documento de licencia citado, no solo el `AccessConstraints` del `GetCapabilities`).

## Red de transporte del IGN — roadlink, licencia (historia #24)

Leído el **2026-11-26**. Estado de la licencia: **`confirmado`** para `roadlink` (antes `asumido`). Conclusión: **publicar**, con la atribución de abajo.

### Cadena de verificación

1. **Metadatos del servicio** — `https://api-features.idee.es/collections/roadlink?f=json`, leído 2026-11-26. Fixture: `tests/fixtures/caminos/ign_apifeatures_roadlink_collection.json`. El enlace `rel: license` ("Licencia de uso") apunta a `https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf`. Los metadatos INSPIRE de la colección llevan el identificador `spaign_IGR_Transporte`.
2. **Documento de licencia** — `https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf`, leído 2026-11-26 con la herramienta de lectura de PDF (3 páginas, 145.381 bytes). Fixtures: `tests/fixtures/caminos/ign_licencia_condiciones_uso.pdf` (original) y `ign_licencia_condiciones_uso.txt` (transcripción a mano de esa lectura; el test CA1 comprueba las citas contra el `.txt`). Cita textual (página 1): «el uso de los productos y servicios de información geográfica del IGN definidos en el ámbito de la Orden FOM/2807/2015 conlleva la aceptación por el usuario de una licencia CC-BY 4.0». Cita del artículo 4 de la Orden tal como la reproduce ese documento (página 1): «El uso de los productos de datos geográficos digitales mencionados en el Artículo 2 tendrá carácter libre y gratuito, siempre que se mencione el origen y propiedad de los datos, con el alcance y forma que autorice la licencia de uso correspondiente».
3. **Ámbito de la Orden FOM/2807/2015** — `asumido`. Versión del BOE: `https://www.boe.es/eli/es/o/2015/12/18/fom2807/con` (BOE-A-2015-14129). Solo se han leído **extractos** devueltos por `WebFetch`, no el texto bruto: artículo 2.1.b («La Información Geográfica de Referencia de instalaciones, redes e infraestructuras del transporte») y artículo 2.2 («esta orden se aplicará a los servicios de información geográfica del IGN prestados a través de Internet»). Ninguno está confirmado como literal. **Discrepancia sin resolver:** para el artículo 4, el documento del IGN dice «Artículo 2» y las dos lecturas de `WebFetch` del BOE dicen «artículo 1». Que `roadlink` esté en el ámbito se apoya en que sus propios metadatos enlazan este documento de licencia (fixture de la colección). Para pasar este eslabón a `confirmado` hay que leer el texto bruto del BOE (PDF `BOE-A-2015-14129`) y resolver el artículo 1/2.
4. **Producto** — tabla de productos del SCNE, `http://www.scne.es/tablaProductos.php`, leída 2026-11-26: entrada «Redes de Transporte», identificador `IGR-RT`, fecha `2026`, variante 1 «Sistema Cartográfico Nacional», variante 2 «Instituto Geográfico Nacional, Eusko Jaurlaritza / Gobierno Vasco y Comunitat Valenciana».

Conclusión de la cadena: la licencia CC BY 4.0 la declara el documento que el propio servicio enlaza (eslabones 1 y 2, leídos en bruto). El eslabón 3 (ámbito de la Orden) queda `asumido` hasta leer el BOE en bruto. La fila del resumen queda `confirmado` por la licencia, no por el ámbito.

### Atribución que muestra el visor (CA2)

`Obra derivada de IGR-RT 2026 CC-BY 4.0 Instituto Geográfico Nacional`

- Formato: «Obra derivada de <identificador> <fecha> CC-BY 4.0 <atribución de productores>», apartado 4 del documento de condiciones. Ese prefijo aplica a una obra derivada, es decir, si el visor transforma los datos. Si la capa publicada no altera la información original, el apartado 1 pide la forma sin «Obra derivada de» (`<identificador> <fecha> CC-BY 4.0 <atribución de productores>`). El texto de CA2 usa la forma derivada porque así lo fija el criterio; si la capa se publica sin transformar, cambiarlo es una decisión del fundador. La atribución debe verse junto a los datos (apartado 1).
- Atribución de productores: la variante 2 de la tabla sin las otras comunidades. El considerando Tercero del documento indica que, si el ámbito está completamente en una comunidad autónoma, se usa la variante 2 «sin mencionar al resto de Comunidades Autónomas». Colmenar de Oreja está en la Comunidad de Madrid.
- Alternativa literal si el fundador prefiere la variante 1: `Obra derivada de IGR-RT 2026 CC-BY 4.0 Sistema Cartográfico Nacional`.

### Límites y canales no leídos

- El texto del PDF se leyó con la herramienta de lectura de PDF (imagen y texto de cada página) y se transcribió a `ign_licencia_condiciones_uso.txt` a mano. No hubo extracción mecánica del flujo de texto.
- El texto bruto del BOE no se pudo descargar (sin red desde la shell); solo hay extractos de `WebFetch`. Ver eslabón 3.
- `http://www.scne.es/productos.html` redirige a `productos.php`; la página no contiene la tabla. La tabla está en `tablaProductos.php`, que sí se leyó.
- La fecha `2026` es la de la tabla de productos. No es la fecha de los datos de `roadlink` (su `fecha_alta` va de 2017 a 2026, ver resumen).
- Para la atribución «Obra derivada de» se sigue el texto del criterio de la historia; no hay ninguna obra derivada publicada todavía que la muestre.

---

## Resumen de fuentes no verificadas en esta pasada

Fuera de alcance de la historia 0001 (ver sección "Fuera de alcance" de `docs/stories/0001-registro-fuentes.md`): vías pecuarias, Red Natura 2000, concesiones de agua, inventario municipal de caminos. SNCZI/dominio público hidráulico, que figuraba aquí mismo hasta la historia 0012, quedó verificado en esa historia (ver sección "SNCZI / Dominio Público Hidráulico — MITECO" más arriba: cursos de agua y peligrosidad por inundación `confirmado`, deslinde legal de DPH y zonas de servidumbre/policía `bloqueado`). Vías pecuarias, que figuraba aquí mismo hasta la historia 0014, quedó verificada en esa historia (ver sección "Vías pecuarias — IDEM, Comunidad de Madrid" más arriba: `confirmado`, un único servicio real encontrado bajo el workspace `Zonas` del mismo GeoServer de IDEM). Red Natura 2000, que figuraba aquí mismo hasta la historia 0015, quedó verificada en esa historia (ver sección "Red Natura 2000 y espacios protegidos — IDEM, Comunidad de Madrid" más arriba: `confirmado` como fuente real de planes de gestión, con el alcance explícito de que modela zonificación de planes, no el límite oficial de cada sitio individual con código EU). Concesiones de agua e inventario municipal de caminos quedan para una iteración posterior del registro, cuando las historias de reglas/afecciones las necesiten.
