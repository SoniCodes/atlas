import psycopg
import json
import argparse


def read_report(path):
    with open(path) as f:
        report = json.load(f)
    return report
    
def insert_scan(cur, report):
    name, _, tag = report["ArtifactName"].partition(":")
    meta = report["Metadata"]
    os_info = meta.get("OS", {})
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
    return scan_id

def insert_package(cur, vuln):
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
    return package_id

def insert_vulnerability(cur, vuln):
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

def insert_findings(cur, scan_id, package_id, vuln):
    cur.execute(
        """
        INSERT INTO findings (scan_id, package_id,vulnerability_id, status, fixed_version)
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


parser = argparse.ArgumentParser(description="Load Trivy JSON reports into Postgres.")
parser.add_argument("reports", nargs="+", help="one or more Trivy JSON report files")
args = parser.parse_args()
for path in args.reports:
    report = read_report(path)
    
    with psycopg.connect(
        host="127.0.0.1",
        dbname="atlas",
        user="atlas",
    ) as conn:
        with conn.cursor() as cur:
            scan_id = insert_scan(cur,report)
            print("scan_id:", scan_id)
            
            for result in report["Results"]:
                for vuln in result.get("Vulnerabilities", []):
                    package_id = insert_package(cur, vuln)
                    insert_vulnerability(cur, vuln)
                    insert_findings(cur, scan_id, package_id, vuln)
