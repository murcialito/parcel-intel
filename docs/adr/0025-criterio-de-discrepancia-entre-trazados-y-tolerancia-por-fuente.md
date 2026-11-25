# ADR 0025 — Criterio de discrepancia entre trazados de distintas fuentes: muestreo a lo largo del trazado, tolerancia métrica por tipo de fuente y confianza determinista

- Estado: aceptada
- Fecha: 2026-11-25
- Historia: #14 (feature #13, épica #4)

## Contexto

El primer hito (docs/vision.md, apartado a) exige que, donde las fuentes de trazados no
coinciden (vías pecuarias de IDEM, Catastro `VT`, red de transporte del IGN, planimetrías
de 1870-1880 y MTN50 histórico), se registre la discrepancia como indicio a verificar,
con confianza, evidencia y regla, y no se elija una fuente en silencio.

Las fuentes tienen formas y precisiones muy distintas (REGISTRY.md, historia 0021):
franjas poligonales de 9 a 38 m de ancho (vías pecuarias), parcelas-camino poligonales
(Catastro), ejes vectoriales (IGN) y trazados vectorizados de mapas manuscritos
georreferenciados a posteriori, con errores de decenas de metros. Un único umbral
métrico para todo daría falsos positivos en los históricos o falsos negativos en las
vectoriales.

El dominio solo puede usar stdlib (CLAUDE.md). Ya existen en `domain/geometry.py`
distancia punto-segmento y punto-en-anillo probados (ADR 0017 y 0018). La entidad común
de trazado (#22) no está diseñada todavía.

## Decisión

1. **Entidad propia `Discrepancy`** en `domain/discrepancy.py` (dataclass congelada) con
   tipo (`AUSENTE_EN_FUENTE`, `DESPLAZAMIENTO`, `SOLAPE`), zona en EPSG:25830, trazado
   sujeto, fuente contraria y trazados contrarios implicados (cada uno con `Provenance` y
   fecha del dato), confianza, evidencia (`Measurement` con nombre, valor y unidad) y
   `CriterionRef` (identificador + versión). No se generaliza `domain.rule.Finding`, atado
   a `Rule` y al informe por parcela; la unificación se revisará con el tercer tipo de
   indicio (candidatos a corte). Ningún campo de titularidad.
2. **Entrada propia `ComparableTrail`** (referencia + forma `Geometry | MultiLineGeometry`)
   en vez de depender de la entidad de #22; la conversión es responsabilidad del caso de
   uso que aplica el criterio (#15).
3. **Geometría en el dominio, stdlib**, no detrás de un port con shapely: el cálculo no
   tiene E/S, ya hay primitivas probadas y evitar una dependencia y un port cuyo único
   implementador sería una librería. Riesgo de la lección 0001 cubierto con tests
   multi-parte sintéticos y reales.
4. **Algoritmo por muestreo**: el trazado sujeto se muestrea cada 5 m (punto medio de cada
   pieza, ponderado por su longitud); las franjas poligonales se reducen a un pseudo-eje
   desplazando su borde hacia dentro la semianchura media (área/perímetro), con peso 0,5,
   de modo que franja y eje de otra fuente son comparables. Para cada muestra se mide la
   distancia a las formas de la otra fuente (0 dentro de un polígono). Muestra cubierta si
   la distancia ≤ tolerancia del par. Todo cubierto, o lo no cubierto ≤ tolerancia: sin
   discrepancia. Parte cubierta: `SOLAPE`. Nada cubierto: mediana ponderada de la distancia
   ≤ 3 × tolerancia → `DESPLAZAMIENTO` con esa mediana; si no, `AUSENTE_EN_FUENTE`. La
   comparación es en un sentido; los dos sentidos y todos los pares los recorre #15.
5. **Tolerancia por tipo de fuente en un único sitio** (`domain/discrepancy_criterion.py`):
   Catastro `VT` 5 m, red IGN 5 m, vía pecuaria 10 m, planimetría 40 m, MTN50 50 m.
   Tolerancia del par = suma cuadrática (`hypot`), por tratarse de errores independientes.
   Radio de búsqueda = 3 × tolerancia del par.
6. **Confianza determinista**: `round(s · f, 3)` con `f = 25 / (25 + tolerancia)` y
   `s = min(1, longitud no coincidente / 100 m)` para ausencias y solapes, o
   `s = min(1, (desplazamiento − tol) / tol)` para desplazamientos. Es un orden relativo
   entre indicios, no una probabilidad. Ningún LLM.
7. **Versionado**: `CRITERION = ("discrepancia_trazados", 1)`. Cualquier cambio de tabla,
   constantes o algoritmo sube la versión; cada discrepancia lleva además la tolerancia,
   el radio y el paso aplicados en su evidencia.
8. **Solo EPSG:25830**: el criterio no reproyecta; otro CRS es un error explícito.

**A revisar con el fundador (umbrales de producto, no decisiones técnicas):** las cinco
tolerancias, el factor 3 del radio, la escala de 25 m de la confianza y los 100 m de
longitud significativa están razonados, no calibrados. Deciden qué discrepancias aparecen
y con qué confianza en el mapa. Se calibran contra el conjunto de validación (vision.md)
antes de publicar nada (#16), y cada recalibración sube la versión del criterio.

## Consecuencias

- #15 aplica `compare_trail` en los dos sentidos para cada par de fuentes de un municipio,
  convierte su `Trail` a `ComparableTrail` y escribe el resultado; no redefine el criterio.
- Precisión conocida: la fracción solapada tiene un error de hasta 5 m por transición; la
  semianchura de una franja se subestima ligeramente (rectángulo de 20 m → 9,09 m), así que
  el desplazamiento medido contra una franja sale alrededor de un metro corto. Franjas muy
  curvas o de anchura irregular alejan el pseudo-eje del eje real; dentro de la tolerancia
  de la vía pecuaria para las anchuras reales observadas, a revisar con los tramos reales
  de Colmenar en #15.
- Coste O(muestras × segmentos candidatos) en Python puro, con poda por bbox. Si en #15 un
  municipio resulta lento, se añade poda medida (precedente ADR 0018), sin cambiar el
  resultado.
- `MultiLineGeometry` y `TrailShape` nuevos en `domain/geometry.py`; `LineGeometry` sigue
  para el informe por parcela.
- `SourceKind` es el vocabulario de tipos de fuente de trazado; la entidad común de #22
  debería reutilizarlo como origen en vez de declarar otro.
- Las plantillas de `describe` son internas; el texto público lo redacta #16 y lo valida el
  fundador.
