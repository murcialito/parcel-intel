# ADR 0041 — Publicar información derivada del Catastro (corrige el §3 del ADR 0035)

- Estado: aceptada
- Fecha: 2026-11-26 (decisión del fundador en #99)
- Corrige: [ADR 0035](0035-licencias-codigo-y-datos-publicados-notice.md), §3, la exclusión de Catastro

## Contexto

El §3 del ADR 0035 dice: «Catastro (INSPIRE): solo uso interno. […] Ninguna capa derivada suya se publica hasta tener consulta jurídica». La #94 (indicios publicados) y el diseño de candidatos a corte (#99, #109) heredaron esa regla y dejaron fuera de la publicación todo lo que tuviera a Catastro como fuente.

Esa regla va más allá de lo que dicen las licencias. Se leyeron completas el 2026-11-26 y están citadas en `src/parcel_intel/sources/REGISTRY.md`.

- **Licencia INSPIRE de 2016, §1.** Autoriza «el uso público, incluido el comercial, de la información catastral que haya sido sometida a cualquier proceso previo de transformación» (art. 21 de la Ley de Propiedad Intelectual). Hay transformación cuando el resultado es una obra diferente. Lo que prohíbe es difundir la información **original** sin transformarla.
- **Licencia de descarga de 2011.** Dice lo mismo en sus cláusulas 5, 6 y 8. La cláusula 12 exige citar a la Dirección General del Catastro y la fecha de acceso.
- **Las dos licencias, además:**
  - la transformación no puede alterar el contenido ni desnaturalizar su sentido;
  - lo publicado no puede presentarse como «cartografía catastral» ni «información catastral»;
  - lo distribuido carece de fehaciencia;
  - las reclamaciones de terceros las asume quien publica.

La duda jurídica que quedó abierta en la historia 0021 era mucho más estrecha. Se trataba de saber si basta con **simplificar o filtrar la geometría de las parcelas** para que cuente como transformación. Ya entonces se anotó que sí se puede publicar una capa propia derivada.

## Decisión

1. **Se publica lo derivado que no reproduce la información original.** Por ejemplo:
   - afirmaciones y resultados sobre un trazado, como «el tramo cae dentro de parcelas que no figuran como camino»;
   - señales, candidatos, indicios, medidas y confianza;
   - capas propias cuya geometría es la del trazado (vía pecuaria, camino actual o histórico) y no la de la parcela.
2. **Condiciones de cada publicación que use Catastro:**
   1. citar la fuente, «Dirección General del Catastro», con la fecha de consulta;
   2. avisar de que no es cartografía ni información catastral, de que no es fehaciente y de que puede haber cambiado desde la consulta;
   3. no llamarlo nunca «cartografía catastral» ni «información catastral»;
   4. no alterar el sentido del dato: si Catastro clasifica una parcela como vía de comunicación, no se presenta como otra cosa.
3. **Sigue sin publicarse:**
   - la geometría de las parcelas, aunque esté simplificada o filtrada (es la duda abierta);
   - los atributos de cada parcela: uso, clase, superficie.
4. **Las referencias catastrales y los números de polígono o parcela no se publican nunca.** Lo impone el principio de no identificar fincas ni propietarios, no la licencia.
5. **Encaje con lo que ya existe:**
   - Catastro sigue marcado `solo_uso_interno` en su geometría (ADR 0028, ADR 0036).
   - La redacción para publicación (ADR 0030 §4) quita la geometría de las fuentes no redistribuibles y conserva identificador, procedencia, medidas y confianza. Lo que cambia es que esos registros redactados **sí se publican** cuando una de sus fuentes es Catastro.
   - La atribución de Catastro se añade a `NOTICE`.

## Consecuencias

- La #94 puede publicar los indicios que tienen a Catastro como contraparte, redactados según el punto 5. La #103 puede publicar candidatos apoyados solo en la señal de Catastro, sin esperar a la de ortofoto. El texto público de cada uno se le propone al fundador, como estaba previsto.
- La frase «hasta tener consulta jurídica» del ADR 0035 §3 queda limitada a la geometría de las parcelas.
- **Riesgo:** que la Dirección General del Catastro discrepe. Su propia licencia prevé un requerimiento previo con un plazo de 10 a 15 días (licencia de 2011, cláusula 26). Si llegara, se retira lo publicado dentro de ese plazo.
- El lenguaje de indicio y el aviso de no fehaciencia son también la defensa ante reclamaciones de terceros.
