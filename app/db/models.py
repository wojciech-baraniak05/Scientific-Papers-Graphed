from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    JSON,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.mysql import BIGINT, MEDIUMTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

AbstractText = Text().with_variant(MEDIUMTEXT(), "mysql")
BigIntType = Integer().with_variant(BIGINT(), "mysql")


class Base(DeclarativeBase):
    pass


class Country(Base):
    __tablename__ = "countries"

    code: Mapped[str] = mapped_column(String(2), primary_key=True)
    iso3: Mapped[str | None] = mapped_column(String(3))
    name: Mapped[str | None] = mapped_column(String(128))
    gdp_usd: Mapped[float | None] = mapped_column(Double)
    gdp_year: Mapped[int | None] = mapped_column(SmallInteger)
    population: Mapped[int | None] = mapped_column(BigIntType)
    population_year: Mapped[int | None] = mapped_column(SmallInteger)
    num_universities: Mapped[int | None] = mapped_column(Integer)


class University(Base):
    __tablename__ = "universities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)
    country_name: Mapped[str | None] = mapped_column(String(128))
    web_page: Mapped[str | None] = mapped_column(String(512))
    domains: Mapped[list | None] = mapped_column(JSON)


class Field(Base):
    __tablename__ = "fields"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255))
    domain_id: Mapped[str | None] = mapped_column(String(20))
    domain_name: Mapped[str | None] = mapped_column(String(255))


class Author(Base):
    __tablename__ = "authors"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(512))
    orcid: Mapped[str | None] = mapped_column(String(64))


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(512))
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)
    type: Mapped[str | None] = mapped_column(String(32))
    ror: Mapped[str | None] = mapped_column(String(255))


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    doi: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(Text)
    publication_year: Mapped[int | None] = mapped_column(SmallInteger)
    cited_by_count: Mapped[int | None] = mapped_column(Integer, index=True)
    referenced_works_count: Mapped[int | None] = mapped_column(Integer)
    is_open_access: Mapped[bool | None] = mapped_column(Boolean)
    oa_status: Mapped[str | None] = mapped_column(String(20))
    oa_url: Mapped[str | None] = mapped_column(String(1024))
    is_educational: Mapped[bool | None] = mapped_column(Boolean)
    primary_field_id: Mapped[str | None] = mapped_column(String(20), index=True)
    primary_field_name: Mapped[str | None] = mapped_column(String(255))
    primary_domain_id: Mapped[str | None] = mapped_column(String(20), index=True)
    primary_domain_name: Mapped[str | None] = mapped_column(String(255))
    abstract: Mapped[str | None] = mapped_column(AbstractText)
    ingested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)


class PaperAuthor(Base):
    __tablename__ = "paper_authors"

    paper_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    author_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("authors.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    author_position: Mapped[str | None] = mapped_column(String(16))


class PaperInstitution(Base):
    __tablename__ = "paper_institutions"

    paper_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    institution_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("institutions.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class PaperCountry(Base):
    __tablename__ = "paper_countries"

    paper_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    country_code: Mapped[str] = mapped_column(
        String(2), ForeignKey("countries.code", ondelete="CASCADE"), primary_key=True, index=True
    )


class PaperReference(Base):
    __tablename__ = "paper_references"

    citing_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    referenced_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    papers_ingested: Mapped[int | None] = mapped_column(Integer)
    db_size_bytes: Mapped[int | None] = mapped_column(BigIntType)
    status: Mapped[str | None] = mapped_column(String(32))
    message: Mapped[str | None] = mapped_column(Text)
