# ADR 0039 — Candidatos a corte: discrepancia con el camino actual, señales por muestra y entidad `CutCandidate`

- Estado: aceptada
- Fecha: 2026-11-26
- Historia: #109 (feature #99, épica #5). Consumidores: #110 y #111 (medición, feature #100), #101 (imágenes) y #103 (publicación).
- Amplía los ADR 0025 y 0030. Reutiliza los ADR 0006 (ortofoto), 0028 (Catastro interno), 0019 y 0020 (reglas propuestas por IA) y la puerta de publicación de los ADR 0036 y 0038.
- Publicación de lo derivado de Catastro: ADR 0041, que corrige el §3 del ADR 0035 (decisión del fundador en #99).

## Contexto

El punto (b) del primer hito (ADR 0021, `docs/vision.md`) pide señalar los tramos donde un trazado que debería ser público (i) deja de distinguirse en la ortofoto actual o (ii) queda dentro de un cierre, con confianza, evidencia y la regla que lo señaló. El fundador fijó el 2026-11-26 que un candidato a corte es una discrepancia (ADR 0025 y 0030) que además cumple (i) o (ii). La cadena de discrepancias ya existe y no se duplica.

A 25 cm de resolución un vallado apenas se ve, así que el método no puede depender de "ver" la valla. Tiene que combinar señales que llegarán de una en una (Catastro, ortofoto actual, serie histórica, quizá OpenStreetMap o LiDAR), medirlas contra el conjunto de validación congelado (#54, `validacion-v1`) y no rediseñarse con cada señal nueva. El dominio solo admite stdlib. Catastro no se redistribuye en bruto (ADR 0028); lo derivado que no reproduce la información original sí se publica, con las condiciones del ADR 0041. Ninguna consulta de usuario llama a un LLM.

## Decisión

### 1. Qué es un candidato

Un candidato a corte es un tramo de un trazado A que cumple a la vez:

- **Discrepancia base.** El tramo está en la zona de un `DiscrepancyRecord` de tipo `AUSENTE_EN_FUENTE` o `SOLAPE` cuya fuente B es `ign_red_transporte` (el camino actual). Con la matriz `ABSENCE_PAIRS` del ADR 0030, A puede ser una vía pecuaria, un camino `VT` de Catastro, una planimetría o el MTN50. Las tablas viven en un solo sitio (`domain/cut_method.py`: `BASE_KINDS`, `BASE_COUNTERPARTS`).
  - No son base las discrepancias frente a otra fuente B (p. ej. vía pecuaria → Catastro). No dicen nada del estado actual del terreno. Además, harían tautológica la señal de Catastro: una vía pecuaria sin parcela `VT` cae, por definición, dentro de otra parcela.
  - `DESPLAZAMIENTO` no es base: el trazado existe, solo que desplazado.
  - Los anejos ya están excluidos (ADR 0030).
- **Alguna señal apoya** la condición (i) o la (ii) en ese tramo.

La ausencia en la red del IGN **no** cuenta como condición (i). El IGN no recoge todas las sendas, y si contara, toda discrepancia base sería un candidato.

### 2. La muestra como unidad común

El método trabaja sobre las muestras del eje del trazado A con el muestreo del ADR 0025, sin cambios: paso de 5 m y pseudo-eje de las franjas con peso 0,5. `_sample_shape` de `domain/discrepancy.py` pasa a ser pública como `trail_samples(shape) -> tuple[TrailSample, ...]`, con el mismo algoritmo, así que el criterio de discrepancia no sube de versión.

Una muestra está **en discrepancia base** si su pieza pertenece a la zona de algún registro base:

- `AUSENTE_EN_FUENTE`: todas las muestras del trazado.
- `SOLAPE`: las que distan como mucho `ZONE_MATCH_M = 0,05 m` de la zona, que se construyó con esas mismas piezas.

Cada señal devuelve **un veredicto por muestra**: `apoya`, `no_apoya` o `sin_dato`. Las señales son intercambiables y se combinan sin geometría nueva. Una señal nueva solo añade un proveedor, sin tocar el método.

### 3. Del veredicto al tramo

1. **Racha**: muestras consecutivas de la misma parte que están en discrepancia base y en las que alguna señal `apoya`.
2. Las rachas del mismo trazado A separadas como mucho `GAP_M = 10 m` (distancia mínima entre sus piezas) se **funden** en un candidato. La agrupación es de enlace simple, en orden de muestra y determinista. Funde los dos lados del pseudo-eje de una franja, que distan menos de 2 m en una franja de 20 m, y salva huecos cortos.
3. Se descartan los candidatos de menos de `MIN_LENGTH_M = 25 m`. La longitud es la suma de los pesos de sus muestras.
4. El **tramo** es una `MultiLineGeometry` en EPSG:25830 con las piezas de sus muestras. Las piezas consecutivas se unen en una sola línea, como `_uncovered_zone` en el ADR 0025.

### 4. Combinación y confianza

- Las condiciones se combinan con **O**, como en la definición del fundador: basta (i) o (ii). `conditions` lista las que tienen alguna señal que apoya.
- Para cada señal s se calcula `f_s`, el peso de las muestras del candidato donde s apoya dividido por el peso total del candidato. Se registra también `n_s`, la fracción de muestras sin dato.
- `confianza = round(d · (1 − Π_s (1 − w_s · f_s)), 3)`, donde:
  - `d` es la mayor confianza de los registros base que tocan el candidato (ADR 0025);
  - `w_s` es el peso de la señal, en una tabla única (`SIGNAL_WEIGHTS`).
- **Es un orden relativo, no una probabilidad.** La forma de "O ruidoso" solo garantiza tres cosas: una señal que concurre nunca baja la confianza, dos señales que concurren ordenan por encima de una, y la confianza nunca supera la de la discrepancia base.
- Pesos iniciales: `parcela_no_camino` 0,6. Para `visibilidad_ortofoto` (0,5) y `serie_historica` (0,7) son propuestas: los fija la historia de cada señal.
- Ningún LLM interviene.

**Ejemplo trabajado** (oráculo de la historia de la entidad):

- Trazado A: vía pecuaria con eje en polilínea de (0, 0) a (200, 0), en EPSG:25830.
- Registro base: `AUSENTE_EN_FUENTE` frente a la red del IGN. Tolerancia del par: `hypot(10, 5)` = 11,180 m. `d = round(1 · 25 / (25 + 11,180), 3)` = 0,691.
- Una sola parcela ordinaria, el rectángulo x ∈ [50, 150], y ∈ [−50, 50].
- Margen de la señal (§6): `hypot(10, 5)` = 11,180 m.
- Hay 40 muestras, en x = 2,5 … 197,5. Apoyan las 16 que van de x = 62,5 a x = 137,5.
- Resultado: tramo de (60, 0) a (140, 0) y `longitud_tramo_m = 80.0`. Con `f = 1`, la confianza es `round(0,691 · (1 − (1 − 0,6 · 1)), 3)` = 0,415.

### 5. Entidad

`domain/cut_candidate.py`: solo stdlib, dataclasses congeladas.

```python
CutCondition = Literal["no_se_distingue", "dentro_de_cierre"]   # (i), (ii)
SignalVerdict = Literal["apoya", "no_apoya", "sin_dato"]

@dataclass(frozen=True)
class SignalRef:
    identifier: str          # "parcela_no_camino", "visibilidad_ortofoto", ...
    version: int
    condition: CutCondition

@dataclass(frozen=True)
class SignalReading:         # lo que devuelve una señal para un trazado A
    signal: SignalRef
    verdicts: tuple[SignalVerdict, ...]   # una por muestra de trail_samples(A), mismo orden
    evidence: tuple[Measurement, ...]     # parámetros aplicados (p. ej. margen_borde_parcela_m)
    provenance: tuple[Provenance, ...]    # datos usados, ordenados, con su marca de redistribución

@dataclass(frozen=True)
class SignalSupport:         # una señal que concurre en un candidato
    signal: SignalRef
    support_fraction: float  # f_s, 3 decimales
    no_data_fraction: float  # n_s, 3 decimales
    provenance: tuple[Provenance, ...]

@dataclass(frozen=True)
class CutCandidate:
    candidate_id: str                  # 16 hex de sha256: método+versión, municipio, fuente y trazado A, tramo a 0,01 m
    municipality_code: str             # INE
    subject: TrailRef                  # trazado que debería ser público (lado A del Discrepancy)
    discrepancy_ids: tuple[str, ...]   # record_id de los DiscrepancyRecord base que toca, ordenados; nunca vacío
    stretch: MultiLineGeometry         # tramo, EPSG:25830, nunca vacío
    conditions: tuple[CutCondition, ...]  # orden fijo ("no_se_distingue", "dentro_de_cierre"); nunca vacío
    signals: tuple[SignalSupport, ...]    # solo las que concurren (f_s > 0), por identificador
    confidence: float                  # [0, 1], 3 decimales; orden relativo, no probabilidad
    evidence: tuple[Measurement, ...]  # orden fijo: longitud_tramo_m, longitud_base_m, confianza_base, …
    method: CriterionRef               # CUT_METHOD = CriterionRef("candidato_corte", 1)

@dataclass(frozen=True)
class SignalRunSummary:      # por municipio y señal: qué se ejecutó y qué faltó
    signal: SignalRef
    status: Literal["ejecutada", "sin_datos"]
    reason: str | None
    provenance: tuple[Provenance, ...]

@dataclass(frozen=True)
class MunicipalCutCandidateReport:
    municipality_code: str
    method: CriterionRef
    discrepancy_criterion_id: str      # criterion_id del informe base
    base_record_ids: tuple[str, ...]   # registros base considerados, ordenados
    signals: tuple[SignalRunSummary, ...]
    candidates: tuple[CutCandidate, ...]  # orden canónico: fuente A, trazado A, primera muestra, candidate_id
```

- `__post_init__` de `CutCandidate` rechaza un `srid` distinto de 25830, un tramo vacío, una confianza fuera de [0, 1], `conditions` o `discrepancy_ids` vacíos y una condición sin ninguna señal de esa condición en `signals`.
- **No hay ningún campo de titularidad, propietario ni referencia catastral de finca.** Un test fija la lista exacta de `dataclasses.fields`.
- `subject.trail_id` es el identificador del **trazado**, como en el ADR 0029. Si A es Catastro `VT`, es la referencia de la parcela del propio camino, que es dominio público, nunca la de la finca. Es interno y no se publica (#103 hará su propio identificador público, como el ADR 0038).
- `Measurement` se reutiliza de `domain/discrepancy.py`. Si una señal necesita otra unidad, su historia amplía el `Literal`.

`domain/cut_method.py` reúne:

- las constantes de §1 a §4;
- `eligible_base_records(report) -> tuple[DiscrepancyRecord, ...]`;
- `build_cut_candidates(report, readings) -> tuple[CutCandidate, ...]`, donde `report` es un `MunicipalDiscrepancyReport` sin redactar (si está redactado, `ValueError`) y `readings` es un `Mapping[tuple[SourceKind, str], Sequence[SignalReading]]` indexado por (fuente, trazado A);
- `describe_candidate(candidate) -> str`.

### 6. Primera señal: `parcela_no_camino`, condición (ii), versión 1

**Criterio:** dentro de la zona base, ¿cae el eje del trazado dentro de una parcela catastral rústica ordinaria (número < 9000)?

- **Huella.** La aplicación convierte cada `Parcel` en `ParcelFootprint(geometry, kind)`, con `kind` igual a:
  - `ordinaria`: rústica con número < 9000;
  - `infraestructura`: rústica con número ≥ 9000, cualquiera que sea su clase (`VT`, `HG`, `I-`…);
  - `otra`: urbana o con una referencia que no se puede leer.

  Para clasificarla usa `parse_rural_reference` e `is_road_parcel_number` (#37) y **descarta la referencia** al construir la huella. La huella no tiene campo de referencia, así que esta nunca llega al dominio de la señal ni al candidato.
- **Veredicto por muestra:**
  - `apoya` si la muestra cae dentro de una huella `ordinaria`, a una distancia de su borde (el anillo tratado como polilínea cerrada) de al menos `margen = hypot(tol(A), tol(catastro_vt))`, y no cae dentro de ninguna huella `infraestructura`. Así, un enclave ≥ 9000 dentro de una parcela ordinaria anula el apoyo.
  - `no_apoya` en cualquier otro caso, también fuera de toda parcela. Un hueco sin parcela suele ser un descuento de dominio público.
  - `sin_dato` si no se pudo obtener la tesela que cubre la muestra.
- **Alcance:** solo se aplica a vías pecuarias, planimetrías y MTN50, nunca a un trazado `catastro_vt`, que por definición es una parcela de camino.
- **Datos:** las parcelas salen de `ParcelsInAreaPort` (#37) con la misma rejilla de teselas que `catastro-caminos`: `tile_bbox` del bbox del término del IGN y lado de 900 m. Solo se piden las teselas que tocan alguna zona base. En la aplicación, las huellas se indexan con `GridIndex`.
- **Por qué es la primera.** Es la más barata que da algo medible:
  - **datos:** ninguna petición nueva si #37 ya descargó el término; si no, unas 140-160 teselas en Colmenar (~112 km²), unos 3 min con la pausa de 1 s y coste 0 €. No necesita `Consulta_DNPPP`.
  - **cómputo:** punto en anillo por muestra con prefiltro de rejilla. Con unos 50 km de zona base (10.000 muestras, ~10 huellas candidatas por muestra y ~50 vértices) son ~5·10⁶ operaciones: segundos en Python puro.
  - **dependencias:** ninguna nueva y ningún proveedor nuevo.
  - Es determinista y no necesita calibrar ningún índice de imagen.
- **Límites conocidos:**
  - una parcela no es un cierre: puede contener un camino con servidumbre, y por eso el peso es 0,6 y no 1;
  - Catastro carece de fehaciencia;
  - no ve un corte puntual con cancela en un camino que sigue visible;
  - no se aplica a los caminos `VT`.

### 7. Condición (ii) sin identificar a nadie, y qué sale a lo publicable

- No entra ningún dato de titularidad: el WFS INSPIRE de parcelas no lo trae y no se consulta ningún otro servicio.
- La referencia catastral se descarta en la aplicación antes de llegar al dominio (§6).
- La evidencia de la señal son longitudes y fracciones, sin geometría de parcela, sin número de parcelas y sin referencias.
- El tramo es geometría del trazado A, nunca de la parcela.
- **Qué puede publicar #103.** Un candidato es un resultado derivado sobre un trazado, que no reproduce la información original de Catastro, así que se publica aunque solo lo sostenga la señal de Catastro (ADR 0041 §1, que corrige el §3 del ADR 0035). De cada candidato, #103 puede publicar:
  - el tramo, si A está en `REDISTRIBUTABLE_SOURCES`;
  - la condición, la confianza y la fracción de apoyo de cada señal, también de `parcela_no_camino`.
- **Condiciones cuando concurre una señal que usa Catastro** (ADR 0041 §2), que #103 aplica a partir de la `provenance` de cada `SignalSupport`:
  - citar «Dirección General del Catastro» con la fecha de consulta;
  - avisar de que no es cartografía ni información catastral, de que no es fehaciente y de que puede haber cambiado desde la consulta;
  - no llamarlo nunca «cartografía catastral» ni «información catastral»;
  - no alterar el sentido del dato: una parcela que Catastro clasifica como vía de comunicación no se presenta como otra cosa.
- **Nunca se publica** la geometría de las parcelas (ni simplificada ni filtrada), sus atributos (uso, clase, superficie), referencias catastrales ni números de polígono o parcela (ADR 0041 §3 y §4), ni `candidate_id` ni `discrepancy_ids`.
- La geometría de Catastro sigue marcada `solo_uso_interno` (ADR 0028 y 0036), así que las `provenance` de la señal la marcan como interna: la marca dice qué geometría no sale, no si el candidato se publica.
- Riesgo residual que el diseño no puede quitar: superponer un tramo publicado sobre el Catastro lleva a la finca. El fundador ya decidió mostrar solo el tramo, y lo mitigan el lenguaje de indicio, el aviso de no fehaciencia y la publicación diferida tras la medición (#100).

### 8. Reparto de capas

| Capa | Pieza | Historia |
| --- | --- | --- |
| domain | `cut_candidate.py`, `cut_method.py`, `trail_samples` público en `discrepancy.py` | H1 |
| domain | `cut_signal_parcel.py` (`ParcelFootprint`, `read_parcel_signal`) | H2 |
| application | `cut_signals.py`: `CutSignalProvider(Protocol)` con `signal`, `applies_to(kind)` y `read(municipality_code, subject, samples) -> SignalReading`, y `CadastralParcelSignalProvider(parcels_for: Callable[[str], ParcelsInAreaPort], boundaries: MunicipalBoundaryPort, tile_side_m)` | H2 |
| application | `detect_cut_candidates.py`: `DetectCutCandidatesUseCase(reports: DiscrepancyReportSource, providers: Sequence[CutSignalProvider], sink: CutCandidateSink).execute(municipality_code) -> MunicipalCutCandidateReport` | H2 |
| ports | `cut_candidate_sink.py` (`write(report)`); reutiliza `DiscrepancyReportSource` (#94), `ParcelsInAreaPort` (#37) y `MunicipalBoundaryPort` (#35) | H2 |
| ports | `cut_candidate_source.py` (`get_report(municipality_code)`), para la medición | H3 |
| adapters | `cut_candidate_files/` (escritor y lector GeoJSON, EPSG:25830, `data/derived/candidatos/interno/<ine>.geojson`) | H3 |
| cli | `candidatos-corte --municipio … \| --ambito [--sin-red]`; sale con 1 si falla un municipio | H3 |

- `CutSignalProvider` es un `Protocol` de aplicación, no un port: lo implementan clases de `application/` que usan ports. Una señal nueva es un proveedor más, inyectado desde `cli/`, y el caso de uso no cambia.
- Que no haya informe de discrepancias es "municipio sin capas" y se registra. Que una señal no tenga datos produce `SignalRunSummary(status="sin_datos")` y veredictos `sin_dato`. Cualquier otro error se propaga (mismo criterio que el ADR 0030 §3).
- Se respeta `lint-imports`: el dominio no importa nada de fuera y la aplicación solo importa ports y dominio.

### 9. Contrato con la medición (#110, #111)

- **El detector recibe** un código INE y lee el informe interno de discrepancias y los datos de cada señal. **Devuelve** un `MunicipalCutCandidateReport`.
- **El arnés solo necesita** `(candidate_id, municipality_code, stretch)` de cada candidato, más saber qué municipios se calcularon: un informe presente, aunque no tenga candidatos, es "municipio evaluable", y uno ausente es `sin_capas`.
- El arnés no lee `signals` ni `evidence`. Así mide igual con cualquier combinación de señales. Puede leer `confidence` para dar cobertura y precisión por umbral, sin cambiar el método.
- El criterio de casamiento lo fija el ADR de #110.
- **Ajustar el método no toca el conjunto de validación.** Las constantes de §1 a §4 y de cada señal viven en un solo sitio, y cualquier cambio sube `CUT_METHOD.version` (y la de la señal) en la misma PR. Todo resultado de medición registra la versión del método y la del conjunto (`validacion-v1` y su huella de #54). `docs/validacion/casos.json` no se edita para ajustar nada: una v2 solo entra por decisión del fundador, con su `CONGELADO-v2.md` (#112). Los umbrales se fijan antes de medir; si se recalibran tras una medición, se dice en el resultado.

### 10. LLM y reglas propuestas por IA

- Ningún LLM interviene al evaluar ni al construir candidatos.
- Las señales son código determinista con constantes versionadas. La versión 1 no carga reglas de la tabla `rule`.
- Si un umbral o una señal llegaran a proponerse con el flujo de autoría (ADR 0019), solo se usarían después de `review approve` (ADR 0020), y la evaluación seguiría sin llamar a ningún LLM.

### 11. Lenguaje

- La salida es siempre un indicio a verificar.
- `describe_candidate` usa plantillas internas fijas por señal, siempre con el cierre "Indicio a verificar, no es un dictamen.":
  - base: «Tramo de {longitud} m de {fuente A} ({fecha}) sin equivalente en el camino actual del IGN.»;
  - `parcela_no_camino`: «Según Catastro, el {porcentaje} % del tramo cae dentro de parcelas que no son camino.».
- La señal de Catastro **no** dice "cierre": describe lo que mide.
- Ninguna plantilla usa «ilegal», «usurpación» ni ninguna otra palabra de `BANNED_WORDS` (`domain/public_card.py`); un test lo comprueba con `banned_words_in`.
- El texto público lo propone #103 y lo valida el fundador.

### 12. Determinismo e identificador

Siguen el ADR 0030 §5 y §6:

- `candidate_id` es un hash de contenido, sin marcas de tiempo;
- todo se ordena antes de iterar;
- confianza, fracciones y medidas se redondean a 3 decimales.

`candidate_id` no se publica: contiene el identificador del trazado A, que puede ser de Catastro.

### Orden de las señales (historias candidatas)

| # | Historia | Condición | Talla | Toca (aproximado) | Depende de |
| --- | --- | --- | --- | --- | --- |
| H1 | Entidad `CutCandidate` y método de combinación (dominio) | — | m | `src/parcel_intel/domain/cut_candidate.py`, `src/parcel_intel/domain/cut_method.py`, `src/parcel_intel/domain/discrepancy.py`, `tests/domain/test_cut_candidate.py`, `tests/domain/test_cut_method.py`, `tests/domain/test_discrepancy.py`, `tests/acceptance/test_historia_<n>.py` | este ADR |
| H2 | Señal `parcela_no_camino` y caso de uso de candidatos | (ii) | m | `src/parcel_intel/domain/cut_signal_parcel.py`, `src/parcel_intel/application/cut_signals.py`, `src/parcel_intel/application/detect_cut_candidates.py`, `src/parcel_intel/ports/cut_candidate_sink.py`, `tests/domain/test_cut_signal_parcel.py`, `tests/application/test_detect_cut_candidates.py`, `tests/acceptance/test_historia_<n>.py` | H1, #37 y #94 |
| H3 | Fichero interno de candidatos y comando `candidatos-corte` | — | m | `src/parcel_intel/adapters/cut_candidate_files/`, `src/parcel_intel/ports/cut_candidate_source.py`, `src/parcel_intel/cli/main.py`, `CLAUDE.md`, `src/parcel_intel/sources/REGISTRY.md`, `tests/adapters/cut_candidate_files/`, `tests/cli/test_main.py`, `tests/acceptance/test_historia_<n>.py` | H2 |
| H4 | Señal `visibilidad_ortofoto` (PNOA 2023): índice de contraste a lo largo del eje frente a franjas laterales | (i) | l | `src/parcel_intel/domain/cut_signal_orthophoto.py`, `src/parcel_intel/ports/` (ventana raster), `src/parcel_intel/adapters/pnoa/`, `src/parcel_intel/application/cut_signals.py`, `src/parcel_intel/cli/main.py`, `pyproject.toml`, `docs/adr/` | H3 y una primera medición con #111 como línea base |
| H5 | Señal `serie_historica` (PNOA 1956-57, 2009, 2017…): el trazado se distinguía antes y ya no; da fecha aproximada | (i) | l | `src/parcel_intel/domain/cut_signal_history.py`, `src/parcel_intel/adapters/pnoa/`, `src/parcel_intel/application/cut_signals.py`, `docs/adr/` | H4 |
| H6 | Señal de barreras y `access=private` declaradas en OpenStreetMap | (ii) | l | `src/parcel_intel/adapters/` (proveedor nuevo), `src/parcel_intel/application/cut_signals.py`, `src/parcel_intel/domain/`, `docs/adr/`, `src/parcel_intel/sources/REGISTRY.md` | decisión del fundador (licencia ODbL y canal) |

**Estimación de las siguientes:**

- **H4:**
  - **datos:** una `GetMap` por ventana de unos 256 m del eje en zona base, entre 200 y 400 por municipio, de ~150 kB cada una: decenas de MB en `data/raw/pnoa/`, con coste 0 €;
  - **dependencias:** una librería para decodificar JPEG en el adapter (no es un proveedor nuevo; su historia comprueba si trae tipos, lección de #36);
  - **caché de PNOA:** la que el ADR 0006 §6 dejó diferida;
  - **calibración:** el índice hay que calibrarlo.

  Va segunda porque es la única que mide la condición (i) en el estado actual.
- **H5:** cuesta lo de H4 multiplicado por los vuelos usados, limitado a las muestras donde H4 apoya y a 3 o 4 vuelos. Es la señal más fuerte para fechar.
- **Aplazadas sin historia:**
  - **Cambio de cubierta.** El PNOA verificado es RGB, sin banda infrarroja verificada, y Sentinel-2 a 10 m no resuelve un camino de 3 a 5 m (`docs/vision.md`).
  - **LiDAR** (3.ª cobertura de 2024, CC BY 4.0 asumida). Su utilidad está sin demostrar: unos 5 puntos/m² no resuelven una alambrada, aunque sí un muro. Los ficheros LAZ pesan cientos de MB por hoja y necesitarían una dependencia y un adapter nuevos. Se revisa cuando la medición muestre falsos negativos de cierres con obra o falsos positivos por cultivo sobre el camino.

### Umbrales de producto a revisar con el fundador

Están razonados, no calibrados. Se ajustan contra la medición (#100), cada cambio sube la versión, y ninguno cambia la arquitectura:

- `BASE_COUNTERPARTS = {ign_red_transporte}` y `BASE_KINDS = {AUSENTE_EN_FUENTE, SOLAPE}`;
- `GAP_M = 10 m` y `MIN_LENGTH_M = 25 m`;
- los pesos `w_s` (0,6 para Catastro);
- el margen al borde de parcela, `hypot(tol(A), 5 m)`;
- tratar como `infraestructura` toda parcela ≥ 9000, sea cual sea su clase.

### Alternativas descartadas

- **Generalizar `Discrepancy` o `domain.rule.Finding`.** Un candidato agrega varias discrepancias y señales y tiene su propio tramo. Forzarlo en `Discrepancy` exigiría campos opcionales que solo valen para uno de los dos tipos (lección 0012). Se reutilizan sus piezas: `TrailRef`, `Measurement` y `CriterionRef`.
- **Un candidato por registro de discrepancia, sin trocear.** Una vía pecuaria entera ausente del IGN daría un candidato de kilómetros por un corte de 200 m, y el arnés y el visor no sabrían dónde mirar.
- **Contar la ausencia en el IGN como condición (i).** Toda discrepancia base sería un candidato.
- **Tomar como base las discrepancias frente a Catastro.** Es una señal tautológica (§1).
- **Combinar con Y o con una media.** Contradice la definición del fundador ((i) o (ii)), y una señal sin datos hundiría a las demás.
- **Que la señal de imagen fuera la primera.** Necesita una dependencia nueva, la caché de PNOA y calibrar un índice antes de dar el primer número.
- **Shapely en el dominio o tras un port para el punto en polígono.** Hay primitivas stdlib probadas y el volumen no lo pide (ADR 0025 §3 y 0030 §2).

## Consecuencias

- Las historias H1 a H3 dan, sin dependencias nuevas, un primer detector medible por #110 y #111. Las señales de imagen se suman como proveedores sin tocar la entidad ni el caso de uso.
- `domain/discrepancy.py` expone `trail_samples`. Sus resultados no cambian y el criterio sigue en la versión 1.
- La medición (#100) recibe un contrato estable, independiente de las señales. Cada resultado queda atado a una versión del método.
- Con H1 a H3 ya hay candidatos publicables: #103 puede publicar los que solo sostiene la señal de Catastro, con las condiciones del ADR 0041 (§7), sin esperar a H4. El texto público se le propone al fundador.
- `candidatos-corte` depende de que #37 haya descargado las parcelas de cada municipio y de que haya un código de Catastro verificado para él (hoy solo Colmenar, ADR 0028). Para los demás municipios, la señal sale `sin_datos`, con su motivo.
- No hay coste recurrente ni PostGIS, y ningún LLM interviene.
