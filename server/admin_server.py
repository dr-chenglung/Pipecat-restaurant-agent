"""悅來餐廳 — 店員訂位管理後台(唯讀)。

獨立的小型 FastAPI 服務,與 bot 共用同一個 SQLite 檔:
- GET /admin         訂位表格頁,每 2 秒自動刷新
- GET /api/bookings  全部訂位 JSON(含已取消)

Run using::

    uv run admin_server.py
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

import booking_db

DB_PATH = booking_db.DEFAULT_DB_PATH
booking_db.init_db(DB_PATH)
booking_db.seed_db(DB_PATH)

app = FastAPI(title="悅來餐廳 訂位管理後台")

ADMIN_PAGE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8" />
<title>悅來餐廳 訂位管理後台</title>
<style>
  body { font-family: 'Segoe UI', 'Microsoft JhengHei', sans-serif;
         background: #1c1410; color: #ede0d4; margin: 0; padding: 2rem; }
  h1 { font-size: 1.4rem; margin: 0 0 0.25rem 0; color: #fbbf24; }
  .subtitle { color: #a8927d; font-size: 0.85rem; margin-bottom: 1.5rem; }
  table { width: 100%; border-collapse: collapse; background: #2a1f18;
          border-radius: 0.5rem; overflow: hidden; }
  th, td { padding: 0.6rem 0.9rem; text-align: left; font-size: 0.9rem; }
  th { background: #3f2f23; color: #fbbf24; font-weight: 600; }
  tr { border-bottom: 1px solid #3f2f23; }
  tr.cancelled td { color: #7c6a58; text-decoration: line-through; }
  .status-confirmed { color: #4ade80; }
  .cancelled .status-cancelled { color: #f87171; text-decoration: none; }
  .empty { color: #a8927d; font-style: italic; padding: 2rem; text-align: center; }
</style>
</head>
<body>
  <h1>悅來餐廳 訂位管理後台</h1>
  <div class="subtitle">每兩秒自動更新;語音訂位完成後,新訂位會即時出現在這裡</div>
  <table>
    <thead>
      <tr><th>編號</th><th>日期</th><th>時段</th><th>姓名</th><th>電話</th><th>人數</th><th>狀態</th></tr>
    </thead>
    <tbody id="rows"></tbody>
  </table>
  <div id="empty" class="empty" style="display:none">目前沒有任何訂位</div>
  <script>
    async function refresh() {
      try {
        const res = await fetch('/api/bookings');
        const data = await res.json();
        const tbody = document.getElementById('rows');
        const empty = document.getElementById('empty');
        tbody.innerHTML = '';
        empty.style.display = data.bookings.length ? 'none' : 'block';
        for (const b of data.bookings) {
          const tr = document.createElement('tr');
          if (b.status === 'cancelled') tr.className = 'cancelled';
          const cells = [b.booking_id, b.date, b.time, b.name, b.phone, b.party_size];
          for (const value of cells) {
            const td = document.createElement('td');
            td.textContent = value;
            tr.appendChild(td);
          }
          const statusTd = document.createElement('td');
          statusTd.textContent = b.status === 'confirmed' ? '有效' : '已取消';
          statusTd.className = 'status-' + b.status;
          tr.appendChild(statusTd);
          tbody.appendChild(tr);
        }
      } catch (e) { /* server 重啟間隔容忍 */ }
    }
    refresh();
    setInterval(refresh, 2000);
  </script>
</body>
</html>"""


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    return ADMIN_PAGE


@app.get("/api/bookings")
async def api_bookings():
    booking_db.init_db(DB_PATH)
    return {"bookings": booking_db.list_all_bookings(DB_PATH)}


@app.get("/")
async def root():
    return {"service": "悅來餐廳 訂位管理後台", "admin": "/admin", "api": "/api/bookings"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7861)
