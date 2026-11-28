# ADR 0058 — Privacidad y moderación de los avisos con foto: sin metadatos, ubicación declarada, contacto opcional, tapado manual y nada publicado sin aprobación humana

- Estado: propuesta (pendiente de validación del fundador: ver «Preguntas al fundador»)
- Fecha: 2026-11-27
- Historias: #102 (feature #97, épica #7). Relacionado con ADR 0021 (coste casi cero), 0040 (purga del historial), 0047 (revisión humana en `curated/`) y la historia #16 (texto público validado).
- Numeración: el diseño de la issue #102 lo llamaba «0052»; ese número y los siguientes hasta el 0057 ya estaban ocupados al crearlo (2026-11-28), así que es el 0058. «El ADR de privacidad de #102» = este ADR.

## Contexto

Los avisos ciudadanos con foto (épica #7) son la primera funcionalidad que recibe y guarda datos de terceros: la foto (que puede llevar EXIF con GPS, hora y dispositivo, y mostrar caras, matrículas o carteles), la ubicación del aviso y, si se pide, un contacto. El fundador pidió el 2026-11-26 analizar EXIF con GPS, caras y matrículas, contacto mínimo, plazo de conservación y moderación humana antes de publicar, y que un aviso confirme o desmienta un indicio, nunca «denuncie». Este ADR fija la política de privacidad y moderación. No elige backend, almacenamiento ni coste: eso es la feature #98 (historia #104), que debe cumplir las restricciones de aquí.

## Decisión

Minimizar en origen: se recibe lo justo para que un moderador pueda decidir, se publica aún menos y nada identifica a la persona que envía el aviso, a terceros ni a un propietario. Las secciones siguientes desarrollan cada punto.

## Metadatos de la foto

1. **Se descartan siempre todos los metadatos** de la imagen (EXIF, XMP, IPTC, perfiles con identificadores, comentarios). Como mínimo, y sin excepción: **GPS** (todas las etiquetas GPS), **fecha y hora** (DateTimeOriginal, DateTimeDigitized, DateTime, OffsetTime), **marca, modelo y número de serie del dispositivo** (Make, Model, BodySerialNumber, LensSerialNumber, Software) y la **miniatura incrustada** (que puede conservar la imagen original sin recortar ni tapar).
2. El descarte se hace **recodificando la imagen** (decodificar los píxeles y volver a codificar), no borrando etiquetas una a una. La orientación se aplica a los píxeles antes de descartar la etiqueta.
3. Se descarta **lo antes posible**: en el navegador antes de enviar, si la opción de recepción lo permite, y otra vez al recibir. **El original con metadatos no se guarda nunca**, ni siquiera de forma temporal más allá del procesamiento.
4. **La ubicación del aviso la declara la persona, no sale de la foto**: elige en el visor un indicio o tramo publicado concreto (por su identificador público) y, opcionalmente, marca un punto sobre el mapa a lo largo de ese tramo. Nunca se lee el GPS de la foto, tampoco «para ayudar».
5. La **fecha de la visita** la declara la persona y se publica solo con precisión de mes (`{mes_anyo}`). El punto marcado sirve al moderador y no se publica: lo publicado se refiere al tramo.

## Personas y matrículas

1. Una cara, una matrícula o un cartel con nombre de finca o de persona visibles se **tapan con un rectángulo opaco** (no desenfoque, que puede revertirse) en la copia que se publica. Si lo identificable es el motivo de la foto (una persona, un vehículo) o taparlo deja la foto sin valor, **se rechaza**.
2. Lo aplica **el moderador humano**, a mano, antes de aprobar. El aviso no se publica hasta que el tapado está hecho y revisado.
3. **Sin reconocimiento automático**: ni LLM ni detector de caras o matrículas en la consulta del usuario ni en la recepción. No se trata ningún dato biométrico (RGPD art. 9.1). Un detector fuera de línea que solo avise al moderador necesitaría un ADR propio y no le quitaría la última palabra.
4. Las matrículas son dato personal si permiten llegar al titular (AEPD, pregunta frecuente FAQ-0002); se tratan igual que las caras.

## Contacto

1. **El contacto es opcional**: el aviso se puede enviar sin dar ninguno. Si se da, solo **un correo electrónico**; nada de nombre, teléfono, DNI ni dirección.
2. **Finalidad única**: que el moderador pueda pedir una aclaración sobre ese aviso y comunicar si se publica, se rechaza o se retira. No se usa para nada más (ni boletines ni estadísticas).
3. **Lo ven solo los moderadores** designados por el fundador.
4. **Nunca se publica**: no aparece en el visor, en `site/`, en el dossier ni en el repositorio git. Un aviso publicado no lleva autoría personal: figura como «aviso ciudadano».
5. Al enviar, la persona recibe un **código de aviso** aleatorio (no derivado de su contacto), que le permite pedir el borrado sin haber dado correo.

## Conservación y borrado

| Dato | Plazo máximo |
| --- | --- |
| Foto sin moderar | 60 días desde su recepción; después se borra sin publicar |
| Foto rechazada | se borra en 7 días desde la decisión; solo queda un registro sin datos personales (código, tramo, fecha de decisión, motivo de la lista) |
| Foto publicada (copia reducida y tapada) | mientras el tramo siga publicado y como máximo 3 años desde la visita; se retira antes si el tramo deja de publicarse |
| Original de una foto publicada | no se conserva: se borra al publicar la copia |
| Punto marcado sobre el mapa | se borra al decidir el aviso |
| Contacto | 30 días desde la decisión del aviso (o desde su caducidad sin moderar), y como máximo 90 días desde la recepción |

**Borrado a petición del autor**: con el código de aviso o desde el correo dado, sin más justificación (RGPD art. 17). Se atiende en un plazo máximo de un mes (RGPD art. 12.3): se borran foto, punto y contacto, y la copia publicada sale en la siguiente publicación del sitio. El almacenamiento que elija #104 tiene que permitir ese borrado efectivo; por eso ni fotos ni contacto viven en el historial de git (borrar de git exige purgarlo, ADR 0040).

## Moderación

1. **Nada se publica sin aprobación humana**. La aprueba un moderador designado por el fundador. Ningún agente ni proceso automático aprueba, rechaza ni tapa.
2. Lista de comprobación, que debe cumplirse entera para aprobar:
   - [ ] La foto no tiene metadatos (comprobado en la copia que se publica).
   - [ ] No se nombra ni se puede identificar a ningún propietario, poseedor o persona (ni en la foto, ni en el texto libre, ni en carteles).
   - [ ] No hay lenguaje de acusación: el texto es una de las plantillas; no se publica texto libre de la persona.
   - [ ] No hay caras ni matrículas visibles: tapadas con rectángulo opaco, o se rechaza.
   - [ ] No aparece ninguna referencia catastral de finca ni dato de titularidad.
   - [ ] La foto se corresponde con el tramo declarado y la fecha de visita es verosímil.
   - [ ] No muestra interiores de viviendas, menores ni situaciones privadas.
3. **Lo rechazado no se publica**: se borra en 7 días (ver «Conservación y borrado»), queda el registro sin datos personales y, si hay contacto, se avisa a la persona con el motivo de la lista.
4. Un aviso aprobado **no cambia el estado del indicio ni de la revisión de candidatos** (ADR 0047): se muestra junto a él como información adicional.
5. El registro de decisiones (código, tramo, estado, motivo, fecha; sin foto ni contacto) puede vivir en `curated/` bajo su guardia, como la revisión de candidatos.

## Lenguaje del aviso

Plantillas públicas, únicas formas en que se publica un aviso. **Pendientes de validación del fundador**: al validarlas se protegen con un hash de su forma canónica junto a la marca de validación, como los textos de #16 (`domain/public_card.py`).

- **Confirma**: «Aviso ciudadano ({mes_anyo}): quien lo envía indica que en su visita no se podía pasar por este tramo. Es un indicio más que hay que verificar; no es un dictamen.»
- **Desmiente**: «Aviso ciudadano ({mes_anyo}): quien lo envía indica que en su visita el camino se podía recorrer por este tramo. El indicio puede no corresponder a un corte; hay que verificarlo.»
- **No concluyente**: «Aviso ciudadano ({mes_anyo}): la visita no permitió saber si se puede pasar por este tramo. Hace falta verificarlo sobre el terreno.»

Ninguna lleva palabras vetadas de `public_card.BANNED_WORDS` ni «denuncia». El único hueco es `{mes_anyo}`.

## Base legal

Fuentes primarias consultadas el 2026-11-27 (por el arquitecto) y releídas el 2026-11-28 (al escribir este ADR):

- Reglamento (UE) 2016/679 (RGPD), en el BOE: https://www.boe.es/buscar/doc.php?id=DOUE-L-2016-80807 (releído el 2026-11-28 en su versión XML del BOE, `https://www.boe.es/buscar/xml.php?id=DOUE-L-2016-80807`; las citas literales de los art. 2.2.c, 4.1 y 30.5 se han cotejado con ese texto).
- Ley Orgánica 3/2018 (LOPDGDD), texto consolidado (última actualización 27/12/2025): https://www.boe.es/buscar/act.php?id=BOE-A-2018-16673 (releída el 2026-11-28: art. 7.1 y art. 11.2).
- AEPD, «¿Se considera la matrícula de un coche dato personal?»: https://www.aepd.es/preguntas-frecuentes/0-conceptos-basicos/FAQ-0002-sobre-la-matricula-de-un-coche (leída por el arquitecto el 2026-11-27; el 2026-11-28 respondió `503`, así que lo que se dice de ella aquí es **paráfrasis**, no cita literal).

Lo que se aplica:

1. **Son datos personales** (RGPD art. 4.1: «toda información sobre una persona física identificada o identificable»): el correo, la foto con personas o matrículas, el punto y la fecha de la visita.
2. **No se aplica la exclusión doméstica** (art. 2.2.c, actividades «exclusivamente personales o domésticas»): se publica para cualquiera.
3. **Minimización y limitación del plazo** (art. 5.1.c y 5.1.e): justifican descartar metadatos, contacto opcional y los plazos de «Conservación y borrado».
4. **Base jurídica**: consentimiento de quien envía para sus propios datos (art. 6.1.a); a los terceros que aparecen por accidente se evita tratarlos, tapándolos o rechazando la foto. Si quedara algún dato de tercero, la base sería el interés legítimo (art. 6.1.f), que exige ponderación (pregunta al fundador).
5. **Protección de datos desde el diseño y por defecto** (art. 25).
6. **Supresión** (art. 17) y plazo de respuesta de un mes (art. 12.3).
7. **Información por capas** (LOPDGDD art. 11): junto al formulario, como mínimo la identidad del responsable, la finalidad y cómo ejercer los derechos de los art. 15 a 22 del RGPD, con enlace a la información completa.
8. **Menores** (LOPDGDD art. 7): el consentimiento propio vale desde los 14 años; el formulario pide declararlo.
9. **Registro de actividades** (art. 30): la excepción del art. 30.5 para organizaciones de menos de 250 personas no cubre tratamientos que no sean ocasionales; recibir avisos lo sería. Se recomienda llevar el registro.
10. No hay datos biométricos (art. 9.1): no hay reconocimiento automático.

No se ha consultado asesoría jurídica ni la guía de la AEPD sobre publicación de imágenes de terceros en internet; EUR-Lex en HTML no devolvió texto. Un canal no leído no equivale a «no hay». Este ADR no es un dictamen jurídico.

## Preguntas al fundador

1. **Responsable del tratamiento**: ¿quién figura (el fundador como persona física, una asociación, otro)? Recomendación: decidirlo antes de #108; la información por capas no se puede publicar sin él.
2. **Licencia de las fotos publicadas**: ¿cesión CC0, CC BY 4.0 con autoría «aviso ciudadano», u otra? Recomendación: CC0 o cesión a Paso Común para publicar bajo la licencia de datos del proyecto (ADR 0035) sin nombrar a quien la envía.
3. **Moderadores**: ¿solo el fundador o personas designadas? Recomendación: lista de moderadores escrita en el repositorio, sin datos de contacto.
4. **Plazos**: ¿se aceptan 60 días sin moderar, 7 tras rechazo, 3 años publicadas y 30/90 días de contacto? Recomendación: sí.
5. **Interés legítimo y evaluación de impacto**: ¿se pide una revisión jurídica externa (gratuita, p. ej. de una asociación) antes de abrir los avisos? Recomendación: sí, antes de publicar el primer aviso.
6. **Plantillas**: validar los tres textos de «Lenguaje del aviso». Recomendación: validarlos tal cual; están escritos con el mismo criterio que los textos de #16.

Mientras haya preguntas sin responder, este ADR queda en `propuesta` y la feature #108 no se diseña: su refinador pregunta lo que siga abierto.

## Restricciones para las historias del flujo de avisos

- R1. El original con metadatos no se guarda; los metadatos se descartan recodificando, en origen y al recibir.
- R2. La ubicación es un tramo publicado (identificador público) y un punto opcional declarados por la persona; nunca se lee el GPS de la foto.
- R3. Nada se publica sin aprobación humana; la aprobación es una entrada humana que ningún agente puede escribir (guardia de `curated/**`, como ADR 0047).
- R4. Ni fotos (tampoco la copia publicada) ni contacto en el repositorio git, porque borrar de git exige purgar el historial (ADR 0040); se publica solo la copia aprobada, tapada y reducida, desde el almacenamiento que decida #104, que debe permitir el borrado efectivo.
- R5. El contacto es opcional, solo correo, solo para moderadores y nunca sale en ninguna vista ni fichero publicado.
- R6. Ninguna foto ni contacto se envía a un LLM (DeepSeek incluido) ni a ningún tercero distinto del proveedor que elija #104; ningún LLM interviene en la recepción ni en la consulta.
- R7. Los plazos de «Conservación y borrado» se cumplen con un proceso por lotes verificable, y hay borrado a petición con el código de aviso.
- R8. El texto público del aviso es una de las tres plantillas validadas, protegidas por hash; nunca texto libre.
- R9. Un aviso no cambia el estado de un indicio ni de un candidato.
- R10. Ningún dato de titularidad ni referencia catastral de finca entra con el aviso ni sale con él.

## Consecuencias

- #104 compara sus opciones contra R1–R10 y dice cuál incumple cada una (su CA7).
- #108 no se refina hasta que este ADR esté aceptado o sus preguntas respondidas.
- Las restricciones encarecen la moderación (tapado manual por aviso): #104 lo estima en su CA4.
- `docs/vision.md` enlaza este ADR desde la línea de avisos con foto.
