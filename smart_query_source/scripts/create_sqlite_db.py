import sqlite3
p = r"D:\BaiduNetdiskDownload\data\smart_query_assistant\src\data\finance_data.sqlite"
con = sqlite3.connect(p)
cur = con.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)')
cur.execute('INSERT OR IGNORE INTO metadata (key, value) VALUES ("created_by","packager")')
cur.execute('CREATE TABLE IF NOT EXISTS companies (id INTEGER PRIMARY KEY, name TEXT, code TEXT)')
con.commit()
con.close()
print('Created', p)
