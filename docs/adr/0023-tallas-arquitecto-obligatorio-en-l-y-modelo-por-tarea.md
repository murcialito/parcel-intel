# ADR 0023 — Tallas de historia, arquitecto obligatorio en las grandes y modelo de Claude según la tarea

- Estado: aceptada
- Fecha: 2026-11-25
- Amplía: [ADR 0022](0022-backlog-en-github-agentes-en-actions-merge-y-despliegue-automaticos.md)

## Contexto

El ADR 0022 unía analista y arquitecto en un solo agente y usaba el mismo modelo para todo. El fundador pide (2026-11-25) dos cambios:

- que el flujo incluya un arquitecto en las tareas grandes;
- que las tareas menores usen modelos más baratos, sin renunciar a la revisión de código.

## Decisión

1. **Tres tallas por historia**: `talla:s`, `talla:m` y `talla:l`. Las pone el refinador con criterios objetivos (ver `.claude/agents/refinador.md`). Ante la duda, la mayor.
2. **Arquitecto como agente propio** (`.claude/agents/arquitecto.md`, workflow `disenar.yml`). Toda historia `talla:l`, o con ADR, pasa por `estado:diseno` antes de `estado:lista`. El arquitecto escribe la sección `## Diseño` y el ADR propuesto, y puede partir la historia.
3. **Modelo según fase y talla**, centralizado en `.github/scripts/modelo.sh` (tabla en `docs/proceso.md`):
   - el barato solo desarrolla `talla:s`;
   - el capaz diseña, desarrolla y revisa las `talla:l`;
   - todo lo demás usa el intermedio.
4. **La revisión nunca baja del intermedio.** Es la única barrera humana delegada antes del merge automático. En `talla:l` además revisa contra el diseño.
5. **Escalado automático:** si el desarrollo de una `talla:s` falla, la historia sube a `talla:m` antes del reintento.
6. **Modelos configurables** con variables de repositorio (`MODELO_BARATO`, `MODELO_INTERMEDIO`, `MODELO_CAPAZ`), para cambiar de versión sin tocar workflows.

## Consecuencias

- Una historia `talla:l` tarda una ejecución más (el diseño), pero el desarrollador ya no toma decisiones de arquitectura.
- Con la suscripción, el modelo pesa sobre los límites de uso más que sobre el dinero. El reparto concentra el modelo caro donde un error cuesta más.
- Una talla mal puesta a la baja es el riesgo principal: un cambio grande desarrollado con el modelo barato. Lo mitigan la regla "ante la duda, la mayor", la revisión con modelo intermedio y el escalado tras un fallo.
