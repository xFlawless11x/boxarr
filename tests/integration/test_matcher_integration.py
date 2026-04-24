"""Integration tests for the full movie matching pipeline.

Tests the complete flow: BoxOfficeMovie list → MovieMatcher.match_batch()
→ MatchResult list, using a realistic Radarr library fixture that mirrors
what a typical home-media user would have. Complements the unit tests in
tests/unit/test_matcher.py which cover individual matching strategies.
"""

import pytest

from src.core.boxoffice import BoxOfficeMovie
from src.core.matcher import MovieMatcher
from src.core.models import MovieStatus
from src.core.radarr import RadarrMovie


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _movie(id: int, title: str, year: int, tmdb_id: int | None = None) -> RadarrMovie:
    return RadarrMovie(
        id=id,
        title=title,
        tmdbId=tmdb_id or id * 100,
        year=year,
        status=MovieStatus.RELEASED,
        hasFile=True,
    )


LIBRARY = [
    _movie(1, "The Dark Knight", 2008),
    _movie(2, "Inception", 2010),
    _movie(3, "Interstellar", 2014),
    _movie(4, "Top Gun: Maverick", 2022),
    _movie(5, "Avatar: The Way of Water", 2022),
    _movie(6, "Spider-Man: No Way Home", 2021),
    _movie(7, "Doctor Strange in the Multiverse of Madness", 2022),
    _movie(8, "Thor: Love and Thunder", 2022),
    _movie(9, "The Batman", 2022),
    _movie(10, "Everything Everywhere All at Once", 2022),
    _movie(11, "Scream", 2022),
    _movie(12, "Scream", 1996),
    _movie(13, "Frozen II", 2019),
    _movie(14, "Dune", 2021),
    _movie(15, "The Menu", 2022),
]


@pytest.fixture
def matcher() -> MovieMatcher:
    m = MovieMatcher(min_confidence=0.8)
    m.build_movie_index(LIBRARY)
    return m


# ---------------------------------------------------------------------------
# Full-batch pipeline tests
# ---------------------------------------------------------------------------


class TestMatcherFullPipeline:
    def test_match_rate_realistic_top_ten(self, matcher):
        """A top-10 list where 8 of 10 titles exist in the library should match ≥7."""
        box_office = [
            BoxOfficeMovie(rank=1, title="Avatar The Way of Water"),
            BoxOfficeMovie(rank=2, title="Top Gun Maverick"),
            BoxOfficeMovie(rank=3, title="Spider-Man No Way Home"),
            BoxOfficeMovie(rank=4, title="The Batman"),
            BoxOfficeMovie(rank=5, title="Doctor Strange Multiverse of Madness"),
            BoxOfficeMovie(rank=6, title="Everything Everywhere All at Once"),
            BoxOfficeMovie(rank=7, title="Scream"),
            BoxOfficeMovie(rank=8, title="The Menu"),
            BoxOfficeMovie(rank=9, title="Blank Budget Sequel That Doesnt Exist"),
            BoxOfficeMovie(rank=10, title="Another Fake Title 2022"),
        ]

        results = matcher.match_batch(box_office, LIBRARY)

        assert len(results) == 10
        matched = [r for r in results if r.is_matched]
        assert len(matched) >= 7, f"Expected ≥7 matches, got {len(matched)}"

    def test_rank_order_preserved(self, matcher):
        """match_batch must return results in the same rank order as input."""
        box_office = [
            BoxOfficeMovie(rank=1, title="Inception"),
            BoxOfficeMovie(rank=2, title="Interstellar"),
            BoxOfficeMovie(rank=3, title="The Dark Knight"),
        ]

        results = matcher.match_batch(box_office, LIBRARY)

        assert [r.box_office_movie.rank for r in results] == [1, 2, 3]

    def test_all_matched_have_radarr_movie(self, matcher):
        """Every matched result must carry a non-None radarr_movie."""
        box_office = [BoxOfficeMovie(rank=i + 1, title=m.title) for i, m in enumerate(LIBRARY[:5])]
        results = matcher.match_batch(box_office, LIBRARY)

        for r in results:
            if r.is_matched:
                assert r.radarr_movie is not None
                assert r.radarr_movie.id > 0

    def test_unmatched_results_have_zero_confidence(self, matcher):
        """Movies not in the library must come back with confidence=0 and no radarr_movie."""
        box_office = [
            BoxOfficeMovie(rank=1, title="A Film That Absolutely Does Not Exist 9999"),
        ]
        results = matcher.match_batch(box_office, LIBRARY)

        assert len(results) == 1
        assert not results[0].is_matched
        assert results[0].confidence == 0.0
        assert results[0].radarr_movie is None


# ---------------------------------------------------------------------------
# Specific title-transformation tests (realistic box-office title variations)
# ---------------------------------------------------------------------------


class TestTitleNormalisationPipeline:
    def test_subtitle_colon_stripped(self, matcher):
        """'Top Gun Maverick' (no colon) → 'Top Gun: Maverick'."""
        result = matcher.match_single("Top Gun Maverick", LIBRARY)
        assert result.is_matched
        assert result.radarr_movie.title == "Top Gun: Maverick"

    def test_avatar_subtitle_variant(self, matcher):
        """'Avatar The Way of Water' without colon should still match."""
        result = matcher.match_single("Avatar The Way of Water", LIBRARY)
        assert result.is_matched
        assert result.radarr_movie.title == "Avatar: The Way of Water"

    def test_roman_numeral_sequel(self, matcher):
        """'Frozen 2' should match 'Frozen II'."""
        result = matcher.match_single("Frozen 2", LIBRARY)
        assert result.is_matched
        assert result.radarr_movie.title == "Frozen II"

    def test_article_the_dropped(self, matcher):
        """'Dark Knight' without leading 'The' should match 'The Dark Knight'."""
        result = matcher.match_single("Dark Knight", LIBRARY)
        assert result.is_matched
        assert result.radarr_movie.title == "The Dark Knight"

    def test_duplicate_title_different_years(self, matcher):
        """'Scream' exists in 1996 and 2022; matcher should return one of them."""
        result = matcher.match_single("Scream", LIBRARY)
        assert result.is_matched
        assert result.radarr_movie.title == "Scream"

    def test_long_title_partial_match(self, matcher):
        """'Doctor Strange Multiverse of Madness' (truncated) should match the full title."""
        result = matcher.match_single("Doctor Strange Multiverse of Madness", LIBRARY)
        assert result.is_matched
        assert "Doctor Strange" in result.radarr_movie.title


# ---------------------------------------------------------------------------
# Empty / edge-case pipeline
# ---------------------------------------------------------------------------


class TestMatcherPipelineEdgeCases:
    def test_empty_box_office_list(self, matcher):
        results = matcher.match_batch([], LIBRARY)
        assert results == []

    def test_empty_library(self):
        m = MovieMatcher()
        m.build_movie_index([])
        results = m.match_batch(
            [BoxOfficeMovie(rank=1, title="Inception")], []
        )
        assert len(results) == 1
        assert not results[0].is_matched

    def test_single_movie_exact_match(self, matcher):
        result = matcher.match_single("Inception", LIBRARY)
        assert result.is_matched
        assert result.radarr_movie.title == "Inception"
        assert result.confidence == 1.0
        assert result.match_method == "exact"
