"""Integration tests for the full scheduler update pipeline.

Tests the complete flow driven by BoxarrScheduler.update_box_office():
  fetch box office → match against Radarr library → generate JSON file

All external HTTP calls are replaced with synchronous fakes via monkeypatch
so the test suite stays fast and offline.  The JSON generator is allowed to
run for real so we verify the file is actually written and parseable.
"""

import asyncio
import json
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock

import pytest

from src.core.boxoffice import BoxOfficeMovie
from src.core.matcher import MovieMatcher
from src.core.models import MovieStatus
from src.core.radarr import RadarrMovie
from src.core.scheduler import BoxarrScheduler
from src.utils.config import Settings


# ---------------------------------------------------------------------------
# Fake service helpers
# ---------------------------------------------------------------------------


def _radarr_movie(id: int, title: str, year: int, has_file: bool = True) -> RadarrMovie:
    return RadarrMovie(
        id=id,
        title=title,
        tmdbId=id * 100,
        year=year,
        status=MovieStatus.RELEASED,
        hasFile=has_file,
    )


RADARR_LIBRARY = [
    _radarr_movie(1, "Avatar: The Way of Water", 2022, has_file=True),
    _radarr_movie(2, "Top Gun: Maverick", 2022, has_file=True),
    _radarr_movie(3, "Spider-Man: No Way Home", 2021, has_file=True),
    _radarr_movie(4, "The Batman", 2022, has_file=False),
    _radarr_movie(5, "Doctor Strange in the Multiverse of Madness", 2022, has_file=False),
]

BOX_OFFICE = [
    BoxOfficeMovie(rank=1, title="Avatar The Way of Water"),
    BoxOfficeMovie(rank=2, title="Top Gun Maverick"),
    BoxOfficeMovie(rank=3, title="Spider-Man No Way Home"),
    BoxOfficeMovie(rank=4, title="The Batman"),
    BoxOfficeMovie(rank=5, title="A Brand New Movie Not In Library"),
]


class _FakeBoxOfficeService:
    def fetch_weekend_box_office(self, year: int, week: int, limit: int = 10):
        return BOX_OFFICE[:limit]

    def get_weekend_dates(self):
        from datetime import datetime
        friday = datetime(2022, 12, 16)
        sunday = datetime(2022, 12, 18)
        return friday, sunday, 2022, 50


class _FakeQualityProfile:
    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name


class _FakeRadarrService:
    def get_all_movies(self):
        return RADARR_LIBRARY

    def get_quality_profiles(self):
        return [_FakeQualityProfile(1, "HD-1080p"), _FakeQualityProfile(2, "Ultra-HD")]

    def get_root_folder_paths(self):
        return ["/movies"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def configured_tmp(tmp_path, monkeypatch):
    """Point BOXARR_DATA_DIRECTORY at tmp_path and reload settings."""
    monkeypatch.setenv("BOXARR_DATA_DIRECTORY", str(tmp_path))
    (tmp_path / "weekly_pages").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    Settings.reload_from_file(tmp_path / "nonexistent.yaml")
    yield tmp_path
    Settings.reload_from_file(tmp_path / "nonexistent.yaml")


@pytest.fixture
def patched_scheduler(configured_tmp, monkeypatch):
    """Build a BoxarrScheduler with fakes injected for all external calls."""
    import src.core.scheduler as sched_module

    # Replace the module-level function used to fetch all Radarr movies
    fake_radarr = _FakeRadarrService()

    def fake_get_all_movies(radarr_service, ignore_cache=False):
        return RADARR_LIBRARY

    monkeypatch.setattr(sched_module, "get_all_movies_with_optional_cache_bypass", fake_get_all_movies)

    # Replace refresh_weekly_data_from_radarr — not under test here
    monkeypatch.setattr(
        sched_module,
        "refresh_weekly_data_from_radarr",
        lambda **kwargs: {"weeks_updated": 0, "movies_refreshed": 0, "movies_linked": 0},
    )

    scheduler = BoxarrScheduler(
        boxoffice_service=_FakeBoxOfficeService(),
        radarr_service=fake_radarr,
        matcher=MovieMatcher(min_confidence=0.8),
    )
    return scheduler, configured_tmp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSchedulerUpdatePipeline:
    def test_json_file_is_written(self, patched_scheduler):
        """update_box_office must write a JSON file to weekly_pages/."""
        scheduler, data_dir = patched_scheduler
        result = asyncio.run(scheduler.update_box_office(year=2022, week=50))

        expected = data_dir / "weekly_pages" / "2022W50.json"
        assert expected.exists(), f"Expected JSON at {expected}"

    def test_json_file_is_valid(self, patched_scheduler):
        """The written JSON must parse without error."""
        scheduler, data_dir = patched_scheduler
        asyncio.run(scheduler.update_box_office(year=2022, week=50))

        path = data_dir / "weekly_pages" / "2022W50.json"
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_result_dict_structure(self, patched_scheduler):
        """update_box_office must return a dict with the documented keys."""
        scheduler, data_dir = patched_scheduler
        result = asyncio.run(scheduler.update_box_office(year=2022, week=50))

        assert isinstance(result, dict)
        for key in ("total_count", "matched_count", "unmatched_count"):
            assert key in result, f"Missing key '{key}' in result"

    def test_match_counts_are_consistent(self, patched_scheduler):
        """matched + unmatched must equal total."""
        scheduler, _ = patched_scheduler
        result = asyncio.run(scheduler.update_box_office(year=2022, week=50))

        assert result["matched_count"] + result["unmatched_count"] == result["total_count"]

    def test_known_library_movies_are_matched(self, patched_scheduler):
        """At least 3 of the 4 library movies in the box office list must match."""
        scheduler, _ = patched_scheduler
        result = asyncio.run(scheduler.update_box_office(year=2022, week=50))

        # BOX_OFFICE has 5 entries; 4 are in RADARR_LIBRARY, 1 is unknown
        assert result["matched_count"] >= 3

    def test_unmatched_movie_not_in_library(self, patched_scheduler):
        """The one fake title in BOX_OFFICE must end up unmatched."""
        scheduler, _ = patched_scheduler
        result = asyncio.run(scheduler.update_box_office(year=2022, week=50))

        assert result["unmatched_count"] >= 1

    def test_idempotent_reruns_overwrite_file(self, patched_scheduler):
        """Running update_box_office twice for the same week must not raise."""
        scheduler, data_dir = patched_scheduler
        asyncio.run(scheduler.update_box_office(year=2022, week=50))
        asyncio.run(scheduler.update_box_office(year=2022, week=50))

        path = data_dir / "weekly_pages" / "2022W50.json"
        assert path.exists()
        with open(path) as f:
            json.load(f)  # must still be valid JSON after second write


class TestSchedulerWithEmptyLibrary:
    def test_all_unmatched_when_library_empty(self, configured_tmp, monkeypatch):
        """When Radarr returns no movies every box office entry is unmatched."""
        import src.core.scheduler as sched_module

        monkeypatch.setattr(
            sched_module,
            "get_all_movies_with_optional_cache_bypass",
            lambda *a, **kw: [],
        )
        monkeypatch.setattr(
            sched_module,
            "refresh_weekly_data_from_radarr",
            lambda **kwargs: {},
        )

        scheduler = BoxarrScheduler(
            boxoffice_service=_FakeBoxOfficeService(),
            radarr_service=_FakeRadarrService(),
            matcher=MovieMatcher(min_confidence=0.8),
        )

        result = asyncio.run(scheduler.update_box_office(year=2022, week=51))

        assert result["matched_count"] == 0
        assert result["unmatched_count"] == result["total_count"]
