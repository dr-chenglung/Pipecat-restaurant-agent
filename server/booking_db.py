"""悅來餐廳訂位資料層。

以 SQLite 儲存訂位;所有函式回傳 dict,錯誤以 {"error": "..."} 表示、不丟例外,
方便直接把結果餵回 LLM 讓它向客人說明。
"""

import os
import sqlite3
from datetime import date, datetime, timedelta

# 營業時段:午餐 11:00–14:00、晚餐 17:00–21:00,每 30 分鐘一個時段(最後可訂 13:30 / 20:30)
LUNCH_SLOTS = ["11:00", "11:30", "12:00", "12:30", "13:00", "13:30"]
DINNER_SLOTS = ["17:00", "17:30", "18:00", "18:30", "19:00", "19:30", "20:00", "20:30"]
ALL_SLOTS = LUNCH_SLOTS + DINNER_SLOTS
CAPACITY_PER_SLOT = 20
MAX_PARTY_SIZE = 20

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "bookings.db")


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    """建立資料庫與 bookings 表(已存在則不動)。"""
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                party_size INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'confirmed',
                created_at TEXT NOT NULL
            )
            """
        )


def seed_db(db_path: str) -> None:
    """塞入示範訂位(僅在資料庫是空的時候),讓查空位與後台有真實感。"""
    with _connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    if count > 0:
        return
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    day_after = (date.today() + timedelta(days=2)).isoformat()
    samples = [
        ("陳美玲", "0922333444", tomorrow, "12:00", 4),
        ("林志豪", "0933555777", tomorrow, "18:00", 6),
        ("張雅婷", "0955666888", tomorrow, "18:30", 2),
        ("黃國倫", "0977888999", day_after, "19:00", 8),
    ]
    with _connect(db_path) as conn:
        for name, phone, d, t, size in samples:
            conn.execute(
                "INSERT INTO bookings (name, phone, date, time, party_size, status, created_at)"
                " VALUES (?, ?, ?, ?, ?, 'confirmed', ?)",
                (name, phone, d, t, size, datetime.now().isoformat(timespec="seconds")),
            )


def _validate_date(value: str) -> str | None:
    """回傳錯誤訊息,合法則回 None。"""
    try:
        parsed = date.fromisoformat(value)
    except (ValueError, TypeError):
        return "日期格式錯誤,請用 YYYY-MM-DD,例如 2026-07-19"
    if parsed < date.today():
        return "這個日期已經過去了,請提供今天以後的日期"
    return None


def _validate_time(value: str) -> str | None:
    if value not in ALL_SLOTS:
        return (
            "這個時間不在可訂時段內。可訂時段為午餐 11:00 到 13:30、"
            "晚餐 17:00 到 20:30,每三十分鐘一個時段"
        )
    return None


def _validate_party_size(value: int) -> str | None:
    if not isinstance(value, int) or value < 1 or value > MAX_PARTY_SIZE:
        return f"人數需在 1 到 {MAX_PARTY_SIZE} 人之間"
    return None


def _booked_seats(conn: sqlite3.Connection, d: str, t: str, exclude_id: int | None = None) -> int:
    sql = (
        "SELECT COALESCE(SUM(party_size), 0) FROM bookings"
        " WHERE date = ? AND time = ? AND status = 'confirmed'"
    )
    args: list = [d, t]
    if exclude_id is not None:
        sql += " AND id != ?"
        args.append(exclude_id)
    return conn.execute(sql, args).fetchone()[0]


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "booking_id": row["id"],
        "name": row["name"],
        "phone": row["phone"],
        "date": row["date"],
        "time": row["time"],
        "party_size": row["party_size"],
        "status": row["status"],
    }


def check_availability(db_path: str, date: str, time: str, party_size: int) -> dict:
    """查詢指定日期時段是否可訂;滿位時回傳同日的替代時段。"""
    for err in (_validate_date(date), _validate_time(time), _validate_party_size(party_size)):
        if err:
            return {"error": err}
    with _connect(db_path) as conn:
        remaining = CAPACITY_PER_SLOT - _booked_seats(conn, date, time)
        if remaining >= party_size:
            return {"available": True, "remaining_seats": remaining}
        # 滿位:找同日其他裝得下的時段,依與原時段的距離排序,最多推薦三個
        requested_idx = ALL_SLOTS.index(time)
        alternatives = []
        for idx, slot in enumerate(ALL_SLOTS):
            if slot == time:
                continue
            if CAPACITY_PER_SLOT - _booked_seats(conn, date, slot) >= party_size:
                alternatives.append((abs(idx - requested_idx), slot))
        alternatives.sort()
        return {
            "available": False,
            "remaining_seats": remaining,
            "alternative_times": [slot for _, slot in alternatives[:3]],
        }


def create_booking(
    db_path: str, name: str, phone: str, date: str, time: str, party_size: int
) -> dict:
    """建立訂位;成功回傳 booking_id。"""
    if not name or not phone:
        return {"error": "姓名與電話都需要提供"}
    availability = check_availability(db_path, date, time, party_size)
    if "error" in availability:
        return availability
    if not availability["available"]:
        return {
            "error": "這個時段位子不夠了",
            "alternative_times": availability["alternative_times"],
        }
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO bookings (name, phone, date, time, party_size, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, 'confirmed', ?)",
            (name, phone, date, time, party_size, datetime.now().isoformat(timespec="seconds")),
        )
        return {
            "booking_id": cur.lastrowid,
            "name": name,
            "date": date,
            "time": time,
            "party_size": party_size,
        }


def find_bookings(db_path: str, phone: str) -> dict:
    """以電話號碼查詢所有有效(confirmed)訂位。"""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM bookings WHERE phone = ? AND status = 'confirmed'"
            " ORDER BY date, time",
            (phone,),
        ).fetchall()
    return {"bookings": [_row_to_dict(r) for r in rows]}


def update_booking(
    db_path: str,
    booking_id: int,
    new_date: str | None = None,
    new_time: str | None = None,
    new_party_size: int | None = None,
) -> dict:
    """修改訂位的日期/時段/人數;會先驗證新時段容量(排除自己原本佔的位子)。"""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM bookings WHERE id = ? AND status = 'confirmed'", (booking_id,)
        ).fetchone()
        if row is None:
            return {"error": f"找不到編號 {booking_id} 的有效訂位"}

        target_date = new_date if new_date is not None else row["date"]
        target_time = new_time if new_time is not None else row["time"]
        target_size = new_party_size if new_party_size is not None else row["party_size"]

        for err in (
            _validate_date(target_date),
            _validate_time(target_time),
            _validate_party_size(target_size),
        ):
            if err:
                return {"error": err}

        remaining = CAPACITY_PER_SLOT - _booked_seats(
            conn, target_date, target_time, exclude_id=booking_id
        )
        if remaining < target_size:
            return {"error": "新的時段位子不夠了", "remaining_seats": remaining}

        conn.execute(
            "UPDATE bookings SET date = ?, time = ?, party_size = ? WHERE id = ?",
            (target_date, target_time, target_size, booking_id),
        )
        return {
            "booking_id": booking_id,
            "date": target_date,
            "time": target_time,
            "party_size": target_size,
        }


def cancel_booking(db_path: str, booking_id: int) -> dict:
    """取消訂位(標記 cancelled,容量隨之釋出)。"""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM bookings WHERE id = ? AND status = 'confirmed'", (booking_id,)
        ).fetchone()
        if row is None:
            return {"error": f"找不到編號 {booking_id} 的有效訂位"}
        conn.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
        return {"cancelled": True, "booking_id": booking_id}


def list_all_bookings(db_path: str) -> list[dict]:
    """回傳所有訂位(含已取消),供管理後台使用。"""
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM bookings ORDER BY date, time, id").fetchall()
    return [_row_to_dict(r) for r in rows]
