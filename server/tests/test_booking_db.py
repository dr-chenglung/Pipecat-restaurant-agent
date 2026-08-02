"""booking_db 單元測試。全部使用 tmp_path 的臨時資料庫,不碰正式檔案。"""

from datetime import date, timedelta

import pytest

import booking_db


TOMORROW = (date.today() + timedelta(days=1)).isoformat()
NEXT_WEEK = (date.today() + timedelta(days=7)).isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    booking_db.init_db(path)
    return path


def make_booking(db, **overrides):
    args = dict(name="王小明", phone="0912345678", date=TOMORROW, time="18:00", party_size=4)
    args.update(overrides)
    return booking_db.create_booking(db, **args)


class TestCreateBooking:
    def test_create_returns_booking_id(self, db):
        result = make_booking(db)
        assert "error" not in result
        assert isinstance(result["booking_id"], int)

    def test_create_rejects_past_date(self, db):
        result = make_booking(db, date=YESTERDAY)
        assert "error" in result

    def test_create_rejects_invalid_time_slot(self, db):
        # 15:00 是午晚餐之間的空檔,不是合法時段
        result = make_booking(db, time="15:00")
        assert "error" in result

    def test_create_rejects_bad_date_format(self, db):
        result = make_booking(db, date="明天")
        assert "error" in result

    def test_create_rejects_party_size_out_of_range(self, db):
        assert "error" in make_booking(db, party_size=0)
        assert "error" in make_booking(db, party_size=21)

    def test_create_rejects_when_slot_full(self, db):
        make_booking(db, party_size=20)
        result = make_booking(db, name="李大華", phone="0987654321", party_size=1)
        assert "error" in result


class TestCheckAvailability:
    def test_available_slot(self, db):
        result = booking_db.check_availability(db, TOMORROW, "18:00", 4)
        assert result["available"] is True
        assert result["remaining_seats"] == 20

    def test_full_slot_offers_alternatives(self, db):
        make_booking(db, party_size=20)
        result = booking_db.check_availability(db, TOMORROW, "18:00", 2)
        assert result["available"] is False
        assert len(result["alternative_times"]) > 0
        assert "18:00" not in result["alternative_times"]

    def test_invalid_time_returns_error(self, db):
        assert "error" in booking_db.check_availability(db, TOMORROW, "15:00", 2)


class TestFindBookings:
    def test_finds_only_confirmed_for_phone(self, db):
        b1 = make_booking(db)
        make_booking(db, phone="0900000000", time="17:00")
        cancelled = make_booking(db, time="19:00")
        booking_db.cancel_booking(db, cancelled["booking_id"])

        result = booking_db.find_bookings(db, "0912345678")
        ids = [b["booking_id"] for b in result["bookings"]]
        assert ids == [b1["booking_id"]]

    def test_no_bookings(self, db):
        result = booking_db.find_bookings(db, "0999999999")
        assert result["bookings"] == []


class TestUpdateBooking:
    def test_update_time(self, db):
        b = make_booking(db)
        result = booking_db.update_booking(db, b["booking_id"], new_time="19:00")
        assert "error" not in result
        found = booking_db.find_bookings(db, "0912345678")["bookings"][0]
        assert found["time"] == "19:00"

    def test_update_rejects_full_target_slot(self, db):
        make_booking(db, phone="0911111111", time="19:00", party_size=20)
        b = make_booking(db)
        result = booking_db.update_booking(db, b["booking_id"], new_time="19:00")
        assert "error" in result

    def test_update_same_slot_party_size_ignores_own_booking(self, db):
        # 自己佔 18 人,改成 20 人仍在容量內(不能把自己的舊訂位算成別人)
        b = make_booking(db, party_size=18)
        result = booking_db.update_booking(db, b["booking_id"], new_party_size=20)
        assert "error" not in result

    def test_update_unknown_id(self, db):
        assert "error" in booking_db.update_booking(db, 9999, new_time="19:00")


class TestCancelBooking:
    def test_cancel_releases_capacity(self, db):
        b = make_booking(db, party_size=20)
        booking_db.cancel_booking(db, b["booking_id"])
        result = booking_db.check_availability(db, TOMORROW, "18:00", 20)
        assert result["available"] is True

    def test_cancel_unknown_id(self, db):
        assert "error" in booking_db.cancel_booking(db, 9999)

    def test_cancel_already_cancelled(self, db):
        b = make_booking(db)
        booking_db.cancel_booking(db, b["booking_id"])
        assert "error" in booking_db.cancel_booking(db, b["booking_id"])


class TestSeed:
    def test_seed_creates_bookings_once(self, db):
        booking_db.seed_db(db)
        first = booking_db.list_all_bookings(db)
        assert len(first) > 0
        booking_db.seed_db(db)  # 第二次不應重複塞
        assert len(booking_db.list_all_bookings(db)) == len(first)
