# ADR 0029 — Trazado común: `Trail` en dominio, un solo vocabulario de fuentes, papel vía/anejo y conversión pura desde vías pecuarias

- Estado: aceptada
- Fecha: 2026-11-26
- Historia: #22 (feature #9). Relacionadas: #14 (ADR 0025), #19 (ADR 0026), #15/#31/#32, #23/#36, #29/#33

## Contexto

El mapa compara y publica trazados de cinco fuentes (vías pecuarias de IDEM, Catastro `VT`, red de transporte del IGN, planimetrías del IGN y MTN50 de 1881). Cada fuente tiene ya, o tendrá, su entidad propia (`LivestockTrail`, `HistoricTrail`…) con campos que solo tienen sentido en ella (área, error de georreferenciación, estado de revisión). La detección de discrepancias (#15) y la publicación necesitan un modelo uniforme.

#14 ya fijó `SourceKind`, un `Literal` con las cinco fuentes, como clave de la tabla de tolerancias, y `TrailShape = Geometry | MultiLineGeometry` como forma de un trazado. #19 decidió que el histórico se *convierte* al trazado común y no lo compone (ADR 0026). #33 añade `Provenance.redistribution`, cerrado por defecto.

Las vías pecuarias de IDEM traen en la misma capa vías (`Cañada`, `Cordel`, `Vereda`, `Colada`) y elementos anejos (`Abrevadero`, `Descansadero`, `Descansadero-Abrevadero`), con la misma estructura (REGISTRY.md, hallazgo 1). Son cartografía informativa, no deslinde. Su licencia, CC BY 4.0 Comunidad de Madrid, permite redistribuir.

## Decisión

1. Entidad `Trail` en `domain/trail.py`, dataclass congelada con `identifier`, `source: SourceKind`, `role: TrailRole` (`via`/`anejo`), `name` y `trail_type` opcionales, `municipality_code` (INE), `geometry: TrailShape` en EPSG:25830, `provenance` con licencia obligatoria, `data_date: date | None` y `character` (nota de carácter del dato). Valida en `__post_init__` y lanza `InvalidTrailError`. Admite geometría sin partes: decidir qué hacer con un trazado vacío es del consumidor, no de la entidad.
2. `SourceKind` se define en `domain/trail.py` y `discrepancy_criterion` lo importa. Un solo vocabulario; su cadena es el valor que se escribe y ordena. No se crea un `Enum` `TrailSource`.
3. Sin campos de titularidad, propietario ni parcela colindante. Ni ahora ni en historias posteriores: un campo así exige un ADR que revoque este punto.
4. Conversión pura `livestock_trail_to_trail` en `domain/livestock_trail.py`: `identifier = CD_VP`, `role` por tabla cerrada de `DS_TIPO` (valor desconocido → `UnknownLivestockTrailTypeError`), `character = "cartografía informativa, no deslinde"`, `data_date = None`, misma geometría. La licencia se rellena con `CC BY 4.0 Comunidad de Madrid` si falta; cualquier otra licencia es error; solo entonces se marca `Redistribution.PUBLIC`.
5. Sin port ni adapter nuevos. `LivestockTrail`, `LivestockTrailPort` y el adapter no cambian; el informe por parcela sigue igual.
6. Cada fuente escribe su conversión a `Trail` en su propio módulo de dominio (`livestock_trail_to_trail`, y más adelante `historic_trail_to_trail`, Catastro e IGN). `trail.py` no conoce las entidades de origen.

## Alternativas consideradas

- **Componer (`LivestockTrail` dentro de `Trail`, o al revés)**: rechazada, mismo motivo que ADR 0026. Mete campos propios de una fuente en el modelo común.
- **`Enum` `TrailSource` nuevo, como proponía #15**: rechazada. Duplicaría el `Literal` de #14 y obligaría a mapear entre los dos. #15 ya preveía usar los nombres que fijara este ADR.
- **Una sola fuente "histórico"**: rechazada. #14 da tolerancias distintas a planimetría (40 m) y MTN50 (50 m).
- **`Geometry | LineGeometry`**: rechazada. `TrailShape` ya existe y admite multi-línea sin partir trazados en identificadores artificiales.
- **Filtrar los anejos en la conversión**: rechazada. Siguen siendo dominio público pecuario y el visor puede querer mostrarlos. Se marcan (`role`) y cada consumidor decide.
- **Clasificar un `DS_TIPO` desconocido como vía (o como anejo) por defecto**: rechazada. Las dos opciones producen indicios falsos o los ocultan sin aviso.
- **Nota de carácter como tabla por fuente en `trail.py`**: rechazada por ahora. El texto de carácter de Catastro, IGN e histórico es texto público que aún no ha validado el fundador; cada conversión lo fija con su fuente.
- **`data_date = 2014-11-29` (modificación de la ficha de datos.gob.es)**: rechazada. Es la fecha del catálogo, no de cada tramo; atribuirla a cada tramo afirmaría algo que la fuente no dice.
- **Rechazar geometrías vacías en `Trail`**: rechazada. #31 tiene que poder contar un trazado vacío sin perderlo.

## Consecuencias

- Nuevo `domain/trail.py`. `domain/discrepancy_criterion.py` importa `SourceKind` de ahí. `domain/livestock_trail.py` gana constantes, `UnknownLivestockTrailTypeError`, `livestock_trail_role` y `livestock_trail_to_trail`.
- #15/#31/#32 usan `Trail`, `SourceKind` (en lugar de `TrailSource`) y `TrailShape`. El lector GeoJSON de #32 mapea `LineString` y `MultiLineString` a `MultiLineGeometry`. `Trail` → `ComparableTrail` lo escribe #31.
- #23/#36 convierten cada pieza recortada con `replace(livestock_trail_to_trail(piece.source), geometry=…, municipality_code=…)`. La clave única de un trazado es `(source, municipality_code, identifier)`.
- Un `DS_TIPO` nuevo, al ampliar el ámbito, detiene el lote con un error explícito; se añade a la tabla junto con la fixture que lo muestra.
- Coste: ninguno. Solo stdlib, sin red ni almacenamiento.
