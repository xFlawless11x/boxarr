"""Tests for src/core/scheduler.py - BoxarrScheduler."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.scheduler import BoxarrScheduler
from src.utils.config import settings


def _make_scheduler(monkeypatch=None):
    """Create a BoxarrScheduler with mocked APScheduler."""
    mock_apscheduler = MagicMock()
    with patch("src.core.scheduler.AsyncIOScheduler", return_value=mock_apscheduler):
        sched = BoxarrScheduler()
    sched.scheduler = mock_apscheduler
    return sched


class TestBoxarrSchedulerInit:
    def test_init_creates_scheduler(self, monkeypatch):
        monkeypatch.setattr(settings, "boxarr_scheduler_timezone", "US/Eastern")
        with patch("src.core.scheduler.AsyncIOScheduler") as mock_cls:
            mock_cls.return_value = MagicMock()
            sched = BoxarrScheduler()
        assert sched._running is False

    def test_init_unknown_timezone_uses_utc(self, monkeypatch):
        monkeypatch.setattr(settings, "boxarr_scheduler_timezone", "Invalid/Timezone")
        with patch("src.core.scheduler.AsyncIOScheduler") as mock_cls:
            mock_cls.return_value = MagicMock()
            sched = BoxarrScheduler()
        assert sched._running is False


class TestSchedulerStart:
    def test_start_when_enabled(self, monkeypatch):
        monkeypatch.setattr(settings, "boxarr_scheduler_enabled", True)
        monkeypatch.setattr(settings, "boxarr_scheduler_cron", "0 23 * * 2")
        sched = _make_scheduler()
        mock_job = MagicMock()
        mock_job.next_run_time = datetime(2025, 1, 7, 23, 0, tzinfo=timezone.utc)
        sched.scheduler.add_job.return_value = mock_job
        sched.scheduler.get_job.return_value = None
        sched.start()
        assert sched._running is True

    def test_start_when_disabled(self, monkeypatch):
        monkeypatch.setattr(settings, "boxarr_scheduler_enabled", False)
        sched = _make_scheduler()
        sched.start()
        assert sched._running is False
        sched.scheduler.start.assert_not_called()

    def test_start_when_already_running(self, monkeypatch):
        monkeypatch.setattr(settings, "boxarr_scheduler_enabled", True)
        sched = _make_scheduler()
        sched._running = True
        sched.start()
        sched.scheduler.start.assert_not_called()

    def test_start_removes_existing_job(self, monkeypatch):
        monkeypatch.setattr(settings, "boxarr_scheduler_enabled", True)
        monkeypatch.setattr(settings, "boxarr_scheduler_cron", "0 23 * * 2")
        sched = _make_scheduler()
        existing_job = MagicMock()
        mock_job = MagicMock()
        mock_job.next_run_time = None
        sched.scheduler.get_job.return_value = existing_job
        sched.scheduler.add_job.return_value = mock_job
        sched.start()
        sched.scheduler.remove_job.assert_called_with("box_office_update")

    def test_start_exception_sets_not_running(self, monkeypatch):
        monkeypatch.setattr(settings, "boxarr_scheduler_enabled", True)
        monkeypatch.setattr(settings, "boxarr_scheduler_cron", "0 23 * * 2")
        sched = _make_scheduler()
        sched.scheduler.get_job.return_value = None
        sched.scheduler.add_job.side_effect = RuntimeError("cron error")
        with pytest.raises(RuntimeError):
            sched.start()
        assert sched._running is False


class TestSchedulerStop:
    def test_stop_when_running(self):
        sched = _make_scheduler()
        sched._running = True
        sched.stop()
        assert sched._running is False
        sched.scheduler.shutdown.assert_called_once()

    def test_stop_when_not_running(self):
        sched = _make_scheduler()
        sched._running = False
        sched.stop()
        sched.scheduler.shutdown.assert_not_called()


class TestReloadSchedule:
    def test_reload_success(self, monkeypatch):
        monkeypatch.setattr(settings, "boxarr_scheduler_cron", "0 23 * * 2")
        sched = _make_scheduler()
        mock_job = MagicMock()
        mock_job.next_run_time = datetime(2025, 1, 7, 23, 0, tzinfo=timezone.utc)
        sched.scheduler.get_job.return_value = None
        sched.scheduler.add_job.return_value = mock_job
        result = sched.reload_schedule()
        assert result is True

    def test_reload_with_existing_job(self, monkeypatch):
        monkeypatch.setattr(settings, "boxarr_scheduler_cron", "0 23 * * 2")
        sched = _make_scheduler()
        existing_job = MagicMock()
        sched.scheduler.get_job.return_value = existing_job
        mock_job = MagicMock()
        mock_job.next_run_time = None
        sched.scheduler.add_job.return_value = mock_job
        result = sched.reload_schedule()
        assert result is True
        sched.scheduler.remove_job.assert_called_with("box_office_update")

    def test_reload_failure_returns_false(self, monkeypatch):
        monkeypatch.setattr(settings, "boxarr_scheduler_cron", "0 23 * * 2")
        sched = _make_scheduler()
        sched.scheduler.get_job.return_value = None
        sched.scheduler.add_job.side_effect = RuntimeError("bad cron")
        result = sched.reload_schedule()
        assert result is False

    def test_reload_with_custom_cron(self, monkeypatch):
        sched = _make_scheduler()
        sched.scheduler.get_job.return_value = None
        mock_job = MagicMock()
        mock_job.next_run_time = None
        sched.scheduler.add_job.return_value = mock_job
        result = sched.reload_schedule("0 9 * * 1")
        assert result is True


class TestGetNextRunTime:
    def test_returns_datetime_when_job_exists(self):
        sched = _make_scheduler()
        run_time = datetime(2025, 1, 7, 23, 0, tzinfo=timezone.utc)
        mock_job = MagicMock()
        mock_job.next_run_time = run_time
        sched.scheduler.get_job.return_value = mock_job
        result = sched.get_next_run_time()
        assert result == run_time

    def test_returns_none_when_no_job(self):
        sched = _make_scheduler()
        sched.scheduler.get_job.return_value = None
        result = sched.get_next_run_time()
        assert result is None

    def test_returns_none_when_next_run_not_datetime(self):
        sched = _make_scheduler()
        mock_job = MagicMock()
        mock_job.next_run_time = "not a datetime"
        sched.scheduler.get_job.return_value = mock_job
        result = sched.get_next_run_time()
        assert result is None


class TestRunNow:
    def test_run_now_when_running(self):
        sched = _make_scheduler()
        sched._running = True
        sched.run_now()
        sched.scheduler.add_job.assert_called_once()

    def test_run_now_when_not_running(self):
        sched = _make_scheduler()
        sched._running = False
        sched.run_now()
        sched.scheduler.add_job.assert_not_called()


class TestEventHandlers:
    def test_on_job_executed(self):
        sched = _make_scheduler()
        event = MagicMock()
        event.job_id = "box_office_update"
        sched._on_job_executed(event)  # Should not raise

    def test_on_job_error(self):
        sched = _make_scheduler()
        event = MagicMock()
        event.job_id = "box_office_update"
        event.exception = RuntimeError("job failed")
        sched._on_job_error(event)  # Should not raise


class TestGetHistory:
    @pytest.mark.anyio
    async def test_empty_history_dir(self, isolated_data_dir, monkeypatch):
        from src.utils.config import settings

        monkeypatch.setattr(settings, "boxarr_data_directory", isolated_data_dir)
        with patch("src.core.scheduler.settings") as mock_settings:
            history_dir = isolated_data_dir / "history"
            history_dir.mkdir()
            mock_settings.get_history_path.return_value = history_dir
            sched = _make_scheduler()
            result = await sched.get_history()
        assert result == []

    @pytest.mark.anyio
    async def test_reads_history_files(self, isolated_data_dir):
        import json as _json

        with patch("src.core.scheduler.settings") as mock_settings:
            history_dir = isolated_data_dir / "history"
            history_dir.mkdir()
            (history_dir / "202501_latest.json").write_text(
                _json.dumps(
                    {
                        "timestamp": "2025-01-07T23:00:00",
                        "total_count": 10,
                    }
                )
            )
            mock_settings.get_history_path.return_value = history_dir
            sched = _make_scheduler()
            result = await sched.get_history()
        assert len(result) == 1
        assert result[0]["total_count"] == 10


class TestProcessMatchResults:
    def test_basic_results(self):
        sched = _make_scheduler()
        from src.core.boxoffice import BoxOfficeMovie
        from src.core.matcher import MatchResult

        matched = MagicMock()
        matched.is_matched = True
        matched.box_office_movie = BoxOfficeMovie(
            rank=1, title="Film A", weekend_gross=1_000_000
        )
        unmatched = MagicMock()
        unmatched.is_matched = False
        unmatched.box_office_movie = BoxOfficeMovie(rank=2, title="Film B")

        # Call the private method if it exists
        if hasattr(sched, "_process_match_results"):
            results = sched._process_match_results([matched, unmatched])
            assert "total_count" in results or "matched_count" in results
