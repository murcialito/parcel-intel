# ADR 0022 — Backlog en GitHub Issues, agentes en GitHub Actions, merge y despliegue automáticos

- Estado: aceptada
- Fecha: 2026-11-25

## Contexto

El fundador quiere dedicarse solo a refinar épicas, features e historias, y solo cuando haga falta. El resto del ciclo (código, tests unitarios, tests de aceptación, revisión y despliegue) debe ir solo. Hasta ahora el flujo de `CLAUDE.md` (analista → arquitecto → implementación → revisor → lecciones) se ejecutaba a mano en sesiones locales.

Decisiones del fundador (2026-11-25):

- Backlog en GitHub, con el proyecto `users/murcialito/projects/1` como tablero.
- Agentes en GitHub Actions con la action oficial `anthropics/claude-code-action@v1`, autenticada con la suscripción (`CLAUDE_CODE_OAUTH_TOKEN`).
- Merge y despliegue automáticos cuando todo está en verde, con veto por etiqueta.
- Despliegue en GitHub Pages con el repo público.

## Decisión

1. **Las etiquetas son la máquina de estados.** Los eventos de proyectos v2 de usuario no disparan GitHub Actions, y la app de Claude no puede escribir en proyectos de usuario. El tablero es una vista sincronizada (ver `docs/proceso.md`).
2. **Tres agentes, no cinco.**
   - `refinador`: une los roles de analista y arquitecto, porque las dos fases producen el mismo artefacto, la issue lista.
   - `desarrollador`: implementa, escribe los tests unitarios y de aceptación y anota las lecciones en la misma PR.
   - `revisor`: revisa la PR.
   Separar las lecciones en otro workflow obligaría a una segunda PR por historia.
3. **El revisor no puede "pedir cambios" formalmente.** La PR y la revisión las firma la misma app, y GitHub no deja pedir cambios en una PR propia. El veredicto se expresa como estado del check `revision` (falla si hay hallazgos bloqueantes) más la etiqueta `cambios-pedidos`, que relanza al desarrollador.
4. **Los eventos de la app sí disparan workflows.** Los cambios hechos con `GITHUB_TOKEN` no disparan otros workflows; los de una GitHub App sí. Por eso hace falta instalar la app de Claude en el repo: sus PRs disparan CI y revisión.
5. **Desarrollo en serie.** Una sola historia en desarrollo o revisión a la vez, más una pasada horaria que coge la siguiente. Así ninguna historia lista se pierde por la cancelación de la cola de concurrencia de Actions.
6. **Tests de aceptación como pytest** en `tests/acceptance/`, con la marca `acceptance`: un test por criterio Dado/Cuando/Entonces y sin red, como el resto de la suite. Cuando exista el visor, se añadirá Playwright con su propio ADR.
7. **Seguridad en repo público.** Solo disparan agentes las etiquetas (exigen permiso de triage) y los comentarios del dueño del repo. Los comentarios de terceros nunca lanzan un agente.
8. **Las historias nuevas viven en su issue.** `docs/stories/` queda como archivo de 0001–0021.

## Consecuencias

- Antes de que funcione, el fundador tiene que:
  - instalar la app de Claude en el repo y crear el secret `CLAUDE_CODE_OAUTH_TOKEN`;
  - activar "Allow auto-merge" y proteger `main` exigiendo los checks `checks` y `revision`;
  - configurar los workflows integrados del proyecto.
- El despliegue a Pages no corre mientras el repo sea privado. Hacerlo público exige antes sacar del repo y de su historial las respuestas crudas de Catastro de `tests/fixtures/`, porque su licencia prohíbe difundirlas sin transformar. Es la primera historia del backlog y necesita refinamiento del fundador.
- Riesgo: un agente fusiona código que nadie ha leído. Lo mitigan la revisión obligatoria, el contrato de capas, mypy estricto, los tests de aceptación por criterio y el veto. El fundador puede pasar a aprobar cada PR quitando el auto-merge, sin tocar nada más.
- La suscripción limita el ritmo. Si se agota, los agentes fallan y la pasada horaria reintenta.
