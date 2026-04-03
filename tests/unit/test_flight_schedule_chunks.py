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


class TestGetChunksForRange:
    """Verify _get_chunks_for_range covers all needed 12h windows."""

    def test_morning_start_single_day(self):
        """Morning from → two chunks covering whole day."""
        from_dt = datetime(2024, 6, 15, 8, 0, 0)
        to_dt = datetime(2024, 6, 16, 0, 0, 0)
        chunks = FlightScheduleService._get_chunks_for_range(from_dt, to_dt, date(2024, 6, 14))
        assert chunks == [datetime(2024, 6, 15, 0, 0, 0), datetime(2024, 6, 15, 12, 0, 0)]

    def test_afternoon_start_single_day(self):
        """Afternoon from → only afternoon chunk."""
        from_dt = datetime(2024, 6, 15, 14, 0, 0)
        to_dt = datetime(2024, 6, 16, 0, 0, 0)
        chunks = FlightScheduleService._get_chunks_for_range(from_dt, to_dt, date(2024, 6, 14))
        assert chunks == [datetime(2024, 6, 15, 12, 0, 0)]

    def test_cross_day_evening_start(self):
        """Evening from, to crosses midnight → afternoon chunk + next-day morning chunk."""
        from_dt = datetime(2024, 6, 15, 22, 0, 0)
        to_dt = datetime(2024, 6, 16, 2, 0, 0)
        chunks = FlightScheduleService._get_chunks_for_range(from_dt, to_dt, date(2024, 6, 14))
        assert chunks == [datetime(2024, 6, 15, 12, 0, 0), datetime(2024, 6, 16, 0, 0, 0)]

    def test_today_afternoon_skips_morning_naturally(self):
        """For today afternoon, morning chunk naturally not included."""
        from_dt = datetime(2024, 6, 15, 15, 30, 0)
        to_dt = datetime(2024, 6, 16, 0, 0, 0)
        chunks = FlightScheduleService._get_chunks_for_range(from_dt, to_dt, date(2024, 6, 15))
        assert chunks == [datetime(2024, 6, 15, 12, 0, 0)]

    def test_today_morning_includes_both_chunks(self):
        """For today morning, both chunks included."""
        from_dt = datetime(2024, 6, 15, 8, 0, 0)
        to_dt = datetime(2024, 6, 16, 0, 0, 0)
        chunks = FlightScheduleService._get_chunks_for_range(from_dt, to_dt, date(2024, 6, 15))
        assert chunks == [datetime(2024, 6, 15, 0, 0, 0), datetime(2024, 6, 15, 12, 0, 0)]

    def test_to_dt_equals_chunk_boundary_not_included(self):
        """to_dt exactly on chunk boundary → that chunk not included."""
        from_dt = datetime(2024, 6, 15, 22, 0, 0)
        to_dt = datetime(2024, 6, 16, 0, 0, 0)  # exactly midnight
        chunks = FlightScheduleService._get_chunks_for_range(from_dt, to_dt, date(2024, 6, 14))
        assert chunks == [datetime(2024, 6, 15, 12, 0, 0)]

    def test_wide_range_three_chunks(self):
        """Range spanning 26h → three chunks."""
        from_dt = datetime(2024, 6, 15, 10, 0, 0)
        to_dt = datetime(2024, 6, 16, 12, 0, 0)  # 26h range
        chunks = FlightScheduleService._get_chunks_for_range(from_dt, to_dt, date(2024, 6, 14))
        assert chunks == [
            datetime(2024, 6, 15, 0, 0, 0),
            datetime(2024, 6, 15, 12, 0, 0),
            datetime(2024, 6, 16, 0, 0, 0),
        ]
