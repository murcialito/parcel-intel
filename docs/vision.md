# Parcel Intel — Caminos públicos

Oct 15, 2026 · revisado Nov 25, 2026 (cambio de rumbo) · @Iñaki

Parcel Intel es una herramienta abierta y sin ánimo de lucro que reconstruye qué trazados deberían ser públicos (vías pecuarias, caminos) y señala los tramos donde hoy parecen haber desaparecido o quedar dentro de una finca cerrada, para que quien defiende esos caminos llegue al ayuntamiento con indicios ordenados y no con sospechas sueltas.

> **Cambio de rumbo (25 nov 2026).** La versión anterior de este documento planteaba un informe de due diligence por referencia catastral para compradores de inmuebles, con suelo rústico como tesis comercial y pisos como segunda fase. Eso queda así: **caminos públicos pasa a ser la fase 1**; el informe de rústico para compradores queda como posible fase posterior; **pisos sale del alcance**. El proyecto deja de tener modelo comercial. La versión anterior está en el historial de git (`git log -- docs/vision.md`). Ver [ADR 0021](adr/0021-cambio-de-rumbo-caminos-publicos-coste-casi-cero.md).

## Problema

Los caminos públicos y las vías pecuarias se pierden poco a poco: se ara el trazado, se cierra con una valla o una cancela, se incorpora a una finca. Quien lo nota (una asociación, un senderista, un ganadero, un ayuntamiento pequeño sin técnico) tiene que reconstruir a mano, fuente por fuente, que ese trazado existía y era público: la cartografía oficial de vías pecuarias, el Catastro, mapas y vuelos antiguos, el inventario municipal si existe. Ese trabajo es lento, poco reproducible y llega tarde.

Vista desde el código, una posible usurpación es una discrepancia entre fuentes: un trazado que la cartografía oficial o histórica dice que existe y que la ortofoto actual ya no muestra, o que muestra dentro de un cierre. El sistema detecta esas discrepancias, las fecha y las presenta con su evidencia.

## Principios (innegociables)

- **Indicios, nunca ilegalidades.** El sistema dice "este tramo debería ser público según X y en la ortofoto de AAAA no se distingue / parece quedar dentro de un cierre", con confianza y evidencia. Nunca dice que algo sea ilegal, una usurpación o un delito. Decidirlo es cosa de la administración y, en su caso, de un juez.
- **No se nombra a propietarios.** Ningún dato de titularidad entra en el sistema ni aparece en el mapa, el dossier o los avisos. Se trabaja sobre trazados y geometrías, no sobre personas.
- **Las reglas propuestas por IA requieren aprobación humana antes de usarse.** El flujo de autoría con revisión (historias 0019–0020) se mantiene tal cual.
- **Coste de funcionamiento casi cero** (ver "Modelo").
- **Todo indicio es rastreable** hasta sus fuentes (con fecha y licencia) y hasta la regla que lo produjo.

## Modelo

Proyecto **sin ánimo de lucro y de código abierto**. Sin clientes, sin precios, sin cuentas de pago. Solo se plantea cobrar o pedir aportaciones si aparecen costes reales de funcionamiento, y el diseño busca que no aparezcan:

- Solo datos públicos.
- El análisis corre por lotes (por municipio) en la máquina del proyecto; lo que se publica son ficheros estáticos (mapa y datos), servibles desde un hosting estático gratuito.
- **Nada llama a un modelo de IA en una consulta de usuario.** El LLM solo interviene fuera de línea: autoría de reglas con revisión humana y, si se usa, redacción de textos que se generan una vez y se publican ya revisados.
- Sin backend que escale con las visitas mientras el mapa estático sea suficiente. Un backend solo entra cuando una funcionalidad lo exija de verdad (p. ej. recibir avisos ciudadanos con foto) y con un ADR que justifique su coste.

## Usuarios

- Asociaciones de defensa de caminos públicos.
- Senderistas y ciclistas.
- Ganaderos (uso tradicional de vías pecuarias).
- Ayuntamientos pequeños, sin técnico propio para inventariar caminos.

Lo que necesitan es lo mismo con distinta profundidad: ver en un mapa qué debería ser público, dónde hay indicios de corte y, llegado el caso, un expediente presentable.

## Fases

1. **Caminos públicos** (actual). Primer hito en Colmenar de Oreja y municipios vecinos; después se extiende por la Comunidad de Madrid y, más adelante, comunidad autónoma a comunidad autónoma (el coste real de escalar es la cartografía de vías pecuarias y los inventarios de caminos de cada una, no el motor).
2. **Rústico para compradores** (posible, no comprometida). El informe por referencia catastral ya construido (historias 0001–0020) queda en el repositorio como base. Solo se retoma si encaja con el modelo sin ánimo de lucro y coste casi cero.
3. ~~Pisos~~ — fuera del alcance.

### Primer hito — Colmenar de Oreja y municipios vecinos

Ámbito (fijado en la historia 0021 con la geometría real de los términos del IGN): Colmenar de Oreja y sus colindantes madrileños, que son Aranjuez, Chinchón, Belmonte de Tajo, Villaconejos, Villarejo de Salvanés y Valdelaguna. Los colindantes de Castilla-La Mancha (Noblejas, Ontígola, Villarrubia de Santiago y Ocaña, en Toledo) quedan fuera de este hito, porque la cartografía oficial de vías pecuarias usada es la de la Comunidad de Madrid.

a) **Mapa de trazados que deberían ser públicos.** Capas: vías pecuarias oficiales de la Comunidad de Madrid (IDEM, ya integrada en la historia 0014) + caminos que figuran en Catastro + caminos de la cartografía histórica. Cada trazado conserva su fuente y su fecha; donde las fuentes no coinciden, se muestra la discrepancia, no se elige una en silencio.

b) **Candidatos a corte.** Tramos donde el trazado (i) desaparece en la ortofoto actual (deja de distinguirse como camino) o (ii) queda dentro de una finca cerrada. Cada candidato lleva confianza, las imágenes de comparación (histórica frente a actual) y la regla que lo señaló. El método de detección queda abierto para el arquitecto. Es la parte con más riesgo técnico: a la resolución del PNOA un vallado se ve mal, así que probablemente haya que combinar señales (continuidad del trazado en la serie histórica, cambio de cubierta, cruce con parcelas catastrales que no son camino) en vez de depender de "ver" la valla.

c) **Visor web sencillo** para enseñarlo: mapa estático (capas pregeneradas, sin servidor de aplicación), con los trazados, los candidatos y una ficha por candidato con su evidencia.

**Después del primer hito** (no diseñado todavía):

- **Avisos ciudadanos con foto**: alguien sobre el terreno confirma o desmiente un candidato. Es lo primero que obliga a almacenar datos de terceros (fotos, posible geolocalización EXIF, contacto), así que necesita su propio análisis de privacidad y de coste antes de diseñarse.
- **Dossier para el ayuntamiento**: documento generado para un tramo concreto, listo para presentar, con trazado, fuentes, serie de imágenes, normativa aplicable y lenguaje de indicio.

## Validación

Sustituye a las "diez compraventas" del enfoque anterior.

**Conjunto de validación:** casos de caminos cerrados o usurpados que asociaciones u otras fuentes ya hayan documentado públicamente en el ámbito del hito (o en la Comunidad de Madrid, si en el ámbito no hay suficientes). Cada caso se registra con su fuente pública, el tramo afectado y la fecha aproximada del cierre.

**Criterio:** el sistema debe señalar esos tramos **por sí solo**, sin que se le indique dónde mirar. Se mide la cobertura (cuántos casos documentados aparecen como candidatos) y se revisan a mano los candidatos que no están en el conjunto, para estimar los falsos positivos. El conjunto se construye y se congela **antes** de ajustar umbrales, para que no se convierta en un conjunto de entrenamiento encubierto.

El conjunto no se publica con datos de propietarios, aunque la fuente original los mencione.

## Fuentes de datos

### Verificar antes de programar

Ninguna historia de código del primer hito empieza hasta que esté documentado, para cada fuente de imágenes y cartografía: **resolución, frecuencia de actualización (o fechas de la serie) y licencia** con cita textual del enlace oficial. Y, para cada municipio del ámbito, **si tiene inventario de caminos publicado** (dónde, en qué formato, de qué año, si está aprobado).

La licencia pesa más que antes: el enfoque anterior generaba informes privados; ahora se **publica un mapa**, es decir, se redistribuyen datos derivados. Una capa cuya licencia no permita la redistribución o la obra derivada no entra en el mapa público, aunque se pueda usar internamente. El resultado se registra en `src/parcel_intel/sources/REGISTRY.md` con el mismo criterio de siempre: solo cuenta como verificado lo comprobado con una petición real y su respuesta grabada (ver `docs/lessons/LESSONS.md`).

### Estado tras la verificación (historia 0021, 25 nov 2026)

Detalle, citas de licencia y fixtures en `src/parcel_intel/sources/REGISTRY.md`, sección "Fuentes del primer hito de caminos públicos". **Publicar** = puede salir en el mapa abierto; **interno** = sirve para analizar, pero no se redistribuye tal cual.

| Fuente | Aporta al hito | Resolución / fechas en el ámbito | Licencia | Uso |
| --- | --- | --- | --- | --- |
| Vías pecuarias — IDEM | Trazados oficiales (polígonos de franja) | Ficha de 2014; sin fecha por tramo | CC BY 4.0 Comunidad de Madrid (declarada en el servicio) | Publicar, como cartografía informativa, no deslinde |
| Catastro INSPIRE | Caminos como parcelas `9xxx`, clase `VT` "vía de comunicación de dominio público" (confirmado en Colmenar) | Actualización semestral (según Catastro) | Licencia propia de 2016: prohíbe difundir el dato original sin transformarlo y llamar "cartografía catastral" a lo derivado | Interno; no se publica por ahora. Una capa derivada propia solo tras consulta jurídica |
| PNOA actual | Estado actual del trazado | 25 cm, vuelo de julio de 2023; Madrid se vuela cada 3 años | CC BY 4.0 (Orden FOM/2807/2015) | Publicar |
| PNOA histórico | Cuándo desaparece un trazado | 1956-57 (50 cm), 1997-2003, 2006, 2009 (50 cm), 2011-2023 cada 3 años (25 cm). Hueco 1957-1997: sin ortofoto en el servicio | CC BY 4.0 | Publicar |
| Planimetrías del IGN (1870-1880) | Caminos de hace 150 años | Los 7 municipios del ámbito tienen planimetría; imagen sin georreferenciar | CC BY 4.0 | Publicar como imagen de referencia |
| MTN50 primera edición / minutas | Caminos de 1881-1975 | Hoja 0606 "Chinchón": 1881, 1934, 1948, 1968… | CC BY 4.0 | Publicar |
| Red de transporte del IGN | Caminos actuales sin asfaltar (vectorial) | 41 de 53 tramos sin asfaltar en una ventana de prueba | CC BY 4.0 (asumido) | Publicar como referencia |
| Inventario municipal de caminos | Fuente más fuerte de titularidad | **No hay ninguno publicado** en los 7 municipios (web y BOCM) | — | Pedirlo por transparencia (Ley 19/2013) |
| PNOA LiDAR | Posible señal de cierres | 3.ª cobertura volada en 2024 sobre Colmenar | CC BY 4.0 (asumido) | Interno; utilidad sin demostrar |
| Ortofoto propia de la Comunidad de Madrid | Imagen más reciente que el PNOA | 2019 a 50 cm confirmada; la de 2025 a 25 cm aparece en el visor pero no en el servicio | Sin verificar | No usar hasta verificar |
| OpenStreetMap | Estado declarado (caminos, `access=private`, barreras) | Sin conteo (Overpass saturado) | ODbL, compartir igual | Interno, como señal; no se publica por ahora |

**Lo que cambia para el diseño:**

- Hay base histórica de sobra (planimetrías de 1870-1880, MTN50 de 1881 y vuelo de 1956) para reconstruir trazados antiguos.
- El cuello de botella está en dos sitios: georreferenciar y vectorizar las planimetrías, y que el dato catastral no se puede publicar en bruto.
- La imagen actual tiene ya más de dos años (julio de 2023). Un cierre posterior no se verá hasta el vuelo de 2026, salvo que la ortofoto de 2025 de la Comunidad resulte utilizable.

**Fuentes del enfoque anterior que quedan en pausa** (el código sigue en el repositorio y no se borra): planeamiento (IDEM `UsoDelSuelo`), BOE y BOCM, Sentinel-2 (con 10 m de resolución no distingue un camino de 3-5 m), cauces y zonas inundables, Red Natura 2000.

## Arquitectura técnica

Se mantiene la arquitectura hexagonal de `CLAUDE.md` y casi todo el motor:

- **Se reutiliza:** cliente de Catastro, cliente PNOA (actual e histórico), cliente de vías pecuarias, PostGIS como base de trabajo, el motor de reglas determinista y el flujo de autoría de reglas con LLM y revisión humana.
- **Cambia el punto de entrada:** el análisis deja de ser "una referencia catastral → un informe bajo petición" y pasa a ser "un municipio → un lote de trazados y candidatos". Lo que se publica son artefactos estáticos (p. ej. GeoJSON o teselas pregeneradas, y un visor HTML/JS que los lee), regenerados cuando cambian las fuentes.
- **Sin cómputo por visita:** el visor no consulta PostGIS ni ninguna API propia; sirve ficheros.
- El detalle (formato de teselas, librería de mapa, dónde se aloja) lo decide el arquitecto en las historias del hito, con ADR donde haya proveedor nuevo.

## Riesgos y decisiones abiertas

El mayor riesgo sigue siendo de confianza, ahora con otro destinatario: un falso positivo publicado en un mapa abierto señala una finca concreta ante sus vecinos.

| Riesgo | Mitigación |
| --- | --- |
| Que un candidato se lea como acusación | Lenguaje de indicio, confianza visible, evidencia siempre al lado, aviso de que no es un dictamen; nunca "ilegal" ni "usurpación" en la interfaz |
| Identificar indirectamente a un propietario aunque no se le nombre | No mostrar titularidad; decidir si el mapa muestra o no la referencia catastral de la finca afectada (ver decisiones abiertas) |
| Licencia de las capas publicadas | Verificada en la historia 0021: IGN y vías pecuarias, CC BY 4.0; Catastro solo transformado; OpenStreetMap obliga a compartir igual. Atribución visible junto a los datos |
| Falsos positivos por limitaciones de la imagen (vallados invisibles, sombras, cultivo sobre un camino que sigue siendo público) | Combinar señales, umbrales conservadores, validación con casos documentados antes de publicar |
| Inventarios municipales inexistentes o no digitalizados | Verificarlo como primera tarea; sin inventario, el mapa se apoya en vías pecuarias oficiales + Catastro + histórico, y lo dice |
| Coste que deje de ser casi cero (avisos con foto, almacenamiento) | Cada funcionalidad con coste recurrente necesita ADR con estimación de coste antes de diseñarse |

**Decisiones cerradas (25 nov 2026):**

- [x] Caminos públicos es la fase 1; rústico para compradores, posible fase posterior; pisos, fuera.
- [x] Sin ánimo de lucro y código abierto; sin clientes, precios ni cuentas de pago.
- [x] Coste casi cero: datos públicos, mapa estático cuando sea posible, ningún LLM en consultas de usuario.
- [x] Primer hito: Colmenar de Oreja y municipios vecinos de la Comunidad de Madrid.
- [x] Validación con casos de caminos cerrados documentados públicamente.
- [x] El LLM sigue siendo DeepSeek detrás de una interfaz única, solo fuera de línea.

**Decisiones abiertas:**

- [ ] Si una capa derivada de Catastro (trazado de camino inferido) cuenta como "transformación" según su licencia de 2016 y se puede publicar.
- [x] Licencia del código: Apache-2.0 (decisión del fundador, 2026-11-25; ver historia #42).
- [x] Licencia de los datos derivados publicados: CC BY 4.0, con atribución visible por capa y procedencia (decisión del fundador, 2026-11-25; ver `NOTICE` e historia #43). Catastro y OpenStreetMap: no se publica por ahora.
- [ ] Si el mapa muestra la referencia catastral de la finca donde queda un candidato, o solo el tramo.
- [ ] Método de detección de "candidato a corte" (ver hito, punto b).
- [ ] Dónde se aloja el mapa estático.
- [ ] Cómo se reciben y moderan los avisos ciudadanos con foto (después del hito).

## Convenciones (sin cambios)

- Todo dato lleva procedencia: fuente, URL, fecha de descarga y licencia.
- Operaciones métricas en EPSG:25830 (ETRS89 / UTM 30N); almacenamiento en ese CRS.
- Datos crudos cacheados e inmutables en `data/`; el procesamiento es reproducible desde la caché.
- Ningún LLM en la evaluación de reglas; solo en autoría (con revisión humana) y en redacción fuera de línea.
- Los tests no llaman a red: fixtures grabadas; tests de integración marcados aparte.

## Primeras tareas, en orden

1. ~~Verificación de fuentes del hito~~ — hecha (historia 0021). Ámbito fijado: Colmenar de Oreja, Aranjuez, Chinchón, Belmonte de Tajo, Villaconejos, Villarejo de Salvanés y Valdelaguna.
2. **Conjunto de validación**: recopilar y congelar los casos de caminos cerrados documentados públicamente en el ámbito.
3. **Solicitudes de acceso a información pública** a los 7 ayuntamientos, pidiendo el epígrafe de caminos del inventario de bienes (las decide y presenta el fundador).
4. **Capa "trazados que deberían ser públicos"** por municipio (vías pecuarias + Catastro + histórico), con discrepancias visibles.
5. **Candidatos a corte**: diseño del método (arquitecto + ADR) y primera versión medida contra el conjunto de validación.
6. **Visor estático** con trazados, candidatos y ficha de evidencia.
