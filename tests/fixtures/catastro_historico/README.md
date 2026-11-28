# Fixtures sintéticas de Catastro a una fecha (historias #209 y #236)

Todo lo de esta carpeta es **sintético**: inventado a mano (ADR 0040). **No hay ninguna respuesta real de Catastro**, ni geometría real, ni referencias catastrales ni titulares reales.

- Las referencias usan provincia `99` y hoja `ZZ`, que no existen.
- Las fechas y los atributos son inventados.
- No hay geometría.
- El formato es el **observado** en local por la historia #236 (2026-11-28), ya no una suposición:
  - `parcelas_fechas_sintetico.xml`: el WFS INSPIRE de parcelas no trae `FECHAALTA`/`FECHABAJA`, sino `cp:beginLifespanVersion` (ISO 8601 con hora) y `cp:endLifespanVersion` vacío (`xsi:nil`, «Unpopulated»), y solo parcelas vigentes;
  - `parcela_dbf_fechas_sintetico.csv`: el `PARCELA.DBF` del Shapefile sí trae `FECHAALTA` y `FECHABAJA` numéricos `AAAAMMDD`, con `99999999` como «sin baja» (en una descarga actual, todas).

Las respuestas reales, si se piden, se quedan en `data/` y no se versionan.
