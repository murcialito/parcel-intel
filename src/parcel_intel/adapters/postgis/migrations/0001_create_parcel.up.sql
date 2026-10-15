CREATE TABLE parcel (
    cadastral_reference TEXT PRIMARY KEY,
    municipality TEXT NOT NULL,
    geometry geometry(MultiPolygon, 25830) NOT NULL,
    area_m2 NUMERIC NOT NULL,
    provenance_source TEXT NOT NULL,
    provenance_url TEXT NOT NULL,
    provenance_retrieved_at DATE NOT NULL,
    provenance_license TEXT
);
