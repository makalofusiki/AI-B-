from fastapi import FastAPI, HTTPException
import os
import sys
# ensure project src is importable
sys.path.insert(0, os.path.dirname(__file__))
from db_client import DBClient
from config import DB_CONFIG

app = FastAPI(title="SmartQuery Top5 API")

QUERY = """SELECT stock_code, stock_abbr, total_operating_revenue
FROM income_sheet
WHERE report_year=2025 AND report_period='Q3' AND total_operating_revenue IS NOT NULL
ORDER BY total_operating_revenue DESC
LIMIT 5
"""

@app.get('/top5/revenue')
def top5_revenue():
    try:
        db = DBClient(DB_CONFIG)
        rows = db.fetch_all(QUERY)
        db.close()
        return {"count": len(rows), "rows": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == '__main__':
    # fallback run for local debugging
    import uvicorn
    uvicorn.run('top5_api:app', host='0.0.0.0', port=8000)
