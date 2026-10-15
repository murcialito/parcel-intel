# ADR 0002 — Dos ports de geometría (parcela y edificios) y `Provenance` como value object de dominio

- Estado: aceptada
- Fecha: 2026-10-15

## Contexto

La historia 0002 (Bloque 2) pide un port de geometría nombrado por capacidad, con el ejemplo `ParcelGeometryPort` que recibe una referencia catastral y devuelve "la geometría de la parcela y, si existen, las de sus edificios" en un solo método. `docs/vision.md` modela `parcel` y `building` como entidades separadas, y crucialmente `building` tiene un campo `origin` (`catastro` o `detected`) que `parcel` no tiene: solo Catastro produce geometría de parcela, pero la geometría de edificios puede venir también de un pipeline de detección en imagen (fase posterior del motor, ya prevista en el modelo de datos).

Un port combinado que entregue parcela+edificios en una sola llamada funciona hoy, porque el único proveedor es Catastro y su WFS devuelve ambos. Pero fija por diseño que "obtener edificios" solo puede hacerse pidiendo también una parcela, lo que no tiene sentido para un futuro adapter de detección de imagen (no tiene autoridad sobre la geometría de parcela, solo sobre la de edificios que observa).

Además, `CLAUDE.md` exige procedencia (fuente, URL, fecha, licencia) en "todo dato", y `vision.md` lista varias entidades futuras que la necesitarán (`parcel`, `building`, `observation`, `layer_feature`, `norm`, `bulletin_entry`). Esta es la primera historia que escribe entidades de dominio reales; si no se fija aquí la forma de la procedencia, cada adapter futuro improvisará la suya.

## Decisión

1. **Dos ports de capacidad, no uno:**
   - `ParcelGeometryPort`: referencia catastral (`str`) → `Parcel`.
   - `BuildingGeometryPort`: referencia catastral o `Parcel` → `list[Building]`.

   El adapter de Catastro implementa ambos (puede compartir un único cliente HTTP internamente, ya que el WFS los resuelve en la misma llamada). La capa `application/` los invoca por separado. Esto deja el punto de extensión correcto para cuando exista un adapter de detección de imagen: implementará únicamente `BuildingGeometryPort`, sin tener que simular una autoridad sobre geometría de parcela que no le corresponde.

2. **`Provenance` como value object de dominio**, no como campos sueltos repetidos: `domain/provenance.py` con una dataclass `frozen=True` (`source: str`, `url: str`, `retrieved_at: date`, `license: str | None`). Toda entidad de dominio que lo requiera (`Parcel`, `Building`, y en historias futuras `Observation`, `LayerFeature`, `Norm`, `BulletinEntry`) la incluye como campo `provenance: Provenance`, por composición, no por herencia ni mixin.

## Alternativas consideradas

- **Un solo port combinado** (`ParcelGeometryPort` devuelve parcela + edificios): rechazada. Es el corte natural si Catastro fuera el único proveedor para siempre, pero colisiona con `building.origin` de `vision.md` en cuanto exista un segundo origen; obligaría a `application/` a pedir una "parcela" para obtener edificios detectados por imagen, contradiciendo el nombrado por capacidad del ADR 0001.
- **Procedencia como campos sueltos duplicados en cada entidad**, sin tipo compartido: rechazada. Duplica forma y validación en cada entidad y adapter, y ya se ve en `vision.md` que `norm`/`provision` necesitan una forma superpuesta (URL, vigencia) que conviene no reinventar cada vez.
- **Procedencia como detalle de adapter** (metadata no tipada en `domain/`): rechazada. El dominio necesita poder razonar sobre antigüedad/fuente de un dato (p. ej. para desempates o explicaciones en reglas más adelante), así que debe ser un tipo de dominio, no un adjunto de infraestructura.

## Consecuencias

- El Bloque 2 de la historia 0002 crea dos `Protocol` (no uno) en `ports/`, y `domain/provenance.py` además de `domain/parcel.py` / `domain/building.py`; `Parcel` y `Building` incluyen `provenance: Provenance`.
- El criterio de aceptación del Bloque 2 que describe "un método que devuelve geometría de parcela y de edificios" debe reescribirse como dos capacidades/dos métodos.
- No introduce dependencia de terceros (son dataclasses de stdlib): no aplica coste de salida de proveedor en este ADR.
- Riesgo residual: si una fuente futura necesita campos de procedencia adicionales y específicos (p. ej. versión de capa en IDEM), se decide entonces si se extiende `Provenance` o se añade un campo propio a esa entidad; no bloquea esta historia.
