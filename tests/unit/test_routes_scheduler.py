"""Tests for /api/scheduler routes."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.utils.config import settings


class _FakeScheduler:
    """Minimal scheduler stub for route tests."""

    _running = False

    def __init__(self):
        self.scheduler = MagicMock()
        self.scheduler.get_jobs.return_value = []

    def get_next_run_time(self):
        return None

    def reload_schedule(self):
        return True

    async def update_box_office(self):
        return {"total_count": 10, "added_movies": ["Movie A"]}


@pytest.fixture
def patched_scheduler(monkeypatch):
    fake = _FakeScheduler()
    import src.api.routes.scheduler as sched_module

    monkeypatch.setattr(sched_module, "_scheduler", fake)
    yield fake
    monkeypatch.setattr(sched_module, "_scheduler", None)


class TestSchedulerStatus:
    def test_returns_status_structure(self, client, patched_scheduler):
        resp = client.get("/api/scheduler/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data
        assert "running" in data
        assert "cron_expression" in data

    def test_includes_last_run_from_history(
        self, client, patched_scheduler, isolated_data_dir
    ):
        history_dir = isolated_data_dir / "history"
        history_dir.mkdir()
        hist_data = {
            "timestamp": "2025-01-07T23:00:00",
            "matched_count": 5,
            "total_count": 10,
        }
        (history_dir / "202501_20250107_230000_latest.json").write_text(
            json.dumps(hist_data)
        )
        resp = client.get("/api/scheduler/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("last_run") is not None


class TestSchedulerHistory:
    def test_no_history_dir_returns_empty(self, client, patched_scheduler):
        resp = client.get("/api/scheduler/history")
        assert resp.status_code == 200
        assert resp.json()["runs"] == []

    def test_history_files_parsed(self, client, patched_scheduler, isolated_data_dir):
        history_dir = isolated_data_dir / "history"
        history_dir.mkdir()
        run_data = {
            "success": True,
            "total_count": 10,
            "added_movies": ["Movie A", "Movie B"],
        }
        (history_dir / "202501_20250107_230000.json").write_text(json.dumps(run_data))
        resp = client.get("/api/scheduler/history")
        assert resp.status_code == 200
        runs = resp.json()["runs"]
        assert len(runs) == 1
        assert runs[0]["success"] is True
        assert runs[0]["movies_found"] == 10
        assert runs[0]["movies_added"] == 2

    def test_malformed_filename_skipped(
        self, client, patched_scheduler, isolated_data_dir
    ):
        history_dir = isolated_data_dir / "history"
        history_dir.mkdir()
        (history_dir / "bad_file.json").write_text("{}")
        resp = client.get("/api/scheduler/history")
        assert resp.status_code == 200
        assert resp.json()["runs"] == []


class TestSchedulerReload:
    def test_reload_not_running_returns_failure(self, client, patched_scheduler):
        patched_scheduler._running = False
        resp = client.post("/api/scheduler/reload")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_reload_running_returns_success(self, client, patched_scheduler):
        patched_scheduler._running = True
        resp = client.post("/api/scheduler/reload")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


class TestSchedulerTrigger:
    def test_trigger_returns_result(self, client, patched_scheduler):
        resp = client.post("/api/scheduler/trigger")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["movies_found"] == 10
        assert data["movies_added"] == 1

    def test_trigger_exception_returns_failure(self, client, patched_scheduler):
        async def _raise():
            raise RuntimeError("oops")

        patched_scheduler.update_box_office = _raise
        resp = client.post("/api/scheduler/trigger")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_reload_failure_returns_false(self, client, patched_scheduler):
        patched_scheduler._running = True
        patched_scheduler.reload_schedule = lambda: False
        resp = client.post("/api/scheduler/reload")
        assert resp.status_code == 200
        assert resp.json()["success"] is False


class TestUpdateWeek:
    def test_invalid_year_returns_400(self, client, patched_scheduler):
        resp = client.post("/api/scheduler/update-week", json={"year": 1999, "week": 1})
        assert resp.status_code == 400

    def test_invalid_week_returns_400(self, client, patched_scheduler):
        resp = client.post("/api/scheduler/update-week", json={"year": 2024, "week": 0})
        assert resp.status_code == 400

    def test_valid_request_no_radarr(self, client, patched_scheduler, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "")
        monkeypatch.setattr(settings, "boxarr_features_box_office_limit", 10)
        from src.core.boxoffice import BoxOfficeMovie

        with (
            patch("src.core.boxoffice.BoxOfficeService") as bo_cls,
            patch("src.core.json_generator.WeeklyDataGenerator") as gen_cls,
        ):
            bo_instance = MagicMock()
            bo_instance.fetch_weekend_box_office.return_value = [
                BoxOfficeMovie(rank=1, title="Film A", weekend_gross=1_000_000)
            ]
            bo_cls.return_value = bo_instance
            gen_instance = MagicMock()
            gen_cls.return_value = gen_instance
            resp = client.post(
                "/api/scheduler/update-week", json={"year": 2024, "week": 1}
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_no_box_office_data_returns_failure(
        self, client, patched_scheduler, monkeypatch
    ):
        monkeypatch.setattr(settings, "radarr_api_key", "")
        monkeypatch.setattr(settings, "boxarr_features_box_office_limit", 10)
        with patch("src.core.boxoffice.BoxOfficeService") as bo_cls:
            bo_instance = MagicMock()
            bo_instance.fetch_weekend_box_office.return_value = []
            bo_cls.return_value = bo_instance
            resp = client.post(
                "/api/scheduler/update-week", json={"year": 2024, "week": 1}
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False


class TestSchedulerStatusWithRunning:
    def test_status_with_running_scheduler(self, client, patched_scheduler):
        from datetime import datetime, timezone

        patched_scheduler._running = True
        future = datetime(2025, 6, 1, 23, 0, 0, tzinfo=timezone.utc)
        patched_scheduler.get_next_run_time = lambda: future
        resp = client.get("/api/scheduler/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["next_run_time"] is not None
