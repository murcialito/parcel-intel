CREATE TABLE rule (
    identifier TEXT PRIMARY KEY,
    region TEXT NOT NULL,
    soil_classes TEXT[] NOT NULL DEFAULT '{}',
    spatial_operation TEXT NOT NULL CHECK (spatial_operation IN ('within_distance', 'overlaps')),
    spatial_layer TEXT NOT NULL CHECK (spatial_layer IN ('dph_cauce', 'via_pecuaria', 'red_natura_plan')),
    spatial_meters NUMERIC,
    building_origins TEXT[] NOT NULL,
    outcome TEXT NOT NULL,
    authority TEXT NOT NULL,
    norm_title TEXT NOT NULL,
    norm_url TEXT NOT NULL,
    provision_article TEXT NOT NULL,
    provision_in_force_since DATE NOT NULL,
    provision_url TEXT,
    status TEXT NOT NULL CHECK (status IN ('proposed', 'approved', 'rejected')),
    explanation TEXT NOT NULL,
    llm_model TEXT NOT NULL,
    llm_prompt_tokens INTEGER NOT NULL,
    llm_completion_tokens INTEGER NOT NULL,
    llm_cost_usd NUMERIC NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    reviewed_at TIMESTAMPTZ,
    CHECK (
        (spatial_operation = 'within_distance' AND spatial_meters IS NOT NULL)
        OR (spatial_operation = 'overlaps' AND spatial_meters IS NULL)
    )
);
CREATE INDEX idx_rule_status ON rule (status);
