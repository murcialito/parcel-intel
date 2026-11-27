# Registro de fuentes

Verificado el 2026-10-15 contra servicios reales (no documentación de terceros). Cada ejemplo de petición/respuesta real está guardado en `tests/fixtures/<fuente>/`. Ver [ADR 0001](../../../docs/adr/0001-sources-es-documentacion-no-capa-de-codigo.md): este archivo es el único contenido permitido en `sources/` — ningún cliente se implementa aquí, solo en `adapters/<proveedor>/`.

Municipios de referencia usados para verificar: Colmenar de Oreja (código Catastro/IDEM: `28043` / `043`) y Villaconejos (código IDEM: `170`), ambos en la Comunidad de Madrid.

---

## Catastro (INSPIRE)

**Fixtures sintéticas (historia #45, ADR 0033).** Desde la historia #45, `tests/fixtures/catastro/` **no contiene ninguna respuesta de Catastro**: todas sus fixtures son **sintéticas**, con el mismo esquema que las respuestas reales (namespaces, elementos, `srsName` EPSG:25830, codificación declarada) y datos inventados (referencias de la provincia `99` y, en urbanas, hoja `ZZ`, que no existen; geometrías dibujadas a mano). Las genera `tests/fixtures/generate_catastro.py` y se regeneran con `uv run python -m tests.fixtures.generate_catastro`; `uv run python -m tests.fixtures.generate_catastro --check` comprueba, sin escribir, que coinciden byte a byte con el generador. De lo real **solo se conservan las envolventes** (4 números cada una) de las tres parcelas que otros tests cruzan con respuestas reales de otras fuentes: `(467550.15, 4442011.35, 467614.92, 4442037.40)` (rústica de Colmenar), `(454555.78, 4441394.86, 454825.45, 4441582.42)` (rústica de Villaconejos) y `(457153.87, 4436018.27, 457183.48, 4436055.23)` (urbana con edificio); dentro de cada una la parcela sintética es un rombo. La **verificación real contra el servicio** se hizo el **2026-10-15** (historias 0001–0002, hallazgos de abajo) y la de la **licencia** el **2026-11-25** (historia 0021). Las respuestas originales se retiraron del árbol; solo quedan sus huellas SHA-256 en `tests/fixtures/catastro_huellas_reales.json`, para comprobar que ninguna referencia ni anillo sintético coincide con uno real. Los hallazgos de abajo se conservan tal como se escribieron; las fixtures que citan son las respuestas originales, ya retiradas.

- **Protocolo:** WFS 2.0.0 (geometría) + servicio REST propio de Catastro (consulta no espacial por polígono/parcela).
- **Autenticación:** ninguna.
- **Formato de respuesta:** GML 3.2 / XML (WFS); XML propio (REST).
- **CRS nativo:** parcelas (`cp:CadastralParcel`) — DefaultCRS `EPSG:4326`, pero acepta y devuelve correctamente `EPSG:25830` si se pide explícito vía `srsname` + bbox en esa proyección. Edificios (`bu:Building`, `bu:BuildingPart`, `bu:OtherConstruction`) — DefaultCRS ya es `EPSG:25830` nativo.
- **Licencia:** licencia propia de Catastro INSPIRE v1.0 (julio 2016), `https://www.catastro.hacienda.gob.es/webinspire/documentos/Licencia.pdf` — **no** es "No conditions apply" (eso es el campo `Fees` del `GetCapabilities`). Prohíbe difundir la información original sin transformarla. Detalle en la sección "Fuentes del primer hito de caminos públicos" (historia 0021).
- **Estado:** `confirmado` (parcial — ver hallazgo pendiente abajo).

**Endpoints verificados:**

| Endpoint | URL base | Verificación |
| --- | --- | --- |
| WFS Cadastral Parcels | `https://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx` | `confirmado`. `GetCapabilities` → fixture `wfsCP_getcapabilities.xml` (respuesta original retirada en la historia #45). `GetFeature` con bbox real en EPSG:25830 sobre Colmenar de Oreja → fixture `wfsCP_getfeature_colmenar_bbox.xml` (respuesta original retirada en la historia #45), devuelve parcela real (`nationalCadastralReference=9900203ZZ0000S`) con geometría GML en EPSG:25830. |
| WFS Buildings | `https://ovc.catastro.meh.es/INSPIRE/wfsBU.aspx` | `confirmado` (cerrado en la historia 0002). `GetFeature` real con `typenames=bu:Building` y bbox pequeño (±100-200 m) centrado en un centroide de `Consulta_CPMRC`: funciona igual que `CadastralParcel` (fixture `wfsBU_colmenar_dense_bbox.xml`, respuesta original retirada en la historia #45; edificios reales con geometría, superficie `officialArea` y rango de fecha de construcción). **Detalle no documentado en `GetCapabilities`:** aunque se pide `typenames=bu:Building`, el elemento devuelto en la respuesta real usa el prefijo `bu-ext2d:Building` (espacio de nombres `bu-ext2d`, no `bu`) — el parsing debe buscar por nombre local del elemento (`Building`), no asumir el prefijo de la petición. |
| REST `Consulta_DNPPP` (datos no protegidos por polígono/parcela rústica) | `http://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCCallejero.asmx/Consulta_DNPPP` | `confirmado`. Petición real `Provincia=MADRID&Municipio=COLMENAR DE OREJA&Poligono=1&Parcela=1` → fixture `dnppp_colmenar_pol1_parc1.xml` (respuesta original retirada en la historia #45). Devuelve referencia catastral completa (`99043A901000010000AQ`), paraje (`CANTERAS`), uso (`Agrario`) y clase (`LABOR O LABRADÍO SECANO`). Confirma además el código de municipio Catastro para Colmenar de Oreja: `28043`. |
| REST `Consulta_CPMRC` (coordenadas por municipio + referencia catastral) | `http://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCCoordenadas.asmx/Consulta_CPMRC` | **Bloqueado** (`asumido`, no `confirmado`). Probado con la referencia rústica de 20 caracteres obtenida arriba → error `"LA REFERENCIA CATASTRAL DEBE SER DE 14 POSICIONES"` (fixture `cpmrc_colmenar.xml`, respuesta original retirada en la historia #45). Este servicio solo acepta el formato compacto urbano de 14 caracteres, no el formato rústico completo polígono/parcela de 20. |

**Hallazgo pendiente — RESUELTO en la historia 0002 (2026-10-15):** ninguno de los mecanismos de filtrado por atributo que expone este WFS funciona. Se probaron los tres candidatos anotados tras la historia 0001:

- **(a) `resourceId=ES.SDGC.CP.<localId>` con el `localId` INSPIRE de 14 caracteres** (confirmado por deducción: `pc1(7)+pc2(7)` sin `car`+checksum — p. ej. para `99043A901000010000AQ` → `99043A90100001`). **No funciona**: sin bbox, el servicio ignora `resourceId` y devuelve un conjunto por defecto de 83 features ajeno a la petición (fixture `wfsCP_getfeature_by_resourceid.xml`, respuesta original retirada en la historia #45; idéntico byte a byte al intento fallido de `CQL_FILTER` sin bbox de la historia 0001).
- **(b) `Filter` OGC estándar vía POST** en vez de `CQL_FILTER` por GET. **No funciona**: el servicio anuncia soporte POST en `GetCapabilities`, pero ignora por completo el cuerpo XML de la petición — con `REQUEST` solo en el cuerpo devuelve `"The parameter REQUEST can't be null"`; añadiéndolo también en la query string, devuelve `"At least one of the parameters TYPENAMES and RESOURCEID must be present in KVP-encoded Ad hoc queries"`, es decir, procesa la petición como KVP (GET) e ignora el body POST entero (fixture `wfsCP_getfeature_post_filter2.xml`, respuesta original retirada en la historia #45).
- **(c, variante real) Combinar el servicio REST de coordenadas con una búsqueda espacial de radio pequeño** — **confirmado como el método correcto, mejor que lo anticipado por la historia 0001.** Cadena verificada con evidencia real, para dos parcelas rústicas de los dos municipios del MVP más una tercera parcela adicional:
  1. **Normalizar** cualquier referencia catastral a su forma compacta de 14 caracteres: `pc1(7) + pc2(7)`, descartando `car` (4) y el checksum (2) del formato completo de 20. Para `99043A901000010000AQ` → `99043A90100001`.
  2. **`Consulta_CPMRC`** (`http://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/OVCCoordenadas.asmx/Consulta_CPMRC?Provincia=<provincia>&Municipio=<municipio>&RC=<refcat-14-caracteres>&SRS=EPSG:25830`) con la referencia de 14 caracteres (no la de 20 — con 20 caracteres este mismo servicio falla con `"LA REFERENCIA CATASTRAL DEBE SER DE 14 POSICIONES"`, fixture `cpmrc_colmenar.xml`, respuesta original retirada en la historia #45) **sí devuelve un centroide real** en el `SRS` pedido. Confirmado para:
     - Colmenar de Oreja, Polígono 1 Parcela 1 (`99043A90100001`) → `xcen=467588.74, ycen=4442023.74` (fixture `cpmrc_colmenar_14char.xml`, respuesta original retirada en la historia #45).
     - Villaconejos, Polígono 1 Parcela 1 (`99170A90100001`) → `xcen=454720.29, ycen=4441476.87` (fixture `cpmrc_villaconejos_14char.xml`, respuesta original retirada en la historia #45).
     - Colmenar de Oreja, parcela adicional del núcleo urbano (`99043A93700001`) → `xcen=456886.92, ycen=4436932.98` (fixture `cpmrc_colmenar_urbano_14char.xml`, respuesta original retirada en la historia #45).
  3. **`GetFeature` del WFS con un bbox pequeño** (±100-200 m) centrado en ese centroide, en `EPSG:25830`, devuelve un puñado de parcelas (no las 600+ de un bbox mayor); la parcela buscada está entre ellas y se identifica del lado del cliente comparando `nationalCadastralReference` con la referencia de 14 caracteres. Confirmado exacto para las dos rústicas: `99043A90100001` aparece como primer resultado (área 901 m², fixture `wfsCP_colmenar_rustica_por_centroide.xml`, respuesta original retirada en la historia #45) y `99170A90100001` aparece en el resultado de Villaconejos (fixture `wfsCP_villaconejos_rustica_por_centroide.xml`, respuesta original retirada en la historia #45).
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

**Hallazgo 1 — `GetFeature` con filtro espacial `BBOX` (KVP, sin `CQL_FILTER`) funciona exactamente igual que con Catastro/PNOA: `bbox=minx,miny,maxx,maxy,EPSG:25830`.** Verificado real sobre el bbox de la parcela rústica `99043A90100001` de Colmenar de Oreja (geometría real tomada de la fixture ya existente `tests/fixtures/catastro/wfsCP_colmenar_rustica_por_centroide.xml`, respuesta original retirada en la historia #45; bbox envolvente `(467550.15, 4442011.35, 467614.92, 4442037.4)` + margen de 2 m aplicado a mano con la misma fórmula que `domain.geometry.bbox_with_margin`) → `GET https://idem.comunidad.madrid/geoidem/UsoDelSuelo/wfs?service=WFS&version=2.0.0&request=GetFeature&typenames=VPLA_V_CLASIFICACION_REF_25&bbox=467548.15,4442009.35,467616.92,4442039.4,EPSG:25830` → `200 OK`, `numberMatched="1" numberReturned="1"` → fixture `wfs_getfeature_bbox_colmenar_rustica_margin2m.xml`. Esa parcela cae dentro de un único polígono de clasificación: `DS_CLASIF_GEN=Suelo No Urbanizable Común`.

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

**Hallazgo 3 — caso real de solape/colindancia entre clasificaciones distintas, encontrado con el bbox de la parcela rústica `99170A90100001` de Villaconejos (geometría real de `tests/fixtures/catastro/wfsCP_villaconejos_rustica_por_centroide.xml`, respuesta original retirada en la historia #45; margen de 2 m).** `GET .../wfs?...&bbox=454553.78,4441392.86,454827.45,4441584.42,EPSG:25830` → `200 OK`, `numberMatched="3" numberReturned="3"` → fixture `wfs_getfeature_bbox_villaconejos_rustica_margin2m_solape.xml`. Los 3 features reales:

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

### WMTS (visor, historia #85) — `confirmado`

Mapa base del visor estático (`site/config.js`, ADR 0037). Verificado por el arquitecto y de nuevo por el desarrollador el 2026-11-26, con peticiones reales (`User-Agent: parcel-intel-verificacion/0.1`).

- **Servicio:** WMTS 1.0.0 `https://www.ign.es/wmts/pnoa-ma`, capa `OI.OrthoimageCoverage`, estilo `default`, `tilematrixset=GoogleMapsCompatible` (EPSG:3857, el de Leaflet por defecto), `image/jpeg`, niveles 0-19.
- **Solo KVP:** el `GetCapabilities` declara `<ows:Value>KVP</ows:Value>` y no trae `ResourceURL` REST. Plantilla usada: `https://www.ign.es/wmts/pnoa-ma?service=WMTS&request=GetTile&version=1.0.0&layer=OI.OrthoimageCoverage&style=default&tilematrixset=GoogleMapsCompatible&format=image/jpeg&tilematrix={z}&tilerow={y}&tilecol={x}`.
- **Petición real:** `GetCapabilities` → 200 (116.001 bytes en la pasada del arquitecto; 112.782 bytes en la del desarrollador, fixture `tests/fixtures/pnoa/wmts_pnoa_ma_getcapabilities.xml`). `GetTile` z=15 x=16075 y=12392 → `200 image/jpeg`, 22.052 bytes, `geowebcache-tile-bounds` −377904,67 / 4880962,88 − −376681,68 / 4882185,87 (EPSG:3857), casco urbano de Colmenar de Oreja → fixture `tests/fixtures/pnoa/wmts_pnoa_ma_colmenar_z15.jpg` (no se publica en `site/`). z=19 también responde (`200 image/jpeg`).
- **Cabeceras útiles:** `access-control-allow-origin: *`, `cache-control: max-age=31536000`, servido por CloudFront. Sin clave ni `Referer`.
- **Licencia:** `ows:AccessConstraints` = `CC BY 4.0 scne.es`; `ows:Fees` = `No se aplican condiciones` (no es la licencia, lección 0021). La licencia es la del documento del IGN (`https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf`), CC BY 4.0, con atribución visible junto a los datos. No se encontró ninguna condición que limite su uso en un visor web público.
- **Atribución exacta** (tabla de productos del SCNE, `https://www.scne.es/tablaProductos.php`, leída en bruto el 2026-11-26). El servicio combina el PNOA de máxima actualidad a escalas grandes y el mosaico Sentinel-2 a escalas pequeñas:
  - fila «Ortofotos PNOA anuales», producto `PNOA`, fecha `2023` → `PNOA 2023 CC-BY 4.0 scne.es` (vuelo de julio de 2023 en el ámbito: `GetFeatureInfo` de `OI.MosaicElement` en Colmenar `467400,4441800,467800,4442200` EPSG:25830 → «Fecha 2023-07», repetido el 2026-11-26);
  - fila «MosaicoSentinel2», fecha `2018-2026` → `MosaicoSentinel2 2018-2026 CC-BY 4.0 ign.es`.
  Las teselas se muestran sin transformar, así que va la forma sin «Obra derivada de». El visor muestra las dos siempre.
- **IGN-Base** (`https://www.ign.es/wmts/ign-base`): desde la historia #185 se usa su capa `IGNBase-gris` como fondo cartográfico del visor (ver la sección siguiente). La ortofoto sigue siendo el otro fondo.
- **Caducidad del año:** la tabla del SCNE ya lista un vuelo PNOA 2024 con la Comunidad de Madrid entre los organismos, pero el servicio sigue sirviendo 2023-07 en Colmenar. Cuando cambie, el criterio `[integración]` CA10 de `tests/acceptance/test_historia_85.py` falla y hay que actualizar `NOTICE`, este registro y `site/config.js` juntos.

### WMTS IGN-Base gris (visor, historia #185, ADR 0051) — `confirmado`

Fondo cartográfico del visor para la vista de España y alternativa a la ortofoto. Verificado el 2026-11-27 con peticiones reales (`User-Agent: paso-comun-verificacion/0.1`).

- **Servicio:** WMTS 1.0.0 `https://www.ign.es/wmts/ign-base`, capa `IGNBase-gris` (título «Callejero gris»), estilo `default`, `GoogleMapsCompatible`, solo `image/jpeg`, niveles 0-20. Solo KVP. Plantilla: `https://www.ign.es/wmts/ign-base?service=WMTS&request=GetTile&version=1.0.0&layer=IGNBase-gris&style=default&tilematrixset=GoogleMapsCompatible&format=image/jpeg&tilematrix={z}&tilerow={y}&tilecol={x}`.
- **Peticiones reales:** `GetCapabilities` → 200, 150.325 bytes (fixture `tests/fixtures/ign_base/wmts_ign_base_getcapabilities.xml`; capas `IGNBase-gris`, `IGNBaseTodo`, `IGNBaseTodo-nofondo`, `IGNBaseOrto`, `IGNBaseSimplificado`). `GetTile` z=6 fila 24 col 31 (centro y sureste peninsular) → `200 image/jpeg`, 9.460 bytes (fixture `tests/fixtures/ign_base/wmts_ignbase_gris_z6.jpg`, no se publica en `site/`). z=15 sobre Colmenar → `200 image/jpeg`, 11.273 bytes; z=17 → 200. Un nombre que no existe (`IGNBaseTodo-gris`) da **400** `text/xml`, no una imagen.
- **Cabeceras:** `access-control-allow-origin: *`, `cache-control: max-age=31536000`. Sin clave ni `Referer`.
- **Licencia:** `ows:AccessConstraints` = `CC BY 4.0 scne.es` (`ows:Fees` = `No se aplican condiciones`, que no es la licencia, lección 0021). La licencia es la del documento del IGN (`https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf`), CC BY 4.0, con atribución visible junto a los datos.
- **Atribución:** la tabla de productos del SCNE (`https://www.scne.es/tablaProductos.php`, leída en bruto el 2026-11-27) **no lista IGN-Base** como producto; IGN-Base combina varios productos del SCNE. El visor muestra el identificador de la capa y la atribución declarada por el servicio, sin completar el formato del SCNE: `IGNBase-gris CC BY 4.0 scne.es`. Formato «<producto> <fecha> CC-BY 4.0 scne.es»: pendiente de verificar.
- **Conclusión:** **Publicar** (las teselas se muestran sin transformar), con esa atribución siempre visible mientras el fondo esté activo.
- **Rótulos sobre la ortofoto (`IGNBaseOrto`, «Callejero para imagen»)**: mismo servicio y licencia; PNG RGBA transparente con nombres de población, carreteras y su numeración. Peticiones reales del 2026-11-27: z=11 fila 774 col 1004 → `200 image/png`, 15.824 bytes; z=13 fila 3098 col 4018 (Colmenar de Oreja y la M-318) → 6.410 bytes (fixture `tests/fixtures/ign_base/wmts_ignbaseorto_z13.png`); z=15 sobre el casco → 7.311 bytes. Niveles 0-20 en `GoogleMapsCompatible`. El visor la pone encima de la ortofoto, en escala de grises (sus carreteras en naranja claro se confundirían con las vías pecuarias) y por debajo de los trazados. Atribución, con el mismo criterio que `IGNBase-gris`: `IGNBaseOrto CC BY 4.0 scne.es`.

### Imágenes de comparación (historia #120, ADR 0042) — `confirmado`

Verificación para el ADR 0042 (ventanas de un tramo y franjas de vuelo). Peticiones reales del 2026-11-26 con `User-Agent: parcel-intel-verificacion/0.1`, hechas por el arquitecto y repetidas por el desarrollador (`PNOA2023` y `PNOA2010`, 20:26 UTC) con el mismo resultado. Las respuestas **no se versionan**: las fixtures del adapter de ventanas las grabará su propia historia (ADR 0042 §8).

- **Ventana**: rural de Colmenar de Oreja, `bbox=467344,4441744,467856,4442256` (EPSG:25830, 512 m de lado), `width=height=1024` (0,5 m por píxel), `format=image/jpeg`, WMS 1.3.0.
- **URL canónica** (la que construye `CachedRawFetcher`, parámetros ordenados y codificados), probada tal cual: `https://www.ign.es/wms/pnoa-historico?bbox=467344%2C4441744%2C467856%2C4442256&crs=EPSG%3A25830&format=image%2Fjpeg&height=1024&layers=PNOA2023&request=GetMap&service=WMS&styles=&version=1.3.0&width=1024`. Las demás filas cambian solo `layers` (y la del servicio actual, la URL base `https://www.ign.es/wms-inspire/pnoa-ma`).

| Servicio y capa | Respuesta | Bytes | sha256 |
| --- | --- | --- | --- |
| `pnoa-historico` `PNOA2023` | 200 `image/jpeg`, empieza por `ff d8` | 243.158 | `a68b31370c9c6ab19329be1a712136698930262b824a823a29bbf54c88ea621b` (idéntico en las dos peticiones del arquitecto, con la URL canónica y en la repetición del desarrollador) |
| `pnoa-ma` `OI.OrthoimageCoverage` | 200 `image/jpeg` | 228.719 | no anotado |
| `pnoa-historico` `PNOA2017` | 200 `image/jpeg` | 167.525 | no anotado |
| `pnoa-historico` `PNOA2009` | 200 `image/jpeg` | 238.891 | no anotado |
| `pnoa-historico` `SIGPAC` | 200 `image/jpeg` | 155.801 | no anotado |
| `pnoa-historico` `OLISTAT` | 200 `image/jpeg` | 140.609 | no anotado |
| `pnoa-historico` `AMS_1956-1957` | 200 `image/jpeg`, caminos de 1956 visibles | 158.660 | no anotado |
| `pnoa-historico` `PNOA2010` (sin vuelo sobre Madrid) | 200 `image/jpeg`, imagen **blanca**, sin error | 6.427 | no anotado |
| `pnoa-historico` `PNOA2023`, ventana de 200 m `467500,4441900,467700,4442100` a 400 px | 200 `image/jpeg` | 41.968 | no anotado |

- **Respuestas sin cobertura**: el WMS no da error cuando el vuelo no cubre la ventana; devuelve una imagen blanca. `PNOA2010` a 1024 px pesa 6.427 bytes; la fixture ya existente `tests/fixtures/pnoa/getmap_colmenar_2004.jpg` (`PNOA2004`, 512 px) es también blanca, de 1.819 bytes. Bytes por píxel: imágenes blancas 0,0061–0,0069; imágenes reales 0,061–0,262 (la más baja, el AMS a 512 px de la fixture de parcela, 16.099 bytes). De ahí el umbral `< 0,02` bytes por píxel del ADR 0042 §3. Los vuelos `Interministerial_1973-1986` y `Nacional_1981-1986` dan un `GetMap` transparente de 334 bytes (sección «PNOA — vuelos reales sobre el ámbito»).
- **Cabeceras** de `pnoa-historico` (`GetMap` de `PNOA2023`): `content-type: image/jpeg`, `access-control-allow-origin: *`, `cache-control: max-age=31536000`, `expires` a un año, servido por CloudFront (`x-cache`, `via`). Sin clave ni `Referer`. Un `<img>` no necesita CORS; si se dibujase en un `canvas`, también valdría.
- **Capas**: el `GetCapabilities` histórico (fixture `wms_pnoa_historico_getcapabilities.xml`) trae, además de `PNOA2004`…`PNOA2024`, `AMS_1956-1957`, `Interministerial_1973-1986` y `Nacional_1981-1986`, las capas `SIGPAC` y `OLISTAT`, que se usan en la franja 1997-2003.
- **Atribuciones literales del SCNE** de cada vuelo usado (tabla de productos, `https://www.scne.es/tablaProductos.php`, leída en bruto el 2026-11-26). Con la imagen remuestreada y el trazado encima, el visor y el dossier las muestran precedidas de «Obra derivada de» (ADR 0042 §5):
  - `Orto-AMS 1956-1957 CC-BY 4.0 ejercito.defensa.gob.es` — **el AMS no es del IGN**: su atribución nombra al Centro Geográfico del Ejército de Tierra;
  - `Orto-SIGPAC 1997-2003 CC-BY 4.0 scne.es`;
  - `Orto-OLISTAT 1997-1999 CC-BY 4.0 scne.es`;
  - `PNOA 2006 CC-BY 4.0 scne.es`, `PNOA 2009 CC-BY 4.0 scne.es`, `PNOA 2011 CC-BY 4.0 scne.es`, `PNOA 2014 CC-BY 4.0 scne.es`, `PNOA 2017 CC-BY 4.0 scne.es`, `PNOA 2020 CC-BY 4.0 scne.es` y `PNOA 2023 CC-BY 4.0 scne.es`.
- **Fixtures del adapter de ventanas (historia #124)**, grabadas el 2026-11-26 con `User-Agent: parcel-intel-verificacion/0.1` en `tests/fixtures/pnoa/`. Ventana de 224 m de Colmenar de Oreja, `bbox=469928,4439888,470152,4440112` (EPSG:25830), `width=height=448`, mismos parámetros que la URL canónica de arriba (cambia `layers`):

  | Fixture | Capa | Respuesta | Bytes | Bytes/píxel |
  | --- | --- | --- | --- | --- |
  | `window_224_pnoa2023.jpg` | `PNOA2023` | 200 `image/jpeg` | 44.674 | 0,223 |
  | `window_224_ams.jpg` | `AMS_1956-1957` | 200 `image/jpeg` | 27.053 | 0,135 |
  | `window_224_sigpac.jpg` | `SIGPAC` | 200 `image/jpeg` | 32.908 | 0,164 |
  | `window_224_pnoa2010_blanca.jpg` | `PNOA2010` (sin vuelo) | 200 `image/jpeg`, **blanca** | 1.459 | 0,0073 |
  | `window_capa_inexistente_serviceexception.xml` | `NOEXISTE` | 200 `text/xml`, `ServiceException code="LayerNotDefined"` | 554 | — |

  Un `ServiceException` llega con **200**, no con un error HTTP: solo la cabecera JPEG lo distingue. `OLISTAT` no tiene fixture propia (la ventana no se pidió); el test de #124 lo sirve con la de `SIGPAC` y solo comprueba que el vuelo se acepta. CA8 de #124 (`PNOA2023` real, `PNOA2010` sin cobertura) pasó contra la red real el 2026-11-26.
- **PNOA en PNG para la evidencia de trazados históricos (historia #140, ADR 0043)**, `confirmado` el 2026-11-26 con `User-Agent: parcel-intel-verificacion/0.1`. Sin Pillow no se lee JPEG, así que el panel de PNOA se pide a `pnoa-ma` en PNG (el `pnoa-historico` da 502 en PNG).
  - **URL canónica** (la que construye `CachedRawFetcher`, parámetros ordenados y codificados; es la ventana de `T003` de la unidad sintética `280075-w1`): `https://www.ign.es/wms-inspire/pnoa-ma?bbox=466400%2C4439749%2C467201%2C4440453&crs=EPSG%3A25830&format=image%2Fpng&height=352&layers=OI.OrthoimageCoverage&request=GetMap&service=WMS&styles=&version=1.3.0&width=400`.
  - **Respuesta**: `200 image/png`, **369.049 bytes**, sha256 `5134e3f3a768c2f471566ad5a4bcab9f963b24ee8aa66ff63128ca5fc995c063`, 400 × 352 px. **Tipo de color 2 (RGB), 8 bits por canal, no entrelazado**, todas las filas con filtro 0 y 47 bloques `IDAT`; el decodificador propio (`adapters/evidence/png.py`) la lee. Es la fixture `tests/fixtures/caminos/planimetrias/historico/pnoa_ma_280075-w1_T003.png`. La primera prueba (200 × 200 px, `466200,4439450,466400,4439650`) dio 104.085 B.
  - CA10 de #140 (`pytest -m integration tests/acceptance/test_historia_140.py`) vuelve a pedirla a la red real y la decodifica.
  - Atribución de la evidencia: `Obra derivada de PNOA 2023 CC-BY 4.0 scne.es` (ADR 0043), con licencia `CC BY 4.0`.
- **Sin fuentes nuevas ni licencias nuevas**: todo es PNOA (actual e histórico), CC BY 4.0, ya en la tabla resumen de licencias, que no cambia (`NOTICE`, historia #43). `NOTICE` recogerá estas atribuciones cuando se publique la primera imagen (#103).

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

**Hallazgo 1 — bbox de la parcela rústica real de Colmenar de Oreja (`99043A90100001`, margen 2 m, mismo bbox ya usado por IDEM en la historia 0011): resultado "sin afección", legítimo.** `GET .../items?bbox=467548.15,4442009.35,467616.92,4442039.4&bbox-crs=EPSG:25830&crs=EPSG:25830` → `200 OK`, `numberMatched=0, numberReturned=0` → fixture `features_watercourse_colmenar_rustica_margin2m_sin_afeccion.json`. Ningún curso de agua a menos de 2 m de esta parcela — resultado real, no forzado, coherente con que es una parcela de secano alejada de cualquier río/arroyo cartografiado.

**Hallazgo 2 — bbox de la parcela rústica real de Villaconejos (`99170A90100001`, margen 2 m, mismo bbox que IDEM): resultado POSITIVO real, no un caso de laboratorio.** `GET .../items?bbox=454553.78,4441392.86,454827.45,4441584.42&bbox-crs=EPSG:25830&crs=EPSG:25830` → `200 OK`, `numberMatched=1, numberReturned=1` → fixture `features_watercourse_villaconejos_rustica_margin2m_barranco_montero.json`. El curso de agua encontrado: **`nombre="Barranco del Montero"`**, `id_demarc="ES030"` / `id_demarcd="Tajo"` (**la misma demarcación hidrográfica del Tajo citada textualmente en `docs/vision.md`** como ejemplo de la regla `within_distance` → `requires_authorization`), `ancho_min="1"` (metro), geometría `LineString` real. Esta es la misma parcela que la historia 0011 (IDEM) ya había encontrado en el borde de dos clasificaciones de suelo y dos municipios (Villaconejos/Chinchón) — ahora confirma, además, estar a menos de 2 m de un cauce real con nombre, sentando la base empírica exacta que `docs/vision.md` pedía para la regla de ejemplo.

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

**Hallazgo 4 — bbox real sobre las dos parcelas del MVP: "sin vía pecuaria cerca" en ambas, resultado real y legítimo, no un artefacto del margen de 2 m.** `GET .../wfs?...&bbox=467548.15,4442009.35,467616.92,4442039.4,EPSG:25830` (parcela rústica `99043A90100001` de Colmenar de Oreja, mismo bbox ya usado por IDEM/`UsoDelSuelo` y por cursos de agua) → `200 OK`, `numberMatched="0"` → fixture `wfs_getfeature_bbox_colmenar_rustica_margin2m_sin_afeccion.xml`. `GET .../wfs?...&bbox=454553.78,4441392.86,454827.45,4441584.42,EPSG:25830` (parcela rústica `99170A90100001` de Villaconejos) → idéntico, `numberMatched="0"` → fixture `wfs_getfeature_bbox_villaconejos_rustica_margin2m_sin_afeccion.xml`. **Confirmado que no es un margen demasiado pequeño**: calculando la distancia real desde el centroide de cada parcela (mismos centroides ya usados por Catastro, `Consulta_CPMRC`) hasta el punto más cercano de cada uno de los 17 tramos reales del hallazgo 2 (aproximación por puntos de la polilínea, no por distancia exacta punto-a-polígono), el tramo más cercano a Colmenar de Oreja está a ≈2,39 km (`"Vereda del Cristo"`) y el más cercano a Villaconejos está a ≈2,25 km (`"Vereda del Raso"`) — ambas muy por encima de cualquier margen razonable de punto flotante. Es un resultado real: las dos parcelas de referencia del MVP, elegidas en la historia 0001 por su simplicidad catastral, simplemente no están cerca de ninguna vía pecuaria cartografiada.

**Hallazgo 5 — prueba positiva real de que el servicio sí tiene datos ricos, para no confundir "sin vía pecuaria cerca de las dos parcelas del MVP" con "la capa está vacía o es pobre".** Los municipios completos de Colmenar de Oreja y Villaconejos sí tienen tramos reales (15 y 2 respectivamente, hallazgo 2) y la Comunidad de Madrid completa tiene **1694 features reales** en esta capa (confirmado con `GetFeature&resultType=hits` sin filtro, sin descargar el contenido completo). El `Abstract` real del `GetCapabilities` del WMS (`Title="Red de Vías Pecuarias de la Comunidad de Madrid"`) cita explícitamente la norma de origen: *"Ley 8/1998, de 15 de junio, de Vías Pecuarias de la Comunidad de Madrid"* y confirma textualmente *"el territorio de la Comunidad de Madrid es atravesado por cuatro cañadas reales, además de por gran número de otras vías pecuarias (cordeles, veredas y coladas)"* — cita que confirma independientemente la taxonomía de cuatro tipos ya anticipada por la historia, aunque el campo real (`DS_TIPO`) tenga también los tres valores anejos no legales ya señalados en el hallazgo 1.

---

## Vías pecuarias por municipio del ámbito — recorte con los límites del IGN (historia #36)

Verificado el 2026-11-26. Las 7 respuestas reales de IDEM por bbox del término de cada municipio (margen 2 m, EPSG:25830, mismo KVP que arriba) están en `tests/fixtures/livestock_trails/wfs_getfeature_bbox_municipio_<ine>.xml`. Los límites son los de la fixture recortada del IGN (`caminos/ign_au_ambito_7_municipios.xml`, sección "Límites municipales"). Los números salen de `ShapelyPolygonClipper` con esos datos, no de un cálculo a mano (lección 0017).

| INE | Municipio | `numberMatched` del bbox | Piezas no vacías tras recortar |
| --- | --- | --- | --- |
| 28043 | Colmenar de Oreja | 32 | 19 |
| 28013 | Aranjuez | 33 | 25 |
| 28052 | Chinchón | 47 | 23 |
| 28019 | Belmonte de Tajo | 1 | 0 |
| 28170 | Villaconejos | 11 | 4 |
| 28180 | Villarejo de Salvanés | 14 | 7 |
| 28157 | Valdelaguna | 10 | 1 |

- **El bbox trae vecinos**: los 7 bbox devuelven 94 tramos distintos (por `CD_VP`), de los que 27 no tocan ningún término del ámbito (Titulcia y otros municipios colindantes). Recortar es lo que los descarta. Total de piezas: 79.
- **Tramos con más de una pieza** (cruzan dos o tres términos del ámbito): 11 de 94. Todos los tramos del ámbito de la fixture CQL (los 15 de Colmenar y los 2 de Villaconejos) tienen al menos una pieza no vacía.
- **Astillas** (áreas de las 79 piezas): mínimo 0,009 m², mediana 21 817,33 m², máximo 627 295,18 m². Menores de 1 m²: 12; menores de 10 m²: 12; menores de 100 m²: 13. Son la diferencia entre la línea municipal que usó IDEM al partir cada vía y la del IGN. No se filtran (umbral de publicación pendiente con el fundador, ADR 0032).
- **Tramo real elegido para el test de dos municipios**: `2801308`, "Vereda de Colmenar" (`MultiSurface` de 2 partes). Área del original 106 767,37 m²; pieza en Colmenar de Oreja 8 020,96 m² (1 anillo); pieza en Aranjuez 98 746,41 m² (3 anillos); suma igual al original con diferencia < 0,01 m². No cae en ningún otro municipio del ámbito.
- **Guarda de truncado**: cada respuesta de IDEM trae `numberMatched`; si no coincide con las features parseadas, el adapter lanza `IncompleteWfsResponseError` y no cachea. Las 7 respuestas reales cumplen la guarda (CA5 de #36, integración).
- **Licencia**: `CC BY 4.0 Comunidad de Madrid`, leída de `AccessConstraints` (sección anterior); el adapter ya la rellena en `Provenance.license`.

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

**Hallazgo 3 — las tres geometrías reales probadas (incluida la vivienda real del fundador) caen dentro del mismo plan de gestión, en su zona genérica (no de conservación prioritaria).** `GET .../wfs?...&bbox=467548.15,4442009.35,467616.92,4442039.4,EPSG:25830` (parcela rústica `99043A90100001`, Colmenar de Oreja) → `200 OK`, `numberMatched="1"` → fixture `wfs_getfeature_bbox_colmenar_rustica_margin2m.xml`. `GET .../wfs?...&bbox=458114.6,4436581.5,458146.0,4436630.0,EPSG:25830` (parcela urbana real `9900204ZZ0000S0001OK`, vivienda real del fundador, Colmenar de Oreja) → idéntico resultado → fixture `wfs_getfeature_bbox_colmenar_urbana_margin2m.xml`. `GET .../wfs?...&bbox=454553.78,4441392.86,454827.45,4441584.42,EPSG:25830` (parcela rústica `99170A90100001`, Villaconejos) → idéntico resultado → fixture `wfs_getfeature_bbox_villaconejos_rustica_margin2m.xml`. **Las tres devuelven el mismo feature real**: `CD_PLAN="SE"` (*"Plan de gestión de vegas, cuestas y páramos del sureste de Madrid..."*), `CD_ZONA="X"` (*"Espacio previamente ordenado/zonificado... no es necesario establecer una zonificación específica"* — la categoría menos restrictiva del esquema de zonificación, distinta de `"Zona A: Conservación Prioritaria"` observada en el hallazgo 1 para otro plan). Resultado real y legítimo, no forzado: confirma que todo el territorio de los dos municipios del MVP (y la vivienda real del fundador) está dentro del área de gestión Red Natura 2000 regional, pero en su categoría de menor restricción, no en una zona de conservación prioritaria.

**Hallazgo 4 — geometría real multi-parte CON anillos interiores reales (huecos), a diferencia de vías pecuarias (historia 0014) y más parecido a IDEM/`UsoDelSuelo` (historia 0011).** La geometría del plan `"SE"` (el feature real que cubre las tres geometrías de prueba) es un `gml:MultiSurface` con **5 `gml:Polygon`/`gml:surfaceMember` reales y 2 `gml:interior` reales** (huecos dentro de alguno de esos 5 polígonos) — confirmado contando explícitamente las etiquetas reales (no solo líneas que las contienen: el XML real viene minificado en una sola línea, `grep -c` sin `-o` habría dado un falso "1" en vez del conteo real; verificado con `grep -o '<gml:interior>' | wc -l`, mismo cuidado que ya exigió la lección de la historia 0011). **Esta fuente sí necesita el mismo patrón de parser que IDEM/`UsoDelSuelo`** (tomar solo `gml:exterior`, descartar `gml:interior`) — nunca asumir, solo porque comparte workspace y técnica de descubrimiento con vías pecuarias, que también comparte su forma de geometría (que resultó ser el caso simple, sin huecos). Cada fuente geoespacial se verifica por sí misma, incluso dentro del mismo servidor.

**Hallazgo 3.1 — CORRECCIÓN del hallazgo 3, encontrada por el arquitecto al diseñar la historia 0018 (motor de reglas, regla de solape): "mismo feature devuelto por `BBOX`" NO equivale a "solape geométrico real" para esta capa concreta.** El hallazgo 3 afirmaba que las tres geometrías de prueba "están dentro" del plan `SE`/`X` basándose solo en que el WFS devolvía el mismo feature para las tres bboxes de consulta. Verificado con geometría real (parsers ya existentes sobre las fixtures ya citadas, cruzado con `shapely` como control independiente, ver `docs/adr/0018-solape-poligono-poligono-vias-pecuarias-red-natura-hallazgo-bbox-laxo.md`): la parcela rústica de Villaconejos (`99170A90100001`) está realmente a **1363.16 m** del polígono real más cercano de la zona; la rústica de Colmenar de Oreja (`99043A90100001`) está a **8329.95 m**. **Ninguna de las dos solapa de verdad.** Causa raíz confirmada: el filtro `BBOX` de OGC Filter Encoding que usa este WFS evalúa la envolvente (bounding box) de la geometría completa del feature, no su geometría real — y el feature `SE`/`X` es un `MultiSurface` de 5 polígonos reales dispersos en un área de ~46×41 km (hallazgo 4), cuya envolvente combinada cubre trivialmente cualquier bbox pequeño dentro de esa región aunque el polígono más próximo esté a más de 1 km. No se ha podido verificar el caso de la vivienda urbana real del fundador (`9900204ZZ0000S0001OK`) con geometría real porque ninguna fixture del repositorio contiene su geometría catastral — queda pendiente de verificación en vivo contra el servidor real. **Lección para cualquier fuente futura que use un filtro espacial `BBOX` (no `Intersects`) de OGC Filter Encoding**: no asumir que "el WFS devolvió este feature" implica solape/proximidad real, sobre todo si el feature es un `MultiSurface` disperso — confirmarlo siempre con geometría real antes de documentarlo como hallazgo.

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

### Límites municipales — IGN unidades administrativas — `confirmado`

Historia #35, ADR 0030. Petición real repetida el 2026-11-26 (la primera, el 2026-11-25): `GET https://www.ign.es/wfs-inspire/unidades-administrativas?service=WFS&version=2.0.0&request=GetFeature&typeNames=au:AdministrativeUnit&bbox=39.98,-3.62,40.22,-3.15,urn:ogc:def:crs:EPSG::4258&count=200` → `200`, 27 MB, `numberMatched=32`, `numberReturned=32`. Recorte de esa respuesta en `tests/fixtures/caminos/ign_au_ambito_7_municipios.xml` (cabecera + los 7 municipios del ámbito + Titulcia; `numberMatched`/`numberReturned` reescritos a 8, y así lo dice el comentario XML del fichero).

- **Orden de ejes**: `bbox` con `urn:ogc:def:crs:EPSG::4258` va en **latitud, longitud**, y `posList` también (`39.322647 -2.663458`). Con el bbox en EPSG:25830 el orden es E,N (nota de #29, probado el 2026-11-25: en N,E devuelve `numberMatched=0` sin error).
- **Nivel**: los municipios son `nationalLevel` `…/AdministrativeHierarchyLevel/4thOrder`; provincia y comunidad (`3rdOrder`, `2ndOrder`, `1stOrder`) vienen en la misma respuesta y se descartan.
- **Código INE**: `au:nationalCode` tiene 11 dígitos; el INE son los 5 últimos (`34132828043` → `28043`). El nombre es el primer `gn:text`.
- **Geometría**: `gml:MultiSurface` con un único `gml:Polygon` y **ningún `gml:interior`** en los 7 municipios del ámbito (contado con `grep -o`, no `grep -c`); sí hay `gml:interior` en la Comunidad de Madrid y en la provincia (niveles 2.º y 3.º).
- **Sin huecos entre los 7**: Colmenar de Oreja y Villaconejos comparten 38 vértices exactos en EPSG:4258 y siguen compartiendo 38 tras reproyectar a EPSG:25830 con un único `Transformer` de `pyproj`, sin `always_xy` (entrada `(lat, lon)`).
- **Licencia**: `CC BY 4.0 ign.es`, la declarada en el `GetCapabilities` y en las condiciones de uso del IGN (sección «Detalle de licencias»). Atribución al publicar: la de esa sección.
- **Ámbito**: 28043, 28013, 28052, 28019, 28170, 28180, 28157.
- **Límite municipal ≠ linde catastral**: la parcela 99170A90100001 (Catastro) tiene 7 de sus 72 vértices fuera del término de Villaconejos según el límite del IGN (65 dentro). El vértice noroeste de su bbox cae a 106,5 m dentro de Chinchón. Los dos son geometrías oficiales distintas: no usar el bbox de una parcela como prueba de pertenencia a un término.

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
  - **Consecuencia:** el mapa no puede servir las parcelas catastrales tal cual. Sí puede publicar una capa propia derivada (p. ej. "trazado de camino inferido", que combina la geometría de las parcelas `VT` con otras fuentes), con un nombre que no la confunda con cartografía catastral. Si basta con simplificar o filtrar para que cuente como "transformación" en el sentido del artículo 21 de la Ley de Propiedad Intelectual es una cuestión jurídica abierta: **consultar antes de publicar** esa geometría. Lo derivado que no reproduce la información original (indicios, señales y candidatos sobre un trazado) sí se publica, con fuente, fecha de consulta y aviso de no fehaciencia (ADR 0041).
- **Catastro, servicios web de datos no protegidos (`Consulta_DNPPP` y demás de la OVC)** — su ficha de datos.gob.es remite como "Condiciones de uso" a `https://www.catastro.hacienda.gob.es/pdf/ovc/licdescargaES.pdf`, la "Licencia de descarga de productos catastrales" (PDF de 2011, leída el 2026-11-26). Dice lo mismo que la licencia INSPIRE: no se autoriza el uso público ni la difusión de la información original (cláusula 5), y en ningún caso se puede difundir por Internet sin transformarla (cláusula 8). Sí se permite el uso público de la información transformada, citando a la Dirección General del Catastro y la fecha de acceso (cláusula 12). Ante un incumplimiento, Catastro primero requiere que cese el uso, con un plazo de 10 a 15 días; si no se atiende, revoca la licencia y puede aplicar el régimen sancionador del art. 11 de la Ley 37/2007 (cláusulas 26 y 27).
- **Discrepancia en los catálogos:** el registro de metadatos de IDEE para las parcelas INSPIRE (`ES_SDGC_CP`) declara "CC BY 4.0 DG Catastro", pero también "otras restricciones". La página INSPIRE de Catastro sigue enlazando la licencia v1.0 de 2016, sin mención a CC BY. Mientras Catastro no lo confirme, manda su propia licencia.
- **Consecuencia para el repo:** las 27 fixtures crudas de `tests/fixtures/catastro/` y `tests/fixtures/caminos/catastro_*` son información original. Por las dos licencias, no pueden quedar accesibles en un repo público. Se sustituyen por fixtures sintéticas (#45) y se purgan del historial (#44, `docs/runbook-publicacion.md`).
- **Vías pecuarias (IDEM)** — el `GetCapabilities` WMS 1.3.0 del workspace `Zonas` (`idem_zonas_wms_getcapabilities.xml`) declara `AccessConstraints` = `CC BY 4.0 Comunidad de Madrid` y `Fees` = `NONE`. La ficha de datos.gob.es (`datosgob_vias_pecuarias_madrid.json`) no trae campo de licencia. El PDF del inventario de vías pecuarias (enero de 2023) que daba la búsqueda web devuelve 404, y su copia indexada lleva el aviso "DATOS CON CARÁCTER EXCLUSIVAMENTE INFORMATIVO". El mapa tiene que repetir ese carácter informativo.

### Catastro — cómo aparecen los caminos en rústico — `confirmado`

> Las respuestas crudas de esta verificación se retiraron del repo y de su historial el 2026-11-26, porque las licencias de Catastro prohíben difundirlas sin transformar (ADR 0040). Lo comprobado sigue descrito aquí; para repetirlo hay que volver a consultar los servicios.

La verificación real se hizo contra el servicio el 2026-11-25 (historia 0021): un `GetFeature` al WFS de parcelas sobre 600×600 m de rústico en Colmenar devolvió 51 parcelas. Los caminos son **parcelas propias con número 9000 o superior** dentro de cada polígono (cuatro en esa ventana). `Consulta_DNPPP` sobre cada una devuelve una subparcela de clase **`VT` — "VÍA DE COMUNICACIÓN DE DOMINIO PÚBLICO"** y su superficie; la parcela de control (la 1 del polígono 1) da en cambio `C-` "LABOR O LABRADÍO SECANO". Además, `areaValue` del WFS y `ssp` de DNPPP **pueden diferir** en un mismo camino (en el dato real, 8.595 frente a 8.604 m² en uno de ellos).

**Fixtures sintéticas de caminos (historia #46, anexo del ADR 0033).** Las respuestas originales de esa verificación se retiraron del árbol. Las sustituyen seis fixtures **sintéticas** en `tests/fixtures/caminos/`, con el mismo esquema que las reales y datos inventados (municipio 28043, polígonos reservados `991` y `992`, ventana de 600×600 m con origen (469000, 4439000) en EPSG:25830, teselado de 20 rectángulos con un anillo horario por parcela):

- `tests/fixtures/caminos/catastro_wfsCP_sintetica_rustica_bbox600m.xml` (WFS, 20 parcelas, cuatro con número ≥ 9000);
- `tests/fixtures/caminos/catastro_dnppp_sintetica_pol991_parc1.xml` (control, `C-`);
- `tests/fixtures/caminos/catastro_dnppp_sintetica_pol991_parc9101.xml`, `…_pol991_parc9102.xml`, `…_pol992_parc9201.xml` y `…_pol992_parc9202.xml` (`VT`).

`ssp` de las parcelas 9101 (6011) y 9201 (3024) difiere de su `areaValue` en la WFS (6000 y 3000), como en el dato real. Se generan con `tests/fixtures/generate_caminos.py` y se regeneran con el mismo comando de arriba (`uv run python -m tests.fixtures.generate_catastro`, que también escribe `caminos/`; `--check` comprueba ambos directorios). Los casos con huecos, multiparte o clase `HG` se añaden como filas nuevas del generador (`render_dnppp`), no como respuestas grabadas. Las huellas SHA-256 de las 51 referencias y de todos los vértices originales están en `tests/fixtures/catastro_huellas_reales.json`.

- Implicación: el filtro "camino según Catastro" es `parcela ≥ 9000` más la clase `VT`, que se comprueba contra `Consulta_DNPPP` (el WFS no trae el uso).
- Límite: Catastro **no prueba la titularidad** (la propia licencia dice que la información carece de fehaciencia). Un camino que no figura como `9xxx` no queda descartado como público, y al revés.
#### Arroyos (`HG`) frente a caminos (`VT`) en parcelas 9xxx — `confirmado` (historia #28, 2026-11-26)

Verificación real, hecha con un script local que **no guarda respuestas** (ni en git ni en `tests/fixtures/`; decisión del fundador en #2 y #28) y que solo anota clase y paraje, sin referencias catastrales de fincas. Para cada cauce de la colección `watercourse` de IDEE (OGC API Features, la misma del adapter `hydrography`) dentro de un bbox, se muestrearon puntos de su traza, se pidió al WFS de parcelas un bbox de 200 m en cada punto, se quedaron las parcelas con número ≥ 9000 del ámbito y se consultó `Consulta_DNPPP` de cada una (`Provincia`, `Municipio`, `Poligono`, `Parcela`).

- **Colmenar de Oreja** (bbox 465000,4438000–472000,4445000 en EPSG:25830; 36 cauces; 47 parcelas ≥ 9000 junto a cauces, incluidas las de términos vecinos que entran en la ventana: Valdelaguna, Belmonte de Tajo, Villarejo de Salvanés, Chinchón). Predomina `VT` (parajes `CAMINO`, `DESCUENTO`, `NO INFORMADO`, carreteras y cañadas). El arroyo aparece solo una vez como `HG — HIDROGRAFÍA NATURAL (RÍO,LAGUNA,ARROYO.)` (paraje `CERROS D`). **Otras clases que no son `VT` ni `HG`:** `I- IMPRODUCTIVO` (doce parcelas; parajes como `REGUERO`, `ARROYO DEL HORCAJO` pero también `CAMINO`, `CR VALDELAGUNA`), y `HC HIDROGRAFIA CONSTRUIDA (EMBALSE,CANAL..)` en una acequia en una prueba previa con la ventana sin filtrar por municipio.
- **Villaconejos** (bbox 450000,4436000–460000,4446000; 50 cauces; 46 parcelas ≥ 9000): **el patrón se repite y es más claro.** Catorce parcelas son `HG` con paraje `ARROYO`, `ARROYO DEL VALLE`, `BARRANCO DE PERNISTELA`, `BARRANCO DEL MOJON`, `RIO JARAMA` o `NO INFORMADO`, frente a 21 de `VT` (parajes `CAMINO`, `CAÑADA…`, carreteras, `DESCUENTO`, `NO INFORMADO`). Hay además parcelas ≥ 9000 con cultivos ordinarios (`C-`, `CR`, `MM`, `E-`, `I-`, hasta seis subparcelas), así que el número ≥ 9000 por sí solo no basta.
- **Regla verificada:** una parcela ≥ 9000 es camino solo si todas sus subparcelas son `VT`. Un arroyo con parcela propia sale como `HG` (a veces `I-` o `HC`), no como `VT`. El filtro es `es_camino` / `es_camino_catastro` en `adapters/catastro/camino.py`; el parseo de `Consulta_DNPPP` (clase, descripción, paraje, superficie), `parse_dnppp` en `adapters/catastro/parsing.py`.
- **Límites:** (1) el **paraje no sirve para clasificar**: hay `VT` con paraje `DESCUENTO` o `NO INFORMADO`, `HG` con `NO INFORMADO` e `I-` con `CAMINO`; manda la clase. (2) `I-` improductivo con paraje `CAMINO` indica que algún camino cartografiado como parcela 9xxx **no** sale como `VT`; el filtro `VT` los deja fuera, y eso es un falso negativo conocido. (3) Un arroyo con parcela propia **no prueba titularidad** (ni pública ni privada); Catastro carece de fehaciencia. (4) El servicio devuelve la `Ñ` de los parajes mal codificada (`CA¥ADA`): no se debe comparar texto de paraje por igualdad. (5) La muestra es de una ventana por municipio y no es un censo; no se contó por término.
- **Canales consultados:** WFS de parcelas de Catastro, `Consulta_DNPPP` y la colección `watercourse` de IDEE, todos leídos con éxito. No se consultó el catálogo de usos del Catastro para saber si existen más clases `H*`.

#### Capa interna de caminos de Catastro (historia #37) — `confirmado` (2026-11-26)

Comando `catastro-caminos` para Colmenar de Oreja (`28043`), con el bbox del término del WFS de unidades administrativas del IGN, EPSG:25830, ejes E,N: `449341, 4431623, 470702, 4442906` (redondeado hacia fuera al metro). Ejecutado en local por el fundador (el WFS de Catastro rechaza los runners de GitHub Actions: primero cortaba la conexión y después respondía HTTP 400. Por eso CA7 va marcado `fuera_de_ci`).

- **Pasada con red:** 312 teselas WFS de 900 m y 988 consultas `Consulta_DNPPP`, en 44 min 44 s. Una tesela del casco de Colmenar pesa unos 3,6 MB y tarda unos 45 s: el tiempo de lectura es de 180 s.
- **Hallazgo:** Catastro es incoherente. El WFS devuelve parcelas ≥ 9000 que `Consulta_DNPPP` no reconoce (`lerr`: «NO EXISTE NINGÚN INMUEBLE CON LOS PARÁMETROS INDICADOS»). Esas parcelas quedan como `unclassified`. La respuesta `lerr` es determinista y se cachea, para que `--sin-red` repita el resultado.
- **Resultado agregado** (pasada con red en verde el 2026-11-26, repetida el 2026-11-27 con reintentos ante cortes de red: los mismos números; la repetición `--sin-red` da la misma capa y no cambia la caché):
  - 12 452 parcelas del municipio vistas;
  - 988 con número ≥ 9000;
  - **505 caminos de clase `VT`**, con 424,0 ha en total;
  - 475 excluidas por tener otra clase;
  - 8 sin clasificar, por `lerr`.
  - El recuento de la pasada final con CA13 es 988; el «980» de un comentario anterior era el de la primera pasada (sin CA13).
- Geometría en teselas contiguas: **idéntica**. Comprobado en local el 2026-11-27: con dos bboxes solapados de 600 m en el casco, cada parcela que cruza el borde del primero llega con la misma geometría en los dos. El WFS no recorta al bbox, así que la deduplicación por referencia de CA3 es válida.

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

Verificado el 2026-11-25 para la [historia #17](https://github.com/murcialito/paso-comun/issues/17) (feature #11). Pregunta: ¿se pueden obtener la planimetría de Colmenar de Oreja (doc. 280075, 1875) y la hoja MTN50 0606 (1881) a una resolución útil, y georreferenciarlas? Datos en `tests/fixtures/caminos/planimetrias/` (`verificacion.json`, recortes de 1 km, procedencia de las imágenes completas y ficha del Centro de Descargas). Script puntual: `scripts/verificar_planimetrias.py`. Imágenes completas (ventana de 5×5 km, 2000×2000 px, 2,5 m/px) en `data/raw/ign_planimetrias/`, fuera de git, con su `*.provenance.json` (URL exacta, fecha, SHA-256, licencia).

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
| Unidad `280075-w1` de la fixture (historia #137): el `GetMap` de la ventana `466200,4439450,467200,4440450` a 500 × 500 px | `confirmado` | Verificado el 2026-11-26 con `User-Agent: parcel-intel-verificacion/0.1`: `200 image/png`, 428.157 B, sha256 `80222cbc…30dd1`, **idéntico** al del recorte versionado `planimetria_colmenar_280075_recorte_casco_2mpx.png`. El render es estable entre descargas. CA12 de #137 lo vuelve a comprobar (`pytest -m integration tests/acceptance/test_historia_137.py`); si algún día cambia, `RawImageMismatchError` es el comportamiento correcto |

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

Verificado el 2026-11-25 para la [historia #26](https://github.com/murcialito/paso-comun/issues/26) (feature #9, pendiente heredada de la historia 0021). Pregunta: para los 7 municipios del ámbito, ¿hay orden de clasificación y deslinde aprobados, y dónde se publican? **Respuesta corta: no se ha podido verificar para ninguno de los 7.** No es que no existan: el canal donde se publican (BOCM) no es consultable por búsqueda desde esta pasada. Las fixtures están en `tests/fixtures/caminos/`.

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
- Desde #94 (ADR 0044) la evidencia de la red de transporte aparece también en las fichas de los indicios publicados (`site/datos/discrepancias/`), con esta misma atribución de `NOTICE`: `SOURCE_POLICY["ign_red_transporte"]` pasa a verificada. No cambia ninguna conclusión de esta sección.

### Límites y canales no leídos

- El texto del PDF se leyó con la herramienta de lectura de PDF (imagen y texto de cada página) y se transcribió a `ign_licencia_condiciones_uso.txt` a mano. No hubo extracción mecánica del flujo de texto.
- El texto bruto del BOE no se pudo descargar (sin red desde la shell); solo hay extractos de `WebFetch`. Ver eslabón 3.
- `http://www.scne.es/productos.html` redirige a `productos.php`; la página no contiene la tabla. La tabla está en `tablaProductos.php`, que sí se leyó.
- La fecha `2026` es la de la tabla de productos. No es la fecha de los datos de `roadlink` (su `fecha_alta` va de 2017 a 2026, ver resumen).
- Para la atribución «Obra derivada de» se sigue el texto del criterio de la historia; no hay ninguna obra derivada publicada todavía que la muestre.

---

## Capa de camino actual por municipio — roadlink (historia #27)

Consulta real del **2026-11-26**, `https://api-features.idee.es/collections/roadlink/items` con `bbox` del término (límite del IGN, margen 2 m) en EPSG:25830, `bbox-crs` y `crs` EPSG:25830. Estado: `confirmado`. ADR 0034.

### Hallazgos de la consulta

- **Un término entero no cabe en una página.** Con el `limit=500` del adapter de #25 y sin filtro, `numberMatched` por término fue 3.996 (Colmenar), 19.557 (Aranjuez), 3.957 (Chinchón), 1.131 (Belmonte), 823 (Villaconejos), 2.938 (Villarejo) y 1.331 (Valdelaguna): casi todo asfaltado. La primera página de Valdelaguna traía 98 caminos sin asfaltar de los 552 reales.
- **El servidor filtra y pagina.** `filter=surfacecategory='unpaved'` (CQL por defecto) devuelve solo los sin asfaltar; `offset` y `limit` paginan; `limit=1000` se acepta. `numberMatched` con el filtro es coherente con la suma de las páginas.
- **Pasada completa** (límites del IGN + todas las páginas, recorte a cada término): tramos de `roadlink` sin asfaltar devueltos por el bbox → piezas dentro del término → de ellas ficticias → longitud total de las piezas:

| INE | Municipio | `numberMatched` | Piezas en el término | `fictitious="true"` | Longitud (m) |
| --- | --- | --- | --- | --- | --- |
| 28043 | Colmenar de Oreja | 1.774 | 893 | 893 | 384.707 |
| 28013 | Aranjuez | 5.522 | 1.486 | 1.486 | 542.153 |
| 28052 | Chinchón | 1.492 | 786 | 786 | 343.524 |
| 28019 | Belmonte de Tajo | 523 | 231 | 231 | 86.197 |
| 28170 | Villaconejos | 370 | 261 | 256 | 107.234 |
| 28180 | Villarejo de Salvanés | 1.446 | 725 | 725 | 354.040 |
| 28157 | Valdelaguna | 552 | 300 | 300 | 131.617 |

  Las cifras salen de ejecutar el propio adapter y `ShapelyLineClipper` sobre las respuestas reales, no de un recuento aparte (lección #36). La diferencia entre `numberMatched` y las piezas son tramos de vecinos que tocan el bbox pero no el término.
- **Casi todo el camino sin asfaltar del ámbito es `fictitious="true"`**: solo 5 tramos `false` en todo Villaconejos y ninguno en los otros seis municipios. El indicador se conserva en el fichero; qué significa para el visor es decisión de publicación.
- **Tramos que cruzan términos**: 151 tramos aparecen en dos o más capas. Casos fijados en los tests: `280430189746` (Colmenar 239,19 m + Chinchón 272,14 m = 511,32 m), multi-parte `281700231594` (Chinchón 3 partes, Villaconejos 2; 111,45 + 110,34 = 221,79 m) y uno en tres términos (`281570201255`).
- **Peso**: la pasada completa son ~60 MB de JSON (≈30 peticiones). Los fixtures de `tests/fixtures/road_network/roadlink_unpaved_recorte_municipio_<ine>.json` son **recortes** de la respuesta real (10-12 tramos por municipio: tramos que cruzan límite, ficticios, no ficticios y vecinos que no tocan el término; geometría y propiedades sin tocar; `numberMatched`/`numberReturned` ajustados). Cómo se obtuvieron está en el docstring de `tests/road_layer_fixtures.py`.

### Licencia y atribución

CC BY 4.0, confirmada en la historia #24 (sección anterior). El fichero derivado interno (`data/derived/camino_actual/`) lleva la atribución «Obra derivada de red de transporte IGN CC-BY 4.0 ign.es», texto fijado por el criterio CA4 de #27. El fichero derivado lleva además el aviso «cartografía informativa».

**Unificada al publicar (historia #84, ADR 0036)**: lo publicado en `site/datos/camino_actual/` lleva la atribución de `NOTICE`, «Obra derivada de IGR-RT 2026 CC-BY 4.0 Instituto Geográfico Nacional» (ADR 0035: lo que ve el público es `NOTICE`). El fichero derivado interno no cambia.

### Publicación en `site/datos/` (historia #84)

Ejecución real del 2026-11-26: `vias-pecuarias-municipios` y `camino-actual-municipios` con red, y después `publicar-capas --municipio 28043`. Recuentos iguales al oráculo (19 vías pecuarias, #36/#83; 893 tramos, #27). Desde #84 las procedencias del formato común llevan `redistribucion`; los ficheros derivados anteriores se leen como de uso interno y hay que regenerarlos (`--sin-red` basta).

| Fichero | Features | Bytes |
| --- | ---: | ---: |
| `site/datos/vias_pecuarias/28043.geojson` | 19 | 82 800 |
| `site/datos/vias_pecuarias/28043.geojson.procedencia.json` | — | 1 028 |
| `site/datos/camino_actual/28043.geojson` | 893 | 1 007 584 |
| `site/datos/camino_actual/28043.geojson.procedencia.json` | — | 1 244 |
| `site/datos/indice.json` | 1 municipio | 215 |
| `site/datos/indice.json.procedencia.json` | — | 205 |

Ningún fichero supera el umbral de simplificación (3 000 000 bytes). Belmonte de Tajo (28019) no tiene piezas de vías pecuarias, y su capa vacía no se publica (resuelto en #86, ADR 0036). El ámbito completo se publicó en #86: 13 capas, ninguna sobre el umbral.

### Candidatos a corte — fichero interno (historia #128)

`candidatos-corte` escribe `data/derived/candidatos/interno/<ine>.geojson` (EPSG:25830, fuera de git). **Deriva de Catastro** (parcelas del WFS de #37, licencia INSPIRE) y de las capas base de #94: es de **uso interno y no redistribuible**; la procedencia de cada señal (`redistribucion: solo_uso_interno`) viaja en el propio fichero. No lleva datos de titularidad, referencias catastrales ni geometría de parcela. Publicar candidatos es #103 y exigirá su propia redacción. Sin fuente nueva ni proveedor nuevo.

Verificación con datos reales de Colmenar de Oreja (CA12, `integration` + `fuera_de_ci`), **en verde** en local el 2026-11-27, con `data/` generada por `catastro-caminos` (41 min), `camino-actual-municipios` y `discrepancias --municipio 28043`. El fichero se genera y el lector lo reconstruye, pero el resultado aún no sirve:

- **0 candidatos**, sobre 17 registros base (discrepancias `SOLAPE` o `AUSENTE_EN_FUENTE` frente a la red del IGN).
- Señal `parcela_no_camino` en **`sin_datos`**: 59 teselas no están en la caché. `candidatos-corte` corta las teselas con otra rejilla, de origen fraccionario, que la de `catastro-caminos` (bbox redondeado del término).
- En `discrepancias` falta además la fuente `catastro_vt`, porque `catastro-caminos` no escribe `data/derived/catastro_caminos/<ine>.geojson`.

Las dos integraciones pendientes están en la #160.

### Integración de `catastro-caminos` con `discrepancias` y `candidatos-corte` (historia #160)

- `catastro-caminos` escribe ahora `data/derived/catastro_caminos/<ine>.geojson` (formato común de #32, `fuente: catastro_vt`, EPSG:25830, `redistribucion: solo_uso_interno`; un feature por camino con id `VT-0001…`, sin referencias catastrales; atómico). **Nunca se publica** (INSPIRE). Sin fuente nueva ni proveedor nuevo.
- La rejilla de teselas de un municipio es única: `municipality_tiles(bbox del límite del IGN, 900 m)`, con el bbox redondeado hacia fuera a metro entero (`domain/geometry.py`). Para Colmenar reproduce el bbox de #37 (`449341,4431623,470702,4442906`; origen `(449341, 4431623)`). Sin `--bbox`, `catastro-caminos` lo toma del límite del IGN; con `--bbox` se respeta y se imprime la rejilla usada.
- **CA8 pendiente de pasar en local** (`PASO_COMUN_DATOS_LOCALES=1 uv run pytest -m "acceptance and integration" tests/acceptance/test_historia_160.py`; usa `data/` del fundador, no el CI). La caché de 107 MB de #128 se descargó con el mismo bbox de #37, así que sus teselas deberían encajar con la rejilla nueva; si alguna no encaja, anótalo en la PR y no se redescarga en el CI. Recuento de Colmenar (`28043`), CA8 pasado en local el 2026-11-27 con la caché de 107 MB, todo `--sin-red`, en 11 min:
  - `discrepancias`: 416 registros (`SOLAPE` 343, `AUSENTE_EN_FUENTE` 70, `DESPLAZAMIENTO` 3). Siguen ausentes `mtn50_historico` y `planimetria_historica`.
  - `candidatos-corte`: **40 candidatos**. La señal `parcela_no_camino` tiene datos en todas las teselas (ninguna `sin_datos`).
  - Los 40 tienen la misma confianza, 0,415, porque solo hay una señal. Longitud: mínimo 50 m, mediana 153 m, máximo 1.259 m, 10,5 km en total.

---

## Sitios de interés — fuentes candidatas (historia #214)

Verificado el 2026-11-27 para valorar si un tramo da acceso a una fuente, una ermita, un mirador, un yacimiento o un núcleo. Solo verificación de fuentes: no hay adapter ni datos en `data/` ni la prioridad de los tramos (historia posterior, #202). Ámbito de referencia: Colmenar de Oreja (INE 28043). Los recuentos de NGBE se hicieron con la caja `40.02,-3.47,40.13,-3.27` (WGS84) filtrada por el polígono municipal del IGN (`tests/fixtures/caminos/ign_au_ambito_7_municipios.xml`, EPSG:4258). Son topónimos y registros de inventario, no prueba de que el sitio exista ni de su acceso.

| Fuente | Formato y vía de acceso | Cobertura en Colmenar | Frecuencia | Licencia (cita) | Estado | Conclusión | Tipos de sitio |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Nomenclátor Geográfico Básico (NGBE), IGN/CNIG | API de entidades `https://api-features.ign.es/collections/namedplace/items` (GeoJSON, leído el 2026-11-27); descarga en el [Centro de Descargas del CNIG](https://centrodedescargas.cnig.es/CentroDescargas/buscadorCatalogo.do?codFamilia=NGBES) (no descargada en esta pasada). Ficha primaria: [datos.gob.es](https://datos.gob.es/es/catalogo/e0dat0002-nomenclator-geografico-basico-de-espana1) | 230 topónimos en la caja; **99 dentro del término**: 30 parajes, 26 caminos y vías pecuarias, 12 edificaciones, 11 cursos de agua, 3 entidades singulares, 1 núcleo de población (Colmenar de Oreja), 2 fuentes («Fuente de la Salceda», «Fuente de Arriba»), 2 ermitas («Ermita de San Isidro», «Ermita del Cristo»), 0 miradores, 0 yacimientos. 91 de los 99 vienen de la BTN25 (campo `fuente`) | Continua (tabla de productos de [scne.es](http://www.scne.es/tablaProductos.php), leída por resumen) | Ficha datos.gob.es: licencia «CC BY 4.0» (URI `http://publications.europa.eu/resource/authority/licence/CC_BY_4_0`). Condiciones del IGN (`https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf`, leídas el 2026-11-27): el uso de los productos «definidos en el ámbito de la Orden FOM/2807/2015» «conlleva la aceptación por el usuario de una licencia CC - BY 4.0». Si el NGBE está en ese ámbito no se comprueba aquí: `asumido` | `verificado` (API) | **Publicar**, con la atribución «NGBE Continua CC-BY 4.0 Instituto Geográfico Nacional» (tabla de scne.es leída por resumen: `asumido` hasta cotejar el texto literal). **Usar primero** | Fuente, ermita, núcleo, paraje |
| Bienes de Interés Cultural / Patrimonio de la Comunidad de Madrid | CSV en datos.comunidad.madrid: [inmuebles BIC](https://datos.comunidad.madrid/dataset/dde86e1d-a06b-4f65-8668-920a566fa264/resource/1804d79a-8643-4f06-8c20-7a0e40641be0/download/inmuebles_bic.csv), [inmuebles BIP](https://datos.comunidad.madrid/dataset/dde86e1d-a06b-4f65-8668-920a566fa264/resource/a20388c0-645d-48fe-81f5-847bcb07ecdf/download/inmuebles_bip.csv) (descargados el 2026-11-27). Ficha primaria: [datos.gob.es](https://datos.gob.es/es/catalogo/a13002908-patrimonio-cultural-protegido-en-la-comunidad-de-madrid). Columnas: denominación, autor, situación, incoación, declaración, número de registro, naturaleza, categoría, municipio. **Sin coordenadas** | 3 inmuebles BIC (iglesia parroquial Santa María la Mayor; «Ciudad de Colmenar de Oreja», conjunto histórico; zona arqueológica del término) y 1 BIP (Museo Ulpiano Checa) | Fecha de última actualización de la ficha: 4/11/2026. Frecuencia no consta | Ficha datos.gob.es: «https://creativecommons.org/licenses/by/4.0/legalcode.es». Ficha de datos.comunidad.madrid no leída en esta pasada | `verificado` | **Publicar** es posible con atribución «Comunidad de Madrid, CC BY 4.0» (`asumido`, forma exacta no leída). **Descartar** como fuente de acceso: pocos registros en el término y sin posición | Núcleo (conjunto histórico) y yacimiento (zona arqueológica), casi nada de fuente, ermita o mirador |
| Base Topográfica Nacional (BTN25), IGN | Ficha primaria: [datos.gob.es, «Base Topográfica Nacional»](https://datos.gob.es/ca/catalogo/datos-gob-es-es-catalogo-edit-e00125901-spaignbtnserie) (frecuencia «Mensual», formato SHP en la serie CNIG `codSerie=02101`, WMS `https://www.ign.es/wms-inspire/ign-base`). Especificación leída: [ESPBTN25.pdf](https://www.ign.es/web/resources/docs/IGNCnig/BTN/ESPBTN25.pdf), versión **1.0 de 2009**, que dice que desde septiembre de 2021 la sustituye ESPBTN_MOD21 (desactualizada); catálogo de fenómenos v1 de 2017-08-03 leído en ese mismo PDF | **No contada en Colmenar de Oreja**: el SHP no se descargó en esta pasada. Proxy: los 217 de 230 topónimos del NGBE de la caja que vienen de la BTN25 (91 de 99 dentro del término). El catálogo define ERMITA (edificio religioso), surgencia con tipo FUENTE y yacimiento arqueológico | Mensual (ficha datos.gob.es) | Condiciones del IGN (mismo documento que en NGBE): atribución de ejemplo en la propia tabla «BTN25 2014 - 2015 CC - BY 4.0 ign.es». En la parte leída de la tabla de scne.es (resumen de `WebFetch`, lectura parcial) no aparece la fila BTN25; sí «BTN Continua CC-BY 4.0» | `bloqueado` (SHP no descargado; la tabla de productos no confirma la BTN25) | **Interno** hasta confirmar la fila y la atribución. No hace falta para el primer uso, porque el NGBE ya trae esa geometría con nombre | Fuente, ermita, yacimiento (catálogo), núcleo |
| OpenStreetMap | Overpass API: `https://overpass-api.de/api/interpreter` y el espejo `https://overpass.kumi.systems/api/interpreter` (JSON). Respuesta: «The data is made available under ODbL» | **Sin recuento válido en Colmenar.** 2026-11-27: `overpass-api.de` devolvió `502` «at capacity» en dos consultas (una por área `ref:INE=28043` y otra por caja con `historic`, `tourism=viewpoint`, `amenity=drinking_water`, `place` y `natural=spring`); en un primer intento devolvió 200 con cero nodos, que no es un recuento válido. En el espejo `overpass.kumi.systems`, la consulta por área dio 0 elementos y la búsqueda de relaciones con `ref:INE=28043` también 0: esa etiqueta no está en OSM, así que el cero no vale. Agotaron el tiempo la búsqueda por nombre (120 s), la consulta por caja (300 s) y la de solo manantiales y agua potable (110 s). La wiki de estado de Overpass (leída por resumen de `WebFetch`, 2026-11-27) recoge timeouts recientes y un bloqueo temporal de rangos de Azure y AWS | Edición continua | Licencia ODbL, «compartir igual». Cita de la respuesta de Overpass, leída el 2026-11-27: «The data is made available under ODbL». `https://www.openstreetmap.org/copyright` no se leyó en esta pasada (`asumido`) | `bloqueado` (Overpass saturado o sin respuesta; no hay recuento) | **Interno**, como señal (ya así en el resumen de la historia 0021). Para un recuento hay que reintentar en otro momento o con instancia propia, como pide la propia página de Overpass para uso automatizado | Fuente (`natural=spring`, `amenity=drinking_water`), mirador (`tourism=viewpoint`), ermita y yacimiento (`historic=*`), núcleo (`place=*`) |

**Canales consultados sin lectura completa.** El PDF de la BTN25 pesa 15 MB: `WebFetch` no lo leyó y se extrajo con un lector propio (zlib) del mismo PDF; la especificación leída es la v1.0 de 2009. Las tablas de scne.es se leyeron por resumen de `WebFetch`, no literalmente: antes de citar la atribución del NGBE o de la BTN25 hay que copiarla del texto de la tabla. Ninguna fila de esta sección se apoya en un resultado de búsqueda sin abrir el documento primario.

### Recomendación

- **Usar primero el NGBE.** Es la única fuente de las cuatro que hoy es `verificada`, con licencia CC BY 4.0 leída y cobertura contada dentro del término (2 fuentes, 2 ermitas y el núcleo). Permite **Publicar** con atribución. Limitación: es un topónimo. Una «Fuente de la Salceda» en el registro no demuestra que el manantial exista ni que dé acceso; eso lo tendría que confirmar una comprobación posterior sobre ortofoto o en el terreno. El NGBE no trae **miradores** ni **yacimientos** en el término.
- **Descartar primero el BIC/Patrimonio para este fin.** Aporta 4 registros en Colmenar y sin coordenadas: sirve como contexto de un bien protegido, no como sitio de acceso.
- **Mantener OSM como `Interno` y reintentarlo.** Es la única fuente con miradores y yacimientos etiquetados de forma abierta, pero no hay recuento. Mientras Overpass esté saturado, no hay que construir nada que dependa de ella, y el uso automatizado desde CI sigue siendo un riesgo de bloqueo.
- **BTN25 en espera.** Sus datos ya están en el NGBE. Solo hace falta si se necesita la geometría de los puntos, y entonces hay que confirmar la fila y la atribución de la tabla de productos.

Tipos de sitio que queda sin cubrir con fuentes `verificadas`: **mirador** y **yacimiento** en el término (el NGBE no los trae y el BIC solo tiene una zona arqueológica sin posición).

---

## Vuelos históricos de la Comunidad de Madrid — 1956, 1975, 1991 (IDEM, historia #206)

Verificado el 2026-11-27 (15:49–15:53 UTC) con peticiones reales desde GitHub Actions, con `User-Agent: paso-comun-verificacion/0.1 (proyecto abierto sin animo de lucro)`. Cierra, para la Comunidad de Madrid, el hueco 1957–1997 que la sección del WMS histórico del IGN daba por perdido (el IGN solo sirve AMS 1956-57 y PNOA desde 1997). Fixtures en `tests/fixtures/idem_vuelos/`; ninguna imagen va a `site/`.

**Estado por vuelo** (lo que #207 y #208 deben tomar como cierto):

| Vuelo | Estado | Motivo |
|---|---|---|
| 1956 | `confirmado` | Imagen real en los 7 municipios, WMS y WMTS. Licencia CC BY 4.0 en la ficha; origen en fondos del CECAF/CEGET (ver «Licencia»). |
| 1975 | `confirmado` | Imagen real en los 7 municipios, WMS y WMTS. Licencia CC BY 4.0 Comunidad de Madrid. |
| 1991 | `confirmado` | Imagen real en los 7 municipios, WMS y WMTS. Licencia CC BY 4.0 Comunidad de Madrid. |

«Confirmado» vale para un punto representativo por municipio (CA3), no para todo el término: la cobertura se describe abajo tal cual.

### Capas y teselas (CA1) — `confirmado`

`GetCapabilities` WMTS: https://idem.comunidad.madrid/visor/release/vgcm/statics/capabilities/produccion/srvimagenes2_visorcartografia2.xml (200, `application/xml`, 13.991.110 bytes, 2026-11-27). El documento completo pesa 14 MB; la fixture `capabilities_wmts_extracto.xml` guarda solo las tres capas (sin sus `TileMatrixLimits`) y los dos `TileMatrixSet` relevantes.

| Vuelo | Identificador de capa | Título |
|---|---|---|
| 1956 | `fotosAereasHistoricas_1950-1959_1956-CT-50cm-mosaico` | `1956 - Ortofoto 50cm` |
| 1975 | `fotosAereasHistoricas_1970-1979_orto-1975-ed50` | `1975 - Ortofoto 50cm` |
| 1991 | `fotosAereasHistoricas_1990-1999_orto-1991-ed50` | `1991 - Ortofoto 50cm` |

Iguales en las tres capas:

- **Formatos**: `image/png`, `image/jpeg`, `image/png8`, `image/jpegxr`, `image/webp`. Estilo `default`. `InfoFormat`: `text/plain`, `text/xml`.
- **`TileMatrixSet` enlazados**: `EPSG3857`, `MD:GoogleMapsCompatible`, `OGC:1.0:GlobalCRS84Pixel`, `OGC:1.0:GoogleMapsCompatible`, `VGCM:epsg:25830` y `VGCM:epsg:4326` (más `VGCM:epsg:4230` en 1956 y `VGCM:epsg:4258` en 1975 y 1991).
- **Tamaño de tesela**: 256 × 256 px en todos los niveles.
- **Niveles**: 0 a 20 en los `TileMatrixSetLimits` de cada capa (las matrices están definidas hasta el 25 en `EPSG3857`, hasta el 20 en `VGCM:epsg:25830`).
- **`EPSG3857`** (3857): esquina superior izquierda (−20037508,34, 20037508,34), escala 559082264,03 en el nivel 0, la habitual de Google Maps.
- **`VGCM:epsg:25830`** (EPSG:25830, el CRS del proyecto): esquina superior izquierda (E −510000, N 4560000), escala 279541132,014 en el nivel 0, con tamaño de píxel `escala × 0,00028 / 2^nivel`.
- **Plantilla REST**: **no**. Solo KVP: la operación `GetTile` anuncia `GetEncoding = KVP` en `https://idem.comunidad.madrid/srvimagenes2/ogc/wmts/visorcartografia2?`, y las capas no traen `ResourceURL`.
- **Cobertura declarada de cada capa** (caja WGS84): 1956, lon −4,6846 a −3,0134, lat 39,8244 a 41,2121; 1975, lon −4,7163 a −2,9365, lat 39,8210 a 41,2096; 1991, lon −4,6719 a −2,9943, lat 39,8737 a 41,1680.

### Teselas reales sobre Colmenar de Oreja (CA2) — `confirmado`

Petición (plantilla KVP; fila y columna calculadas para el punto representativo del término, 40,08498° N, −3,42488° E):

```
https://idem.comunidad.madrid/srvimagenes2/ogc/wmts/visorcartografia2?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=<capa>&STYLE=default&FORMAT=image/png&TILEMATRIXSET=EPSG3857&TILEMATRIX=18&TILEROW=99161&TILECOL=128578
```

- **Nivel «0,5 m»**: en `EPSG3857` el nivel 18 mide 0,5971 m por píxel en el ecuador y **0,457 m por píxel de terreno a 40,085° N** (×cos(latitud)); es el más cercano a los 0,5 m nativos. En el `TileMatrixSet` propio `VGCM:epsg:25830`, el nivel 17 da 0,597 m por píxel y el 18, 0,299 m (no hay un nivel de 0,5 m exactos). Las tres fixtures son del nivel 18 de `EPSG3857`. Con `VGCM:epsg:25830` se probaron también los niveles 17 y 18 (fila 802, columna 6369, y fila 1605, columna 12739): 200 con imagen real en los tres vuelos, no se guardan.
- **Resultado** (2026-11-27, todas con 200 y `Content-Type: image/png`; 256 × 256 px):

| Vuelo | Hora UTC | Bytes | Varianza (gris) | Niveles de gris distintos | Fixture |
|---|---|---|---|---|---|
| 1956 | 15:50:57 | 46.251 | 310,1 | 157 | `tesela_1956_colmenar_z18.png` |
| 1975 | 15:51:02 | 92.250 | 3.181,9 | 247 | `tesela_1975_colmenar_z18.png` |
| 1991 | 15:51:05 | 68.472 | 1.540,7 | 224 | `tesela_1991_colmenar_z18.png` |

- **Método de «no está en blanco»**: se decodifica el PNG, se pasa a gris (media de R, G, B) y se calcula la varianza y el número de niveles de gris distintos. Una imagen es **en blanco** si la varianza es menor que 1 o solo tiene 1 nivel. Las teselas reales tienen varianza ≥ 114 y ≥ 81 niveles (sobre todas las pruebas); la de 1956 es la menos contrastada (película gris, pero se ve el parcelario).
- **Sorpresa del 200 en blanco**: una tesela **fuera de la cobertura** (UTM 440000, 4380000, nivel 18) devuelve también 200 con `image/png`, pero es blanca (255 en todo, varianza 0, 1 nivel, 854 bytes en los tres vuelos): sin la comprobación de varianza no se distingue de una buena. Fixture de referencia: `tesela_1956_fuera_cobertura_z18.png`.
- Los bytes de una misma tesela no son estables entre peticiones (la de 1991 pesó 68.472 y 66.229 bytes en dos peticiones sobre la misma fila y columna): la caché no debe comparar hashes con otra petición.

### Tabla municipio × vuelo (CA3) — nivel 18 de `EPSG3857`

Un punto por municipio: el punto representativo (`representative_point`) del contorno que publica `publicar-cobertura --ambito`. **No se generaliza** al resto del término.

| Municipio (INE) | 1956 | 1975 | 1991 |
|---|---|---|---|
| Aranjuez (28013) | con imagen | con imagen | con imagen |
| Belmonte de Tajo (28019) | con imagen | con imagen | con imagen |
| Colmenar de Oreja (28043) | con imagen | con imagen | con imagen |
| Chinchón (28052) | con imagen | con imagen | con imagen |
| Valdelaguna (28157) | con imagen | con imagen | con imagen |
| Villaconejos (28170) | con imagen | con imagen | con imagen |
| Villarejo de Salvanés (28180) | con imagen | con imagen | con imagen |

Las 21 peticiones: 200, `image/png`, entre 47.356 y 102.254 bytes, varianza entre 237 y 3.182, entre 156 y 256 niveles. Ninguna `en blanco` ni `error`. Ningún otro punto del término se ha probado: el borde de la caja de cada capa (sobre todo la de 1991, más estrecha al norte y al sur) no se ha explorado.

### Licencia y atribución (CA4) — `confirmado` en la ficha, con una reserva en 1956

Documentos primarios leídos el 2026-11-27: las fichas ISO 19139 del catálogo IDEM, en `https://idem.comunidad.madrid/catalogocartografia/srv/api/records/<id>/formatters/xml` con `<id>` = `spacm_vuelo1956_50cm`, `spacm_vuelo1975_50cm`, `spacm_vuelo1991_50cm` (200, `application/xml`), y el aviso legal que enlazan: https://idem.comunidad.madrid/recursos_cat_geo/Catalogo/aviso_legal.htm (200, `text/html`).

- **Restricciones de la ficha** (`gmd:otherConstraints`): `Sin limitaciones al acceso público.` (INSPIRE `LimitationsOnPublicAccess/noLimitations`) y, como condición de uso, **`CC BY 4.0`** en 1956 y **`CC BY 4.0 Comunidad de Madrid`** en 1975 y 1991, con enlace a https://creativecommons.org/licenses/by/4.0/deed.es.
- **Aviso legal, cita textual** de la condición de uso: «El acceso a los datos geográficos digitales y a los servicios de información geográfica disponibles en el Geoportal de la Infraestructura de Datos Espaciales de la Comunidad de Madrid (IDEM) […] tiene carácter libre y gratuito siempre que se mencione la fuente original y la propiedad de los mismos de la siguiente manera: "Información geográfica de la Comunidad de Madrid. Acceso público y gratuito en CC BY 4.0 Comunidad de Madrid ."». Y la cautela: «Los datos geográficos y servicios de información geográfica que se facilitan tienen carácter meramente orientativo y en ningún caso podrán ser vinculantes para la resolución de los procedimientos administrativos […]».
- **Conclusión**: la ficha permite reutilizar y redistribuir con atribución (CC BY 4.0), así que la **imagen derivada en el visor y en el dossier** (un recorte con el trazo dibujado encima) está permitida con la atribución literal del aviso legal. No se supone CC BY 4.0 por lo que dijera la issue padre: la ficha de cada vuelo lo dice.
- **Reserva en 1956**: la ficha dice que el vuelo es del Army Map Service de EEUU, escaneado por el CEGET, con «Fondos del CECAF […] y CEGET […] cedidos al Centro Nacional de Información Geográfica para su distribución. Ortorrectificación y mosaicado realizado por la Comunidad de Madrid», y que es «Vuelo no disponible para descarga, ni para su certificación» (competencia del CECAF). La licencia CC BY 4.0 de la ficha es la de la ortofoto de la Comunidad de Madrid; la del IGN para el mismo vuelo (AMS 1956-57) también es CC BY 4.0, con atribución `ejercito.defensa.gob.es` (ver `NOTICE`). No se ha leído un documento del CECAF que condicione la reutilización de la ortofoto de la Comunidad de Madrid; queda como riesgo a confirmar antes de publicar recortes de 1956.
- **Canales no leídos**: el visor `https://idem.comunidad.madrid/visor/` (aplicación de JavaScript) y el catálogo en `catalog.search#/…` (no se renderizan sin navegador); la fuente es la API XML de la ficha, que es el mismo registro.

### Petición por ventana (CA5) — `confirmado`, hay WMS

El WMS de la IDEM publica las mismas tres capas, con el **mismo identificador** y `EPSG:25830` entre sus CRS:

- `GetCapabilities`: `https://idem.comunidad.madrid/srvimagenes2/ogc/wms/visorcartografia2?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0` (200, `text/xml`, 941.429 bytes, ERDAS APOLLO Core 2016). Cajas nativas en `EPSG:25830` con `resx = 0,5`: 1956, E 358750–498850, N 4409575–4562300; 1975 y 1991 con resolución 0,49999… m.
- **Sorpresa**: el `GetMap` que anuncia el documento (`http://idem.comunidad.madrid/erdas-iws/ogc/wms/visorcartografia2?`) responde **404**; el que funciona es el de `srvimagenes2/ogc/wms/visorcartografia2` (el mismo de `GetCapabilities`).
- **`GetMap` real** (2026-11-27, 15:52:56–15:52:58 UTC), 1.3.0, `CRS=EPSG:25830` (ejes E, N), `BBOX=463700,4437200,463828,4437328` (128 m sobre Colmenar de Oreja), 256 × 256 px = 0,5 m por píxel, `FORMAT=image/png`:

| Vuelo | Código | `Content-Type` | Bytes | Varianza (gris) | Niveles |
|---|---|---|---|---|---|
| 1956 | 200 | `image/png` | 47.620 | 202,1 | 154 |
| 1975 | 200 | `image/png` | 91.685 | 2.414,1 | 247 |
| 1991 | 200 | `image/png` | 69.328 | 1.047,6 | 217 |

- **Consecuencia para #207**: hay ventana directa por `GetMap` en EPSG:25830 con 0,5 m por píxel, igual que el WMS del IGN de #122/#124; **no hace falta mosaico y recorte de teselas**. Las teselas WMTS (solo KVP, `EPSG3857` o `VGCM:epsg:25830`) quedan como alternativa. Hay que aplicar a cada respuesta la comprobación de varianza, porque fuera de cobertura el servicio responde 200 con una imagen blanca. No se ha probado el límite de tamaño de ventana de este WMS.
- **COG**: la ficha de 1956 lista «ortofotos en formato tiff, ecw, cog» pero «Vuelo no disponible para descarga»; no se ha probado ni se usa. Las de 1975 y 1991 solo listan «mosaico en formato ecw».

### Fecha y cobertura de cada vuelo (CA6)

| Vuelo | Fecha del vuelo | Fuente | Cobertura |
|---|---|---|---|
| 1956 | solo el año (1956); la ficha pone `1956-01-01` como fecha de la cita, no es un mes | ficha `spacm_vuelo1956_50cm`; título del WMTS «Vuelo Americano AMS SERIE B de 1956» | región entera según el título; caja WGS84 de la capa, arriba |
| 1975 | solo el año (1975); `1975-01-01` en la ficha es la fecha de la cita | ficha `spacm_vuelo1975_50cm`, «Vuelo a escala 1:15.000 […] Comisión de Planeamiento y Coordinación del Area Metropolitana de Madrid» | «Ortoimagen histórica del total de la Comunidad de Madrid» |
| 1991 | solo el año (1991); `1991-01-01` en la ficha es la fecha de la cita | ficha `spacm_vuelo1991_50cm`, «Vuelo 1:18.000 Consejería de Política Territorial. Comunidad de Madrid» | «total de la Comunidad de Madrid» |

Ninguna ficha publica mes. Las tres fichas declaran la misma caja (lon −4,61284 a −2,97615, lat 39,83781 a 41,20036), pero las cajas de las capas del WMTS son distintas (arriba) y la de 1991 es la más estrecha: «total de la Comunidad» es lo que dice el proveedor, no lo que se ha medido. Los 7 municipios del ámbito caen dentro de las tres cajas y dan imagen en el punto probado.

---

## Catastrones (minutas MTN50 del IGN): cobertura, año y atribución en el ámbito (historia #211)

Verificado el **2026-11-27** para la [historia #211](https://github.com/murcialito/paso-comun/issues/211) (hija de #195). Pregunta: ¿qué hojas de catastrones cubren los 7 municipios del ámbito, de qué año son, con qué atribución se pueden publicar y merece la pena georreferenciarlas? Servicio: `https://www.ign.es/wms/primera-edicion-mtn`, capa `catastrones` (WMS 1.3.0, EPSG:25830). Script puntual: `scripts/verificar_catastrones.py` (`hojas`, `imagenes`, `descargas`, `fixtures`). Fixtures en `tests/fixtures/caminos/catastrones/` (`GetFeatureInfo` de cada hoja, recortes de 1 km a 2 m/px, `hojas.json`, `imagenes.json`, `descargas.json`, ficha del Centro de Descargas de la 0606, `procedencia.json`). Crudos en `data/raw/ign_catastrones/`, fuera de git. Ninguna prueba llama a red.

### CA1 — Hojas que cubren cada municipio (`GetFeatureInfo`, `confirmado`)

Método: rejilla de 2,5 km dentro del término (límite del IGN, fixture `ign_au_ambito_7_municipios.xml`) más un punto interior; un `GetFeatureInfo` por punto sobre una ventana de 100 m (`text/html`). Todos los puntos devolvieron hoja (0 «sin hoja»). Año = «Año de edición» de la tabla; ninguna hoja salió «sin año». Entre paréntesis, puntos de la rejilla que caen en esa hoja.

| Municipio (INE) | Puntos | Hojas (número, nombre, año) |
|---|---|---|
| Colmenar de Oreja (28043) | 19 | **0606** Chinchón 1963 (17); 0605 Aranjuez 1943 (2) |
| Aranjuez (28013) | 31 | 0630 Yepes 1945 (17); 0605 Aranjuez 1943 (14) |
| Chinchón (28052) | 20 | 0606 Chinchón 1963 (6); 0583 Arganda 1956 (9); 0582 Getafe 1964 (3); 0605 Aranjuez 1943 (2) |
| Belmonte de Tajo (28019) | 5 | 0606 Chinchón 1963 (5) |
| Villaconejos (28170) | 6 | 0606 Chinchón 1963 (6) |
| Villarejo de Salvanés (28180) | 20 | 0606 Chinchón 1963 (18); 0583 Arganda 1956 (2) |
| Valdelaguna (28157) | 7 | 0583 Arganda 1956 (5); 0606 Chinchón 1963 (2) |

Cinco hojas en total: 0582 (1964), 0583 (1956), 0605 (1943), 0606 (1963) y 0630 (1945). Las cinco son posteriores a 1881 y la mitad anteriores al vuelo AMS de 1956-57: son una fuente distinta del MTN50 de 1881 y de las planimetrías de #17. Los recuentos son de una rejilla, no una medición de área: una hoja con pocos puntos solo toca el borde del término.

### CA2 — `GetMap` con contenido (`confirmado`)

`GetMap` de 1 km × 1 km (500 × 500 px, 2 m/px) centrado en un punto de cada hoja dentro de cada municipio: **14 de 14 combinaciones municipio-hoja devuelven `image/png` con contenido** (200 OK; 353.043 a 557.674 bytes; desviación típica de gris 25 a 40; fracción de píxeles no blancos ≥ 0,9999). Ejemplos (sha256 completo en `imagenes.json`; el recorte de cada hoja está en `recorte_<hoja>_1km_2mpx.png`):

| Hoja | Municipio de la ventana | Bytes | sha256 (inicio) |
|---|---|---|---|
| 0582 | Chinchón | 540.585 | `877af140d9f3` |
| 0583 | Chinchón | 435.344 | `06d28048ecf0` |
| 0605 | Colmenar de Oreja | 489.424 | `7bb04c2b6c1a` |
| 0606 | Colmenar de Oreja | 416.485 | `247a1b994963` |
| 0630 | Aranjuez | 353.043 | `20f43e017f42` |

**Resolución efectiva** (curva de gradiente de `verificar_planimetrias.py`, ventana de 300 m pedida a 0,25 m/px): la curva normalizada es ≈ 1,00 hasta 1 m y cae a 0,86-0,90 a 2 m y a 0,68-0,76 a 4 m en las 14 ventanas, así que el detalle real se agota hacia **1 a 2 m/px** (escala 1:25.000 escaneada). Es `asumido` como estimación, no medido contra el original. Un recorte de 1 km a 2 m/px basta para ver caminos con nombre.

### CA3 — Atribución (`confirmado` salvo el identificador exacto)

- **Licencia**: CC BY 4.0. El `GetCapabilities` declara `AccessConstraints` = `CC BY 4.0 ign.es` (fixture `ign_primera-edicion-mtn_getcapabilities.xml`). La capa `catastrones` solo declara `Attribution` = «Instituto Geográfico Nacional» (enlace a `https://www.ign.es`); no lleva texto de licencia propio.
- **Licencia de uso del IGN** (fixture `ign_licencia_condiciones_uso.txt`, Orden FOM/2807/2015, art. 4): el uso es libre y gratuito mencionando origen y propiedad. Para un **servicio sin modificar** vale la fórmula de `AccessConstraints`: «CC BY 4.0 ign.es». Para una **obra derivada** (cualquier georreferenciación o trazado que hagamos sobre la minuta) la fórmula es «Obra derivada de `<identificador del producto>` `<fecha>` CC-BY 4.0 `<atribución de productores>`», visible junto a los datos.
- **Atribución literal propuesta** para lo que salga de catastrones: «Obra derivada de Minutas MTN50 (catastrones) 1910-1970 CC-BY 4.0 © Instituto Geográfico Nacional de España». Es la misma construcción que ya usan `scripts/verificar_planimetrias.py` y el sitio para planimetrías y MTN50.
- **¿Basta el aviso «© Instituto Geográfico Nacional de España» del WMS?** No para una obra derivada: falta «Obra derivada de», el producto, la fecha y «CC-BY 4.0». Para mostrar la imagen del WMS sin modificar bastaría «CC BY 4.0 ign.es» más ese reconocimiento; para el resto hay que añadir lo anterior.
- **`asumido`**: el identificador y el rango de fechas exactos de la tabla de productos de `scne.es/productos.html` no se pudieron leer (la página cerró la conexión TLS y su contenido es dinámico). Se usa el título del servicio («Minutas del Mapa Topográfico Nacional 1:50.000 (catastrones) 1910-1970»). Si el IGN publica otro identificador, corregir la cadena antes de publicar.

### CA4 — Descarga del original (`bloqueado` por reCAPTCHA para un script)

Los enlaces de `GetFeatureInfo` (`http://centrodedescargas.cnig.es/CentroDescargas/busquedaRedirigida.do?ruta=PUBLICACION_CNIG_DATOS_VARIOS/Minutas_MTN50/MinutaMTN50-<hoja>-<Nombre>.zip`) redirigen a HTTPS y devuelven la **ficha HTML** del producto (200, `text/html`), no el zip. La descarga se autoriza con una llamada a `preAutorizarDescarga` que exige un token de **reCAPTCHA v3** (`grecaptcha.execute`, acción `preautorizar_descarga`), igual que la ficha de ALTI de #17: no hay descarga directa sin navegador. Los datos de las fichas sí se leen:

| Hoja | Fichero | Fecha | Tamaño | Formato | Estado |
|---|---|---|---|---|---|
| 0582 Getafe | `MINUTAMTN50-0582-GETAFE.ZIP` | 1964 | 141,14 MB | JPG + ECW | `bloqueado` (reCAPTCHA v3) |
| 0583 Arganda | `MINUTAMTN50-0583-ARGANDA.ZIP` | 1956 | 132,75 MB | JPG + ECW | `bloqueado` (reCAPTCHA v3) |
| 0605 Aranjuez | `MINUTAMTN50-0605-ARANJUEZ.ZIP` | 1943 | 125,25 MB | JPG + ECW | `bloqueado` (reCAPTCHA v3) |
| 0606 Chinchón | `MINUTAMTN50-0606-CHINCHON.ZIP` | 1963 | 125,14 MB | JPG + ECW | `bloqueado` (reCAPTCHA v3) |
| 0630 Yepes | `MINUTAMTN50-0630-YEPES.ZIP` | 1945 | 126,76 MB | JPG + ECW | `bloqueado` (reCAPTCHA v3) |

Escala declarada en la ficha: 25.000. Sistema: ETRS89, coordenadas geográficas. Unidad de descarga: hoja del MTN50. **No hay manera de automatizar el original**: o lo baja una persona en el navegador, o se trabaja con el render del WMS cacheado (opción A de #17: cero coste, 1-2 m/px, ya reproyectado). No se bajó ningún zip.

### CA5 — Recomendación por hoja

El WMS entrega una imagen ya georreferenciada por el IGN, así que «georreferenciar» aquí significa medir su desajuste frente a PNOA y, si hace falta, corregirlo con puntos de control (como #139), no escanear nada.

| Hoja | Año | Municipios | Recomendación |
|---|---|---|---|
| **0606** Chinchón | 1963 | 6 de 7 (todos salvo Aranjuez) | **Georreferenciar, prioridad 1**: cubre casi todo el ámbito, caminos con nombre y es la única con cobertura completa de Colmenar de Oreja, Belmonte de Tajo y Villaconejos. |
| **0605** Aranjuez | 1943 | Aranjuez, borde de Colmenar y Chinchón | **Georreferenciar, prioridad 2**: la más antigua y anterior al vuelo de 1956; da una fecha distinta para Aranjuez y el sur de Colmenar. |
| **0583** Arganda | 1956 | Valdelaguna, Chinchón, Villarejo de Salvanés | **Georreferenciar, prioridad 2**: es de 1956, el mismo año que el vuelo AMS de PNOA histórico, lo que permite contrastar minuta y foto. |
| **0630** Yepes | 1945 | Aranjuez (17 de 31 puntos) | **Georreferenciar, prioridad 3**: solo aporta a Aranjuez; hacerlo si Aranjuez entra en un hito. |
| 0582 Getafe | 1964 | Chinchón (3 de 20 puntos, borde) | **Descartar por ahora**: solo toca el borde norte de un término; el 1963 de la 0606 ya cubre esa zona. |

Límites: el año de la minuta no es el año del camino; la resolución efectiva es de 1 a 2 m/px; el original no se puede bajar sin captcha. La recomendación no mide el desajuste frente a PNOA (queda para la historia hermana de georreferenciación).
>
---

## Resumen de fuentes no verificadas en esta pasada

Fuera de alcance de la historia 0001 (ver sección "Fuera de alcance" de `docs/stories/0001-registro-fuentes.md`): vías pecuarias, Red Natura 2000, concesiones de agua, inventario municipal de caminos. SNCZI/dominio público hidráulico, que figuraba aquí mismo hasta la historia 0012, quedó verificado en esa historia (ver sección "SNCZI / Dominio Público Hidráulico — MITECO" más arriba: cursos de agua y peligrosidad por inundación `confirmado`, deslinde legal de DPH y zonas de servidumbre/policía `bloqueado`). Vías pecuarias, que figuraba aquí mismo hasta la historia 0014, quedó verificada en esa historia (ver sección "Vías pecuarias — IDEM, Comunidad de Madrid" más arriba: `confirmado`, un único servicio real encontrado bajo el workspace `Zonas` del mismo GeoServer de IDEM). Red Natura 2000, que figuraba aquí mismo hasta la historia 0015, quedó verificada en esa historia (ver sección "Red Natura 2000 y espacios protegidos — IDEM, Comunidad de Madrid" más arriba: `confirmado` como fuente real de planes de gestión, con el alcance explícito de que modela zonificación de planes, no el límite oficial de cada sitio individual con código EU). Concesiones de agua e inventario municipal de caminos quedan para una iteración posterior del registro, cuando las historias de reglas/afecciones las necesiten.

### Publicar los tramos a verificar (historia #170)

- **CA15 (flujo real), pendiente de la primera publicación real.** Por decisión del fundador en #170 (2026-11-27), no bloquea el merge: necesita candidatos aprobados a mano en `curated/candidatos/28043/revision.json`, y ningún agente puede aprobarlos (ADR 0047). Sin aprobados, `publicar-candidatos` no publica nada. La primera vez que se publique de verdad, ejecuta `uv run pytest -m "acceptance and integration" tests/acceptance/test_historia_170.py -k ca15` y anota aquí la fecha, cuántos tramos aprobados se publicaron y la línea `medición:` (solo números, sin referencias catastrales).
