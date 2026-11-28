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

## Datos internos: copia en el repo privado (ADR 0055)

Las fuentes que no se pueden publicar se copian, solo para copia de seguridad y reutilización interna, al repo privado del proyecto, como adjuntos de release con un catálogo por fuente (sha256, licencia, `publicable: false` y restricciones de uso). Las reglas de acceso, el formato del catálogo y qué parte de `data/derived/*/interno/` se copia están en el [ADR 0055](../../../docs/adr/0055-repositorio-privado-de-datos-internos-adjuntos-de-release-catalogo-y-reglas-de-acceso.md). Fuentes que se copian:

- **Catastro INSPIRE**: la caché cruda de `data/raw/catastro/`, por municipio y fecha (no se puede volver a descargar igual).
- **Catastro histórico** de rústica (historias #268 y #287): los originales descargados de la Sede Electrónica.
- **Fondo Documental de Vías Pecuarias**: los proyectos de clasificación, cuando lleguen (#280, #284).

Estado a 2026-11-28: **todavía no se ha subido nada**; el repo privado lo crea #296 y la sincronización la implementa #295. Ningún dato de titularidad se copia.

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
- **Licencia:** citada explícitamente (a diferencia del resto de fuentes de este registro, donde queda `asumido` sin ningún enlace) — `https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf`, enlazada desde los metadatos de la propia colección (`rel: license`). El PDF se descargó y leyó entero el 2026-11-27 (historia #247): contenido `confirmado`, ver el apartado «Licencia de la capa de cauces y zona de servidumbre» más abajo (CC BY 4.0, con «Obra derivada de …» para derivados).
- **Paginación y caché (historia #257, verificado el 2026-11-27 contra la red):** la colección se pagina con `limit` y un enlace `rel=next` (`href` con `offset=<n>`); una consulta municipal puede traer más de una página y solo la primera es la respuesta completa de un bbox pequeño. `HydrographyAdapter.get_watercourses_in_bbox` pide `limit=1000`, sigue `rel=next` (solo si apunta a esta colección) hasta el final, deduplica por `id` y falla si pasa de 50 páginas. Con `CachedRawFetcher` cada página queda en la caché cruda inmutable (sha256 y fecha); con `--sin-red` una página ausente es un error, nunca un resultado parcial. La licencia `CC BY 4.0` («Obra derivada de» al derivar) va en la procedencia de cada cauce. Fixture: `features_watercourse_aranjuez_con_datos_reales.json` (página 1 real, con `next`) y `features_watercourse_aranjuez_pagina2_sintetica.json` (página 2 **sintética**, con un `id` repetido para el test de duplicados). El bbox de Aranjuez (`430000,4428000,445000,4440000`, `numberMatched` 179 con `limit=10`) cabe en una página con `limit=1000`.
- **Estado:** `confirmado`.

#### Licencia de la capa de cauces y zona de servidumbre (historia #247, consultado el 2026-11-27) — `confirmado`

Los **tres** documentos se descargaron con `curl` (HTTP 200) y se leyeron enteros; el PDF, de 3 páginas, con extracción de texto (`pypdf`), porque `WebFetch` no lo decodifica (PDF comprimido). Ningún canal quedó sin leer: nada se da por «no hay».

**1. Licencia del IGN — `https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf` (consultada el 2026-11-27). Licencia de la capa `watercourse`: de `asumido` a `confirmado`.**

- Base: «conlleva la aceptación por el usuario de una licencia CC-BY 4.0» (Orden FOM/2807/2015, de 18 de diciembre, BOE 26-12-2015). Art. 4 de la Orden, citado en el PDF: «El uso de los productos de datos geográficos digitales mencionados en el Artículo 2 tendrá carácter libre y gratuito, siempre que se mencione el origen y propiedad de los datos, con el alcance y forma que autorice la licencia de uso correspondiente».
- **Obras derivadas (punto 4 del PDF), literal:** «Cuando el usuario licenciado genere una obra derivada de uno o varios de los productos y servicios de datos del IGN, se añadirá «Obra derivada de» delante de la expresión general, con lo que quedará «Obra derivada de <identificador del producto> <fecha> CC- BY 4.0 <atribución de productores>» y seguirán siendo de aplicación los considerandos indicados en los puntos anteriores.» Ejemplo del PDF: «Obra derivada de PNOA 2010-2013 CC-BY scne.es».
- **Nuevo conjunto de datos por modificación (punto 5):** el licenciado debe incluir la atribución «también en los metadatos si los hubiera, concretamente en los siguientes elementos de metadatos o en sus equivalentes: resumen (abstract), linaje (lineage) y en las restricciones de acceso (AccessConstraints)». Nuevo servicio web (punto 6): también en la autodescripción (`GetCapabilities` o similar) y en `otherConstraints`/resumen.
- **Visibilidad (punto 1):** «Esta mención de atribución obligatoria se mostrará visible junto con los datos, de forma legible y a pie de mapa, imagen, presentación o ventana de visualización»; si hay imposibilidad justificable, en listados de capas, leyendas o créditos. Forma abreviada permitida (considerando cuarto): «CC-BY 4.0 <atribución productores> <fecha>».
- **Veredicto (CA1): SÍ permite publicar una capa derivada** (por ejemplo, una franja calculada a partir del eje del cauce): el PDF regula expresamente las obras derivadas y solo exige la atribución, sin prohibir la redistribución ni exigir autorización. Condiciones para las historias de derivar y publicar: (a) atribución visible a pie de mapa con la fórmula «Obra derivada de <identificador del producto> <fecha> CC-BY 4.0 <atribución de productores>»; (b) esa misma frase en el abstract, el lineage y las restricciones de acceso del `.procedencia.json` y de los metadatos; (c) los valores de `<identificador del producto>`, `<fecha>` y `<atribución de productores>` salen de la tabla `http://www.scne.es/productos.html`, **que esta historia no ha leído** y que hay que consultar al fijar la atribución (hoy queda `pendiente`, no `asumido`).
- No dice nada sobre excluir de la licencia a las capas de otros productores (MITECO/Confederaciones): el dato lo atribuye el propio servicio como `fuented="Instituto Geográfico Nacional"` (ver hallazgo 3), que es lo que cubre esta licencia.

**2. Texto Refundido de la Ley de Aguas (RDLeg 1/2001) — `https://www.boe.es/buscar/act.php?id=BOE-A-2001-14276` (texto consolidado; `fecha_actualizacion` 2026-09-03 del XML del BOE; consultado el 2026-11-27). Art. 6, «Definición de riberas», literal:**

- «1. Se entiende por riberas las fajas laterales de los cauces públicos situadas por encima del nivel de aguas bajas, y por márgenes los terrenos que lindan con los cauces. Las márgenes están sujetas, en toda su extensión longitudinal: a) A una zona de servidumbre de cinco metros de anchura, para uso público que se regulará reglamentariamente. b) A una zona de policía de 100 metros de anchura en la que se condicionará el uso del suelo y las actividades que se desarrollen.»
- «2. En las zonas próximas a la desembocadura en el mar, en el entorno inmediato de los embalses o cuando las condiciones topográficas o hidrográficas de los cauces y márgenes lo hagan necesario para la seguridad de personas y bienes, podrá modificarse la anchura de ambas zonas en la forma que reglamentariamente se determine.»

**3. Reglamento del Dominio Público Hidráulico (Real Decreto 849/1986, de 11 de abril) — `https://www.boe.es/buscar/act.php?id=BOE-A-1986-10638` (texto consolidado; `fecha_actualizacion` 2026-07-20 del XML del BOE; consultado el 2026-11-27):**

- **Anchura y desde dónde (art. 6):** repite el art. 6 del TRLA: «Las márgenes están sujetas, en toda su extensión longitudinal: a) A una zona de servidumbre de cinco metros de anchura para uso público que se regula en este Reglamento.» Las márgenes son «los terrenos que lindan con los cauces». El art. 6 no dice «medidos horizontalmente»; esa expresión aparece solo para la zona de policía (art. 9.1: «100 metros de anchura medidos horizontalmente a partir del cauce»). Ninguno de los dos textos dice en este punto desde qué línea exacta (eje, orilla, nivel de aguas bajas) se mide la servidumbre: la franja es contigua al cauce, no al eje. Esto es lo que **no** puede darse por leído: medirla desde el eje del IGN es una aproximación.
- **Art. 6.2 a) (numeración vigente):** las márgenes «están sujetas en toda su extensión longitudinal: a) A una zona de servidumbre de cinco metros de anchura para uso público, que se regula en este reglamento.»
- **Usos (art. 7.1), redacción consolidada vigente, literal:** «La zona de servidumbre para uso público definida en el artículo anterior tendrá los fines siguientes: a) Protección del ecosistema fluvial y del dominio público hidráulico. b) Paso público peatonal y para el desarrollo de los servicios de vigilancia, conservación y salvamento, salvo que por razones ambientales o de seguridad el organismo de cuenca considere conveniente su limitación. c) Varado y amarre de embarcaciones de forma ocasional y en caso de necesidad.» (La redacción anterior a la reforma de 2016 enumeraba otros fines —vigilancia, pesca fluvial, salvamento, varado—; ya no está vigente y no debe citarse.)
- **Art. 7.2, literal:** «Los propietarios de estas zonas de servidumbre podrán libremente sembrar y plantar especies no arbóreas, siempre que no deterioren el ecosistema fluvial o impidan el paso señalado en el apartado anterior. Las talas o plantaciones de especies arbóreas requerirán autorización del organismo de cuenca.»
- **Art. 7.3 (construcción), literal en lo esencial:** «Con carácter general no se podrá realizar ningún tipo de construcción en esta zona salvo que resulte conveniente o necesaria para el uso del dominio público hidráulico o para su conservación y restauración. Solo podrán autorizarse edificaciones en zona de servidumbre en casos muy justificados.» Añade que debe garantizarse «la efectividad de la servidumbre, procurando su continuidad o su ubicación alternativa».
- **Art. 8, literal:** «Por razones topográficas, hidrográficas, o si lo exigieran las características de la concesión de un aprovechamiento hidráulico, podrá modificarse la zona de servidumbre. La modificación se hará por causas justificadas de exigencia del uso público, previa la tramitación de un expediente en el que se oirá al propietario del terreno y, en su caso, al titular de la concesión, determinándose la correspondiente indemnización de acuerdo con la legislación de expropiación forzosa, si procediera.» Es decir, 5 m es la regla general, no un valor fijo.
- El art. 7.1 b) incluye «paso público peatonal», limitable por el organismo de cuenca por razones ambientales o de seguridad. No se interpreta más (lección 0021). Texto leído el 2026-11-27 en el consolidado del BOE (carácter informativo).

**4. Coherencia del texto de la ficha (CA5).** Texto aprobado por el fundador, sin modificarlo: «Zona de servidumbre aproximada de la margen de un cauce (art. 6 TRLA), calculada a partir del eje del cauce de la capa del IGN. Es una aproximación, no un deslinde.» Es **coherente** con lo leído: el art. 6 TRLA es la fuente de la servidumbre; «margen» y «cauce» son los términos del artículo; «aproximada» y «a partir del eje» cubren que la ley no fija el punto de medida y que la anchura puede modificarse (TRLA art. 6.2, RDPH art. 8); «no un deslinde» es exacto. Observación, no cambio: la ficha no menciona la anchura de 5 m ni los usos del art. 7 RDPH; las historias de publicar decidirán si los citan. Sobre la atribución, la ficha no la contiene: va aparte, según el punto 1.

**5. Estado de desbloqueo (CA4).** La licencia sí permite publicar derivados con atribución, así que no hace falta comentario en #196 ni bloquear las historias de derivar y publicar. Queda como condición previa de ellas leer la tabla `scne.es/productos.html` para fijar la cadena de atribución exacta.

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

## Montes de utilidad pública — IDEM, Comunidad de Madrid (`Zonas:IDEM_MA_MONTES_UP`, historia #220)

Verificado el 2026-11-27 (peticiones reales; fixtures en `tests/fixtures/public_utility_forests/`).

- **Servicio**: mismo GeoServer y workspace que las vías pecuarias, WFS 2.0.0 en `https://idem.comunidad.madrid/geoidem/Zonas/wfs`, capa `Zonas:IDEM_MA_MONTES_UP`, EPSG:25830. 208 elementos en toda la Comunidad.
- **Esquema** (`DescribeFeatureType`, `wfs_describefeaturetype_montes_up.xml`): `CD_UP` (decimal), `DS_ELENCO`, `DS_NOMBRE`, `DS_MUNICIPIO`, `CD_COMARCA`, `DS_PROPIETARIO`, `DS_NOM_PROPIETARIO`, `DS_GESTION`, `CD_ANNO_INCOR_CAT`, `DS_DESLINDE`, `FC_APROB_DESLINDE`, `DS_AMOJONAMIENTO`, `FC_APROB_AMOJONA`, `NM_SUPERF_CATALOGO`, `GEOMETRY1`.
- **Titularidad**: la capa publica `DS_PROPIETARIO` y `DS_NOM_PROPIETARIO`. El parser lee solo `CD_UP`, `DS_NOMBRE`, `DS_MUNICIPIO` y la geometría (lista blanca); esos dos campos no entran en el dominio ni en ningún fichero. En las fixtures, sus valores reales están sustituidos por «PROPIETARIO FICTICIO» y «TITULAR FICTICIO».
- **Licencia**: `CC BY 4.0 Comunidad de Madrid`, `AccessConstraints` del workspace `Zonas` (mismo texto que vías pecuarias; el proveedor no publica un documento aparte). El test de integración de #220 la vuelve a leer del `GetCapabilities`.
- **Cobertura del ámbito** (bbox de cada término, margen 2 m; `numberMatched` y piezas tras recortar con el límite del IGN):

| INE | Municipio | `numberMatched` | Piezas tras recortar |
| --- | --- | --- | --- |
| 28043 | Colmenar de Oreja | 0 | 0 |
| 28013 | Aranjuez | 1 | 1 (`208` Soto de las Cuevas) |
| 28052 | Chinchón | 1 | 1 (`184`, 122 m²: astilla de borde) |
| 28019 | Belmonte de Tajo | 2 | 1 (`182`, 1 920 m²: astilla de borde) |
| 28170 | Villaconejos | 0 | 0 |
| 28180 | Villarejo de Salvanés | 1 | 0 |
| 28157 | Valdelaguna | 2 | 2 (`182` y `184`, multiparte) |

- **Colmenar de Oreja no tiene ningún monte**: la capa sale vacía y es un resultado válido («sin montes»).
- **Astillas**: dos piezas (Chinchón, Belmonte) son diferencia entre la línea municipal de IDEM y la del IGN. No se filtran (como en vías pecuarias, ADR 0032).
- **Anillos interiores**: las respuestas de Valdelaguna traen `gml:interior` (21 contra 28 `gml:exterior`). El parser solo lee `gml:exterior` (ADR 0011): el área de la pieza puede sobrestimar el monte si hay claros dentro. Pendiente si algún día se publica el área.
- **No usado**: el catálogo nacional de MITECO; la capa autonómica es de la misma administración, ya en EPSG:25830 y con licencia leída.

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

En #26 las siete filas quedaron `bloqueado`: solo se había buscado en el BOCM, y las clasificaciones anteriores a 1984 se publicaron en el BOE. Chinchón, Villaconejos y Villarejo de Salvanés se resolvieron en la historia #281 (2026-11-27): ver «Órdenes de clasificación leídas en el BOE — historia #281» más abajo. Colmenar de Oreja, Aranjuez, Belmonte de Tajo y Valdelaguna se consultaron en la historia #282: ver «Canales consultados — historia #282». «No localizada» significa «no localizada por los canales consultados», no «no existe».

| Municipio | INE | Orden de clasificación | Estado |
| --- | --- | --- | --- |
| Colmenar de Oreja | 28043 | no localizada en BOE ni BOCM (canales en #282) | no localizada |
| Aranjuez | 28013 | no localizada en BOE ni BOCM (canales en #282) | no localizada |
| Chinchón | 28052 | Orden de 20/05/1974, BOE-A-1974-44784 (sección #281) | `confirmado` |
| Belmonte de Tajo | 28019 | no localizada en BOE ni BOCM (canales en #282) | no localizada |
| Villaconejos | 28170 | Orden de 13/07/1972, BOE-A-1972-46448 (sección #281) | `confirmado` |
| Villarejo de Salvanés | 28180 | Orden de 08/10/1969, BOE-A-1969-49149, y primera modificación de 20/05/1974, BOE-A-1974-44786 (sección #281) | `confirmado` |
| Valdelaguna | 28157 | no localizada en BOE ni BOCM (canales en #282) | no localizada |

`asumido`: la clasificación de vías pecuarias en la Comunidad de Madrid se aprueba por orden de la Consejería competente en medio ambiente (Ley 8/1998, citada en el `Abstract` del WMS `Zonas`, `wms_zonas_getcapabilities.xml`). Por eso el sitio donde buscarla es el BOCM. La cita exacta de la norma de cada municipio no se ha comprobado.

### Canales consultados — historia #282 (2026-11-27) — `confirmado` salvo lo indicado

Consulta del 2026-11-27 para los cuatro municipios sin orden localizada en #26: Colmenar de Oreja (28043), Aranjuez (28013), Belmonte de Tajo (28019) y Valdelaguna (28157). Un canal que no se pudo leer se anota como tal, con su motivo, y no como «no hay». Los extractos versionados, con el sha256 de cada respuesta, son `tests/fixtures/caminos/clasificacion_282_extracto_boe.txt` (sha256 `4c6d18d0c2d0b2c889115865ca40a74b3d3c67b5e494d9742619cc0ba1c96a4d`) y `tests/fixtures/caminos/clasificacion_282_extracto_bocm.txt` (sha256 `937b1b75bfd399d521b69fbbe75acbfcf174055af74aacea8fd028455c55ebd0`). En los extractos se han sustituido por `[sociedad omitida]` o `[proyecto omitido]` los nombres de sociedades y de proyectos de instalaciones que citaba la fuente, y el sha256 es el del extracto ya depurado, no el de la respuesta cruda. Matriz de consulta: solo títulos genéricos y por municipio; no se probó una orden agrupada de varios términos, porque ninguna búsqueda genérica devolvió una orden de clasificación de estos municipios. Las respuestas crudas están en `data/raw/h282/` (caché, fuera de git).

Patrones de consulta (`<municipio>` o `<término>` es lo que se indica en cada fila):

- BOE, por título: `https://www.boe.es/buscar/boe.php?campo[1]=TITULOS&dato[1]=<término>&accion=Buscar&sort_field[0]=FPU&sort_order[0]=desc` (la búsqueda rápida del BOE redirige a esta URL).
- BOCM, búsqueda avanzada: `https://www.bocm.es/advanced-search?search_api_views_fulltext_1=<término>`; con frase exacta, el término va entre `%22`.

| Canal | Término | Colmenar de Oreja (28043) | Aranjuez (28013) | Belmonte de Tajo (28019) | Valdelaguna (28157) |
| --- | --- | --- | --- | --- | --- |
| BOE, título: clasificación | `clasificación vías pecuarias <municipio>` | sin documentos | sin documentos | sin documentos | sin documentos |
| BOE, título: pecuarias | `pecuarias <municipio>` | sin documentos | sin documentos | sin documentos | sin documentos |
| BOE, título: proyecto de clasificación | `proyecto de clasificación vías pecuarias <municipio>` | sin documentos | sin documentos | sin documentos | sin documentos |
| BOE, título: solo el municipio | `<municipio>`, primera página (las 60 más recientes) | 25 documentos; ninguno de vías pecuarias | 8 documentos; ninguno de vías pecuarias | 33 documentos; ninguno de vías pecuarias | 19 documentos; ninguno de vías pecuarias |
| BOCM, frase exacta | `"clasificación de las vías pecuarias del término municipal de <municipio>"` (paginador: 2.405 páginas) | página 1 sin orden del término; salen Colmenar del Arroyo, Chapinería y Lozoya | página 1 sin orden del término (paginador: 2.289 páginas) | página 1 sin orden del término (paginador: 2.345 páginas) | página 1 sin orden del término (paginador: 2.100 páginas) |
| BOCM, texto libre | `vías pecuarias <municipio>` | página 1: ocupaciones de 2013 y 2023 en el término y la clasificación de Colmenar del Arroyo | página 1: una ocupación de 2022 en el término y deslindes de Redueña y Titulcia | página 1: un deslinde de Fuentidueña de Tajo | página 1: ningún resultado del término |

Canales generales, sin municipio:

| Canal | Consulta | Resultado |
| --- | --- | --- |
| BOE, título genérico | `campo[1]=TITULOS&dato[1]=clasificación de las vías pecuarias` | primera página (50 referencias): ningún título de los cuatro municipios; órdenes de otras provincias |
| BOE, título genérico | `campo[1]=TITULOS&dato[1]=proyecto de clasificación vías pecuarias` | primera página (50 referencias): ningún título de los cuatro municipios |
| BOE, texto completo | `campo[1]=TEXTO` y `campo[1]=TODO` | no se pudo leer: el formulario responde «Los valores de búsqueda enviados son incorrectos» |
| BOE, sumarios 1960–1990 (Medio Ambiente y Agricultura) | lectura sumario a sumario | no se pudo leer: no se leyó ningún sumario de esos años. La búsqueda por título sí devuelve documentos de 1969 a 1986, pero no sustituye la lectura del sumario |
| BOCM, archivo por boletín | boletines anteriores a 2009 | no se pudo leer: los resultados vistos empiezan en 2009 (Acuerdo de 11 de noviembre de 2009); no se comprobó el inicio de la serie del buscador ni se leyó ningún boletín anterior |
| BOCM, ELI | `https://www.bocm.es/eli` | no se pudo leer como archivo: la página de entrada no muestra listado por norma ni por fecha |
| BOCM, índices anuales de la Consejería | `https://www.bocm.es/boletin-archivo` | no se pudo leer: 404; no se localizó ningún índice anual |
| BOE, control positivo | títulos con «pecuarias» y un municipio conocido | Chinchón (1 documento, orden de 1974), Villaconejos (1972) y Villarejo de Salvanés (1969 y 1974): el buscador por título encuentra órdenes cuando existen |
| BOCM, control positivo | frase exacta con Chapinería | la Orden 3/2011 sale en el primer resultado |
| BOCM, control no válido | texto libre con Villaconejos | no pone en la página 1 ninguna orden de Villaconejos, aunque el BOE sí tiene una de 1972: el texto libre no sirve para afirmar ausencias |

Conclusión (`confirmado` para los canales; la conclusión sobre el municipio es de alcance limitado):

- Colmenar de Oreja, Aranjuez, Belmonte de Tajo y Valdelaguna: **no localizada** en los canales de arriba (BOE por título; BOCM por frase exacta en la primera página). Esto no es un «no hay»: quedan sin leer los sumarios del BOE de 1960 a 1990, el archivo por boletín del BOCM anterior a 2009 y el texto completo del BOE.
- Siguiente paso: solicitud al Fondo Documental, borrador en #284. Desde aquí no se envía nada.
- Orden localizada (la fila con referencia, URL y fixture) y propuesta de historia hija en #280: no aplican, porque en esta pasada no se localizó ninguna orden legible.
- Esta sección no clasifica ningún tramo ni cambia el mapa.

### Órdenes de clasificación leídas en el BOE — historia #281

Descargadas y leídas el **2026-11-27** (historia [#281](https://github.com/murcialito/paso-comun/issues/281), hija de #280). Cada PDF se descargó con `curl` desde el enlace «PDF» de la ficha `doc.php?id=…` y se leyó con la herramienta de lectura de PDF (imagen y texto de la página). Las cifras de las tablas se transcriben de la **imagen**; el texto extraído tiene errores de reconocimiento (en Chinchón, «6,E9» y «6 69» por 6,69). Fixtures en `tests/fixtures/caminos/` (el PDF es la página de la disposición en el BOE, que comparte página con otras disposiciones sin relación).

| Municipio | Disposición | Fecha de la orden | Ficha | PDF | Fixture (bytes) | Estado |
| --- | --- | --- | --- | --- | --- | --- |
| Chinchón (28052) | BOE-A-1974-44784, clasificación | 1974-05-20 (BOE 177, 25-07-1974, pp. 15414-15415) | https://www.boe.es/buscar/doc.php?id=BOE-A-1974-44784 | https://www.boe.es/boe/dias/1974/07/25/pdfs/A15414-15415.pdf | `boe_BOE-A-1974-44784.pdf` (164 669) | `confirmado` |
| Villarejo de Salvanés (28180) | BOE-A-1969-49149, clasificación | 1969-10-08 (BOE 248, 16-10-1969, p. 16179) | https://www.boe.es/buscar/doc.php?id=BOE-A-1969-49149 | https://www.boe.es/boe/dias/1969/10/16/pdfs/A16179-16179.pdf | `boe_BOE-A-1969-49149.pdf` (86 526) | `confirmado` |
| Villarejo de Salvanés (28180) | BOE-A-1974-44786, primera modificación | 1974-05-20 (BOE 177, 25-07-1974, p. 15415) | https://www.boe.es/buscar/doc.php?id=BOE-A-1974-44786 | https://www.boe.es/boe/dias/1974/07/25/pdfs/A15415-15415.pdf | `boe_BOE-A-1974-44786.pdf` (88 331) | `confirmado` |
| Villaconejos (28170) | BOE-A-1972-46448, clasificación | 1972-07-13 (BOE 199, 19-08-1972, p. 15328) | https://www.boe.es/buscar/doc.php?id=BOE-A-1972-46448 | https://www.boe.es/boe/dias/1972/08/19/pdfs/A15328-15328.pdf | `boe_BOE-A-1972-46448.pdf` (87 682) | `confirmado` |

Fecha de descarga de las cuatro: 2026-11-27. En la ficha del BOE la orden de Villaconejos lleva fecha de publicación 1972-08-19; la fecha de la orden es la que firma el texto (13 de julio de 1972).

**Licencia — `confirmado`.** Condiciones de reutilización de la sede del BOE, leídas el 2026-11-27 en `https://www.boe.es/informacion/aviso_legal/index.php` (apartado «Condiciones de reutilización», conforme a la licencia tipo aprobada por Resolución de la Agencia de 27 de junio de 2024): permiten «la reutilización de los documentos sometidos a ellas para fines comerciales y no comerciales, siempre que dicho uso no constituya una actividad administrativa pública y que se realice una utilización diligente de los contenidos». Condiciones que se cumplen aquí: citar la fuente con enlace a `https://www.boe.es`; en una obra derivada, «Basado en datos de la Agencia Estatal Boletín Oficial del Estado»; no sugerir carácter oficial ni patrocinio de la Agencia. Las anchuras transcritas son una extracción de datos de la orden, no el texto oficial.

**Regla común a las tres órdenes.** Cada una dice, con esta redacción en lo esencial, que «en aquellos tramos de las mismas afectados por situaciones topográficas, paso por zonas urbanas, alteraciones por el transcurso del tiempo en cauces fluviales o situaciones de derecho previstas en el artículo 2.º del Reglamento de Vías Pecuarias, su anchura quedará definitivamente fijada al practicarse el deslinde». Esa frase **afecta a todas las vías de la orden** y a los tramos que reúnan alguna de esas situaciones. Villarejo de Salvanés (1969) la escribe «en el artículo segundo». Las anchuras de abajo son dato de la orden, no prueba de ocupación ni de que el camino exista hoy con esa anchura.

#### Chinchón — Orden de 20/05/1974 (BOE-A-1974-44784), 10 vías y 4 abrevaderos/descansaderos

Proyecto de clasificación de fecha 13 de abril de 1967, «cuyo contenido se tendrá presente en todo cuanto les afecte».

| N.º | Vía | Clase | Anchura según la orden | Tramo o descripción |
| --- | --- | --- | --- | --- |
| 1 | Cañada Galiana | cañada | tramo primero 37,61 m; tramo segundo 75,22 m | dos tramos; el recorrido está en el proyecto de 1967 |
| 2 | Cordel llamado de La Julia | cordel | tramo primero 37,61 m | solo se cita el tramo primero |
| 3 | Vereda de La Blanca | vereda | tramo primero 6,69 m; tramo segundo 20,89 m | dos tramos |
| 4 | Vereda de La Carcabilla y Mojón Alto | vereda | 20,89 m | — |
| 5 | Vereda de Molincaldo | vereda | 20,89 m | — |
| 6 | Vereda del Rosario, Rostro de Valquegigoso y Valladares | vereda | 20,89 m | — |
| 7 | Vereda de La Cuesta del Gramoso | vereda | 20,89 m | — |
| 8 | Vereda de Valdelazarza | vereda | 20,89 m | — |
| 9 | Colada del Puente de Tablas o del Quiñón | colada | 6,69 m | — |
| 10 | Colada del Serranillo | colada | 12 m | — |

Frase de deslinde: afecta a las 10 vías (ver «Regla común»).

Abrevaderos y descansaderos: la orden da **superficie**, no anchura: A) La Fuente del Valle, 29 áreas y 11 centiáreas; B) Valquegigoso, 6 áreas y 82 centiáreas; C) Valdelaspozas, 29 áreas y 11 centiáreas; D) Valdelazarza, 46 áreas y 50 centiáreas. La orden no dice cuál es abrevadero y cuál descansadero; la encabeza «Abrevaderos y descansaderos». Las superficies de los tres primeros que aparecen en el texto con ruido («seis areas», «SO centiáreas») se comprobaron en la imagen.

#### Villarejo de Salvanés — Orden de 08/10/1969 (BOE-A-1969-49149), 3 vías

| Vía | Clase | Anchura según la orden | Tramo o descripción |
| --- | --- | --- | --- |
| Vereda del Cañuelo | vereda | 20,89 m | — |
| Vereda de San José | vereda | 20,89 m | — |
| Vereda de las Esperillas | vereda | 20,89 m | «Estas tres veredas con una anchura de 20,89 metros» |

Frase de deslinde: afecta a las tres (ver «Regla común»). La orden no recoge descansaderos ni abrevaderos. La modificación de 1974 escribe «Asperillas» donde esta orden escribe «Esperillas»: se recoge tal como figura en cada una; no se identifican como la misma vía sin leer el proyecto.

#### Villarejo de Salvanés — primera modificación, Orden de 20/05/1974 (BOE-A-1974-44786)

Amplía la clasificación de 1969 con dos vías y rectifica el recorrido de otra (proyecto de modificación de 29 de septiembre de 1973). Declara firme lo no opuesto del proyecto de 1969. Esta disposición comparte página con otras dos órdenes (Tales, Castellón; Domeño, Navarra), sin relación con el ámbito.

| N.º en la orden | Vía | Clase | Anchura según la orden | Tramo o descripción |
| --- | --- | --- | --- | --- |
| 3 a) | Vereda de las Asperillas, primer tramo | vereda | 33,43 m («anchura legal») | «queda comprendido entre los términos municipales de Villarrubia de Santiago y Villamanrique de Tajo» |
| 4 | Colada Toledana | colada | variable, mínimo 6 m, «determinada con exactitud en el acto de su reglamentario deslinde» | «tiene como eje el antiguo camino viejo de Villamanrique a Fuentidueña de Tajo» |
| 3 b) | Vereda de las Asperillas, segundo tramo | vereda | no se da anchura | «su itinerario queda fijado de conformidad con la descripción» del proyecto de modificación (recorrido rectificado) |

Frase de deslinde: esta orden no la repite; la anchura de la Colada Toledana la fija el deslinde por su propio texto. La cifra 33,43 m (inusual frente a los 20,89 m de la orden de 1969) se comprobó en la imagen: «33,43 metros».

#### Villaconejos — Orden de 13/07/1972 (BOE-A-1972-46448), 2 vías

Proyecto de clasificación redactado por un perito agrícola del Estado (no se reproduce su nombre).

| Vía | Clase | Anchura según la orden | Tramo o descripción |
| --- | --- | --- | --- |
| Vereda del Raso | vereda | 20,89 m | — |
| Vereda del Rosario | vereda | 20,89 m | — |

Frase de deslinde: afecta a las dos (ver «Regla común»). La orden no recoge descansaderos ni abrevaderos.

#### Qué se verificó y qué no (#281)

- **Verificado contra la imagen del PDF:** las cifras de anchura y superficie de las cuatro tablas, los nombres de las vías, las fechas de las órdenes y los números de página. Los nombres de vías se dan como en la imagen (el texto extraído tiene errores de OCR: «Cañweio» por «Cañuelo»).
- **No verificado / fuera de la orden:** el recorrido, la dirección y la superficie de cada vía están en los proyectos de clasificación (1967, 1973 y los de 1969 y 1972), que **no** se han localizado ni leído. La anchura de la orden es la legal, no la que hoy tenga el camino. Aquí no hay geometría ni deslinde.
- **Canal ilegible ≠ «no hay»:** no se leyó el texto completo del BOE (`campo[1]=TEXTO`), ni los sumarios de 1960–1990 (ver #282); en Chinchón no se buscó una modificación posterior ni deslindes. Para Villaconejos y Chinchón no se ha comprobado si existe modificación como la de Villarejo.
- **Datos personales:** las cuatro páginas del BOE mencionan nombres de personas (periciales de los proyectos y, en la modificación de Villarejo, una reclamación desestimada). No se copian a este registro ni a ningún fichero de texto; el PDF es el documento oficial tal cual.
- **Anchuras y ley vigente:** las órdenes citan el Reglamento de Vías Pecuarias de 1944; no dicen de dónde salen sus cifras. Su relación con las anchuras máximas de la Ley 3/1995, art. 4, no se ha estudiado aquí.

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

### Red asfaltada del IGN como contraparte (historia #183)

ADR 0050. Misma fuente (`roadlink`, CC BY 4.0, #24) y mismo endpoint que #27; solo cambia el filtro: `filter=surfacecategory='paved'`. `camino-actual-municipios` escribe además `data/derived/camino_asfaltado/<ine>.geojson` (formato común, `fuente: ign_red_transporte`, `superficie: paved`), que **no se publica**: solo lo lee `discrepancias` como contraparte, nunca como sujeto. Estado: `confirmado`.

Consulta real del **2026-11-27** con red (caché nueva en `data/raw`, límites del IGN, bbox del término con margen 2 m, EPSG:25830, `limit=500` y `offset`). Las cifras salen de pasar las respuestas íntegras por `RoadNetworkAdapter.query_roads(..., "paved")` y `ShapelyLineClipper` (lección #36):

| INE | Municipio | `numberMatched` `paved` | `unpaved` (#27) + `paved` = sin filtro (#27) | Piezas en el término | `fictitious="true"` | Longitud (m) |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| 28043 | Colmenar de Oreja | 2.222 | 1.774 + 2.222 = 3.996 ✔ | 1.184 | 1.077 | 166.382 |
| 28013 | Aranjuez | 14.035 | 5.522 + 14.035 = 19.557 ✔ | 2.628 | 2.190 | 286.985 |
| 28052 | Chinchón | 2.465 | 1.492 + 2.465 = 3.957 ✔ | 766 | 698 | 100.377 |
| 28019 | Belmonte de Tajo | 608 | 523 + 608 = 1.131 ✔ | 308 | 279 | 27.178 |
| 28170 | Villaconejos | 453 | 370 + 453 = 823 ✔ | 401 | 390 | 34.500 |
| 28180 | Villarejo de Salvanés | 1.492 | 1.446 + 1.492 = 2.938 ✔ | 855 | 745 | 122.875 |
| 28157 | Valdelaguna | 779 | 552 + 779 = 1.331 ✔ | 301 | 280 | 40.719 |

- **No hay un tercer valor de `surfacecategory`** en ninguno de los 7 términos: `unpaved + paved` da el `numberMatched` sin filtro de #27.
- A diferencia de los caminos, en la red asfaltada sí hay tramos `fictitious="false"` (107 de 1.184 piezas en Colmenar).
- La misma pasada regeneró `camino_actual`: 893 tramos en Colmenar, y `publicar-capas --municipio 28043 --capa camino_actual` da un fichero idéntico al publicado salvo la `fecha_descarga` (caché nueva: 2026-11-27 en vez de 2026-11-26). `site/datos/camino_actual/` no cambia en esta historia (CA5).
- **Fixtures**: `tests/fixtures/road_network/roadlink_paved_recorte_municipio_<ine>.json` son **recortes** de esa respuesta: 8 tramos reales por municipio, sin tocar geometría ni propiedades (2 que cruzan el límite, 2 de vecinos que no lo tocan, 2 no ficticios y el resto dentro), elegidos por orden de `id_tramo` con un script de Bloque 0 que pasa la respuesta por el adapter y el recorte; `numberMatched`/`numberReturned` ajustados a 8. Las fixtures de `tests/fixtures/asfaltado/` son **sintéticas** (ver su LEEME.md).

#### Indicios antes y después, sin Catastro (Bloque 0, 2026-11-27)

`discrepancias --ambito` y `publicar-discrepancias --ambito` sobre las capas reales recién regeneradas, sin `catastro_caminos` (Catastro ausente). «Antes» usa las mismas capas con `camino_asfaltado` vacío; reproduce **exactamente** los ids publicados hoy en `site/datos/discrepancias/` (que no tienen registros con Catastro).

| INE | Municipio | Publicados antes | Publicados después | Ids que siguen | Antes → después por tipo |
| --- | --- | ---: | ---: | ---: | --- |
| 28043 | Colmenar de Oreja | 19 | 19 | 10 | `AUSENTE` 1 → 1, `DESPLAZAMIENTO` 2 → 2, `SOLAPE` 16 → 16 |
| 28013 | Aranjuez | 27 | 27 | 14 | `AUSENTE` 5 → 3, `DESPLAZAMIENTO` 4 → 4, `SOLAPE` 18 → 20 |
| 28052 | Chinchón | 19 | 17 | 11 | `AUSENTE` 4 → 3, `SOLAPE` 15 → 14 |
| 28019 | Belmonte de Tajo | 0 | 0 | — | — |
| 28170 | Villaconejos | 4 | 2 | 2 | `AUSENTE` 2 → 1, `SOLAPE` 2 → 1 |
| 28180 | Villarejo de Salvanés | 5 | 5 | 2 | `DESPLAZAMIENTO` 1 → 1, `SOLAPE` 4 → 4 |
| 28157 | Valdelaguna | 0 | 0 | — | — |

Un `SOLAPE` reducido a su parte sin contraparte cambia de zona y por tanto de id: en Colmenar los 19 siguen siendo 19, pero 9 son `SOLAPE` nuevos más cortos (como mucho un 8,7 % de su zona a ≤ 15 m de asfalto) que sustituyen a 9 anteriores.

**Los 3 indicios de Colmenar con ≥ 57 % de su zona a ≤ 15 m de un tramo `paved`** (medido con `shapely` sobre `site/datos/discrepancias/28043.geojson` de `main`, zonas reproyectadas a EPSG:25830; para un polígono, su contorno):

| `public_id` | Tipo | Sobre asfalto | Después |
| --- | --- | ---: | --- |
| `228d09f82d066f2e` | `SOLAPE` vía → IGN | 82,2 % | deja de publicarse (reducido) |
| `415956c18feed794` | `DESPLAZAMIENTO` IGN (sin asfaltar) → vía | 64,5 % | **se mantiene a propósito** |
| `b1f47704c7f34945` | `SOLAPE` vía → IGN | 57,0 % | deja de publicarse (reducido) |

`415956c18feed794` se mantiene **a propósito** (decisión del fundador en #183, «opción 1», que reescribe CA8): su sujeto es un camino **sin asfaltar** (`280430215621`) que corre en paralelo a una carretera, a 13–25 m de ella y a 24–40 m de la vía, y no va bajo asfalto; la vía, en ese tramo, tampoco (1,9 % cubierta a ≤ 11,18 m). La red asfaltada no entra en esa comparación (su contraparte es la vía), y no se añade ninguna regla para suprimirlo (ADR 0050). Ningún indicio publicado tiene como sujeto un tramo asfaltado. Los otros tres que el arquitecto midió entre el 25 % y el 36 % (`58c697f68088debf`, `c6a7f6f2a943c5d9`, `a2d854c24b69ae92`) también se reducen.

#### Paso local con Catastro (CA9 y CA13, hecho el 2026-11-27)

Ejecutado en local el 2026-11-27 (paso 11 del diseño; antes `pendiente-local`): `catastro-caminos --sin-red`, `camino-actual-municipios` (con red), `discrepancias --ambito`, `publicar-discrepancias --ambito`, `candidatos-corte --municipio 28043 --sin-red` y `revision-candidatos --municipio 28043`. `vias-pecuarias-municipios --sin-red` falla porque la respuesta de IDEM no está en la caché cruda; se usaron las capas derivadas de vías pecuarias ya existentes, las mismas que produjeron los indicios publicados antes. La capa `camino_actual` regenerada es idéntica a la anterior en los 7 municipios (mismos ids); lo nuevo es `camino_asfaltado`. Como su `fecha_descarga` pasa al 2026-11-27, se republicó también con `publicar-capas --ambito` (mismos tramos, solo cambia la fecha), para que coincida con la de los indicios. Las vías pecuarias siguen con el 2026-11-26 y Catastro con el 2026-11-27: las fechas de las fuentes de un indicio pueden diferir, y cada una coincide con su capa de origen.

**Colmenar sube de 19 a 32 por Catastro, no por esta historia.** Los 19 indicios publicados antes se generaron sin la capa interna de Catastro. Con ella, se publican por primera vez indicios con Catastro como **contraparte** (ADR 0041 y 0044: sin geometría ni referencias de Catastro, con su atribución y aviso de no fehaciencia), y se omiten 348 con Catastro en el lado A. Para aislar el efecto de #183 se repitió Colmenar **sin** Catastro: siguen siendo 19 indicios, pero 9 ids cambian. Son `228d09f82d066f2e` y `b1f47704c7f34945` (CA8) y otros 7 `SOLAPE` cuya zona se reduce a la parte sin contraparte asfaltada, lo que cambia el id público. `415956c18feed794` se mantiene.

**Candidatos de Colmenar.** Siguen siendo los mismos 40, con la misma geometría, pero en 36 cambia la evidencia `longitud_base_m` (por ejemplo, 1174,706 → 1161,1 m): la discrepancia base se reduce por el tramo asfaltado, que ahora es solo contraparte. Su huella cambia y **36 de las 40 aprobaciones caducaron** (medido el 2026-11-27: 4 vigentes, 36 caducadas, 0 huérfanas). El fundador las volvió a aprobar con la huella nueva en la PR #300 (2026-11-28, fusionada por él; ADR 0047), así que la tabla recoge el estado tras #300: 40 vigentes, 0 caducadas, 0 huérfanas. Siguen siendo aprobaciones provisionales de prueba (#181). `site/datos/candidatos/` no se republica en esta PR (hoy no hay ninguno publicado).

| INE | Municipio | Indicios publicados antes | Después |
| --- | --- | ---: | ---: |
| 28043 | Colmenar de Oreja | 19 | 32 |
| 28013 | Aranjuez | 27 | 27 |
| 28052 | Chinchón | 19 | 17 |
| 28019 | Belmonte de Tajo | 0 | 0 |
| 28170 | Villaconejos | 4 | 2 |
| 28180 | Villarejo de Salvanés | 5 | 5 |
| 28157 | Valdelaguna | 0 | 0 |

| Medida | Antes | Después |
| --- | ---: | ---: |
| candidatos de 28043 | 40 | 40 |
| aprobaciones vigentes | 40 | 40 |
| aprobaciones caducadas | 0 | 0 |
| revisiones huérfanas | 0 | 0 |

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
- **Uso en #208** (ADR 0052): 1975 (`CM_1975`) y 1991 (`CM_1991`) entran en la serie de imágenes de comparación como franjas propias y se enlazan en las fichas de tramos a verificar con la atribución literal precedida de «Obra derivada de» y el aviso de carácter informativo. 1956 (`CM_1956`) queda fuera de la serie hasta confirmar la licencia del CECAF (decisión del fundador en #208). Medidas de `GetMap` del arquitecto, 2026-11-27: 1024 × 1024 px en `CM_1975` → 200 `image/png`, 1.488.555 bytes, idénticos en dos peticiones; `CM_1991` en la ventana `463638,4437138,463862,4437362` (448 px) → 200 `image/png`, 218.049 bytes, imagen real. Esa ventana es la del test de integración de #208 (CA10, marcador `red`).

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

## Catastro a una fecha (historia #209)

Hija de #201. Solo recoge lo **legible desde GitHub Actions** (páginas de ayuda y texto de licencia). Las peticiones reales a `ovc.catastro.meh.es` van en #236 y se pasan en local, porque esa máquina rechaza las conexiones de los runners (lección de #37).

### Qué dice la ayuda de antecedentes — según la documentación, sin verificar con petición real

Canal: `https://www.catastro.hacienda.gob.es/ayuda/ayuda_antecedentes.htm` (HTTP 200, HTML, leída el 2026-11-27). Resumen, no copia:

- Existe una capa del visor de la Sede Electrónica llamada «Cartografía a una fecha» («Antecedentes Cartografía»), con un calendario para elegir día, mes y año.
- Rango: «una consulta estable y fluida desde el 1 de enero de 2005 hasta la actualidad». Hay municipios cuya cartografía digital es posterior a 2005; si no aparece a la fecha elegida, es que no existía.
- Capas: la cartografía digital catastral histórica (líneas de parcelas y edificios) sobre la ortofoto PNOA actual como fondo.
- Es un **WMS**: solo visualización. La página dice que «no permite descargar las geometrías históricas». Tampoco permite consultar datos no protegidos históricos de una parcela.
- Uso responsable: servicio libre y gratuito; el abuso puede acarrear restricciones.
- Para tener las geometrías, remite a la Difusión de Datos Catastrales (Shapefile) y a filtrar la tabla por los campos `FECHAALTA` y `FECHABAJA` para ver la geometría a una fecha.
- **La página no nombra el parámetro WMS** (`TIME` u otro) ni la capa. #236 comprobó que el WMS acepta `TIME=AAAA-MM-DD` (ver «Peticiones reales» abajo).
- Canales no consultados: el `GetCapabilities` del WMS (es `ovc.catastro.meh.es`, no legible desde Actions) y la descarga de Shapefile.

### Licencia: ¿puede una fecha derivada apoyar un indicio publicado?

Documento primario: `https://www.catastro.hacienda.gob.es/webinspire/documentos/Licencia.pdf` (HTTP 200, PDF de 3 páginas, 2026-11-27). **Limitación:** el PDF usa fuentes con codificación propia y no se pudo extraer su texto en esta pasada (ni con `WebFetch` ni descomprimiendo los flujos). Las citas literales de abajo son las que ya se anotaron al leerlo en #21 (2026-11-25), arriba, en «Catastro INSPIRE»; **no se han releído en #209**. Quien pueda abrir el PDF en un visor debería confirmar la numeración de las cláusulas.

- «sea transformada» — condición para «la elaboración y distribución de nuevos productos de valor añadido».
- Prohibido difundir la información original «por Internet ni por ningún otro medio sin su previa transformación».
- La transformación no puede alterar ni desnaturalizar el contenido; el producto no se identifica como «cartografía catastral» ni «información catastral».
- La información distribuida a terceros «carecerá de fehaciencia».

**Conclusión con cautela (no es un permiso):** una **fecha** o un intervalo de fechas, sin geometría ni referencia de parcela, no reproduce la información original y parece encajar en lo derivado que ya se publica (indicios, señales y candidatos, ADR 0041). Pero el texto no habla de fechas sueltas, y una fecha de alta/baja procede del dato original. **Decisión del fundador (2026-11-28, comentario en #201):** sí, se puede publicar una fecha derivada de Catastro. Las condiciones son las de esta sección y las de los indicios con Catastro (ADR 0041 y 0044):
- como intervalo «entre A y B», con la fuente y la evidencia de cada extremo;
- sin geometría, sin referencias catastrales y sin datos de parcela;
- con la atribución a la Dirección General del Catastro, la fecha de consulta y el aviso de no fehaciencia.

### Cómo expresar la fecha: intervalo con evidencia

`FECHAALTA`/`FECHABAJA` (y la fecha del WMS) son del **registro de la parcela**, no de cuándo se cerró o desapareció el camino físico: una parcela se da de baja o se parte por un trámite que puede ir años por detrás o por delante del hecho. Por eso:

- Se expresa como intervalo «**entre A y B**», nunca como fecha puntual del corte.
- Cada extremo lleva su **fuente y su evidencia**: A = última fecha en que el trazado aparece (p. ej. «consta en la cartografía a fecha A», o un vuelo o minuta del año A); B = primera fecha en que ya no aparece (p. ej. «ya no consta a fecha B»). Con extremo desconocido, se escribe «sin dato», no se inventa.
- Ejemplo con datos inventados: «entre 2009 y 2015 — extremo inicial: cartografía catastral a fecha 2009-01-01, consta; extremo final: cartografía catastral a fecha 2015-01-01, no consta».
- Un único extremo de Catastro no basta: el intervalo se estrecha con las demás fuentes (vuelos históricos, minutas).
- El texto que se publique no dice «se cortó en…» ni da un año como hecho.

### Peticiones reales (#236, en local, 2026-11-28)

Hechas desde la red del fundador: `ovc.catastro.meh.es` rechaza a los runners de Actions. `User-Agent: parcel-intel-verificacion/0.1`, unas 20 peticiones en total. Las respuestas están en `data/raw/catastro_fecha/` (fuera de git, ADR 0040).

| Qué | Estado | Dónde se resuelve |
|---|---|---|
| WMS con `TIME` (nombre de capa, formato de fecha, qué devuelve para 2005 y para hoy) | `confirmado` (2026-11-28): acepta `TIME=AAAA-MM-DD` aunque no lo declara; las imágenes de 2005 y de hoy difieren; en la tesela probada hay datos desde diciembre de 2001 | [#236](https://github.com/murcialito/paso-comun/issues/236), en local |
| Campos `FECHAALTA`/`FECHABAJA` del WFS (¿existen, con qué formato?) | `descartado` en el WFS INSPIRE (2026-11-28): no existen, trae `beginLifespanVersion` y `endLifespanVersion` vacío. Sí existen en el Shapefile (`AAAAMMDD`), pero solo con parcelas vigentes | [#236](https://github.com/murcialito/paso-comun/issues/236), en local |

**WMS a una fecha (CA1).**
- Servicio `https://ovc.catastro.meh.es/Cartografia/WMS/ServidorWMS.aspx`, **WMS 1.1.1**, con el parámetro `SRS`. Con `VERSION=1.3.0` y `CRS` responde `200` con una `ServiceException` «SRS () Invalido».
- Capa `PARCELA`; el servicio tiene también `CONSTRU`, `SUBPARCE`, `MASA` y sus rótulos. `SRS=EPSG:25830`, `image/png`.
- El `GetCapabilities` no declara ninguna dimensión `TIME`, ni este WMS ni el INSPIRE (`spadgcwms.aspx`). Ninguno de los dos menciona fechas.
- Aun así, con `TIME=AAAA-MM-DD` dibuja el parcelario a esa fecha y estampa en la imagen el rótulo rojo «FECHA: dd/mm/aaaa». Prueba en una tesela de 900 m de Colmenar de Oreja, una de la rejilla de #37 (`BBOX=467341,4441523,468241,4442423`, 900 × 900 píxeles):
  - `TIME=2005-01-01` frente a `TIME=2026-11-28`: 28.436 píxeles distintos, con cambios de parcelario visibles.
  - Entre 2002-01-01 y 2005-01-01: 2.580 píxeles distintos.
  - Sin `TIME`: devuelve el parcelario actual sin rótulo. Solo difiere en el rótulo de la de hoy (1.932 píxeles).
  - `TIME=2005`, solo el año: se ignora y devuelve el actual. La fecha tiene que ser completa.
- **Fecha más antigua con datos en esa tesela**: entre el 2001-12-01, que solo trae el rótulo, y el 2001-12-31, que ya trae líneas. Con 1990, 1998, 2000, 2001-01, 2001-07, 2001-10 y 2001-12-01 responde **`200` con una imagen que solo tiene el rótulo** (≈1.900 píxeles dibujados frente a ≈20.000 con parcelario). Un `200` no prueba que haya datos: hay que comprobar que hay líneas. La ayuda habla de consulta estable desde 2005, y la fecha más antigua puede cambiar de una zona a otra.
- Es **solo imagen**, sin geometría. Sirve para decir «consta» o «no consta» a fecha X comparando imágenes, que es el extremo del intervalo que pide #201.

**Fechas en el WFS de parcelas (CA2).**
- El WFS INSPIRE de #37 (`wfsCP.aspx`) **no trae `FECHAALTA` ni `FECHABAJA`**. Cada `cp:CadastralParcel` lleva:
  - `cp:beginLifespanVersion`, fecha y hora ISO 8601 (por ejemplo `2012-06-08T00:00:00`): la fecha de alta de la versión vigente;
  - `cp:endLifespanVersion`, vacío (`xsi:nil="true"`, `nilReason` «Unpopulated»).
- En la caché de #37 (312 teselas y 38.888 elementos, contando repetidos entre teselas), `endLifespanVersion` va vacío en 38.887. El único con valor dice `3026-09-10T00:00:00`, un error del origen. `beginLifespanVersion` va del 2001-09-24 a 2026.
- **Solo trae parcelas vigentes.** Las dadas de baja o fusionadas no están en la descarga.
- El **Shapefile** de la Sede (descarga del fundador del 2026-11-27, foto del 14-08-2026; #298 y #299) sí tiene en `PARCELA.DBF` los campos `FECHAALTA` y `FECHABAJA`, numéricos de 8 cifras `AAAAMMDD`. Pero en las 13.100 parcelas rústicas de Colmenar `FECHABAJA` vale `99999999`: también trae solo las vigentes.
- El filtro por `FECHAALTA`/`FECHABAJA` que propone la ayuda no recupera geometrías dadas de baja de una descarga actual. Para eso harían falta descargas antiguas guardadas, o comparar imágenes del WMS.

**Qué cambia para #201.**
- La única forma de ver el parcelario de una fecha pasada es el WMS con `TIME`, y solo como imagen.
- `beginLifespanVersion` y `FECHAALTA` solo dicen desde cuándo existe la versión vigente de una parcela, no cuándo desapareció otra.
- La fecha derivada de Catastro se puede publicar con las condiciones de arriba (decisión del fundador, 2026-11-28).

### Fixtures sintéticas

`tests/fixtures/catastro_historico/` contiene solo ejemplos **inventados** (ADR 0040); su README lo declara. No hay ninguna respuesta real de Catastro en git.

---

## SIGPAC de la Comunidad de Madrid: recintos, atributos, licencia y uso (historia #216)

Verificado el **2026-11-27** para la [historia #216](https://github.com/murcialito/paso-comun/issues/216) (hija de #200, señal de ocupación de la franja de la vía pecuaria con SIGPAC). Solo documentación: sin adapter ni código de producción. Los ficheros crudos están en `data/raw/sigpac_madrid_28043/` (fuera de git); las fixtures de esta historia son solo la cabecera del DBF, el `.prj` y extractos de texto (`tests/fixtures/sigpac/`).

### Procedencia de lo descargado

| Recurso | URL | sha256 | Bytes | Estado |
|---|---|---|---|---|
| ZIP de recintos de Colmenar de Oreja (28043) | `https://idem.comunidad.madrid/recursos_cat_geo/Catalogo/recursos/UsoDelSuelo/spacm_sigpac.tm.28043.zip` | `74dfc29a7ebf7639aeb1a14a9b1715a616d0aec029c1e2749a1a90e4ea04c46f` | 21.319.837 | `confirmado` (descargado y leído) |
| Feed ATOM de Madrid (`updated` 2025-12-15) | `https://idem.comunidad.madrid/recursos_cat_geo/Catalogo/atom/ds.cm_sigpac.xml` | `c289d729a264440e474284571ccf3cc89ccc34c49a129caf6276a7397dbd255f` | 358.671 | `confirmado` |
| Ficha en datos.gob.es | `https://datos.gob.es/es/catalogo/a13002908-recintos-sigpac-de-la-comunidad-de-madrid` | `5c7de03c3bc20b2ac9ab517cfc3dd9e3f7bfe4b8d186d65e096542e9f5e3d692` | 109.444 | `confirmado` |
| «Términos de uso de la información de alto valor del SIGC» (FEGA), dentro del ZIP | `Terminos_de_uso_de_informacion_de_alto_valor_del_SIGC.pdf` | `bbf4908b9ffcc1805d050a1a9c4c4d124a90f4f405c50de72e4e711142015cdf` | 475.254 | `confirmado` (extraído del ZIP; texto leído sin OCR) |
| «Resumen de los datos contenidos en el SIGPAC para la campaña 2026», FEGA | copia en `https://www.agrodigital.com/wp-content/uploads/2026/02/SIGPAC2026.pdf` (el documento es del FEGA; leído solo la tabla de usos) | — | — | `confirmado` el contenido; copia de tercero |

El Shapefile trae `RECINTO.shp` (polígonos, tipo 5), `RECINTO.dbf` (21.633 registros, 20 campos), `RECINTO.prj` y el PDF de términos. El `.prj` es `GCS_ETRS_1989` (geográficas, sin código EPSG declarado).

### CA1 — Campos, tipos y usos reales; cómo aparecen los caminos y las vías pecuarias (`confirmado`)

Lectura del DBF con la librería estándar (sin dependencias): cabecera en `tests/fixtures/sigpac/recinto_dbf_cabecera.bin`. Todos los valores de la tabla son de los 21.633 recintos.

| Campo | Tipo (longitud, decimales) | Valores observados |
|---|---|---|
| `DN_PK` | N 23 | Identificador interno, único por registro (21.633 distintos) |
| `DN_OID` | N 23 | Identificador de objeto, único |
| `DN_VERSION` | N 11 | Versión del recinto (2.243 distintos) |
| `DN_INITIAL` | D 8 | Inicio de vigencia de la versión: de 2012-11-15 a 2025-11-28; 16.933 con año 2023 |
| `DN_ENDDATE` | D 8 | Vacío en todos |
| `SUPERFICIE` | N 20,5 | Superficie del recinto. El DBF no declara la unidad: la suma (126,4 km² en el término) indica **m²** (`asumido`) |
| `PROVINCIA` / `MUNICIPIO` | N 6 | 28 / 43 en todos |
| `AGREGADO` / `ZONA` | N 6 | 0 en casi todos (AGREGADO = 999 en 1 registro) |
| `POLIGONO` / `PARCELA` / `RECINTO` | N 6 / 11 / 11 | Identificadores SIGPAC (79 polígonos, 943 parcelas, 172 recintos distintos). **No son referencias catastrales** |
| `CSP 2023` | N 6 | Valores 0–100 (17 distintos). Significado no verificado en esta pasada |
| `PENDIENTE` / `ALTITUD` | N 6 | Valores numéricos (532 y 282 distintos). Unidades no declaradas: `asumido` (%, m) |
| `COEF_REGAD` | N 6 | 0 (10.916), 100 (2.686), vacío (8.031) |
| `USO_SIGPAC` | C 2 | Uso del recinto; tabla de abajo |
| `INCIDENCIA` | C 50 | Código de incidencia; vacío en 8.201. Codificación no leída |
| `REGION` | N 6 | 1, 7, 12, 16; vacío en 3.492. No documentado en esta pasada |

**Usos (`USO_SIGPAC`)**, con las descripciones del FEGA para la campaña 2026 (tabla de usos del Anexo IV del Real Decreto 1047/2022, según la propia ficha del FEGA):

| Código | Descripción (FEGA 2026) | Recintos | | Código | Descripción (FEGA 2026) | Recintos |
|---|---|---|---|---|---|---|
| TA | Tierras arables | 6.645 | | VI | Viñedo | 855 |
| OV | Olivar | 4.877 | | FY | Frutales | 619 |
| PR | Pasto arbustivo | 4.361 | | FO | Forestal | 468 |
| IM | Improductivos | 1.321 | | PS | Pastizal | 349 |
| **CA** | **Viales** | **1.228** | | AG | Corrientes y superficies de agua | 283 |
| ED | Edificaciones | 164 | | ZU | Zona urbana | 125 |
| VO | Viñedo-Olivar | 112 | | FS | Frutos secos | 97 |
| PA | Pasto con arbolado | 81 | | TH | Huerta | 29 |
| IV | Invernaderos y cultivos bajo plástico | 13 | | VF / OF / FV / FL | Viñedo-Frutal / Olivar-Frutal / Frutos secos y viñedo / Frutos secos y olivar | 2 / 2 / 1 / 1 |

Fuente de la tabla: `https://www.agrodigital.com/wp-content/uploads/2026/02/SIGPAC2026.pdf`, tabla «DESCRIPCIÓN USO SIGPAC» (`confirmado`). Usar `CA` = Viales para caminos (no hay código de «camino» ni de «vía pecuaria»).

**Cómo aparecen las vías pecuarias (cruce de control, `confirmado` como medida, sin validar contra un SIG de referencia).** SIGPAC no tiene código para vías pecuarias. Se cruzaron los 15 tramos de Colmenar de Oreja de la capa #36 (`tests/fixtures/livestock_trails/wfs_cql_colmenar_municipio_completo_15_tramos.xml`, EPSG:25830) con los recintos: cada vértice de cada polígono de tramo se pasó a lon/lat (inverso de UTM 30N, ETRS89) y se buscó el recinto que lo contiene.

- 3.188 vértices; 3.157 caen dentro de un recinto (99 %). Usos de esos vértices: **TA 857 (26,9 %), OV 713 (22,4 %), CA 442 (13,9 %), PR 420 (13,2 %), ZU 180 (5,6 %)**, FO 148, IM 131, VI 102, PS 51, otros < 40 cada uno.
- El peso de `CA` varía mucho entre tramos: en la Cañada de la Alameda 29 de 53 vértices caen en `CA`; en la Cañada de los Lanchares, 11 de 492. Ningún tramo se puede tomar como «de viales» por su uso SIGPAC.
- **Conclusión:** la franja de una vía pecuaria no aparece como tal en SIGPAC: su superficie lleva el uso del recinto que atraviesa (o del que se le superpone). Que un recinto sea `CA` indica viales, no vía pecuaria, y la ausencia de `CA` no prueba que la vía esté cubierta. No sirve como señal directa de ocupación; sí como contexto.
- Límites del cruce: se muestrean vértices del borde del polígono, no su interior; es un indicio de orden de magnitud, no una tabla de superficies.

### CA2 — Campos de titular, declarante o similares (`confirmado`)

**No existe ningún campo de titular, declarante, NIF ni similar** en el DBF (los 20 campos están en la tabla del CA1). Por tanto no entra nada de titularidad en el sistema por esta fuente. Nada que copiar ni descartar al leer.

### CA3 — Licencia: textos citados y conclusión (`asumido`, no `confirmado`)

Tres textos de la fuente, citados literalmente:

1. **`<rights>` del feed de Madrid, a nivel de feed** (`feed_ds.cm_sigpac.xml`): «Según el Acuerdo de Distribución del FEGA, O.A. por el que se aprueban los criterios de acceso, formatos de entrega y condiciones.» La entrada de Colmenar de Oreja (28043) **no tiene `<rights>` propio**. Los otros dos `<rights>` del feed están en las entradas de «01» (toda la Comunidad) y de Acebeda (28001), no en la de 28043. Extracto en `tests/fixtures/sigpac/feed_derechos_extracto.txt`.
   - Texto de uso (PAC, en las entradas de «01» y Acebeda): «El uso, delimitación gráfica u otros atributos de los recintos que aparecen en el SIGPAC tienen por objeto facilitar al agricultor la cumplimentación de su solicitud de ayudas a la PAC. Cuando el uso que aparece en el SIGPAC sea distinto del uso real, el agricultor debe realizar su solicitud de ayuda en base a este último, el real, debiendo comunicar la incidencia al servicio competente de su Comunidad Autónoma.» **Consecuencia:** el campo `USO_SIGPAC` es orientativo, no una prueba del uso real. Hay que tratarlo como indicio a verificar, nunca como hecho.
2. **Ficha de datos.gob.es** (`ficha_datos_gob_extracto.txt`): «Licencia https://creativecommons.org/licenses/by/4.0/legalcode.es»; publicador «Comunidad de Madrid»; descripción «…actualizados anualmente».
3. **Términos de uso de la información de alto valor del SIGC (FEGA)**, dentro del ZIP (`terminos_fega_hvd_extracto.txt`): «los Recintos (capa RECINTOS) y los Elementos del paisaje (capa ELEMENTOS DEL PAISAJE) del SIGPAC, y las Líneas de declaración (capa LINEA DECLARACION) del Sistema Integrado de Gestión y Control (SIGC), tienen la consideración de datos específicos de alto valor»; el FEGA los pone a disposición «para su reutilización en las condiciones de la licencia Creative Commons Atribución/Reconocimiento (CC BY 4.0)». Extiende la consideración a «los que en cada momento se visualizan en el Visor Sigpac (datos de la Campaña en curso y datos de la Campaña previa)». Exige citar «Fuente de los datos: FONDO ESPAÑOL DE GARANTÍA AGRARIA O.A.», indicar cambios, no sugerir respaldo del FEGA y no alterar el contenido.

**Conclusión.** Las tres fuentes apuntan a CC BY 4.0 con atribución, y los términos del FEGA son la evidencia primaria más fuerte. Pero **no es concluyente** para este fichero: el `<rights>` de Madrid remite a un «Acuerdo de Distribución del FEGA» cuyo texto **no se ha podido leer** (no está en el ZIP ni en el feed; una búsqueda solo dio una copia de tercero, `data.source.coop`, sin fecha ni validez confirmada), y el enlace entre el fichero regional y los términos HVD es una inferencia. Por eso la licencia queda `asumido`.

- **Atribución mínima si se publica:** «Fuente de los datos: FONDO ESPAÑOL DE GARANTÍA AGRARIA O.A. (SIGPAC, CC BY 4.0)», con indicación de que los datos están transformados si lo están, y sin sugerir respaldo del FEGA.
- **Antes de publicar en el mapa** (regla de `CLAUDE.md`: solo si la licencia permite redistribución): el fundador debe confirmar en #200 que el Acuerdo de Distribución del FEGA dice CC BY 4.0 para este fichero, o que los términos HVD cubren la distribución de la Comunidad de Madrid.

### CA4 — Vías pecuarias (capa #36): polígono y anchura (`confirmado` salvo lo marcado)

- La capa #36 (`Zonas:IDEM_MA_VIAS_PECUARIAS`) trae **polígono** de la franja, no línea de eje (hallazgo 3 de la sección de vías pecuarias de este registro). Confirmado de nuevo con la fixture de los 15 tramos de Colmenar (`gml:Polygon`/`gml:MultiSurface`).
- **No hay campo de anchura legal** (hallazgo 2 de la misma sección: el esquema tiene 8 campos + geometría).
- Anchura **legal**: la Ley 3/1995 (estatal), art. 4 (BOE-A-1995-7241, texto consolidado, leído en `boe.es`): cañadas, «anchura no exceda de los 75 metros»; cordeles, «no sobrepase los 37,5 metros»; veredas, «no superior a los 20 metros». Las coladas y los abrevaderos, descansaderos y majadas **no tienen tope**: su anchura la fija el acto de clasificación. La Ley 8/1998 de la Comunidad de Madrid (BOE-A-1998-20648, art. 6) remite a ese art. 4: no fija anchuras propias.
- Anchura **medida** desde la propia capa: `NM_AREA / NM_LONG` (superficie entre longitud; `confirmado` sobre la fixture). Valores de los 15 tramos de Colmenar: veredas 11,1–11,6 m; cañadas 35,2–37,3 m; coladas 13,9–16,7 m; abrevaderos y descansaderos 6,4–37,8 m (sin tope legal).
- **Viable para #200:** usar `NM_AREA / NM_LONG` como anchura de la franja tal como la dibuja la capa, y el tope legal de la tabla por tipo como **cota de contraste** (una franja que excede su tope legal es un indicio a verificar, nunca una conclusión). No usar la tabla como anchura oficial: el acto de clasificación que fija la anchura real no está en ninguna fuente leída.

### CA5 — Proyección: EPSG:4258 → EPSG:25830 (`confirmado`)

- El `.prj` es `GCS_ETRS_1989` (geográficas sobre ETRS89, el datum de EPSG:4258). El `bbox` del `.shp` (lon −3,594 a −3,344; lat 40,034 a 40,136) confirma grados.
- Para medir solape con vías pecuarias (que están en EPSG:25830): **hay que reproyectar** a UTM 30N (ETRS89, `lon0` −3°, factor de escala 0,9996). Entre ETRS89 y ETRS89 no hay desplazamiento de datum, solo proyección. Si se usase ED50 o WGS84 sin transformar la diferencia sería del orden de 100 m en la península.
- Probado: el cruce de CA1 (inverso de UTM sobre los 3.188 vértices) deja el 99 % de vértices dentro de un recinto. Si la conversión fuera mala, la fracción caería mucho.

---

## Resumen de fuentes no verificadas en esta pasada

Fuera de alcance de la historia 0001 (ver sección "Fuera de alcance" de `docs/stories/0001-registro-fuentes.md`): vías pecuarias, Red Natura 2000, concesiones de agua, inventario municipal de caminos. SNCZI/dominio público hidráulico, que figuraba aquí mismo hasta la historia 0012, quedó verificado en esa historia (ver sección "SNCZI / Dominio Público Hidráulico — MITECO" más arriba: cursos de agua y peligrosidad por inundación `confirmado`, deslinde legal de DPH y zonas de servidumbre/policía `bloqueado`). Vías pecuarias, que figuraba aquí mismo hasta la historia 0014, quedó verificada en esa historia (ver sección "Vías pecuarias — IDEM, Comunidad de Madrid" más arriba: `confirmado`, un único servicio real encontrado bajo el workspace `Zonas` del mismo GeoServer de IDEM). Red Natura 2000, que figuraba aquí mismo hasta la historia 0015, quedó verificada en esa historia (ver sección "Red Natura 2000 y espacios protegidos — IDEM, Comunidad de Madrid" más arriba: `confirmado` como fuente real de planes de gestión, con el alcance explícito de que modela zonificación de planes, no el límite oficial de cada sitio individual con código EU). Concesiones de agua e inventario municipal de caminos quedan para una iteración posterior del registro, cuando las historias de reglas/afecciones las necesiten.

- **Mosaico de ortofotos históricas catastrales (Sede Electrónica, años 80-90)**: fuente **no verificada**; acceso y licencia sin comprobar. Podría cubrir el hueco de 1957 a 1997 de la sección PNOA histórico, sin afirmar nada más (historia #287, fuente: comentario del fundador en #268).

### Publicar los tramos a verificar (historia #170)

- **CA15 (flujo real), pendiente de la primera publicación real.** Por decisión del fundador en #170 (2026-11-27), no bloquea el merge: necesita candidatos aprobados a mano en `curated/candidatos/28043/revision.json`, y ningún agente puede aprobarlos (ADR 0047). Sin aprobados, `publicar-candidatos` no publica nada. La primera vez que se publique de verdad, ejecuta `uv run pytest -m "acceptance and integration" tests/acceptance/test_historia_170.py -k ca15` y anota aquí la fecha, cuántos tramos aprobados se publicaron y la línea `medición:` (solo números, sin referencias catastrales).
- **CA11 de #315 (datos reales de 28043), pasado en local el 2026-11-28** (PR #326, commit 32dfd75): `uv run pytest -m "acceptance and integration" tests/acceptance/test_historia_315.py -k ca11` → 1 passed. `publicar-candidatos --municipio 28043`, en una carpeta temporal, publica **40 tramos aprobados, los 40 con tabla de convergencia** (582.878 bytes; 0 propuestos y 0 rechazados sin publicar). `medición:` 0 de 0 evaluables, no calculable (6 casos: 4 fuera del ámbito, 2 sin geometría). Antes se regeneró `data/derived/` de 28043 tras #183 (capa `camino_asfaltado`, 380 discrepancias, los mismos 40 candidatos con sus 40 aprobaciones vigentes) y el manifiesto de imágenes con los vuelos de la IDEM de 1975 y 1991 (#208): 7 imágenes por tramo. **`site/` no se tocó**: el CA15 de #170 sigue pendiente de la primera publicación real.

## Polígonos catastrales rústicos: `cp:CadastralZoning` del WFS INSPIRE de Catastro (historia #217)

Verificado el 2026-11-27 desde un runner de Actions contra `https://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx` (`GetFeature`, `typenames=cp:CadastralZoning`, `srsname=urn:ogc:def:crs:EPSG::25830`). Mismo servicio, caché cruda y licencia INSPIRE de Catastro que las parcelas (ADR 0028): **capa de uso interno, nunca se publica**. Sin proveedor nuevo.

- **Forma**: cada feature trae `cp:geometry` = `gml:MultiSurface/gml:Surface/gml:patches/gml:PolygonPatch/gml:exterior/…/gml:posList` (no `gml:Polygon`), `cp:label` (número de polígono, p. ej. `040`), `cp:level` con el nivel en `xlink:href` (`…/CadastralZoningLevelValue/2ndOrder`), `cp:levelName` (`POLIGONO`) y `cp:nationalCadastalZoningReference` (sic, referencia de zona). La referencia es de zona, no de finca, y el adaptador no la lee: solo sale la etiqueta.
- **Niveles (CA2)**: el parser lee el nivel de cada feature y el adaptador se queda solo con `2ndOrder` (polígonos). Se descarta `1stOrder` (el término municipal, si la capa lo devuelve; no se observó en las teselas reales de Colmenar, solo se contempla). Los anillos interiores (`gml:interior`) se descartan como en las parcelas (lecciones 0011 y 0015); la tesela real de 1 km² de Colmenar no tenía ninguno.
- **Límite de área**: el mismo de las parcelas, 1000×1000 m sí y el término entero no. La excepción de esta capa llega **en español**: `Area de la extensión fuera de los límites` (`OperationProcessingFailed`); la de parcelas, en inglés (`out of limits`). El adaptador reconoce ambos textos.
- **Teselado**: rejilla única de `municipality_tiles` (teselas de 900 m), como `catastro-caminos`; un polígono grande (p. ej. `28043A040`, ~2 × 3 km) aparece en varias teselas y se une por etiqueta, nivel y geometría.
- **No verificado**: cobertura de los 7 municipios del ámbito (solo Colmenar de Oreja, 4 polígonos en la tesela `460000,4436000,461000,4437000`).
- Comando: `uv run python -m parcel_intel.cli.main catastro-poligonos --codigo 28043 [--bbox …] [--sin-red]`; sin fichero derivado, las respuestas quedan en `data/raw/catastro`.

## QField / proyecto de campo (historia #219)

Verificado el **2026-11-27** para la [historia #219](https://github.com/murcialito/paso-comun/issues/219) (hija de #204, kit de campo sin servidor). Solo documentación y una fixture mínima; no introduce proveedor.

- **URLs primarias consultadas** (2026-11-27): `https://docs.qfield.org/get-started/`, `https://docs.qfield.org/how-to/project-setup/storage/`, `https://github.com/opengisch/QField`, `https://qgis.org/license/`, `https://www.geopackage.org/spec/`.
- **Licencias**: QField, GPL-2.0 o posterior (README del repositorio `opengisch/QField`). QGIS, GPL v2 con excepción para enlazar con Qt (`qgis.org/license/`). Estándar GeoPackage: licencia OGC, que permite copiar, modificar y distribuir el documento con los avisos de copyright. La documentación de QField es CC-BY-SA 4.0. Un proyecto generado por nosotros es un fichero de datos (`.qgs` XML + `.gpkg`), no código de QField ni de QGIS; **no se leyó** ninguna cláusula que diga qué licencia tiene un proyecto como obra. `asumido`: no queda sujeto a la GPL por abrirse con ellos. La atribución de las capas (CC BY 4.0 de IDEM e IGN, ver `NOTICE`) es compatible con distribuirlas dentro del proyecto siempre que se conserve en el propio `.qgs` (`projectMetadata/rights`, como en la fixture) y en la descripción de la capa.
- **Instalación en el móvil**: tienda de aplicaciones (Android, iOS) o la última versión de GitHub (`v4.3.8`, «Danube», vista en la página de releases; no se leyó la lista de ficheros). El proyecto se pasa **sin QFieldCloud**: copiando la carpeta al dispositivo y usando «Open local file» en la pantalla de bienvenida (docs de almacenamiento); en Android, en `Android/data/ch.opengis.qfield/files/Imported Projects` y «importar proyecto desde ZIP» (esto último sale de un resultado de búsqueda sobre las docs, no se leyó en la página). **QFieldCloud** es un servicio externo con cuenta: **descartado** (CLAUDE.md, coste recurrente y servicio externo). QFieldSync (plugin de QGIS) no se necesita para abrir el proyecto, solo para empaquetarlo y seguir cambios.
- **Formato**: las docs recomiendan el GeoPackage («We recommend using the GeoPackage file format for projects in QField»); el proyecto y los datos van en una misma carpeta.
- **Veredicto: `viable sin QGIS`, con una reserva.** Un GeoPackage escrito con `sqlite3` (tablas `gpkg_spatial_ref_sys`, `gpkg_contents`, `gpkg_geometry_columns`, `application_id` `GPKG`, `user_version` 10300) y un `.qgs` XML escrito a mano con campos de tipo `ValueMap` se generan y validan en CI sin QGIS, GDAL ni `qgis_process` (`tests/fixtures/kit_campo/qfield/`). **Reserva (`asumido`)**: no se ha abierto la fixture en QField ni en QGIS (no hay en CI). El `.qgs` sigue la estructura que QGIS escribe (`maplayer`, `fieldConfiguration`, `editWidget type="ValueMap"`) y declara `version="3.34.0"`; esa versión mínima y que QField abra el fichero **no están confirmadas**. La hija que genere el proyecto real debe pedir a quien tenga el móvil que lo abra y anotar aquí el resultado.
- **Tamaño y atribución**: la fixture ocupa unos 40 KB con un solo punto; el tamaño real por municipio depende de las capas y de las teselas que se incluyan y **no se midió**. La atribución se ve dentro del proyecto en las propiedades de metadatos y en la descripción de capa; cómo la muestra QField en pantalla no se verificó.
- **Formulario de la fixture**: `tipo_obstaculo` (cancela, valla, cadena, zanja, bloques, cartel de prohibido el paso, arado, vegetación) y `estado` (practicable, tapado por la vegetación, con obstáculo, deteriorado por máquinas), más `notas` y `fecha`. Un único registro sintético, sin datos de Catastro, titularidad ni personas.
- **Canales no leídos**: la versión mínima de Android/iOS y de QGIS de QField (la ficha de Google Play y las docs no la dan en el texto recuperado); las páginas `get-started/tutorial`, `how-to/outside-layers` e `installation` de las docs (404); la lista de ficheros de la release; el texto del estándar GeoPackage más allá de los primeros 100.000 caracteres (las tablas obligatorias se tomaron del Anexo C y de la especificación conocida); la licencia de los ficheros de proyecto de QGIS como obra. Que no se leyeran no equivale a que no existan.
- **Alternativa (punto 5)**: no hace falta de momento; si la reserva falla, GPX con puntos de interés y hoja de campo imprimible (el kit GPX/KML de #213 ya existe, coste cero).
- **Generador real (historia #222)**: `publicar-kit-campo-qfield` escribe el proyecto por municipio con `sqlite3` y `xml.etree`. **Apertura en QField: PENDIENTE (`asumido`, no verificada).** Hasta que alguien con móvil abra el `.qgs` real de un municipio y anote aquí versión de QField, dispositivo y resultado (¿carga las capas? ¿aparece la advertencia y los desplegables de `tipo` y `estado`? ¿se guarda una incidencia con foto?), el ZIP no se enlaza ni se despliega en `site/` y `kit/indice.json` no se toca. El formulario usa elementos que la fixture de #219 no tenía (`DateTime`, `ExternalResource`, `attributeEditorHtmlElement` como cabecera): tampoco están comprobados en QField. Cuando se anote, ejecutar con `--incluir-en-indice`.

## Catastro histórico de rústica (Sede Electrónica, historia #287)

Historia #287, hija de #268 (épica #4). Solo documentación: no hay código ni datos en git. Los PDF y sus recortes están en `data/raw/catastro_historico/28043/` (fuera de git) y **no se publican nunca**. El agente no puede abrirlos, así que los datos de los productos se atribuyen al comentario del fundador en #268 (2026-11-27) y a su complemento en #287 (2.ª y 3.ª renovación). Uso **solo interno** (ADR 0040). Ver también «Catastro a una fecha (historia #209)» y «Catastrones (historia #211)».

### Productos de rústica en la Sede, para Colmenar de Oreja

- La Sede ofrece **5 productos de rústica** para Colmenar de Oreja (28043; código de Catastro 282043): Avance catastral, Topográfico Parcelario, 1.ª renovación, 2.ª renovación y 3.ª renovación (fundador, #268 y #287).
- **No hay foto aérea retintada** para Colmenar. La página general de la ayuda menciona imágenes aéreas retintadas entre los productos del servicio, pero el fundador no encontró ninguna para este municipio (WebFetch de la ayuda del 2026-11-27 y comentario del fundador).
- El inventario Excel de la provincia de Madrid **aún no está disponible**.

### Lo descargado en Colmenar (2026-11-27)

Cinco productos bajados por el fundador con su Cl@ve. Datos transcritos de su comentario; ninguno se ha abierto desde el agente.

| Producto | Nº PDF | Polígonos | Escaneado | Época y escala | Nota |
|---|---|---|---|---|---|
| Avance catastral (AC) | 79 | 49 (numeración propia, «Sección A») | ~254 ppp, A4 | 1902-1913 (manual); croquis sin escala | Caminos con nombre y doble trazo. A mano, en rojo, el número de polígono posterior |
| Topográfico Parcelario (TP) | 105 | 79 | 10029×7677 px, ~250 ppp (~0,2 m/px a 1:2000) | Febrero de 1947 (muestra del pol. 3), 1:2000 | Cuadrícula sin coordenadas. Caminos y cañadas con nombre, numerados en romanos (I, II, III) |
| 1.ª renovación (1R) | 83 | 79 | ~200 ppp | 1985-1988 (manual); hojas 1:5000 (pol. 5, 1:4000) | Trae el único distribuidor (1:25 000). Los límites de polígono siguen los caminos. Mismos 79 polígonos que el TP: sirve de índice del TP. Los caminos aparecen como parcelas de la serie 9000 |
| 2.ª renovación (2R) | 85 (incluye distribuidor) | no indicado | ~200 ppp | 1994-2005 (manual); hojas 1:5000 | **Coordenadas UTM en el margen** (p. ej. 4.436.500 N / 467.000 E en el pol. 9). Por error de origen, el `.7z` trae una hoja de la 1.ª renovación |
| 3.ª renovación (3R) | 34 (solo parte de los polígonos) | no indicado | ~200 ppp | 2005-2006 (manual), actualización sobre ortofotografía; hojas 1:5000 | **Coordenadas UTM en el margen** y cruces de cuadrícula. La hoja del pol. 5 está escaneada al revés y lleva «ACT-2000» a mano. Vienen `POL073` y `POL73` como hojas separadas |

- El TP no trae el distribuidor georreferenciado (`jpg` + `jgw`) que anuncia el manual de la Sede.
- Las coordenadas de 2R y 3R permiten georreferenciar a partir de la cuadrícula impresa. **Suposición sin verificar**: quizá estén en ED50 / UTM 30N, que habría que transformar a ETRS89 (EPSG:25830).

### Acceso y formato

- **Acceso**: exige certificado electrónico o Cl@ve personal (la ayuda de la Sede admite ambos; las condiciones técnicas de la resolución de 2011 hablan de certificado digital). La descarga la hace una persona; un agente no puede iniciar sesión.
- **Formato**: cada producto es un `.7z` con solo cartografía: un PDF por polígono y hoja. Escaneado JPEG sin texto y **sin georreferenciar** (ninguno trae `jgw`); solo 2R y 3R tienen coordenadas impresas en el margen.
- No vienen Hojas de Características, Relación de Propietarios ni Fichas parcelarias (ver Exclusiones).
- **Renovaciones**: la historia proponía no bajar la 2.ª y la 3.ª por haber PNOA desde 1994. Ese criterio queda sin efecto: la 2.ª y la 3.ª **sí se bajaron**, y el fundador pidió incluirlas aquí (complemento de #287, 2026-11-27).

### Licencia

Documento primario: [Resolución de 23 de marzo de 2011 de la Dirección General del Catastro](https://www.catastro.hacienda.gob.es/ayuda/legislacion/ovc/resoluciondgc20110323_tfs.pdf), leída el **2026-11-27** (texto extraído del PDF con `pypdf`). Se citan las cláusulas generales del Anexo I por su número:

- **Cláusula 5**: «No se autoriza el uso público ni la comercialización de la información catastral original.» Tampoco su difusión por procedimientos distintos a la interoperabilidad (cláusulas 9 y 10).
- **Cláusula 6**: se autoriza el uso público, incluido el comercial, de la información **transformada**; la transformación no puede alterar el contenido ni desnaturalizar su sentido.
- **Cláusula 7**: los productos derivados no suplantan a los de la DGC: no se identifican como «cartografía catastral», «información catastral» ni términos equivalentes que puedan inducir a confusión.
- **Cláusula 8**: «En ningún caso se autoriza a que la información catastral original descargada y no trasformada pueda ser difundida a través de Internet.»
- **Cláusula 12**: hay que citar la fuente (la Dirección General del Catastro, del Ministerio de Economía y Hacienda) y la fecha de acceso al producto.
- Plazo (cláusula 13): 10 años desde la descarga. Séptimo: la información distribuida sin transformar «carecerá de fehaciencia».

**Conclusión**: `publicable: no` para los originales (PDF y escaneados) y para sus recortes (cláusulas 5 y 8). Un trazado redibujado a partir de ellos, transformado, sería una decisión aparte. Cita del dossier, tal como la decidió el fundador: «Dirección General del Catastro, cartografía histórica, Sede Electrónica, municipio, producto y polígono, fecha de acceso». Aviso: la cláusula 12 pide además «Ministerio de Economía y Hacienda», que la cita decidida no incluye; queda para decidir con el fundador.

### Exclusiones

- **Nunca se bajan** las Hojas de Características, la Relación de Propietarios y las Fichas parcelarias: llevan nombres de propietarios.
- Este registro no copia ninguna referencia catastral de finca ni ningún nombre de persona o sociedad. Los nombres de caminos y los números de polígono son topónimos y numeración de la cartografía pública.

### Siguiente paso

- La **ficha interna por trazado** en `curated/` (cita de la fuente, sin imagen publicada) queda como **decisión posterior**, a tomar con esta verificación (#268).
- Para el TP se valorará si sirve la tubería de `curated/historico` (historia #139, ADR 0043: unidad, puntos de control y ajuste). La dificultad es que el TP **no está georreferenciado** y hoy esa tubería espera imágenes de `ign_planimetrias`. 2R y 3R sí traen coordenadas en el margen (ED50 probable, sin verificar).
- Numeración: el Avance catastral y el TP tienen numeraciones distintas; la anotación roja del AC parece dar la equivalencia. **Sin verificar.**

## Catálogo de caminos públicos de Cáceres y Extremadura como conjunto de validación (historia #279)

Verificado el **2026-11-27** (hija de #271). Solo investigación: sin código, sin port, sin fichero de este catálogo en git ni en `site/`. Estado: **completo**. Lo leído por red desde GitHub Actions está abajo; el **contenido** del catálogo (CA1, CA2) no se pudo descargar desde Actions y quedó `pendiente-local`: se pasó en local el 2026-11-27 (19:54 UTC) y sus resultados están en CA1 y CA2.

### Lo que se leyó (`confirmado`)

- **Ficha en el portal del Ayuntamiento** (`https://opendata.caceres.es/datosabiertos/catalogo/dataset/catalogo-caminos-publicos-de-caceres`, CKAN; API `.../api/3/action/package_show?id=catalogo-caminos-publicos-de-caceres`): título «Catálogo Caminos Públicos de Cáceres», nota «BOP-2023-2983 Aprobación definitiva del Catálogo de Caminos Públicos del Término Municipal de Cáceres», responsable SIG de Cáceres (Ayuntamiento), fecha de creación 2023-01-26, «Fecha de última actualización de datos» 8 de octubre de 2026, frecuencia `notPlanned`, CRS declarado EPSG:25829 (el WMS ofrece también EPSG:4326).
- **El endpoint de la ficha de datos.gob.es ya no sirve datos**: `http://opendata.caceres.es/GetData/GetData?dataset=om%3ACamino&format=geojson&geojson=LineString` redirige (301) a HTTPS, cuyo certificado no valida con la cadena del sistema (`unable to get local issuer certificate`; se usó `curl -k` solo para esta verificación) y responde `200 text/html` con la **portada del portal**, no un GeoJSON (6.619 bytes). No es dato.
- **Recursos reales del conjunto** (de `package_show`): WMS (`https://ide.caceres.es/geoserver/sigaytocc/caminos/wms` y `.../sigaytocc/wms`), **CSV** y **GeoJSON** por WFS 1.0.0 de `sigaytocc:caminos` en `https://ide.caceres.es/geoserver/sigaytocc/ows` (`outputFormat=CSV` y `application/json`), página de descarga `https://ide.caceres.es/descargas/movilidad-catalogo/`, dos visores (`sig.caceres.es`) y apps móviles.
- **Licencia: discrepancia con la historia.** El registro del portal dice `licence: ["No se aplican condiciones"]`, `access_constraints: []` y **no trae `license_id`**. La historia citaba **CC-BY** (ficha de datos.gob.es, que no se leyó en esta pasada). Ninguna es la licencia leída en un documento aparte, y «No se aplican condiciones» es el mismo tipo de campo de metadato que la lección de 0021 dice que **no** es la licencia (`asumido`). Antes de redistribuir nada hay que leer el aviso legal de `opendata.caceres.es` o `ide.caceres.es` y citarlo; aquí no se hizo.
- **Contenido declarado**: líneas de caminos (resumen JIIDE 2023, citado en la historia: 204–208 caminos, ~1.088–1.100 km, aprobado el 10 de mayo de 2023). El linaje del metadato describe las fuentes históricas usadas para demostrar la existencia del camino (planimetrías 1898–1945, MTN, catastros de rústica de 1956 y 1981, vuelo de 1956, Libro de Yerbas de 1909). **No menciona puntos de pérdida de traza, cancelas ni obras de acceso.**

### CA1 — descarga del GeoJSON real: `confirmado` (en local, 2026-11-27)

Desde GitHub Actions `ide.caceres.es` agotó el tiempo de espera en todas las peticiones (raíz, `geoserver/web/`, `GetCapabilities`, `GetFeature`, `descargas/movilidad-catalogo/`; 30–300 s), y `opendata.caceres.es` respondió solo a ratos: mismo patrón que Catastro (servicio que no atiende a los runners). En local responde sin problema.

- **URL**: `https://ide.caceres.es/geoserver/sigaytocc/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=sigaytocc%3Acaminos&outputFormat=application%2Fjson` (`User-Agent: parcel-intel-verificacion/0.1`), `200 application/json`, 1.352.223 bytes.
- **Fecha de descarga**: 2026-11-27 (19:54 UTC). Fichero: `data/raw/caceres_caminos/caminos.geojson` (fuera de git).
- **sha256**: `636efda3644cb7c416a44130269ebd2ab8b7c2cb65e0d3f4260f35ca3abcbecb`.
- **Elementos**: 278 features (`totalFeatures` = `numberMatched` = `numberReturned` = 278: la respuesta no está truncada), todas `MultiLineString`. Son 274 índices distintos: los índices 12, 47, 50 y 124 aparecen dos veces (un camino en dos piezas). La suma del campo `longitud` da ~1.221 km (el resumen JIIDE hablaba de 204–208 caminos y ~1.100 km).
- **CRS**: la respuesta declara `urn:ogc:def:crs:EPSG::4326` y redondea las coordenadas a **4 decimales (~10 m)**. El dato nativo es EPSG:25829 (ETRS89 / UTM 29N): con `&srsName=EPSG:25829` el mismo WFS devuelve coordenadas al décimo de milímetro (comprobado con `maxFeatures=2`). Para cualquier uso métrico hay que pedirlo así, no en 4326.
- **Campos** (todos presentes en las 278): `indice`, `nombre` (nombre del camino), `anchura` (0 en 169 de 278; 5–10 m en el resto), `longitud` (m), `inicio`, `fin` (texto: término municipal, otro camino, carretera o «acceso a parcelas»), `url` (ficha PDF por camino en `https://sig.caceres.es/fotosOriginales/CAMINOS/FICHAS_CAMINOS/<indice>.pdf`), `inicio_x`/`inicio_y`/`fin_x`/`fin_y`/`centro_x`/`centro_y` (ETRS89 / UTM 29N), `inicio_lat`/`inicio_lon`/`fin_lat`/`fin_lon`/`lat`/`long`.
- **Defectos del origen**: en las 278 features `fin_lat`/`fin_lon` repiten `inicio_lat`/`inicio_lon`, así que sirven solo `fin_x`/`fin_y`; hay al menos un `fin_x` con un dígito de más (`7340403`, índice 12, también en su ficha PDF).
- **Licencia leída en la página de origen**: el pie de `https://ide.caceres.es/descargas/movilidad-catalogo/` (página de descarga del conjunto, leída el 2026-11-27) dice «Contenidos liberados bajo licencia: Creative Commons Reconocimiento 4.0 — IDE Cáceres © 2026» (la misma página arrastra un pie antiguo con «Reconocimiento 3.0 — © 2016»). Es decir, **CC BY 4.0, atribución «IDE Cáceres»** (`confirmado` en la página de origen). En cambio, el CKAN de `opendata.caceres.es` dice «No se ha provisto de una licencia» y su metadato `licence` dice «No se aplican condiciones»: no es la licencia (lección de 0021). La ficha de datos.gob.es (CC-BY) queda como dato secundario.

### CA2 — ¿hay pérdida de traza, cancela u obra de acceso en los datos?: **no, solo trazados** (en local, 2026-11-27)

- **Ningún campo** del GeoJSON trata de pérdida de traza, cancelas, obras de acceso, cortes u ocupación (lista completa de campos en CA1).
- **Ningún valor** los menciona. Búsqueda en todos los campos de texto de `pérdid|traza|cancel|obra|cort|cerrad|vall|portill|usurp|ocupa|interrump|desapar`: solo coinciden topónimos («Valle Redondo», «Valle Cristóbal», «Cortijada de Casas Altas»). Los valores «acceso a parcelas» del campo `fin` (46 de 278) describen dónde termina el camino, no una obra de acceso.
- **Fichas PDF por camino** (muestra de 3: índices 12, 26 y 100, descargadas solo para verificar, no guardadas en el proyecto): índice, anchura estimada, longitud, inicio y fin con coordenadas ETRS89, nombre y dos mapas de situación con el trazado. **Sin apartado de incidencias**, pérdidas de traza ni obras de acceso. Con 3 de 274 fichas no se puede afirmar que ninguna lo tenga, pero el formato es una plantilla fija.
- Respuesta: **solo hay trazados**. Ningún nombre de persona ni referencia catastral copiados aquí.

### CA3 — canales de Extremadura (~13.000 pérdidas de traza, ~19.000 obras de acceso)

| Canal | Resultado |
|---|---|
| Resumen JIIDE 2023 (`dgterritorio.gov.pt/jiide2023/pdfs/resumos/27-ES_Resumen_FaustinoCordero.pdf`) | **descargado (211 KB, 2 págs.), texto no extraído** (sin herramienta de PDF en el entorno). Por sus enlaces es un resumen de autores del Ayuntamiento de Cáceres (`sig.caceres.es`, `visor.caceres.es/visor?map=6`, QGIS), no un documento de descarga de datos. Las cifras de Extremadura vienen de la historia, no se verificaron aquí. |
| datos.gob.es, API `apidata/catalog/dataset/title/caminos` (13 resultados) | **solo dos fichas de Cáceres**; ninguna de la Junta de Extremadura sobre pérdidas ni obras de acceso. La búsqueda es por título: un conjunto con otro título no saldría. |
| Búsqueda web (Junta de Extremadura, IDEEX, datos.gob.es) | sin conjunto descargable; solo el marco legal (art. 178 Ley Agraria de Extremadura: el catálogo oficial lo elabora la Consejería e incluye longitud, puntos inicial y final, denominación y anchura estimada) y presentaciones antiguas de IDEEX (2010, 2016), vistas en resultados, no leídas. |
| `visor.ideex.es` | **ilegible**: responde 200, pero es una aplicación Ionic/Angular que se pinta con JavaScript; sin navegador no se ve ninguna capa. **No equivale a que no existan.** |
| CICTEX | **no consultado**. |
| Catálogo de datos de la Junta (datos.gob.es) y PDF «Datos abiertos 2026» de `juntaex.es` | solo vistos en resultados de búsqueda; **no leídos**. |

Licencia de un conjunto de Extremadura: **no se encontró** (no se halló conjunto).

### Conclusión (CA4)

**Solo hay trazados.** El catálogo de Cáceres (CC BY 4.0, IDE Cáceres) da 274 caminos públicos aprobados que **deberían existir**, sin ningún dato de pérdida de traza, cancela ni obra de acceso, ni en el GeoJSON ni en la muestra de fichas. No es verdad conocida de cortes. Sirve, como mucho, de **control de recall de la capa de trazados**, no del método de cortes. En Extremadura no se encontró un conjunto descargable de pérdidas de traza, pero quedaron sin leer el visor IDEEX, CICTEX y la ficha de la Junta. Usarlo fuera de Madrid exigiría: la red del IGN y Catastro VT, que son nacionales; y un sustituto de las vías pecuarias de IDEM, que no tiene equivalente registrado en Extremadura (no se buscó, coste sin estimar). Además, pedir el WFS en EPSG:25829, no en 4326.

## Capa derivada de servidumbre de cauces (historia #250)

Fuente: colección `watercourse` de IDEE (IGN, CC BY 4.0, ver #247 y #257). La capa derivada `data/derived/servidumbre_cauces/<ine>.geojson` es **una aproximación** (eje + semianchura + 5 m), no deslinde ni zona de policía, y de uso interno hasta #251. Lleva la marca «Obra derivada de»; la cadena exacta de atribución con la tabla de `scne.es` queda para #251. La semianchura sale de `ancho_max`, o de `ancho_min` si falta, o es 0 (anotado en `anchura_usada`).
