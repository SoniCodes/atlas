import sys
import psycopg
import json

REPORT_PATH = sys.argv[1]

with open(REPORT_PATH) as f:
    report = json.load(f)

name, _, tag = report["ArtifactName"].partition(":")
meta = report["Metadata"]
os_info = meta.get("OS", {})

with psycopg.connect(
    host="127.0.0.1",
    dbname="atlas",
    user="atlas",
) as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO scans (name, tag, image_digest, os_family,
                               os_version, size_bytes, scanned_at, trivy_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                name,
                tag or None,
                meta["ImageID"],
                os_info.get("Family"),
                os_info.get("Name"),
                meta["Size"],
                report["CreatedAt"],
                report["Trivy"]["Version"],
            ),
        )
        scan_id = cur.fetchone()[0]
        print("scan_id:", scan_id)

        for result in report["Results"]:
            for vuln in result.get("Vulnerabilities", []):
                cur.execute(
                    """
                    INSERT INTO packages (name, version) VALUES (%s, %s)
                    ON CONFLICT (name, version) DO UPDATE SET name = EXCLUDED.name
                    RETURNING id
                    """,
                    (
                        vuln["PkgName"],
                        vuln["InstalledVersion"],
                    ),
                )
                package_id = cur.fetchone()[0]

                # Alt approach: ON CONFLICT DO NOTHING inserts nothing on a
                # conflict, so RETURNING gives back no row and fetchone() is
                # None -- which needs an `if` plus a fallback SELECT to find
                # the existing id. DO UPDATE SET name = EXCLUDED.name is a
                # deliberate no-op: nothing changes, but a row counts as
                # "affected", so RETURNING fires every time and there's no
                # branch to write.

                cur.execute(
                    """
                    INSERT INTO vulnerabilities (vulnerability_id, title, description,
                                                 severity, published_date, primary_url)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (vulnerability_id) DO NOTHING
                    """,
                    (
                        vuln["VulnerabilityID"],
                        vuln.get("Title"),
                        vuln.get("Description"),
                        vuln["Severity"],
                        vuln.get("PublishedDate"),
                        vuln.get("PrimaryURL"),
                    ),
                )

                cur.execute(
                    """
                    INSERT INTO findings (scan_id, package_id,
                                          vulnerability_id, status, fixed_version)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        scan_id,
                        package_id,
                        vuln["VulnerabilityID"],
                        vuln.get("Status"),
                        vuln.get("FixedVersion"),
                    ),
                )
