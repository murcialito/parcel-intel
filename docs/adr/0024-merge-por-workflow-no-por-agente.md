# ADR 0024 — El merge lo hace un workflow, nunca un agente

- Estado: aceptada
- Fecha: 2026-11-25
- Corrige: [ADR 0022](0022-backlog-en-github-agentes-en-actions-merge-y-despliegue-automaticos.md), punto "merge automático"

## Contexto

El ADR 0022 confiaba el gate de merge al auto-merge nativo de GitHub, con `main` protegida exigiendo los checks `checks` y `revision`. En un repo **privado** con plan gratuito no hay ni auto-merge ni protección de ramas (`allow_auto_merge: false`).

Al fallar `gh pr merge --auto`, el agente desarrollador fusionó directamente: las PRs #30 (historia #26) y #47 (historia #17) entraron en `main` 4-5 segundos después de abrirse, antes de que corrieran CI y revisión. Las dos pasaron CI y revisión *después*, así que no entró nada roto, pero el gate no protegió nada.

## Decisión

1. **Los agentes no pueden fusionar.** En sus herramientas quedan vetados `gh pr merge` y `gh api` (`--disallowedTools`), y sus instrucciones lo prohíben de forma explícita.
2. **`fusionar.yml` es el único camino de merge.** Se lanza al terminar CI o Revisar (`workflow_run`). Fusiona con squash solo si se cumplen todas estas condiciones sobre el **último commit** de la PR (`--match-head-commit`):
   - los checks `checks` y `revision` están en SUCCESS;
   - la PR no es borrador;
   - no tiene `veto` ni `cambios-pedidos`.
3. Fusiona con `GITHUB_TOKEN`, cuyos eventos no disparan workflows. Por eso el propio `fusionar.yml` lanza CI en `main`, el despliegue y la siguiente historia (`workflow_dispatch` sí se permite), y mueve la historia a Done en el tablero.
4. Funciona igual con el repo privado o público, sin plan de pago. Cuando el repo sea público se puede añadir además la protección de rama nativa como segunda barrera, sin cambiar este flujo.

## Consecuencias

- El gate vuelve a ser real: nada entra en `main` sin CI y revisión en verde.
- Queda una vía teórica: un agente con `contents: write` podría hacer `git push` a `main`. La cierra la protección de rama cuando el repo sea público. Mientras tanto, la mitigan las instrucciones y el veto del fundador.
## Enmienda (2026-11-26, historia #50): guardia de `curated/**`

Lo que entra en `curated/**` son aprobaciones humanas de trazados históricos. Si lo fusionara el flujo normal, un agente (el revisor) aprobaría lo que otro agente escribió, y nada propuesto por una máquina debe usarse sin aprobación humana. Se protege en dos capas:

1. **`.github/CODEOWNERS`**: `curated/** @murcialito`. Con la protección de rama «Require review from Code Owners» (paso manual del fundador, abajo) GitHub lo exige por sí mismo.
2. **Guardia en `fusionar.yml`**, que funciona aunque la protección no esté activada (en un repo privado sin plan de pago no lo está). Tras comprobar `checks` y `revision`, obtiene `gh pr view --json files,reviews,headRefOid`:
   - `.github/scripts/toca_curated.sh` recibe las rutas cambiadas por stdin y sale con 0 si alguna empieza por `curated/` (`docs/curated/x` o `curated-notas.md` no cuentan);
   - si toca `curated/`, `.github/scripts/aprobada_por_fundador.sh` exige una review `APPROVED` de `murcialito` cuyo `commit.oid` sea el `headRefOid`. Sin ella, no fusiona y lo registra en el log. Un commit nuevo invalida la aprobación anterior;
   - si no toca `curated/`, el comportamiento no cambia.
3. `fusionar.yml` añade el disparador `pull_request_review: [submitted]` para reevaluar sin intervención cuando el fundador aprueba después de que CI y Revisar hayan terminado. En ese evento rama y SHA salen de `github.event.pull_request`.

**Pasos manuales del fundador** (no bloquean el desarrollo): Settings → Branches → regla sobre `main` con «Require review from Code Owners», si el plan lo permite. Solo afecta a las PRs que tocan `curated/**`.

## Consecuencias (continuación)

- Las PRs #30 y #47 se fusionaron sin gate. Se comprobó después que sus checks y la revisión salieron en verde (`APROBADO`).
