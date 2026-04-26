"""Tests for /api/boxoffice routes."""

from unittest.mock import MagicMock, patch

import pytest

from src.utils.config import settings


def _make_bo_movie(rank=1, title="Test Movie", weeks=1, gross=1_000_000):
    m = MagicMock()
    m.rank = rank
    m.title = title
    m.weekend_gross = gross
    m.total_gross = gross * 2
    m.weeks_released = weeks
    return m


class TestCurrentBoxOffice:
    def test_no_radarr_returns_raw_list(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "")
        with patch("src.api.routes.boxoffice.BoxOfficeService") as mock_cls:
            instance = MagicMock()
            instance.get_current_week_movies.return_value = [
                _make_bo_movie(1, "Film A"),
                _make_bo_movie(2, "Film B", weeks=2),
            ]
            mock_cls.return_value = instance

            resp = client.get("/api/boxoffice/current")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["title"] == "Film A"
        assert data[0]["is_new_release"] is True
        assert data[1]["is_new_release"] is False

    def test_scraper_exception_returns_500(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "")
        with patch("src.api.routes.boxoffice.BoxOfficeService") as mock_cls:
            instance = MagicMock()
            instance.get_current_week_movies.side_effect = RuntimeError("scrape failed")
            mock_cls.return_value = instance
            resp = client.get("/api/boxoffice/current")

        assert resp.status_code == 500

    def test_with_radarr_returns_match_data(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        match_result = MagicMock()
        match_result.is_matched = False
        match_result.confidence = 0.0

        with (
            patch("src.api.routes.boxoffice.BoxOfficeService") as bo_cls,
            patch("src.api.routes.boxoffice.RadarrService") as radarr_cls,
            patch("src.api.routes.boxoffice.MovieMatcher") as matcher_cls,
        ):
            bo_instance = MagicMock()
            bo_instance.get_current_week_movies.return_value = [
                _make_bo_movie(1, "Some Film")
            ]
            bo_cls.return_value = bo_instance

            radarr_instance = MagicMock()
            radarr_instance.get_all_movies.return_value = []
            radarr_cls.return_value = radarr_instance

            matcher_instance = MagicMock()
            matcher_instance.match_movie.return_value = match_result
            matcher_cls.return_value = matcher_instance

            resp = client.get("/api/boxoffice/current")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Some Film"


class TestHistoricalBoxOffice:
    def test_invalid_year_returns_400(self, client):
        resp = client.get("/api/boxoffice/history/1999/W01")
        assert resp.status_code == 400

    def test_invalid_week_returns_400(self, client):
        resp = client.get("/api/boxoffice/history/2024/W99")
        assert resp.status_code == 400

    def test_valid_request_returns_data(self, client):
        with patch("src.api.routes.boxoffice.BoxOfficeService") as mock_cls:
            instance = MagicMock()
            instance.fetch_weekend_box_office.return_value = [
                _make_bo_movie(1, "Historical Film")
            ]
            mock_cls.return_value = instance
            resp = client.get("/api/boxoffice/history/2024/W01")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Historical Film"
        assert data[0]["rank"] == 1

    def test_scraper_error_returns_500(self, client):
        with patch("src.api.routes.boxoffice.BoxOfficeService") as mock_cls:
            instance = MagicMock()
            instance.fetch_weekend_box_office.side_effect = RuntimeError(
                "network error"
            )
            mock_cls.return_value = instance
            resp = client.get("/api/boxoffice/history/2024/W01")

        assert resp.status_code == 500
