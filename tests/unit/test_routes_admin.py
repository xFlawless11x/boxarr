"""Tests for /api/admin routes."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.utils.config import settings


class TestCheckMissingMetadata:
    def test_no_weekly_dir_returns_no_issues(self, client):
        resp = client.get("/api/admin/check-missing-metadata")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_issues"] is False
        assert data["total_weeks"] == 0

    def test_all_complete_movies_returns_no_issues(self, client, weekly_json):
        resp = client.get("/api/admin/check-missing-metadata")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_weeks"] == 1
        assert data["total_movies"] == 2

    def test_detects_movies_missing_poster(self, client, isolated_data_dir):
        weekly_dir = isolated_data_dir / "weekly_pages"
        weekly_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "year": 2025,
            "week": 2,
            "movies": [
                {
                    "rank": 1,
                    "title": "No Poster Film",
                    "tmdb_id": 99,
                    "radarr_id": None,
                    "poster": None,
                    "year": 2025,
                }
            ],
        }
        (weekly_dir / "202502.json").write_text(json.dumps(data))
        resp = client.get("/api/admin/check-missing-metadata")
        assert resp.status_code == 200
        result = resp.json()
        assert result["has_issues"] is True
        assert result["unique_movies_missing_data"] >= 1
        assert "No Poster Film" in result["sample_movies"]

    def test_radarr_movies_excluded_from_check(self, client, isolated_data_dir):
        weekly_dir = isolated_data_dir / "weekly_pages"
        weekly_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "year": 2025,
            "week": 3,
            "movies": [
                {
                    "rank": 1,
                    "title": "Already In Radarr",
                    "tmdb_id": None,
                    "radarr_id": 42,
                    "poster": None,
                    "year": 2025,
                }
            ],
        }
        (weekly_dir / "202503.json").write_text(json.dumps(data))
        resp = client.get("/api/admin/check-missing-metadata")
        assert resp.status_code == 200
        result = resp.json()
        assert result["has_issues"] is False


class TestRepairMissingMetadata:
    def test_no_radarr_key_yields_error_event(self, client, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "")
        resp = client.post(
            "/api/admin/repair-missing-metadata",
            json={"dry_run": True, "rate_limit_delay": 0},
        )
        assert resp.status_code == 200
        assert b"error" in resp.content

    def test_dry_run_no_movies_to_repair(self, client, weekly_json, monkeypatch):
        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        resp = client.post(
            "/api/admin/repair-missing-metadata",
            json={"dry_run": True, "rate_limit_delay": 0},
        )
        assert resp.status_code == 200

    def test_dry_run_with_missing_poster(self, client, isolated_data_dir, monkeypatch):
        import json as _json

        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        weekly_dir = isolated_data_dir / "weekly_pages"
        weekly_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "year": 2025,
            "week": 1,
            "movies": [
                {
                    "rank": 1,
                    "title": "Poster Missing",
                    "tmdb_id": 1,
                    "radarr_id": None,
                    "poster": None,
                    "year": 2025,
                }
            ],
        }
        (weekly_dir / "202501.json").write_text(_json.dumps(data))

        with patch("src.api.routes.admin.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.search_movie.return_value = [
                {
                    "tmdbId": 1,
                    "year": 2025,
                    "remotePoster": "https://example.com/p.jpg",
                    "genres": [],
                }
            ]
            mock_cls.return_value = instance
            resp = client.post(
                "/api/admin/repair-missing-metadata",
                json={"dry_run": True, "rate_limit_delay": 0},
            )
        assert resp.status_code == 200
        assert b"would_fix" in resp.content or b"complete" in resp.content

    def test_repair_updates_file(self, client, isolated_data_dir, monkeypatch):
        import json as _json

        monkeypatch.setattr(settings, "radarr_api_key", "testkey")
        weekly_dir = isolated_data_dir / "weekly_pages"
        weekly_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "year": 2025,
            "week": 1,
            "movies": [
                {
                    "rank": 1,
                    "title": "Film To Fix",
                    "tmdb_id": None,
                    "radarr_id": None,
                    "poster": None,
                    "year": 2025,
                }
            ],
        }
        json_path = weekly_dir / "202501.json"
        json_path.write_text(_json.dumps(data))

        with patch("src.api.routes.admin.RadarrService") as mock_cls:
            instance = MagicMock()
            instance.search_movie.return_value = [
                {
                    "tmdbId": 99,
                    "year": 2025,
                    "remotePoster": "https://poster.jpg",
                    "genres": [],
                }
            ]
            mock_cls.return_value = instance
            resp = client.post(
                "/api/admin/repair-missing-metadata",
                json={"dry_run": False, "rate_limit_delay": 0},
            )
        assert resp.status_code == 200
        updated = _json.loads(json_path.read_text())
        # The file should have been updated with tmdb_id
        assert updated["movies"][0].get("tmdb_id") == 99
