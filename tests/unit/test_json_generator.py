"""Tests for src/core/json_generator.py."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.boxoffice import BoxOfficeMovie
from src.core.json_generator import WeeklyDataGenerator
from src.core.matcher import MatchResult
from src.core.models import MovieStatus
from src.utils.config import settings


def _make_bo_movie(rank=1, title="Test Movie", gross=1_000_000):
    return BoxOfficeMovie(rank=rank, title=title, weekend_gross=gross)


def _make_unmatched(rank=1, title="Unmatched Film"):
    bo = _make_bo_movie(rank=rank, title=title)
    return MatchResult(box_office_movie=bo, radarr_movie=None, confidence=0.0)


def _make_matched(rank=1, title="Matched Film", has_file=False, status="released", is_available=True):
    bo = _make_bo_movie(rank=rank, title=title)
    movie = MagicMock()
    movie.id = 100
    movie.title = title
    movie.hasFile = has_file
    movie.status = MovieStatus(status)
    movie.isAvailable = is_available
    movie.qualityProfileId = 1
    movie.year = 2024
    movie.genres = ["Action", "Drama"]
    movie.overview = "A test movie."
    movie.imdbId = "tt0000001"
    movie.tmdbId = 12345
    movie.original_language = "en"
    movie.poster_url = "https://example.com/poster.jpg"
    return MatchResult(box_office_movie=bo, radarr_movie=movie, confidence=0.95)


class TestWeeklyDataGenerator:
    def test_creates_output_dir(self, isolated_data_dir):
        gen = WeeklyDataGenerator()
        assert gen.output_dir.exists()

    def test_generate_unmatched_no_service(self, isolated_data_dir):
        gen = WeeklyDataGenerator(radarr_service=None)
        path = gen.generate_weekly_data([_make_unmatched()], 2025, 1)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["movies"][0]["status"] == "Not in Radarr"

    def test_generate_matched_downloaded(self, isolated_data_dir):
        result = _make_matched(has_file=True)
        gen = WeeklyDataGenerator(radarr_service=None)
        path = gen.generate_weekly_data([result], 2025, 1)
        data = json.loads(path.read_text())
        assert data["movies"][0]["status"] == "Downloaded"

    def test_generate_matched_missing(self, isolated_data_dir):
        result = _make_matched(has_file=False, status="released", is_available=True)
        gen = WeeklyDataGenerator(radarr_service=None)
        path = gen.generate_weekly_data([result], 2025, 1)
        data = json.loads(path.read_text())
        assert data["movies"][0]["status"] == "Missing"

    def test_generate_matched_in_cinemas(self, isolated_data_dir):
        result = _make_matched(has_file=False, status="inCinemas", is_available=False)
        gen = WeeklyDataGenerator(radarr_service=None)
        path = gen.generate_weekly_data([result], 2025, 1)
        data = json.loads(path.read_text())
        assert data["movies"][0]["status"] == "In Cinemas"

    def test_generate_matched_pending(self, isolated_data_dir):
        result = _make_matched(has_file=False, status="announced", is_available=False)
        gen = WeeklyDataGenerator(radarr_service=None)
        path = gen.generate_weekly_data([result], 2025, 1)
        data = json.loads(path.read_text())
        assert data["movies"][0]["status"] == "Pending"

    def test_generate_with_quality_profiles(self, isolated_data_dir):
        profile = MagicMock()
        profile.id = 1
        profile.name = "HD-1080p"
        svc = MagicMock()
        svc.get_quality_profiles.return_value = [profile]
        result = _make_matched(has_file=True)
        gen = WeeklyDataGenerator(radarr_service=svc)
        path = gen.generate_weekly_data([result], 2025, 1)
        data = json.loads(path.read_text())
        assert data["movies"][0]["quality_profile_name"] == "HD-1080p"

    def test_generate_quality_profiles_error(self, isolated_data_dir):
        svc = MagicMock()
        svc.get_quality_profiles.side_effect = RuntimeError("API error")
        gen = WeeklyDataGenerator(radarr_service=svc)
        path = gen.generate_weekly_data([_make_unmatched()], 2025, 1)
        assert path.exists()

    def test_generate_tmdb_enrichment_for_unmatched(self, isolated_data_dir):
        svc = MagicMock()
        svc.get_quality_profiles.return_value = []
        svc.search_movie.return_value = [
            {
                "tmdbId": 99999,
                "year": 2024,
                "overview": "A short description.",
                "remotePoster": "https://example.com/p.jpg",
                "imdbId": "tt0001111",
                "genres": ["Comedy"],
                "originalLanguage": {"name": "English"},
            }
        ]
        gen = WeeklyDataGenerator(radarr_service=svc)
        path = gen.generate_weekly_data([_make_unmatched()], 2025, 1)
        data = json.loads(path.read_text())
        assert data["movies"][0]["tmdb_id"] == 99999

    def test_generate_tmdb_enrichment_error_continues(self, isolated_data_dir):
        svc = MagicMock()
        svc.get_quality_profiles.return_value = []
        svc.search_movie.side_effect = RuntimeError("tmdb error")
        gen = WeeklyDataGenerator(radarr_service=svc)
        path = gen.generate_weekly_data([_make_unmatched()], 2025, 1)
        assert path.exists()

    def test_generated_metadata_structure(self, isolated_data_dir):
        gen = WeeklyDataGenerator(radarr_service=None)
        path = gen.generate_weekly_data([_make_unmatched()], 2025, 5)
        data = json.loads(path.read_text())
        assert data["year"] == 2025
        assert data["week"] == 5
        assert "generated_at" in data
        assert "friday" in data
        assert "sunday" in data

    def test_ultra_hd_profile_detection(self, isolated_data_dir, monkeypatch):
        monkeypatch.setattr(settings, "boxarr_features_quality_upgrade", True)
        monkeypatch.setattr(settings, "radarr_quality_profile_upgrade", "")
        ultra = MagicMock()
        ultra.id = 5
        ultra.name = "Ultra-HD"
        normal = MagicMock()
        normal.id = 1
        normal.name = "HD-1080p"
        svc = MagicMock()
        svc.get_quality_profiles.return_value = [ultra, normal]
        result = _make_matched(has_file=True)
        result.radarr_movie.qualityProfileId = 1  # normal profile
        gen = WeeklyDataGenerator(radarr_service=svc)
        path = gen.generate_weekly_data([result], 2025, 1)
        data = json.loads(path.read_text())
        assert data["movies"][0]["can_upgrade_quality"] is True

    def test_long_overview_truncated(self, isolated_data_dir):
        result = _make_matched(has_file=True)
        result.radarr_movie.overview = "x" * 200
        gen = WeeklyDataGenerator(radarr_service=None)
        path = gen.generate_weekly_data([result], 2025, 1)
        data = json.loads(path.read_text())
        assert len(data["movies"][0]["overview"]) <= 155  # 150 + "..."
