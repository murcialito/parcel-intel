# Proceso de trabajo: backlog en GitHub y agentes en GitHub Actions

Decidido el 2026-11-25 ([ADR 0022](adr/0022-backlog-en-github-agentes-en-actions-merge-y-despliegue-automaticos.md)). El fundador solo interviene en el **refinamiento**, y solo cuando un agente se lo pide. Todo lo demás (código, tests unitarios, tests de aceptación, revisión, merge y despliegue) lo hacen agentes de Claude Code en GitHub Actions.

## Jerarquía

| Tipo | Etiqueta | Qué es | Quién la parte |
| --- | --- | --- | --- |
| Épica | `tipo:epica` | Un objetivo de producto (p. ej. "Mapa de trazados que deberían ser públicos") | El agente de refinamiento la parte en features |
| Feature | `tipo:feature` | Una capacidad entregable dentro de la épica | El agente de refinamiento la parte en historias |
| Historia | `tipo:historia` | Un incremento que cabe en una PR y se puede probar | Es lo que se desarrolla |

Las tres son issues del repo. La relación padre-hijo usa **sub-issues** de GitHub. Todas aparecen solas en el tablero del proyecto [Paso Común](https://github.com/users/murcialito/projects/1) (ver "Sincronización con el tablero").

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

Cualquier estado ──► estado:bloqueada ──► (se cierran sus dependencias) ──► el estado de su línea "Desbloqueo"
                                        │      ▲
                                        ▼      │
                                   cambios-pedidos
```

| Etiqueta | Significa | Quién la pone |
| --- | --- | --- |
| `estado:refinar` | El agente de refinamiento debe trabajarla | El fundador (o el agente al crear hijas) |
| `estado:necesita-fundador` | Hay preguntas para el fundador en el último comentario | Agente de refinamiento, o desarrollo/revisión si se atascan |
| `estado:diseno` | Historia grande o con decisión nueva: la diseña el arquitecto | Agente de refinamiento |
| `estado:bloqueada` | Espera a que se cierren las issues de su línea `Desbloqueo: estado:<x> cuando se cierren #a, #b` | Cualquier agente; la quita `desbloquear.yml` |
| `estado:lista` | Cumple la Definición de Lista | Agente de refinamiento o arquitecto |
| `estado:en-desarrollo` | Un agente la está programando | Agente de desarrollo |
| `estado:en-revision` | Hay PR abierta | Agente de desarrollo |
| `cambios-pedidos` (en la PR) | La revisión encontró problemas bloqueantes | Agente de revisión |
| `veto` (en la PR o la issue) | El fundador para el merge automático | El fundador |
| `pendiente-local` (en la PR) | Tiene tests `fuera_de_ci` (servicios que rechazan a GitHub, como Catastro) por pasar en local; Fusionar espera | El desarrollador; la quita quien lo pasa en local |

## Cuándo te necesito

Solo en estos casos. Siempre con un comentario en la issue que te menciona, así que GitHub te avisa (también en el móvil):

1. **Refinamiento con preguntas abiertas**: decisiones de producto, de alcance, de lenguaje público, o cualquier cosa que toque los principios (indicios, propietarios, licencias).
2. **Acción externa en nombre del proyecto**: p. ej. solicitudes de transparencia a ayuntamientos, contactar con asociaciones.
3. **Atasco**: una historia vuelve de revisión 3 veces, o un test de aceptación no se puede cumplir tal como está escrito.

No te preguntan cómo encontrar o verificar fuentes: los agentes buscan y leen en la web (`WebSearch`, `WebFetch`) con las reglas del ADR 0027.

**Para responder:** contesta en la issue con un comentario. Tu comentario vuelve a lanzar el refinamiento. No hace falta cambiar etiquetas.

**Para empezar algo nuevo:** crea una issue con `tipo:epica`, `tipo:feature` o `tipo:historia` y la etiqueta `estado:refinar`. Basta con una frase.

## Definición de Lista (DoR)

Una historia pasa a `estado:lista` solo si:

- Tiene historia ("Como… quiero… para…"), contexto y **criterios de aceptación en formato Dado / Cuando / Entonces**, numerados (CA1, CA2…).
- Cada criterio es comprobable **sin red** con fixtures grabadas, o está marcado `[integración]` y dice qué fuente real toca.
- Las fuentes que usa están verificadas en `REGISTRY.md`. Si no, la primera historia es la de verificación.
- Tiene una línea `Toca:` con las zonas del código que creará o modificará; sin ella se desarrolla sola, sin paralelo.
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
| `desarrollador` | `desarrollar.yml` | Etiqueta `estado:lista` en una historia, cada hora como cola |
| `desarrollador` | `corregir.yml` | La etiqueta `cambios-pedidos` en su PR, que pone el revisor o Fusionar si falla CI. Se lanza desde `main` por `workflow_dispatch`: con el evento de etiqueta, el workflow sale de la versión de la PR y `claude-code-action` se salta si no coincide con `main`. Si la etiqueta se puso con la PR en conflicto, el evento se pierde (GitHub no crea runs de `pull_request` en una PR con conflictos): `correcciones_pendientes.sh` la relanza tras cada CI o Revisar (Fusionar) y cada hora (cron de `desarrollar.yml`) |
| `desarrollador` | `actualizar-rama.yml` | Su PR queda en conflicto con `main` (lo detecta `fusionar.yml` tras cada merge, y la pasada diaria de `desbloquear.yml`): trae `main` a la rama con merge y vuelve a pasar CI y revisión |
| `revisor` | `revisar.yml` | PR abierta o actualizada desde una rama `claude/` |
| — | `fusionar.yml` | Termina CI o Revisar: fusiona si `checks` y `revision` están en verde sobre el último commit y no hay `veto` (ADR 0024) |
| — | `ci.yml` | Toda PR y todo push a `main` |
| Claude a demanda | `claude.yml` (del instalador de la app) | Escribes `@claude` en una issue o PR: pregunta o encargo puntual fuera del flujo |
| — | `desplegar.yml` | Push a `main` (solo si el repo es público) |

**Orden de la cola:** Priority del tablero (P0 → P1 → P2 → sin prioridad) y, dentro, la más antigua. Salta las que tienen dependencias abiertas. Solo cuenta una línea que empieza por `Depende de` (`Depende de: #84, #85`); lo escrito en prosa no cuenta. Ver `.github/scripts/elegir_historia.sh`.

**Historias en paralelo.** Se desarrollan a la vez hasta `HISTORIAS_EN_PARALELO` historias (variable de repo; ahora 2). Solo ocupan hueco las que están en `estado:en-desarrollo`. Las que están en revisión no lo ocupan, porque la revisión y el CI no necesitan agente de desarrollo, pero sus zonas `Toca:` siguen contando para el solape. La cola solo junta dos historias si las dos tienen línea `Toca:` y sus zonas no se solapan; una sin `Toca:` va sola. La elección va en serie y reclama la historia al elegirla, así que dos ejecuciones nunca cogen la misma. Fusionar solo fusiona una PR al día con `main`: si va por detrás, la actualiza con `PROJECT_TOKEN` y espera a que CI y la revisión pasen sobre la combinación real.

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

## Dependencias entre issues

Una issue que no puede avanzar hasta que se cierren otras lleva `estado:bloqueada` y una línea en el cuerpo:

```
Desbloqueo: estado:diseno cuando se cierren #18, #19
```

`desbloquear.yml` (`.github/scripts/desbloquear.sh`, sin LLM) comprueba las bloqueadas:

- tras cada merge, porque lo lanza `fusionar.yml`;
- cuando cierras una issue a mano;
- una vez al día, por si se escapa algo.

Cuando todas sus dependencias están cerradas como completadas, le pone el estado de la línea, quita `estado:bloqueada`, lo comenta y lanza el workflow del agente (`disenar.yml`, `refinar.yml` o la cola de `desarrollar.yml`). Una dependencia cerrada como "not planned" no desbloquea: la issue se queda esperando a que lo decidas tú.

En la misma pasada, `desbloquear.yml` cierra los contenedores terminados: épicas, features e historias madre con todas sus sub-issues cerradas. Si después se les añade trabajo, el refinador las reabre.

## Sincronización con el tablero

Todas las issues se reflejan en el proyecto [Paso Común](https://github.com/users/murcialito/projects/1) mediante `sincronizar-tablero.yml`. Este workflow se lanza cuando se abre, cierra, reabre o cambia de etiquetas cualquier issue, y llama a `.github/scripts/sincronizar_tablero.sh`:

| Etiqueta o estado de la issue | Columna (Status) |
| --- | --- |
| Sin estado, `estado:refinar`, `estado:diseno` o `estado:bloqueada` | Backlog |
| `estado:necesita-fundador` | **Necesita al fundador** (lo que te espera) |
| `estado:lista` | Ready |
| `estado:en-desarrollo` | In progress |
| `estado:en-revision` | In review |
| Cerrada | Done |

`talla:s`, `talla:m` y `talla:l` se copian al campo Size del proyecto (S, M, L). **Priority** la pones tú, y los agentes no la tocan. Es tu palanca sobre la cola: `desarrollar.yml` coge primero las P0, luego P1, P2 y las que no tienen prioridad, y dentro de cada grupo la más antigua.

Además:

- **Assignees**: te asigna mientras una issue tiene `estado:necesita-fundador` y te quita al salir. La vista **Me esperan** (`assignee:@me`) es tu bandeja. Los agentes no aparecen como assignee, porque un bot no se puede asignar.
- **Start date / Target date**, para la vista **Roadmap**, con fechas reales y no estimadas:
  - historia: Start es cuando entra en `estado:en-desarrollo` y Target cuando se cierra (hoy mientras sigue abierta); sin empezar, no tiene fechas;
  - feature y épica: van de la primera Start a la última Target de sus sub-issues.
  - Una pasada diaria refresca el "hoy".
- No hay iteraciones: el flujo es continuo (una historia tras otra), así que no hay sprints que planificar.

La app de Claude no puede escribir en proyectos de usuario, así que el workflow necesita el secret `PROJECT_TOKEN`: un token clásico con los permisos `repo` y `project` (mientras el repo sea privado, sin `repo` el proyecto no puede resolver las issues). Sin él, el workflow no hace nada y las etiquetas siguen mandando.

## Coste

Los agentes usan la suscripción de Claude del fundador mediante `CLAUDE_CODE_OAUTH_TOKEN`, sin API de pago aparte. GitHub Actions es gratis en repos públicos. Los límites de la suscripción marcan el ritmo: si se agotan, los workflows fallan y se reintentan en la siguiente pasada horaria.
