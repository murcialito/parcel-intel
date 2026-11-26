# ADR 0045 — Carga de trazados históricos: la base como proyección de git por unidad

- Estado: aceptada
- Fecha: 2026-11-26
- Historias: #20 (y sus hijas #136–#140). Depende de ADR 0043 (#18, método) y ADR 0026 (#19, entidad)

> Número: el diseño de #20 lo llamaba 0044, pero el 0044 lo ocupó #94 (publicación de indicios de
> discrepancia) antes de que se desarrollara esta hija. Se usa el siguiente libre.

## Contexto

El ADR 0043 fija el método (afín por unidad sobre el render del WMS, RMSE LOO, umbrales, entrada humana
en `curated/historico/<unit_id>/`) y deja a #20 dos decisiones: cómo retirar las filas que dejan de
valer y cómo invalidar aprobaciones cuando cambian los puntos de control. El port de #19
(`save_proposal`, `record_review`) no pisa filas revisadas y confirma cada operación por separado: con
él no hay carga atómica, ni corrección de un aprobado cuya geometría cambió, ni retirada de uno borrado
de git. Además, `domain/` no puede importar `ports/`, y `ST_AsText` no devuelve exactas las coordenadas
arbitrarias.

## Decisión

1. **PostGIS es una proyección de git por unidad.** `GeoreferenceRepositoryPort.sync_unit(unit, approved)`
   reescribe en una transacción la unidad (`historic_georeference`, UPSERT por `unit_id`) y sus trazados
   aprobados: inserta los nuevos, actualiza los que cambiaron, borra los que ya no están aprobados en git
   y no toca los idénticos. La base solo recibe `approved`; propuesta y revisión viven en git (#50).
2. **Vínculo trazado → unidad**: columna `historic_trail.unit_id` (FK a `historic_georeference`).
   `HistoricTrail` no cambia. Una fila con otro `unit_id` o sin él no se adueña: error y rollback.
3. **Invalidación solo con git**: cada trazado `aprobado` lleva `control_points_sha256`, el del
   `puntos_control.csv` que vio quien aprobó (lo imprime `historico ajuste`). Si no coincide con el
   fichero actual, la unidad entera se rechaza. `.gitattributes` marca `curated/historico/**` como `-text`.
4. **Rechazo por unidad, exclusión por trazado.** Imagen, puntos, umbrales, fichero de trazados o
   aprobación caducada rechazan la unidad antes de escribir; la base conserva la última carga válida.
   Solo la extrapolación (vértice fuera de la envolvente de los retenidos) excluye un trazado concreto.
5. **Vértices redondeados al milímetro** al transformar, para que la ida y vuelta por PostGIS sea exacta
   y una recarga sin cambios sea `unchanged`.
6. **Ajuste reproducible**: mínimos cuadrados con coordenadas centradas; degenerado si
   `det(M) ≤ 1e-12·Σu²·Σv²` (también en cada LOO); cuadrante por `width/2`, `height/2`; motivos con
   métrica, valor y umbral.
7. **Errores del dominio en el dominio** (`InsufficientControlPointsError`, `InvalidControlPointError`,
   `GeoreferenceRejectedError`, `InvalidDigitizationError`, `StaleApprovalError`); en `ports/errors.py`
   solo los de adapters (`RawImageMismatchError`, `WorkingImageUnavailableError`,
   `CuratedUnitNotFoundError`, `GeoreferenceUnitNotFoundError`). Corrige el ADR 0043, que los ponía
   todos en `ports/`.
8. **Evidencia sin Pillow**: el panel PNOA se pide en PNG a `pnoa-ma` (`OI.OrthoimageCoverage`), porque
   `pnoa-historico` no sirve PNG (502, verificado el 2026-11-26) y JPEG no se decodifica sin Pillow.
   En el ámbito, `pnoa-ma` es el vuelo 2023-07.
9. **CLI** `historico ajuste|evidencia|cargar <unit_id>`; nada en `api/`.

### Umbrales de producto

Ninguno nuevo: los del ADR 0043, como constantes del dominio.

## Alternativas descartadas

- **`save_proposal` + `record_review` por trazado** (sugerido en ADR 0026): cada llamada confirma por su
  cuenta, no puede actualizar ni retirar revisados y obligaría a pasar por `proposed` en la base algo que
  ya se aprobó en git.
- **Añadir `unit_id` o métodos de borrado a `HistoricTrail` / `HistoricTrailRepositoryPort`**: mezcla el
  ciclo de revisión de #19 con la proyección por unidad; la columna basta y la entidad no la necesita.
- **Invalidar comparando con el hash guardado en la base**: depende del estado de una base local; con el
  hash en el GeoJSON la regla se comprueba en la PR, donde revisa el fundador.
- **Rechazar la unidad entera por un trazado extrapolado**: contradice el ADR 0043 ("rechaza ese
  trazado") y bloquearía trazados válidos.
- **Comparar geometrías con `ST_Equals` en SQL**: tolera diferencias que la entidad no tolera y oculta la
  inexactitud de `ST_AsText`; redondear en el dominio es explícito y testeable.
- **PNOA en JPEG con Pillow**: dependencia nueva para un panel de revisión; PNG de `pnoa-ma` lo evita.

## Consecuencias

- Migración `0006_create_historic_georeference` (tabla nueva y columna `unit_id`); `conftest.py` la
  trunca. Las filas de `save_proposal` (fixtures de #19) quedan con `unit_id` nulo y la carga no las toca.
- Quien aprueba copia `control_points_sha256` de `historico ajuste`; cambiar los puntos obliga, en la
  misma PR, a devolver los trazados a `propuesto` y regenerar la evidencia.
- Mientras git no esté en estado cargable, la base muestra la última carga válida y `historico cargar`
  sale con 1: hay que vigilarlo antes de publicar (fuera de esta historia).
- Si el WMS cambia sus bytes para la misma URL, la imagen ya no se puede volver a descargar con el mismo
  sha256: la caché de `data/raw/` es la única copia; perderla obliga a rehacer los puntos.
- #21 y sus hijas (#56–#62) reutilizan todo sin cambios y añaden solo `curated/historico/<unit_id>/`.
- Esta hija (#136) entrega el dominio: `domain/georeferencing.py` y `domain/digitization.py`. Dos
  detalles propios del algoritmo: con menos de tres posiciones distintas el ajuste se rechaza como
  «repetidos» (motivo distinto del de «colineales»), y la envolvente de los retenidos admite el borde con
  una tolerancia de 1e-9 px de distancia a la arista.
