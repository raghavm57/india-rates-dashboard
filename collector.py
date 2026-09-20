import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "data" / "market.db"
DB.parent.mkdir(exist_ok=True)

SCHEMA = '''
CREATE TABLE IF NOT EXISTS observations (
 date TEXT NOT NULL, source TEXT NOT NULL, series TEXT NOT NULL,
 tenor TEXT NOT NULL DEFAULT '', value REAL NOT NULL,
 unit TEXT NOT NULL DEFAULT '%', publication_time TEXT,
 source_url TEXT, status TEXT NOT NULL DEFAULT 'published',
 PRIMARY KEY(date, source, series, tenor)
);
'''

con = sqlite3.connect(DB)
con.execute(SCHEMA)
con.commit()
con.close()
print("Database initialized:", DB)
