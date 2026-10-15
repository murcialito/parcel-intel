# Parcel Intel — Due diligence legal y física de inmuebles

Oct 15, 2026 · @Iñaki

Parcel Intel genera, a partir de una referencia catastral, un informe que cruza lo que hay sobre el terreno con lo que la norma permite, para que quien compra un inmueble cierre incertidumbres antes de firmar.

## Visión y problema

En una compraventa el comprador suele revisar la nota simple y poco más. Los riesgos reales están dispersos en fuentes que nadie cruza: Catastro, ortofotos, planeamiento municipal, boletines oficiales, inventarios de dominio público y concesiones de agua.

Una irregularidad, vista desde el código, es una discrepancia: la imagen o el anuncio dicen X y el registro o la norma dicen Y. El producto detecta esas discrepancias, las fecha y las explica con la norma aplicable.

**Tesis comercial: suelo rústico en Murcia, Alicante y Almería.** Es donde el comprador está más a ciegas (viviendas sin licencia, ampliaciones no declaradas, pozos sin concesión, lindes sobre caminos públicos) y donde casi no hay competencia. El comprador extranjero en esa zona es un segmento con dolor alto y concentrado. Esta es la tesis de mercado, no el punto de partida técnico (ver "Fases geográficas" más abajo).

**Principio rector:** el sistema señala indicios a verificar, con nivel de confianza y norma aplicable. Nunca emite un dictamen jurídico.

## Producto

El entregable es un informe por inmueble (entrada: referencia catastral) con hallazgos agrupados por módulo. Cada hallazgo lleva severidad, confianza, evidencia (capa, imagen, documento) y norma aplicable.

| Módulo | Qué responde | Fase |
| --- | --- | --- |
| Situación urbanística | Clasificación del suelo y usos/edificación permitidos según ley autonómica y plan general | Rústico |
| Construcciones | Edificaciones detectadas en imagen frente a las que constan en Catastro, con superficies | Rústico |
| Datación | Cuándo aparece cada construcción en ortofotos históricas (clave para prescripción y regularización) | Rústico |
| Afecciones | Cauces, inundabilidad, vías pecuarias, caminos públicos, espacios protegidos, servidumbres | Rústico |
| Agua | Si la parcela se riega (NDVI) y si hay concesión que lo ampare | Rústico |
| Entorno y futuro | Proyectos, expropiaciones y cambios de planeamiento publicados en BOE o boletín autonómico cerca del inmueble | Rústico y piso |
| Superficie | Discrepancia entre anuncio, Catastro y realidad | Piso |
| Ampliaciones | Terrazas cerradas o áticos crecidos (Catastro frente a ortofoto y LiDAR) | Piso |
| Edificio | Antigüedad, inspección técnica donde sea consultable, certificado energético, vivienda turística | Piso |

**Clientes y canal.** El comprador final paga por informe. El canal principal previsto a medio plazo son abogados y gestorías de compraventa, sobre todo los que trabajan con extranjeros (informe también en inglés); después, agencias que venden fincas "con informe", tasadoras, bancos e inversores en subastas del BOE. **En el MVP no se busca canal B2B ni validación de un despacho**: es un servicio abierto e independiente desde el principio. Se evaluará sumar un abogado o despacho validador solo si el producto demuestra tracción.

**Fases de producto.**

1. Rústico: construye el motor (capas legales, imágenes, cruce espacial).
2. Piso: producto de volumen, más barato y automatizado, reutilizando el motor.
3. Caminos públicos: la capa de caminos, ya presente como afección, se abre a escala de término municipal como herramienta social.

**Fases geográficas (independientes de las fases de producto).**

0. **MVP técnico — Colmenar de Oreja y Villaconejos (Comunidad de Madrid).** Objetivo: que el motor funcione de punta a punta (Catastro → capas → reglas → informe) sobre parcelas que el fundador puede verificar en persona. Elegidos por acceso directo al terreno y por la infraestructura de datos de la Comunidad de Madrid (IDEM: WMS/WFS reales, planeamiento vigente digitalizado para 179 municipios a 31/12/2025), notablemente más madura que la de la Región de Murcia en esta fecha. Colmenar de Oreja mantiene Normas Subsidiarias estables de 1985 (caso simple). Villaconejos está revisando su PGOU (de Normas Subsidiarias de 1984 a una reclasificación que llevaría ~76% del suelo a urbanizable) — buen caso de prueba real para el módulo "Entorno y futuro". En esta fase no importa el perfil de comprador extranjero: importa que el motor no mienta.
1. **Entrada comercial — Murcia, Alicante, Almería.** Una vez validado el motor, se despliega sobre la tesis de mercado: suelo rústico, comprador extranjero, poca competencia. Aquí sí importa el canal (abogados/gestorías).
2. **España entera.** Mismo motor, añadiendo comunidad autónoma a comunidad autónoma. El coste real de escalar es el boletín y el planeamiento de cada una, no el motor.

## Fuentes de datos

Casi todo es público y abierto; el cuello de botella es el planeamiento municipal, heterogéneo y a menudo solo en PDF. Los endpoints concretos están sin verificar: la primera tarea de implementación es confirmarlos y fijarlos en un registro de fuentes.

| Fuente | Aporta | Acceso previsto | Notas |
| --- | --- | --- | --- |
| Catastro (INSPIRE) | Geometría de parcelas y edificios, superficies, año de construcción | WFS + servicios de consulta | En rústico, caminos y cauces suelen figurar como parcelas propias (a verificar) |
| Sentinel-2 L2A | Cambios recientes, NDVI, humedad; ~5 días, 10 m | STAC (Copernicus Data Space o catálogos públicos en la nube) | Detecta cambios grandes; no casetas pequeñas |
| PNOA ortofoto actual e histórica (IGN/CNIG) | Detalle submétrico y serie temporal para datar construcciones | WMS / descarga | Base del módulo de datación |
| PNOA LiDAR | Alturas: volúmenes, plantas añadidas | Descarga CNIG | Pesado; procesar solo el entorno de la parcela |
| Planeamiento urbanístico (Comunidad de Madrid) | Clasificación del suelo y parámetros | IDEM (geoportal): WMS/WFS, Visor SIT, dataset de clasificación del suelo en datos.gob.es | Infraestructura madura: planeamiento vigente para 179 municipios a 31/12/2025. Confirmar cobertura exacta de Colmenar de Oreja y Villaconejos como primera tarea |
| BOE | Normativa estatal, anuncios, expropiaciones | API de datos abiertos (sumario diario) | Ingesta diaria |
| BOCM (BORM y BOP en fases posteriores) | Normativa autonómica, información pública, proyectos | Scraping del sumario diario | Formato distinto por boletín; BORM se retoma en la fase de entrada comercial (Murcia) |
| Zonas inundables (SNCZI) y dominio público hidráulico | Cauces, zonas de policía, inundabilidad | WMS/WFS del Ministerio | |
| Vías pecuarias | Trazados y anchuras legales | Cartografía autonómica | Cobertura desigual |
| Red Natura 2000 y espacios protegidos | Restricciones ambientales | Capas del Ministerio | |
| Concesiones de agua (Confederación del Tajo en Madrid; Segura en fase de entrada comercial) | Derechos de riego | Registro de aguas, consulta parcial | Posiblemente manual en el MVP |
| Inventario municipal de caminos | Caminos públicos | Ayuntamiento | Rara vez digital; alternativa: Catastro + cartografía IGN |

## Arquitectura técnica

Un monolito modular en Python sobre PostGIS, desplegado con Docker Compose en el servidor casero; tres pipelines independientes alimentan una base común y un evaluador determinista produce el informe.

Los tres pipelines (imagen, boletines, normativa) corren con calendarios propios: imágenes al llegar una nueva escena, boletines a diario y normativa bajo demanda con revisión humana. El informe se genera bajo petición, se entrega como página HTML (no PDF en el MVP) y queda versionado.

## Modelo de datos y motor de normativa

Las normas se convierten en reglas estructuradas que un LLM propone y una persona revisa; el informe solo evalúa reglas revisadas, de forma determinista. El LLM nunca decide en tiempo de informe si algo es legal: solo redacta la explicación. El LLM usado en el MVP es la API de DeepSeek (créditos ya disponibles), siempre detrás de una interfaz única que permita alternar a otro proveedor en la nube o a un modelo local sin tocar el resto del motor. Todo consumo de LLM queda registrado (coste y tokens), con la misma disciplina de coste por entregable que rige en otros proyectos del fundador.

**Entidades principales (PostGIS):**

- `parcel`: referencia catastral, geometría, municipio, clasificación del suelo.
- `building`: edificación con origen (`catastro` o `detected`), geometría, superficie, altura, primera fecha observada.
- `observation`: imagen o cambio detectado (fuente, fecha, tipo de cambio, geometría, confianza).
- `layer_feature`: elemento de una capa de afección (cauce, vía pecuaria, camino, espacio protegido) con su tipo y anchura legal.
- `norm` y `provision`: norma (BOE, BOCM/BORM, plan general, ordenanza) y artículo concreto, con vigencia y URL.
- `rule`: regla estructurada derivada de una disposición, con estado `proposed` / `approved` / `rejected`.
- `bulletin_entry`: anuncio de boletín con entidades extraídas, geometría resuelta y confianza de geolocalización.
- `finding` y `report`: hallazgo con severidad, confianza, evidencias y regla aplicada; informe versionado por parcela y fecha.

**Forma de una regla.** Ámbito territorial, condición espacial, condición de atributos, consecuencia y cita:

```yaml
id: madrid-colmenar-distancia-cauce
scope: { region: "madrid", soil_class: ["no_urbanizable"] }
spatial: { op: within_distance, layer: dph_cauce, meters: 100 }
attributes: { building.origin: [detected, catastro] }
outcome: requires_authorization
authority: "Confederación Hidrográfica del Tajo"
citation: { norm: "<norma>", provision: "<artículo>", url: "<url>" }
status: approved
```

(Ejemplo de forma; distancias y citas reales se fijan en la revisión.)

**Geolocalización de boletines**, el problema más difícil: un LLM extrae municipio, paraje, polígono, parcelas, referencias catastrales y coordenadas; un resolutor las convierte en geometría vía Catastro; el resultado guarda confianza y método de resolución. Se mide con un conjunto etiquetado a mano desde el primer día. En el MVP, el conjunto etiquetado se construye sobre BOE + BOCM filtrado a Colmenar de Oreja y Villaconejos, para mantener el alcance acotado mientras se valida el resolutor.

## Riesgos, límites legales y decisiones abiertas

El mayor riesgo no es técnico sino de confianza: un falso positivo puede tumbar una venta y un falso negativo, dar falsa seguridad.

| Riesgo | Mitigación |
| --- | --- |
| Que el informe se lea como dictamen jurídico | Lenguaje de "indicio a verificar", confianza visible, aviso legal revisado por abogado, firma o revisión profesional en el canal B2B |
| Responsabilidad legal si el informe se usa para decidir una compra real y falla | **Abierto.** Sin canal B2B ni abogado validador en el MVP, el riesgo recae directamente sobre el servicio. Antes de cobrar el primer informe real hay que resolver aviso legal, límites de responsabilidad y, probablemente, un seguro de responsabilidad civil — no solo el disclaimer de "indicio a verificar" |
| Licencias, prescripción o cambios de planeamiento invisibles | Mostrar siempre qué no se ha podido comprobar; la datación alimenta la pregunta de prescripción, no la responde |
| Protección de datos | Trabajar por referencia catastral, sin titularidad ni datos personales; informes privados, nunca mapas públicos de "ilegalidades" |
| Condiciones de uso de fuentes | Solo fuentes abiertas o con licencia; nada de scraping de portales inmobiliarios sin acuerdo |
| Cuello de botella de boletines y planeamiento no digitalizado | **Abierto.** La geolocalización de boletines es, por diseño, el problema más difícil del sistema, y el planeamiento municipal rara vez tiene API limpia. El MVP lo acota a un conjunto etiquetado a mano sobre dos municipios (Colmenar de Oreja, Villaconejos), pero escalar a España entera (fase 2) requiere decidir cómo se financia la digitalización municipio a municipio antes de prometerla |
| Calidad de detección en imágenes | Umbrales conservadores, evidencia visual en el informe, conjunto de validación con casos reales |

**Decisiones cerradas en esta revisión (15 oct 2026):**

- [x] Municipios del MVP: Colmenar de Oreja y Villaconejos (Comunidad de Madrid), no Murcia — ver "Fases geográficas".
- [x] Abogado o despacho validador: ninguno en el MVP; se evalúa si hay tracción.
- [x] LLM: API de DeepSeek en la nube (créditos ya disponibles), detrás de interfaz única.
- [x] Formato del informe: solo HTML/web en el MVP, sin PDF.

**Decisiones abiertas:**

- [ ] Modelo de precio: por informe, suscripción para despachos o mixto — no urgente hasta tener el motor funcionando.
- [ ] Responsabilidad legal y seguro antes de cobrar el primer informe real (ver tabla de riesgos).
- [ ] Cómo acotar el cuello de botella de boletines/planeamiento al escalar más allá de los dos municipios del MVP.

## Instrucciones para Claude Code

**Estructura del repositorio:**

```
parcel-intel/
  CLAUDE.md
  docs/vision.md
  infra/docker-compose.yml        # PostGIS, API, worker, MLflow
  src/parcel_intel/
    sources/      # un módulo por fuente: catastro, sentinel, pnoa, lidar, boe, bocm, layers
    detection/    # cambios, edificaciones, NDVI, datación
    bulletins/    # extracción de entidades y geolocalización
    rules/        # esquema, evaluador determinista, CLI de revisión
    reports/      # hallazgos, composición y render (HTML)
    api/          # FastAPI
  tests/
    fixtures/     # respuestas grabadas de cada fuente
    golden/       # parcelas reales con hallazgos esperados
  data/           # caché local, fuera de git
```

**Stack:** Python 3.12 con `uv`, PostGIS, `geopandas`/`shapely`, `rasterio`, `pystac-client` con `odc-stac`, FastAPI, `pytest`, MLflow para experimentos de detección y Docker Compose en el servidor casero. LLM detrás de una interfaz única para poder alternar API en la nube (DeepSeek en el MVP) y modelo local.

**Convenciones:**

- Todo dato lleva procedencia: fuente, URL, fecha de descarga y licencia.
- Operaciones métricas en EPSG:25830 (ETRS89 / UTM 30N); almacenamiento en ese CRS.
- Datos crudos cacheados e inmutables; el procesamiento es reproducible desde la caché.
- Ningún LLM en la evaluación de reglas; solo en extracción (con revisión) y en redacción de explicaciones.
- Los tests no llaman a red: fixtures grabadas; tests de integración marcados aparte.
- Cada hallazgo debe poder rastrearse hasta su evidencia y su regla.

**Primeras tareas, en orden:**

1. Verificar y documentar los endpoints de cada fuente en `sources/REGISTRY.md`, empezando por Catastro y el IDEM de la Comunidad de Madrid (WMS/WFS de planeamiento) para Colmenar de Oreja y Villaconejos.
2. Cliente de Catastro: dada una referencia catastral, devolver geometría de parcela y edificios.
3. Esquema PostGIS y migraciones para las entidades del modelo de datos.
4. Cliente de Sentinel-2: serie de NDVI y máscara de cambios sobre la parcela con un margen configurable.
5. Cliente de PNOA: ortofotos actual e históricas recortadas a la parcela.
6. Ingesta diaria de BOE y BOCM con filtro por los dos municipios del MVP.
7. Esquema y evaluador de reglas con dos o tres reglas de prueba y una capa de afección (zonas inundables).
8. Informe mínimo en HTML con hallazgos y evidencias para una parcela de prueba en Colmenar de Oreja o Villaconejos.
