import psycopg

with psycopg.connect(
        host="127.0.0.1",
        dbname="atlas",
        user="atlas",
) as conn:
        with conn.cursor() as cur:
                cur.execute(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = 'public' ORDER BY tablename"
                )
                for row in cur.fetchall():
                        print(row[0])
