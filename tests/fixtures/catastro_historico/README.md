# Fixtures sintéticas de Catastro a una fecha (historia #209)

Todo lo de esta carpeta es **sintético**: inventado a mano, con el formato que se supone para una respuesta WFS con fechas de alta y baja (ADR 0040). **No hay ninguna respuesta real de Catastro**, ni geometría real, ni referencias catastrales ni titulares reales.

- Las referencias usan provincia `99` y hoja `ZZ`, que no existen.
- Las fechas y los atributos son inventados.
- No hay geometría.
- El formato (`FECHAALTA`/`FECHABAJA` en `AAAAMMDD`) es una **suposición** hasta que la historia #236 lo verifique en local.

Las respuestas reales, si se piden, se quedan en `data/` y no se versionan.
