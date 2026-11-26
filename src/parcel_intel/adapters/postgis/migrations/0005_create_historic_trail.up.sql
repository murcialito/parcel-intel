CREATE TABLE historic_trail (
    identifier TEXT PRIMARY KEY,
    municipality_code TEXT NOT NULL CHECK (municipality_code ~ '^[0-9]{5}$'),
    document_kind TEXT NOT NULL CHECK (document_kind IN ('planimetria', 'mtn50')),
    document_id TEXT NOT NULL,
    document_date DATE NOT NULL,
    document_date_precision TEXT NOT NULL CHECK (document_date_precision IN ('day', 'year')),
    geometry geometry(LineString, 25830) NOT NULL,
    georeferencing_error_m DOUBLE PRECISION NOT NULL CHECK (georeferencing_error_m >= 0),
    provenance_source TEXT NOT NULL,
    provenance_url TEXT NOT NULL,
    provenance_retrieved_at DATE NOT NULL,
    provenance_license TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('proposed', 'approved', 'rejected')),
    reviewer TEXT,
    reviewed_at TIMESTAMPTZ,
    CHECK (
        (status = 'proposed' AND reviewer IS NULL AND reviewed_at IS NULL)
        OR (status <> 'proposed' AND reviewer IS NOT NULL AND reviewed_at IS NOT NULL)
    )
);
CREATE INDEX idx_historic_trail_geometry ON historic_trail USING GIST (geometry);
CREATE INDEX idx_historic_trail_municipality_status ON historic_trail (municipality_code, status);
