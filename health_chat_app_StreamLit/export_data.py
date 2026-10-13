"""Copy the health_indicators table from SQL Server into a small SQLite file.

Why: the online copy of the app cannot reach SQL Server on your PC, so it reads this file instead.
Run once on your PC (and again whenever the table changes):

    python export_data.py

Then add the new health_indicators.db to your GitHub repository and redeploy.
"""
import decimal
import sqlite3
from pathlib import Path

import pandas as pd
import pyodbc

SERVER = "127.0.0.1"
DATABASE = "DataAnalysis"
DRIVER = "ODBC Driver 17 for SQL Server"
TABLE = "health_indicators"
OUT = Path(__file__).with_name("health_indicators.db")

conn_str = (f"DRIVER={{{DRIVER}}};SERVER={SERVER};DATABASE={DATABASE};"
            "Trusted_Connection=yes;TrustServerCertificate=yes;")

print(f"Reading {DATABASE}.{TABLE} from SQL Server ...")
src = pyodbc.connect(conn_str, timeout=15)
cur = src.cursor()
cur.execute(f"SELECT * FROM {TABLE}")
columns = [c[0] for c in cur.description]
df = pd.DataFrame([list(r) for r in cur.fetchall()], columns=columns)
src.close()

# SQLite cannot store Decimal values, so convert them to floats
for col in df.columns:
    if df[col].dtype == object and df[col].map(lambda v: isinstance(v, decimal.Decimal)).any():
        df[col] = df[col].astype(float)

if OUT.exists():
    OUT.unlink()
dst = sqlite3.connect(OUT)
df.to_sql(TABLE, dst, index=False)
if "GHO_CODE" in df.columns:
    dst.execute(f"CREATE INDEX idx_{TABLE}_gho ON {TABLE}(GHO_CODE)")
dst.commit()
dst.close()

size_mb = OUT.stat().st_size / 1_000_000
print(f"Done: {len(df):,} rows, {len(columns)} columns -> {OUT.name} ({size_mb:.1f} MB)")
if size_mb > 90:
    print("WARNING: GitHub rejects files over 100 MB. Filter the table to the columns/rows you need.")
