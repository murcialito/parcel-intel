-- Sin esto, dos peticiones concurrentes a la misma referencia catastral
-- nueva (ambas cache-miss, ambas consultando Catastro y guardando) pueden
-- duplicar edificios permanentemente: el caché es intencionalmente
-- permanente (ADR 0005), así que una duplicación aquí nunca se autocorrige.
ALTER TABLE building
    ADD CONSTRAINT building_parcel_reference_cadastral_reference_key
    UNIQUE (parcel_reference, cadastral_reference);
