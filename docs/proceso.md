# Proceso de trabajo: backlog en GitHub y agentes en GitHub Actions

Decidido el 2026-11-25 ([ADR 0022](adr/0022-backlog-en-github-agentes-en-actions-merge-y-despliegue-automaticos.md)). El fundador solo interviene en el **refinamiento**, y solo cuando un agente se lo pide. Todo lo demás (código, tests unitarios, tests de aceptación, revisión, merge y despliegue) lo hacen agentes de Claude Code en GitHub Actions.

## Jerarquía

| Tipo | Etiqueta | Qué es | Quién la parte |
| --- | --- | --- | --- |
| Épica | `tipo:epica` | Un objetivo de producto (p. ej. "Mapa de trazados que deberían ser públicos") | El agente de refinamiento la parte en features |
| Feature | `tipo:feature` | Una capacidad entregable dentro de la épica | El agente de refinamiento la parte en historias |
| Historia | `tipo:historia` | Un incremento que cabe en una PR y se puede probar | Es lo que se desarrolla |

Las tres son issues del repo. La relación padre-hijo usa **sub-issues** de GitHub. Todas aparecen solas en el tablero del proyecto [Parcela Intel](https://github.com/users/murcialito/projects/1) (ver "Sincronización con el tablero").

El número de historia es el número de la issue: "Historia #12". Las historias 0001–0021 de `docs/stories/` se quedan como archivo histórico; las nuevas viven solo en su issue.

## Estados (etiquetas)

Las etiquetas son la fuente de verdad: los workflows reaccionan a ellas. La columna del tablero las refleja (ver "Sincronización con el tablero").

```
estado:refinar ──► estado:necesita-fundador ──► (respondes) ──► estado:refinar
      │
      ├─ talla:s / talla:m ─────────────────────────┐
      └─ talla:l o ADR ──► estado:diseno ──► (arquitecto)
                                                    ▼
                                              estado:lista
                                                    │
                                                    ▼
          estado:en-desarrollo ──► estado:en-revision ──► (merge) ──► issue cerrada
                                        │      ▲
                                        ▼      │
                                   cambios-pedidos
```

| Etiqueta | Significa | Quién la pone |
| --- | --- | --- |
| `estado:refinar` | El agente de refinamiento debe trabajarla | El fundador (o el agente al crear hijas) |
| `estado:necesita-fundador` | Hay preguntas para el fundador en el último comentario | Agente de refinamiento, o desarrollo/revisión si se atascan |
| `estado:diseno` | Historia grande o con decisión nueva: la diseña el arquitecto | Agente de refinamiento |
| `estado:lista` | Cumple la Definición de Lista | Agente de refinamiento o arquitecto |
| `estado:en-desarrollo` | Un agente la está programando | Agente de desarrollo |
| `estado:en-revision` | Hay PR abierta | Agente de desarrollo |
| `cambios-pedidos` (en la PR) | La revisión encontró problemas bloqueantes | Agente de revisión |
| `veto` (en la PR o la issue) | El fundador para el merge automático | El fundador |

## Cuándo te necesito

Solo en estos casos. Siempre con un comentario en la issue que te menciona, así que GitHub te avisa (también en el móvil):

1. **Refinamiento con preguntas abiertas**: decisiones de producto, de alcance, de lenguaje público, o cualquier cosa que toque los principios (indicios, propietarios, licencias).
2. **Acción externa en nombre del proyecto**: p. ej. solicitudes de transparencia a ayuntamientos, contactar con asociaciones.
3. **Atasco**: una historia vuelve de revisión 3 veces, o un test de aceptación no se puede cumplir tal como está escrito.

**Para responder:** contesta en la issue con un comentario. Tu comentario vuelve a lanzar el refinamiento. No hace falta cambiar etiquetas.

**Para empezar algo nuevo:** crea una issue con `tipo:epica`, `tipo:feature` o `tipo:historia` y la etiqueta `estado:refinar`. Basta con una frase.

## Definición de Lista (DoR)

Una historia pasa a `estado:lista` solo si:

- Tiene historia ("Como… quiero… para…"), contexto y **criterios de aceptación en formato Dado / Cuando / Entonces**, numerados (CA1, CA2…).
- Cada criterio es comprobable **sin red** con fixtures grabadas, o está marcado `[integración]` y dice qué fuente real toca.
- Las fuentes que usa están verificadas en `REGISTRY.md`. Si no, la primera historia es la de verificación.
- Tiene talla (`talla:s`, `talla:m` o `talla:l`). Las `talla:l`, y cualquiera con decisión de arquitectura o proveedor nuevo, han pasado por el arquitecto: la sección `## Diseño` y el ADR propuesto están en la issue.
- No quedan preguntas abiertas para el fundador.
- Cabe en una PR revisable (orientativo: menos de ~600 líneas de producción).
- Respeta los principios: indicios y no ilegalidades, ningún dato de propietarios, aprobación humana de reglas propuestas por IA, coste casi cero, licencia de publicación.

## Definición de Hecho (DoD)

La PR de una historia la fusiona el workflow `fusionar.yml` (nunca un agente) cuando:

- CI en verde: `ruff`, `mypy`, `lint-imports`, `pytest` (unitarios) y `pytest -m acceptance`.
- Hay **un test de aceptación por criterio** en `tests/acceptance/test_historia_<n>.py`, con el texto del criterio en el docstring.
- La revisión del agente revisor termina en `APROBADO`.
- Si hubo lección, está en `docs/lessons/LESSONS.md` dentro de la misma PR. Si hubo decisión, el ADR también.
- La PR no tiene la etiqueta `veto`.

El despliegue a GitHub Pages ocurre solo al fusionar en `main`.

## Agentes

Definidos en `.claude/agents/` y lanzados por los workflows de `.github/workflows/`:

| Agente | Workflow | Disparo |
| --- | --- | --- |
| `refinador` (analista) | `refinar.yml` | Etiqueta `estado:refinar`, o un comentario tuyo en una issue `estado:necesita-fundador` |
| `arquitecto` | `disenar.yml` | Etiqueta `estado:diseno` |
| `desarrollador` | `desarrollar.yml` | Etiqueta `estado:lista` en una historia, cada hora como cola, o la etiqueta `cambios-pedidos` en su PR |
| `revisor` | `revisar.yml` | PR abierta o actualizada desde una rama `claude/` |
| — | `fusionar.yml` | Termina CI o Revisar: fusiona si `checks` y `revision` están en verde sobre el último commit y no hay `veto` (ADR 0024) |
| — | `ci.yml` | Toda PR y todo push a `main` |
| Claude a demanda | `claude.yml` (del instalador de la app) | Escribes `@claude` en una issue o PR: pregunta o encargo puntual fuera del flujo |
| — | `desplegar.yml` | Push a `main` (solo si el repo es público) |

**Una historia a la vez.** El desarrollo va en serie para evitar conflictos entre PRs: si ya hay una historia `estado:en-desarrollo` o `estado:en-revision`, la siguiente `estado:lista` espera a la pasada horaria.

## Talla, arquitecto y modelos por tarea

El refinador pone una talla a cada historia. La talla decide si pasa por el arquitecto y qué modelo trabaja en cada fase (`.github/scripts/modelo.sh`):

| Fase | `talla:s` | `talla:m` | `talla:l` |
| --- | --- | --- | --- |
| Refinamiento | Intermedio | Intermedio | Intermedio |
| Diseño (arquitecto) | — | — | **Capaz** |
| Desarrollo y corrección | **Barato** | Intermedio | Capaz |
| Revisión | Intermedio | Intermedio | Capaz, y revisa también contra el diseño y el ADR |

Por defecto: barato = `claude-haiku-5-5`, intermedio = `claude-sonnet-5-5`, capaz = `claude-opus-5-5`. Se cambian sin tocar código con las variables de repositorio `MODELO_BARATO`, `MODELO_INTERMEDIO` y `MODELO_CAPAZ` (Settings → Secrets and variables → Actions → Variables).

La revisión nunca usa el modelo barato: es la última barrera antes del merge automático. Si el desarrollo de una `talla:s` falla, el reintento sube sola a `talla:m`.

## Sincronización con el tablero

Todas las issues se reflejan en el proyecto [Parcela Intel](https://github.com/users/murcialito/projects/1) mediante `sincronizar-tablero.yml`. Este workflow se lanza cuando se abre, cierra, reabre o cambia de etiquetas cualquier issue, y llama a `.github/scripts/sincronizar_tablero.sh`:

| Etiqueta o estado de la issue | Columna (Status) |
| --- | --- |
| Sin estado, `estado:refinar` o `estado:diseno` | Backlog |
| `estado:necesita-fundador` | **Necesita al fundador** (lo que te espera) |
| `estado:lista` | Ready |
| `estado:en-desarrollo` | In progress |
| `estado:en-revision` | In review |
| Cerrada | Done |

`talla:s`, `talla:m` y `talla:l` se copian al campo Size del proyecto (S, M, L). Priority lo pones tú si quieres: los agentes no lo tocan.

La app de Claude no puede escribir en proyectos de usuario, así que el workflow necesita el secret `PROJECT_TOKEN`: un token clásico con el permiso `project`. Sin él, el workflow no hace nada y las etiquetas siguen mandando.

## Coste

Los agentes usan la suscripción de Claude del fundador mediante `CLAUDE_CODE_OAUTH_TOKEN`, sin API de pago aparte. GitHub Actions es gratis en repos públicos. Los límites de la suscripción marcan el ritmo: si se agotan, los workflows fallan y se reintentan en la siguiente pasada horaria.
