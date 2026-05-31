from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class GraphDirection(str, Enum):
    cites = "cites"
    cited_by = "cited_by"


class RankingOrderBy(str, Enum):
    citations = "citations"
    papers = "papers"
    universities = "universities"
    gdp = "gdp"
    population = "population"
    papers_per_gdp = "papers_per_gdp"
    papers_per_university = "papers_per_university"
    papers_per_capita = "papers_per_capita"


class HealthResponse(BaseModel):
    status: str
    database: str


class AuthorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str | None = None
    orcid: str | None = None
    author_position: str | None = None


class PaperDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    doi: str | None = None
    title: str | None = None
    publication_year: int | None = None
    cited_by_count: int | None = None
    referenced_works_count: int | None = None
    is_open_access: bool | None = None
    oa_status: str | None = None
    oa_url: str | None = None
    is_educational: bool | None = None
    primary_field_id: str | None = None
    primary_field_name: str | None = None
    primary_domain_id: str | None = None
    primary_domain_name: str | None = None
    abstract: str | None = None
    authors: list[AuthorOut] = []


class PaperSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None = None
    doi: str | None = None
    cited_by_count: int | None = None
    publication_year: int | None = None
    is_open_access: bool | None = None
    primary_field_id: str | None = None
    primary_field_name: str | None = None
    primary_domain_id: str | None = None
    primary_domain_name: str | None = None


class GraphFocus(BaseModel):
    id: str
    title: str | None = None
    cited_by_count: int | None = None


class GraphNode(BaseModel):
    id: str
    title: str | None = None
    cited_by_count: int | None = None
    publication_year: int | None = None
    is_open_access: bool | None = None
    is_focus: bool = False


class GraphEdge(BaseModel):
    source: str
    target: str


class GraphResponse(BaseModel):
    focus: GraphFocus
    direction: str
    total_related: int
    shown: int
    live: bool
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []


class FieldInfo(BaseModel):
    id: str
    name: str | None = None
    domain_id: str | None = None
    domain_name: str | None = None
    paper_count: int = 0


class DomainInfo(BaseModel):
    id: str
    name: str | None = None
    paper_count: int = 0


class FieldsResponse(BaseModel):
    fields: list[FieldInfo] = []
    domains: list[DomainInfo] = []


class TopPaper(BaseModel):
    id: str
    title: str | None = None
    cited_by_count: int | None = None
    doi: str | None = None


class CountryRankingRow(BaseModel):
    country_code: str
    country_name: str | None = None
    paper_count: int
    total_citations: int
    num_universities: int | None = None
    gdp_usd: float | None = None
    population: int | None = None
    papers_per_gdp: float | None = None
    papers_per_university: float | None = None
    papers_per_capita: float | None = None
    top_paper: TopPaper | None = None


class CountryRankingResponse(BaseModel):
    scope_type: str
    scope_id: str
    order_by: str
    count: int
    items: list[CountryRankingRow] = []
