from __future__ import annotations

from app.repository.countries import (
    _ratio_per_100b_gdp,
    _ratio_per_million_capita,
    _ratio_per_university,
)


def test_ratio_per_100b_gdp():
    assert _ratio_per_100b_gdp(2, 1.0e12) == 0.2
    assert _ratio_per_100b_gdp(10, 5.0e11) == 2.0


def test_ratio_per_100b_gdp_guards():
    assert _ratio_per_100b_gdp(2, 0) is None
    assert _ratio_per_100b_gdp(2, None) is None


def test_ratio_per_university():
    assert _ratio_per_university(2, 50) == 0.04


def test_ratio_per_university_guards():
    assert _ratio_per_university(2, 0) is None
    assert _ratio_per_university(2, None) is None


def test_ratio_per_million_capita():
    assert _ratio_per_million_capita(2, 17_000_000) == 0.118


def test_ratio_per_million_capita_guards():
    assert _ratio_per_million_capita(2, 0) is None
    assert _ratio_per_million_capita(2, None) is None
