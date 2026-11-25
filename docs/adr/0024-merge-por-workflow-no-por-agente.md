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
- Las PRs #30 y #47 se fusionaron sin gate. Se comprobó después que sus checks y la revisión salieron en verde (`APROBADO`).
