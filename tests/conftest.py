from __future__ import annotations

import os
import tempfile

_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ["DATABASE_URL"] = "sqlite:///" + _db_path.replace("\\", "/")

from app.config import get_settings

get_settings.cache_clear()

import app.db.database as database

database._engine = None
database._SessionFactory = None

import pytest
from fastapi.testclient import TestClient

from app.api.cache import clear_all_caches
from app.api.main import app
from app.db import models as m
from app.db.database import get_session_factory, init_db


def _seed() -> None:
    init_db()
    session = get_session_factory()()
    try:
        session.add_all(
            [
                m.Country(code="NL", iso3="NLD", name="Netherlands", gdp_usd=1.0e12,
                          gdp_year=2022, population=17_000_000, population_year=2022,
                          num_universities=50),
                m.Country(code="US", iso3="USA", name="United States", gdp_usd=2.0e13,
                          gdp_year=2022, population=331_000_000, population_year=2022,
                          num_universities=1000),
                m.Country(code="ZZ", iso3="ZZZ", name="Zedland", gdp_usd=None,
                          gdp_year=None, population=None, population_year=None,
                          num_universities=0),
                m.Field(id="22", name="Engineering", domain_id="3",
                        domain_name="Physical Sciences"),
                m.Field(id="11", name="Agricultural and Biological Sciences",
                        domain_id="1", domain_name="Life Sciences"),
                m.Author(id="A1", display_name="Alice", orcid="0000-0001"),
                m.Author(id="A2", display_name="Bob"),
                m.Author(id="A3", display_name="Carol"),
                m.Paper(id="W1", doi="10.1/w1", title="Deep Learning", publication_year=2015,
                        cited_by_count=1000, referenced_works_count=2, is_open_access=True,
                        oa_status="gold", oa_url="http://oa/w1", is_educational=True,
                        primary_field_id="22", primary_field_name="Engineering",
                        primary_domain_id="3", primary_domain_name="Physical Sciences",
                        abstract="Abstract one", ingested=True),
                m.Paper(id="W2", doi="10.1/w2", title="Neural Networks", publication_year=2016,
                        cited_by_count=500, referenced_works_count=1, is_open_access=False,
                        is_educational=False, primary_field_id="22",
                        primary_field_name="Engineering", primary_domain_id="3",
                        primary_domain_name="Physical Sciences", abstract="Abstract two",
                        ingested=True),
                m.Paper(id="W3", doi="10.1/w3", title="Crop Science", publication_year=2017,
                        cited_by_count=300, referenced_works_count=1, primary_field_id="11",
                        primary_field_name="Agricultural and Biological Sciences",
                        primary_domain_id="1", primary_domain_name="Life Sciences",
                        ingested=True),
                m.Paper(id="W4", doi="10.1/w4", title="Genomics", publication_year=2018,
                        cited_by_count=200, referenced_works_count=0, primary_field_id="11",
                        primary_field_name="Agricultural and Biological Sciences",
                        primary_domain_id="1", primary_domain_name="Life Sciences",
                        ingested=True),
                m.Paper(id="W5", title=None, cited_by_count=50, ingested=False),
                m.PaperAuthor(paper_id="W1", author_id="A1", author_position="first"),
                m.PaperAuthor(paper_id="W1", author_id="A2", author_position="last"),
                m.PaperAuthor(paper_id="W2", author_id="A3", author_position="first"),
                m.PaperCountry(paper_id="W1", country_code="NL"),
                m.PaperCountry(paper_id="W1", country_code="US"),
                m.PaperCountry(paper_id="W2", country_code="NL"),
                m.PaperCountry(paper_id="W3", country_code="US"),
                m.PaperCountry(paper_id="W4", country_code="ZZ"),
                m.PaperReference(citing_id="W1", referenced_id="W2"),
                m.PaperReference(citing_id="W1", referenced_id="W5"),
                m.PaperReference(citing_id="W2", referenced_id="W5"),
                m.PaperReference(citing_id="W3", referenced_id="W1"),
            ]
        )
        session.commit()
    finally:
        session.close()


@pytest.fixture(scope="session", autouse=True)
def seed_db():
    _seed()
    clear_all_caches()
    yield


@pytest.fixture()
def client():
    clear_all_caches()
    return TestClient(app)
