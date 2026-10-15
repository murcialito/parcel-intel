# 0001 — Registro verificado de endpoints de fuentes de datos

## Historia

Como ingeniero que va a construir los adapters de `src/parcel_intel/adapters/`, quiero un registro verificado de los endpoints reales de cada fuente de datos externa, para no construir ningún cliente sobre una URL o un formato de respuesta asumido y sin confirmar.

## Contexto

`docs/vision.md` deja explícito que "los endpoints concretos están sin verificar: la primera tarea de implementación es confirmarlos y fijarlos en un registro de fuentes". El MVP depende de cruzar Catastro con el planeamiento del IDEM de la Comunidad de Madrid para dos municipios concretos (Colmenar de Oreja y Villaconejos); si la cobertura de IDEM no incluye realmente esos dos municipios, o si el protocolo asumido (WFS/WMS) no es el que expone el servicio en producción, el resto del motor se construye sobre un supuesto falso y el coste de descubrirlo tarde es mucho mayor que el de verificarlo ahora.

Esta historia es de investigación e infraestructura, no de lógica de dominio: no toca `domain/`, `ports/` ni `application/`. Su único entregable es documentación que servirá de contrato de facto para las historias de cliente de cada fuente (Catastro, PNOA, BOE, BOCM...).

## Criterios de aceptación

- [ ] Existe el archivo `src/parcel_intel/sources/REGISTRY.md`.
- [ ] El registro cubre, como mínimo, estas cinco fuentes, cada una en su propia sección: Catastro (INSPIRE WFS), IDEM / Comunidad de Madrid (planeamiento urbanístico), PNOA (ortofoto actual e histórica), BOE (API de datos abiertos) y BOCM (sumario diario).
- [ ] Cada sección de fuente documenta, como campos explícitos y rellenados (no en blanco ni con placeholders tipo "TBD"):
  - URL base del endpoint (o, si la fuente no expone un único endpoint estable, las URLs de cada operación relevante).
  - Protocolo (WFS / WMS / REST / scraping de HTML / descarga de ficheros).
  - Parámetros de autenticación, si los hay (API key, token, ninguno).
  - Formato de la respuesta (GML, GeoJSON, JSON, XML, HTML, imagen con su formato de fichero).
  - CRS nativo de la geometría devuelta, si la fuente expone geometría (Catastro WFS, IDEM WMS/WFS). `CLAUDE.md` exige operar en EPSG:25830; si el CRS de origen es distinto, se registra tal cual lo devuelve el servicio — la reproyección es tarea del futuro adapter, no de este registro.
  - Estado de verificación: `confirmado` (se hizo una petición real y se registró su resultado) o `asumido` (pendiente de verificar), sin términos intermedios.
- [ ] Para la sección de Catastro, el registro indica explícitamente si la consulta por referencia catastral devuelve la geometría de la parcela y de los edificios en la misma operación o si requiere operaciones separadas.
- [ ] Para la sección de IDEM, el registro responde de forma explícita y verificable (no como suposición) si el servicio de planeamiento/clasificación del suelo cubre Colmenar de Oreja y Villaconejos, citando el nombre de la capa o el dataset usado para comprobarlo.
- [ ] Para la sección de BOCM, el registro documenta la estructura del sumario diario (URL de la portada/sumario del día, cómo se enlaza a cada disposición individual) y señala si existe alguna vía estructurada (RSS, API, dataset en datos.gob.es) antes de asumir que hace falta scraping de HTML.
- [ ] Cada fuente tiene al menos un ejemplo de petición documentado (URL completa con parámetros, o comando `curl` equivalente) junto con:
  - la respuesta real obtenida (completa o un fragmento representativo, con fecha de la consulta), **o**
  - si no se pudo verificar, el motivo concreto (p. ej. "requiere alta previa", "el servicio devolvió error 403 el DD/MM/AAAA", "no se encontró documentación pública del endpoint") y qué haría falta para desbloquearlo.
- [ ] Cada respuesta real obtenida para una fuente `confirmado` se guarda también como fichero en `tests/fixtures/<fuente>/` (no solo embebida en el markdown), para que la historia 0002 y las siguientes la reutilicen como fixture grabada sin volver a llamar a la red.
- [ ] Ninguna fuente queda con el estado `confirmado` sin un ejemplo de petición/respuesta real adjunto; si el estado es `asumido`, el criterio de petición de ejemplo se sustituye por la explicación del bloqueo exigida arriba.
- [ ] El registro indica, para cada fuente, si el acceso es gratuito y abierto o si tiene algún requisito de licencia o límite de uso (rate limit, cuota diaria) detectado durante la verificación.
- [ ] El registro no contiene código de cliente ni lógica de parsing: es documentación de contrato de endpoint, no implementación.

## Fuera de alcance

- Escribir el cliente de ninguna fuente (eso corresponde a la historia 0002 — cliente de Catastro — y a las historias posteriores de PNOA, BOE/BOCM).
- Verificar fuentes que no sean Catastro, IDEM, PNOA, BOE o BOCM (SNCZI, vías pecuarias, Red Natura 2000, concesiones de agua, inventario municipal de caminos quedan para una iteración posterior del registro).
- Verificar cobertura de IDEM o de cualquier otra fuente para municipios distintos de Colmenar de Oreja y Villaconejos.
- Decidir el formato de caché o el modelo de reintentos/rate-limiting del futuro adapter: esto es diseño técnico y corresponde al arquitecto en la siguiente fase.
- Evaluar fuentes de la Región de Murcia (BORM, IDEM Murcia): corresponden a la fase 1 (entrada comercial), no al MVP.

## Preguntas abiertas

- Si al verificar IDEM se confirma que no cubre uno de los dos municipios (o cubre solo parcialmente), ¿se ajusta el alcance del MVP a un solo municipio o se busca una fuente alternativa de planeamiento para el que falte? Decisión para el arquitecto o el fundador una vez se tenga el resultado de la verificación.
- Si BOE o BOCM requieren una clave de API o un alta que no es inmediata, ¿quién la solicita y con qué plazo se asume que estará disponible para no bloquear la historia 0006 (ingesta diaria de BOE y BOCM)?
- ¿El registro de fuentes debe incluir también los términos de licencia exactos (texto legal) o basta con enlazar a la página de condiciones de cada organismo? Afecta a si esta historia necesita revisión legal antes de cerrarse.

## Métricas de éxito

- Cero reaperturas de esta historia por "el endpoint que asumimos no era el correcto" durante la implementación de los clientes de Catastro, PNOA, BOE o BOCM (historias 0002, 0005, 0006).
- Tiempo invertido en esta historia registrado y comparado contra el tiempo que tomaría descubrir un endpoint incorrecto a mitad de la implementación de un cliente (señal cualitativa, a valorar en el cierre de ciclo con `lessons-learned`).
- El registro permite a cualquier persona nueva en el proyecto reproducir, copiando y pegando, al menos una petición exitosa por cada fuente marcada como `confirmado`, sin tener que buscar documentación externa adicional.
