"""
Unit tests for chunk-based caching helpers in FlightScheduleService.
"""
from datetime import datetime, time, date
from src.services.flight_schedule_service import FlightScheduleService


class TestGetChunkStart:
    def test_midnight_maps_to_morning(self):
        dt = datetime(2024, 6, 15, 0, 0, 0)
        assert FlightScheduleService._get_chunk_start(dt) == datetime(2024, 6, 15, 0, 0, 0)

    def test_morning_time_maps_to_morning(self):
        dt = datetime(2024, 6, 15, 8, 30, 0)
        assert FlightScheduleService._get_chunk_start(dt) == datetime(2024, 6, 15, 0, 0, 0)

    def test_exactly_noon_maps_to_afternoon(self):
        dt = datetime(2024, 6, 15, 12, 0, 0)
        assert FlightScheduleService._get_chunk_start(dt) == datetime(2024, 6, 15, 12, 0, 0)

    def test_afternoon_time_maps_to_afternoon(self):
        dt = datetime(2024, 6, 15, 15, 37, 22)
        assert FlightScheduleService._get_chunk_start(dt) == datetime(2024, 6, 15, 12, 0, 0)

    def test_last_minute_of_day_maps_to_afternoon(self):
        dt = datetime(2024, 6, 15, 23, 59, 59)
        assert FlightScheduleService._get_chunk_start(dt) == datetime(2024, 6, 15, 12, 0, 0)

    def test_seconds_and_microseconds_stripped(self):
        dt = datetime(2024, 6, 15, 9, 45, 33, 123456)
        result = FlightScheduleService._get_chunk_start(dt)
        assert result.second == 0
        assert result.microsecond == 0


class TestGetChunksForDatetime:
    """Verify chunk selection logic — pure function, no DB needed."""

    def test_today_afternoon_returns_only_afternoon_chunk(self):
        from_dt = datetime(2024, 6, 15, 15, 30, 0)
        today = date(2024, 6, 15)
        chunks = FlightScheduleService._get_chunks_for_datetime(from_dt, today)
        assert chunks == [datetime(2024, 6, 15, 12, 0, 0)]

    def test_today_morning_returns_both_chunks(self):
        from_dt = datetime(2024, 6, 15, 8, 30, 0)
        today = date(2024, 6, 15)
        chunks = FlightScheduleService._get_chunks_for_datetime(from_dt, today)
        assert chunks == [datetime(2024, 6, 15, 0, 0, 0), datetime(2024, 6, 15, 12, 0, 0)]

    def test_today_exactly_noon_returns_only_afternoon_chunk(self):
        from_dt = datetime(2024, 6, 15, 12, 0, 0)
        today = date(2024, 6, 15)
        chunks = FlightScheduleService._get_chunks_for_datetime(from_dt, today)
        assert chunks == [datetime(2024, 6, 15, 12, 0, 0)]

    def test_future_date_afternoon_returns_both_chunks(self):
        from_dt = datetime(2024, 6, 16, 14, 0, 0)  # tomorrow at 14:00
        today = date(2024, 6, 15)
        chunks = FlightScheduleService._get_chunks_for_datetime(from_dt, today)
        assert chunks == [datetime(2024, 6, 16, 0, 0, 0), datetime(2024, 6, 16, 12, 0, 0)]

    def test_past_date_afternoon_returns_both_chunks(self):
        from_dt = datetime(2024, 6, 14, 15, 0, 0)
        today = date(2024, 6, 15)
        chunks = FlightScheduleService._get_chunks_for_datetime(from_dt, today)
        assert chunks == [datetime(2024, 6, 14, 0, 0, 0), datetime(2024, 6, 14, 12, 0, 0)]

    def test_today_midnight_returns_both_chunks(self):
        from_dt = datetime(2024, 6, 15, 0, 0, 0)
        today = date(2024, 6, 15)
        chunks = FlightScheduleService._get_chunks_for_datetime(from_dt, today)
        assert chunks == [datetime(2024, 6, 15, 0, 0, 0), datetime(2024, 6, 15, 12, 0, 0)]
