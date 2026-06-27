CREATE TABLE searches (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_role    TEXT NOT NULL,
    location    TEXT NOT NULL,
    job_type    TEXT NOT NULL,
    company     TEXT,
    status      TEXT DEFAULT 'queued',
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_id       UUID REFERENCES searches(id),
    jobs_list       JSONB,
    analysis_report TEXT,
    skills_report   TEXT,
    prep_guide      TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);