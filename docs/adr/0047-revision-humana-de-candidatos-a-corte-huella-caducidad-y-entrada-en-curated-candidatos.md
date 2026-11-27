# ADR 0047 — Revisión humana de candidatos a corte: huella del candidato, caducidad y entrada en curated/candidatos

Estado: aceptado
Fecha: 2026-11-27
Historias: #168 (feature #103)

## Contexto

El fundador decidió en #103 (2026-11-27) que ningún candidato a corte se publica sin que una persona lo
haya revisado con sus imágenes de comparación: con dos casos de validación en el ámbito, la medición de
#111 no basta para fijar un umbral. La revisión debe seguir el mecanismo de los trazados históricos
(ADR 0043): estados propuesto/aprobado/rechazado, `reviewed_by`, `reviewed_at`, nota y aprobaciones que
caducan si cambia lo que se vio.

Los candidatos (#128, ADR 0039) viven en `data/derived/candidatos/interno/`, fuera de git, porque derivan
de Catastro. Se regeneran con `candidatos-corte`. Su `candidate_id` es el sha256 (16 hex) del método y
versión, municipio, fuente y trazado A, y tramo a 0,01 m. El manifiesto de imágenes de #122 (ADR 0042)
indexa sus tramos por el `properties.id` del fichero de entrada.

## Decisión

1. **Entrada humana en git**: `curated/candidatos/<ine>/revision.json`, con formato cerrado
   `{"municipio", "revisiones": [{candidate_id, review, reviewed_by?, reviewed_at?, candidate_sha256?,
   review_note?}]}`. `review` vale `propuesto`, `aprobado` o `rechazado`. Un candidato sin entrada está
   `propuesto`. La revisión se hace editando el fichero en una PR. No hay comando que apruebe. Al estar
   bajo `curated/**`, la PR necesita la aprobación del fundador (CODEOWNERS más la guardia de
   `fusionar.yml`, #50). Ningún agente marca `aprobado` ni `rechazado`.
2. **Reglas de la revisión**, las de ADR 0043:
   - `aprobado` exige `reviewed_by` (usuario de GitHub), `reviewed_at` con zona horaria y
     `candidate_sha256`.
   - `rechazado` exige `reviewed_by`, `reviewed_at` y `review_note`.
   - `propuesto` no admite `reviewed_by`, `reviewed_at` ni `candidate_sha256`.
   - La nota tiene como mucho 500 caracteres y no admite referencias catastrales, localizadores de
     parcela ni palabras vetadas (#16).
   - El fichero se rechaza entero ante cualquier clave o valor fuera de lo declarado. Ningún mensaje
     repite el valor rechazado.
3. **Huella del candidato** (`candidate_fingerprint`, 64 hex): cubre lo que el `candidate_id` no cubre y
   que la persona revisora juzga o que acabará en la ficha pública (#169). Es el sha256 de
   `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)` en UTF-8, con:
   - `"candidato"`: `candidate_id`;
   - `"metodo"`: `[method.identifier, method.version]`;
   - `"municipio"`: `municipality_code`;
   - `"sujeto"`: `[subject.source.kind, subject.trail_id, subject.source.data_date ISO o null]`;
   - `"tramo"`: `stretch_key(stretch)` (la misma clave que el id, a 0,01 m, con `+ 0.0` contra `-0.0`);
   - `"condiciones"`: `list(conditions)`;
   - `"senales"`: `[[s.signal.identifier, s.signal.version, s.signal.condition, round(s.support_fraction, 3) + 0.0,
     round(s.no_data_fraction, 3) + 0.0] for s in signals]`, ordenadas por identificador;
   - `"confianza"`: `round(confidence, 3) + 0.0`;
   - `"evidencia"`: `[[m.name, round(m.value, 3) + 0.0, m.unit] for m in evidence]`, en su orden.

   **Excluye** la procedencia (fechas y URLs de consulta) y los `discrepancy_ids`. Volver a consultar
   Catastro con el mismo resultado, o regenerar las discrepancias base sin que cambie el candidato, no
   hace caducar la aprobación.
4. **Caducada frente a huérfana.** Si cambia el tramo, el método o su versión, cambia el `candidate_id`:
   la revisión antigua queda **huérfana** y el candidato nuevo, `propuesto`. Si el id se mantiene pero
   cambia la huella (otra fracción de apoyo, otra confianza, otra evidencia), la aprobación queda
   **caducada**. Las dos cosas hacen salir con 1 al comando de listado y bloquearán la publicación (#170,
   con `check_candidate_approvals_current`). Se corrigen en la misma PR que las detecta: se vuelve a
   `propuesto` o se revisa de nuevo con la huella actual. Un `rechazado` no caduca: no publicarlo es el
   lado seguro.
5. **Imágenes**: el fichero interno de candidatos se pasa tal cual como `--tramos` a
   `imagenes-comparacion`, cuyo lector toma el `id` de la feature si falta `properties.id`. Así el id del
   manifiesto es el `candidate_id` sin mapeo. El listado informa de la disponibilidad de imágenes por
   candidato, pero no exige imágenes para aprobar. Publicar sin imágenes lo decide #172.
6. **Capas**: la revisión es dominio puro (`domain/candidate_review.py`). La leen dos ports nuevos
   (`CandidateReviewSource` y `ComparisonAvailabilitySource`), con adapters en
   `adapters/curated_candidates/` y `adapters/comparison_files/`, y el caso de uso
   `ListCandidateReviewsUseCase`, que no escribe nada. El patrón de usuario de GitHub pasa a
   `domain/human_review.py`, común a digitalización, georreferenciación y candidatos.

### Umbrales y decisiones de producto a revisar con el fundador

No bloquean; cambiarlos solo exige tocar este ADR y sus tests.

- La huella excluye la fecha de consulta de Catastro, aunque la ficha de #169 la muestra: un cambio de
  fecha sin cambio de resultado no obliga a revisar de nuevo.
- Un `rechazado` no caduca.
- La nota tiene un tope de 500 caracteres.
- Aprobar no exige tener imágenes de comparación.

### Detalles de la implementación (#168)

- `revision-candidatos --municipio` no valida el código en `argparse` (a diferencia de otros comandos):
  un código que no cumple `^[0-9]{5}$` falla solo ese municipio (CA8). En esa línea de fallo el código
  no se repite (`municipio (no válido): fallo: …`), por la misma razón que los mensajes del fichero de
  revisión no repiten valores.
- En `rechazado`, un `candidate_sha256` presente debe tener la forma de 64 hex, aunque no se compare con
  la huella.
- Un `null` en una clave opcional cuenta como ausente, igual que en `trazados.geojson` (ADR 0043).

## Consecuencias

- `revision.json` es público (repo público). Solo lleva ids opacos, huellas, usuarios de GitHub,
  fechas y notas filtradas. No revela geometría ni datos de Catastro. Cuántos candidatos hay y cuántos
  se rechazan sí queda a la vista.
- La comprobación de vigencia solo puede ejecutarse donde existe el fichero interno de candidatos (en
  local; Catastro rechaza a GitHub). En CI el comando informa `sin candidatos`. #170 vuelve a
  comprobarlo al publicar.
- Cualquier cambio del método que suba `CUT_METHOD.version` deja huérfanas todas las revisiones. Es
  intencionado: con otro método, lo revisado ya no es lo mismo.
- Si la ficha de #169 empieza a usar un campo del candidato que no está en la huella, ese campo debe
  entrar en la huella, y eso invalida las aprobaciones existentes.
