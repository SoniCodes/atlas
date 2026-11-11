import psycopg
from mcp.server import MCPServer

mcp = MCPServer("sbom")


def connect():
    conn = psycopg.connect(host="127.0.0.1", dbname="atlas", user="atlas")
    conn.read_only = True
    return conn


@mcp.tool()
def list_scans() -> list[dict]:
    """List every image scan: its scan id, image name, tag, and scan date."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, tag, scanned_at::date FROM scans ORDER BY id")
            rows = cur.fetchall()

    scans = []
    for scan_id, name, tag, scanned_on in rows:
        scans.append({"scan_id": scan_id, "image": name, "tag": tag, "scanned_on": scanned_on})
    return scans

@mcp.tool()
def severity_for_scan(scan_id: int) -> list[dict]:
    """Count the vulnerabilities found in one scan, grouped by severity. Get the scan id from list_scans."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT severity, count(*) FROM findings JOIN vulnerabilities v ON findings.vulnerability_id = v.vulnerability_id  WHERE scan_id = %s GROUP BY severity;", 
                        (scan_id,))
            rows = cur.fetchall()

    severities = []
    for severity, count in rows:
        severities.append({"severity": severity, "count": count})
    return severities


if __name__ == "__main__":
    mcp.run()
