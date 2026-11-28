# ADR 0056 — Financiación y gobierno del dinero: asociación sin ánimo de lucro, ni un euro a particulares e infraestructura por fases

- Estado: propuesta (pendiente del fundador; ver «Pendiente del fundador»)
- Fecha: 2026-11-28
- Historia: ninguna; nace de una conversación con el fundador (2026-11-28). Amplía el ADR 0021 (coste casi cero) y el ADR 0053 (dominio, primer coste recurrente). No sustituye a #104 (coste y alojamiento de avisos con foto), que sigue decidiendo esa pieza.
- Guía práctica: [`docs/asociacion.md`](../asociacion.md)

## Contexto

Paso Común es hoy un MVP estático: GitHub Pages, ficheros pregenerados y análisis por lotes en el portátil del fundador. El único coste recurrente es el dominio (ADR 0053), que paga el fundador.

Para que el proyecto crezca más allá del MVP harán falta piezas con coste:
- un backoffice para colaboradores (revisión de tramos, gestión de casos y avisos);
- algo de infraestructura propia: al menos un VPS, una base de datos servida (PostGIS) y almacenamiento de objetos (fotos de avisos, #104; datos internos, ADR 0055);
- dinero para actividades: promoción, encuentros, reconocimiento a quien aporta.

El fundador ha fijado tres condiciones (2026-11-28):
1. El proyecto no busca ganar dinero, y el fundador no va a cobrar nada.
2. Si sobra dinero, va a promoción o a reconocer a quien aporta, por ejemplo con una cena y un premio de reconocimiento. **Nunca se da dinero a las personas que colaboran**, porque eso abre la puerta a cosas que no queremos.
3. **Ni un euro del proyecto acaba en manos de particulares.**

Además, casi todas las subvenciones y muchas donaciones exigen una entidad con CIF. Recibir dinero en una cuenta personal hace que Hacienda lo trate como renta del titular, y desde fuera es opaco.

## Decisión

### 1. El dinero entra y sale por una asociación, nunca por cuentas personales

- El vehículo es una **asociación sin ánimo de lucro** (Ley Orgánica 1/2002, del Derecho de Asociación), inscrita en el registro de la Comunidad de Madrid. Los pasos están en [`docs/asociacion.md`](../asociacion.md).
- **Fundación, descartada**: exige una dotación inicial de 30.000 € (Ley 50/2002, art. 12) y un patronato con más obligaciones.
- **Hasta que la asociación exista, no se recauda dinero.** El fundador sigue pagando el dominio como hasta ahora. Usar un anfitrión fiscal (tipo Open Collective) como puente queda pendiente del fundador.
- Lo que ya tienen las asociaciones de caminos existentes se suma, no se duplica: se las invita a ser socias o a colaborar mediante convenio. La herramienta sigue siendo técnica y neutral. **La asociación no presenta denuncias en nombre de Paso Común.** Las acciones de defensa las llevan las asociaciones que usan la herramienta, para que el principio de «indicios a verificar, nunca acusaciones» no quede comprometido.

### 2. Ni un euro a manos particulares

Es la regla central de este ADR, y se escribe también en los estatutos.

**No se permite:**
- pagar a quien colabora por colaborar (avisos, revisiones, código, trabajo de campo), ni por pieza ni por objetivos;
- recompensas en dinero o en algo equivalente al dinero: tarjetas regalo, vales, saldo, criptomonedas o material de valor que se pueda revender;
- retribuir los cargos de la junta directiva, que son gratuitos, ni al fundador;
- pagar a una empresa o a un profesional vinculado a la junta, a los socios o a colaboradores, o a sus familiares (conflicto de interés).

**Sí se permite**, siempre con factura a nombre de la asociación, aprobación de la junta y publicación en las cuentas:
- infraestructura: VPS, almacenamiento, copias de seguridad y dominio;
- servicios profesionales de terceros sin vínculo con el proyecto (gestoría, seguro, asesoría jurídica puntual);
- promoción: impresión, materiales, inscripción en jornadas;
- **reconocimiento no monetario**: un encuentro o cena anual de colaboradores y un premio de reconocimiento (diploma, placa o trofeo sin valor de reventa). También la mención pública en el sitio, solo con el consentimiento de la persona.

### 3. Transparencia e independencia

- **Cuentas públicas.** Cada año se publica en el repositorio cada ingreso y cada gasto, con su concepto y su factura. Una persona donante solo se nombra si lo consiente. Un ingreso que no se puede publicar no se acepta.
- **Independencia.** No se aceptan fondos de quien tenga interés directo en un tramo señalado: titulares de fincas afectadas, promotores, partes de un litigio sobre un camino. Ningún financiador puede influir en qué se señala ni en cómo: el método, las reglas y la revisión humana no se negocian a cambio de dinero.
- **Subvenciones.** Solo se piden las que son compatibles con los principios del proyecto: código abierto, nunca titularidad ni nombres de propietarios, indicios y no dictámenes. No se acepta ninguna que exija comprometer resultados («N denuncias», «N caminos recuperados»).

### 4. Infraestructura por fases: cada coste nuevo, solo cuando una funcionalidad lo exige

| Fase | Qué hay | Coste recurrente | Cuándo se pasa a la siguiente |
|---|---|---|---|
| 0 (hoy) | Sitio estático en GitHub Pages, análisis en local, revisión con PRs sobre `curated/` | Dominio (ADR 0053) | Cuando colaboradores sin GitHub necesiten revisar o aportar |
| 1 | Backoffice mínimo **sin servidor propio**: issues, formularios y PRs de GitHub, y el repo privado de datos (ADR 0055) | 0 € adicional | Cuando una funcionalidad necesite servidor de verdad: avisos con foto (#104), base servida o backoffice web |
| 2 | Un VPS con PostGIS y el backoffice web, almacenamiento de objetos para fotos y copias de seguridad | Ver orden de magnitud | Cuando el uso lo pida (más municipios, más colaboradores) |

Orden de magnitud de la fase 2, **no verificado**. Son cifras de memoria del 2026-11-28 para dimensionar: no entran en ninguna decisión hasta que el ADR de cada pieza las contraste con la página primaria del proveedor y su fecha de consulta, como exige #104 (CA8).

| Concepto | Orden de magnitud (no verificado) |
|---|---|
| VPS pequeño en un proveedor europeo | 5–20 €/mes |
| Almacenamiento de objetos (fotos, al principio) | unos 5 €/mes |
| Copias de seguridad | 2–5 €/mes |
| Dominio | unos 14 €/año más IVA (ADR 0053) |
| **Total** | **unos 300–600 €/año** |

Siguen en vigor las reglas de CLAUDE.md: cada componente con coste recurrente tiene su propio ADR con estimación verificada; ningún LLM en consultas de usuario; ningún dato de titularidad. La fase 2 no se diseña por adelantado: entra cuando una historia la necesite.

## Pendiente del fundador

1. **Reembolso de gastos justificados** (por ejemplo, el desplazamiento de un trabajo de campo, contra ticket o factura). No es lucro, pero es dinero que pasa por manos de una persona. Opciones: (a) prohibido: la asociación paga directamente al proveedor o no se hace; (b) permitido solo contra justificante, con aprobación de la junta y publicado. Mientras no se decida, se aplica (a).
2. **Puente hasta que exista la asociación**: no recaudar nada (por defecto) o usar un anfitrión fiscal tipo Open Collective, comprobando antes cuál sigue activo en Europa.
3. **Quiénes son los socios fundadores** (mínimo tres) y si se invita a las asociaciones existentes a formar parte de la junta.
4. **Nombre de la asociación**, sujeto a que el registro lo admita (por ejemplo, «Asociación Paso Común»).

## Consecuencias

- La regla «ni un euro a particulares» y la de independencia se copian en los estatutos (ver la lista de cláusulas en `docs/asociacion.md`). Si los estatutos no las recogen, este ADR no se da por aplicado.
- Las cuentas se publican en el repositorio. Su formato se decide cuando haya un primer movimiento.
- La declaración de utilidad pública (LO 1/2002, art. 32) se podrá pedir tras dos años de actividad. Es la que permite que las donaciones desgraven (Ley 49/2002), y esa ley exige cargos gratuitos, que es lo que ya decide este ADR.
- Ningún agente da de alta cuentas, firma, paga ni presenta nada ante el registro o Hacienda. Todo eso lo hacen el fundador y la junta.
- Alternativas descartadas: (a) cuenta personal del fundador, que es opaca y le imputa el dinero como renta; (b) fundación, por la dotación; (c) recompensar a colaboradores con dinero o con algo equivalente, por los incentivos que crea (avisos falsos o exagerados, competencia por puntos) y por la decisión expresa del fundador; (d) montar el VPS ya «por si acaso», que añade coste sin funcionalidad que lo pida.
