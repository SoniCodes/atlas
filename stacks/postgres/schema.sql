CREATE TABLE IF NOT EXISTS vulnerabilities (
        vulnerability_id TEXT PRIMARY KEY,
        title            TEXT,
        description      TEXT,
        severity         TEXT NOT NULL,
        published_date   TIMESTAMPTZ,
        primary_url      TEXT
);

CREATE TABLE IF NOT EXISTS packages (
        id      BIGSERIAL PRIMARY KEY,
        name    TEXT NOT NULL,
        version TEXT NOT NULL,
        UNIQUE (name, version)
);

CREATE TABLE IF NOT EXISTS scans (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        tag  TEXT,
        image_digest TEXT NOT NULL,
        os_family TEXT,
        os_version TEXT,
        size_bytes BIGINT NOT NULL,
        scanned_at TIMESTAMPTZ NOT NULL,
        trivy_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
        scan_id BIGINT NOT NULL REFERENCES scans(id),
        package_id BIGINT NOT NULL REFERENCES packages(id),
        vulnerability_id TEXT NOT NULL REFERENCES vulnerabilities(vulnerability_id),
        status TEXT NOT NULL,
        fixed_version TEXT,
        PRIMARY KEY(scan_id, package_id, vulnerability_id)
);

