"""Tests for src/core/models.py."""

from datetime import datetime

import pytest

from src.core.models import (
    MovieCard,
    MovieStatus,
    WeeklyBoxOfficeEntry,
    WeeklyBoxOfficeReport,
)


class TestMovieStatus:
    def test_has_file_returns_downloaded(self):
        assert MovieStatus.from_radarr("released", True) == MovieStatus.DOWNLOADED

    def test_has_file_overrides_any_status(self):
        for status in ("tba", "announced", "inCinemas", "deleted"):
            assert MovieStatus.from_radarr(status, True) == MovieStatus.DOWNLOADED

    def test_released_no_file_returns_missing(self):
        assert MovieStatus.from_radarr("released", False) == MovieStatus.MISSING

    def test_known_status_no_file_returns_enum(self):
        assert MovieStatus.from_radarr("tba", False) == MovieStatus.TBA
        assert MovieStatus.from_radarr("announced", False) == MovieStatus.ANNOUNCED
        assert MovieStatus.from_radarr("inCinemas", False) == MovieStatus.IN_CINEMAS
        assert MovieStatus.from_radarr("deleted", False) == MovieStatus.DELETED

    def test_unknown_status_returns_announced(self):
        assert MovieStatus.from_radarr("bogusStatus", False) == MovieStatus.ANNOUNCED


class TestMovieCard:
    def _make(self, **kwargs):
        defaults = {"tmdb_id": 1, "title": "Test Movie"}
        defaults.update(kwargs)
        return MovieCard(**defaults)

    def test_imdb_url_with_id(self):
        card = self._make(imdb_id="tt1234567")
        assert card.imdb_url == "https://www.imdb.com/title/tt1234567/"

    def test_imdb_url_without_id(self):
        card = self._make()
        assert card.imdb_url is None

    def test_status_color_no_status(self):
        card = self._make()
        assert card.status_color == "#888"

    def test_status_color_downloaded(self):
        card = self._make(radarr_status=MovieStatus.DOWNLOADED)
        assert card.status_color == "#4CAF50"

    def test_status_color_missing(self):
        card = self._make(radarr_status=MovieStatus.MISSING)
        assert card.status_color == "#FF9800"

    def test_status_color_in_cinemas(self):
        card = self._make(radarr_status=MovieStatus.IN_CINEMAS)
        assert card.status_color == "#2196F3"

    def test_status_color_announced(self):
        card = self._make(radarr_status=MovieStatus.ANNOUNCED)
        assert card.status_color == "#9C27B0"

    def test_status_color_deleted(self):
        card = self._make(radarr_status=MovieStatus.DELETED)
        assert card.status_color == "#F44336"

    def test_to_dict_round_trip(self):
        card = MovieCard(
            tmdb_id=27205,
            title="Inception",
            year=2010,
            poster_url="https://example.com/poster.jpg",
            overview="A dream within a dream.",
            genres=["Action", "Sci-Fi"],
            runtime=148,
            imdb_id="tt1375666",
            radarr_id=101,
            radarr_status=MovieStatus.DOWNLOADED,
            quality_profile="HD-1080p",
            monitored=True,
        )
        d = card.to_dict()
        assert d["tmdb_id"] == 27205
        assert d["radarr_status"] == "downloaded"
        assert d["monitored"] is True

    def test_from_dict_with_status(self):
        data = {
            "tmdb_id": 1,
            "title": "Film",
            "radarr_status": "missing",
        }
        card = MovieCard.from_dict(data)
        assert card.radarr_status == MovieStatus.MISSING

    def test_from_dict_without_status(self):
        data = {"tmdb_id": 2, "title": "Film 2"}
        card = MovieCard.from_dict(data)
        assert card.radarr_status is None

    def test_from_dict_defaults(self):
        card = MovieCard.from_dict({"tmdb_id": 3, "title": "Film 3"})
        assert card.genres == []
        assert card.monitored is False
        assert card.year is None

    def test_to_dict_no_status(self):
        card = self._make()
        d = card.to_dict()
        assert d["radarr_status"] is None


class TestWeeklyBoxOfficeEntry:
    def _make_card(self):
        return MovieCard(tmdb_id=1, title="Test")

    def test_formatted_weekend_gross_present(self):
        entry = WeeklyBoxOfficeEntry(
            rank=1, movie_card=self._make_card(), weekend_gross=1234567
        )
        assert entry.formatted_weekend_gross == "$1,234,567"

    def test_formatted_weekend_gross_absent(self):
        entry = WeeklyBoxOfficeEntry(rank=1, movie_card=self._make_card())
        assert entry.formatted_weekend_gross == "N/A"

    def test_formatted_total_gross_present(self):
        entry = WeeklyBoxOfficeEntry(
            rank=1, movie_card=self._make_card(), total_gross=9000000
        )
        assert entry.formatted_total_gross == "$9,000,000"

    def test_formatted_total_gross_absent(self):
        entry = WeeklyBoxOfficeEntry(rank=1, movie_card=self._make_card())
        assert entry.formatted_total_gross == "N/A"

    def test_to_dict(self):
        card = self._make_card()
        entry = WeeklyBoxOfficeEntry(
            rank=2, movie_card=card, weekend_gross=500000, is_new_release=True
        )
        d = entry.to_dict()
        assert d["rank"] == 2
        assert d["weekend_gross"] == 500000
        assert d["is_new_release"] is True
        assert "movie" in d


class TestWeeklyBoxOfficeReport:
    def _make_report(self, year=2025, week=1, entries=None):
        return WeeklyBoxOfficeReport(
            year=year,
            week=week,
            generated_at=datetime(2025, 1, 10),
            entries=entries or [],
        )

    def test_date_range_returns_tuple(self):
        report = self._make_report(year=2025, week=1)
        start, end = report.date_range
        assert start <= end

    def test_date_range_end_is_6_days_after_start(self):
        report = self._make_report(year=2025, week=10)
        from datetime import timedelta

        start, end = report.date_range
        assert end - start == timedelta(days=6)

    def test_formatted_date_range_is_string(self):
        report = self._make_report(year=2025, week=1)
        s = report.formatted_date_range
        assert isinstance(s, str)
        assert "2025" in s

    def test_to_dict(self):
        report = self._make_report()
        d = report.to_dict()
        assert d["year"] == 2025
        assert d["week"] == 1
        assert "generated_at" in d
        assert "entries" in d

    def test_from_dict_empty_entries(self):
        d = {
            "year": 2025,
            "week": 2,
            "generated_at": "2025-01-15T10:00:00",
            "entries": [],
        }
        report = WeeklyBoxOfficeReport.from_dict(d)
        assert report.year == 2025
        assert report.entries == []

    def test_from_dict_with_entry(self):
        d = {
            "year": 2025,
            "week": 2,
            "generated_at": "2025-01-15T10:00:00",
            "entries": [
                {
                    "rank": 1,
                    "movie": {"tmdb_id": 1, "title": "A Film"},
                    "weekend_gross": 1000000,
                    "is_new_release": True,
                }
            ],
        }
        report = WeeklyBoxOfficeReport.from_dict(d)
        assert len(report.entries) == 1
        assert report.entries[0].rank == 1
