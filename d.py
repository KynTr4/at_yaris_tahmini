import sqlite3

c = sqlite3.connect('pedigreeall_2026_only.db')
rows = c.execute("SELECT substr(race_date,7,4), COUNT(*) FROM horse_races GROUP BY substr(race_date,7,4)").fetchall()
for r in rows:
    print(r)