import pytest

from app.pipeline.populate import scope_to_filter


def test_popular_scope_has_no_filter():
    assert scope_to_filter("popular") is None


@pytest.mark.parametrize(
    "value", ["22", "fields/22", "https://openalex.org/fields/22"]
)
def test_field_scope_normalizes_to_canonical_url(value):
    assert (
        scope_to_filter(f"field:{value}")
        == "primary_topic.field.id:https://openalex.org/fields/22"
    )


@pytest.mark.parametrize(
    "value", ["1", "domains/1", "https://openalex.org/domains/1"]
)
def test_domain_scope_normalizes_to_canonical_url(value):
    assert (
        scope_to_filter(f"domain:{value}")
        == "primary_topic.domain.id:https://openalex.org/domains/1"
    )


def test_invalid_scope_raises():
    with pytest.raises(ValueError):
        scope_to_filter("nonsense")
