import os, sys, psycopg2

env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
db_url = ""
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line.startswith("DATABASE_URL"):
            db_url = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
conn = psycopg2.connect(db_url)
cur = conn.cursor()

# Get all tables
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    ORDER BY table_name;
""")
tables = [r[0] for r in cur.fetchall()]

print("="*80)
print("FINAL AUDIT SUMMARY FOR CLEANUP REPORT")
print("="*80)

for t in tables:
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    cnt = cur.fetchone()[0]
    print(f"Table: {t:<35} | Total Records: {cnt}")

conn.close()
