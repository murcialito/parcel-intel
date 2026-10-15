CREATE TABLE building (
    id BIGSERIAL PRIMARY KEY,
    parcel_reference TEXT NOT NULL REFERENCES parcel(cadastral_reference) ON DELETE CASCADE,
    cadastral_reference TEXT NOT NULL,
    geometry geometry(MultiPolygon, 25830) NOT NULL,
    area_m2 NUMERIC NOT NULL,
    construction_year INTEGER,
    origin TEXT NOT NULL CHECK (origin IN ('catastro', 'detected')),
    provenance_source TEXT NOT NULL,
    provenance_url TEXT NOT NULL,
    provenance_retrieved_at DATE NOT NULL,
    provenance_license TEXT
);

CREATE INDEX idx_building_parcel_reference ON building (parcel_reference);
