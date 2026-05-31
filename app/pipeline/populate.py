from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.database import (
    get_db_size_bytes,
    get_session_factory,
    init_db,
)
from app.db.models import (
    Author,
    Country,
    Field,
    IngestRun,
    Institution,
    Paper,
    PaperAuthor,
    PaperCountry,
    PaperInstitution,
    PaperReference,
    University,
)
from app.db.upsert import bulk_insert, bulk_upsert
from app.ingestion.openalex_client import OpenAlexClient
from app.ingestion.universities_client import UniversitiesClient
from app.ingestion.worldbank_client import WorldBankClient
from app.logging_config import configure_logging
from app.processing.transform import (
    ParsedWork,
    build_country_rows,
    parse_stub,
    parse_universities,
    parse_work,
    short_id,
)

_PAPER_DATA_COLS = [
    "doi",
    "title",
    "publication_year",
    "cited_by_count",
    "referenced_works_count",
    "is_open_access",
    "oa_status",
    "oa_url",
    "is_educational",
    "primary_field_id",
    "primary_field_name",
    "primary_domain_id",
    "primary_domain_name",
    "abstract",
    "ingested",
]
_STUB_DATA_COLS = [
    "doi",
    "title",
    "publication_year",
    "cited_by_count",
    "is_open_access",
    "oa_status",
    "oa_url",
    "primary_field_id",
    "primary_field_name",
    "primary_domain_id",
    "primary_domain_name",
]


@dataclass
class PipelineConfig:
    scope: str = "popular"
    target_gb: float = 5.0
    max_papers: int | None = None
    max_enrichment_ids: int = 50000
    skip_reference_data: bool = False
    skip_enrichment: bool = False
    batch_size: int = 200


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


_OPENALEX_BASE = "https://openalex.org"


def scope_to_filter(scope: str) -> str | None:
    if scope == "popular":
        return None
    if ":" in scope:
        kind, value = scope.split(":", 1)
        key = short_id(value.strip())
        if kind == "field" and key:
            return f"primary_topic.field.id:{_OPENALEX_BASE}/fields/{key}"
        if kind == "domain" and key:
            return f"primary_topic.domain.id:{_OPENALEX_BASE}/domains/{key}"
    raise ValueError(
        f"Invalid scope {scope!r}; expected 'popular', 'field:ID' or 'domain:ID' "
        "(ID may be '22', 'fields/22', or the full OpenAlex URL)."
    )


def load_reference_data(session: Session, settings: Settings) -> None:
    logger.info("Phase 1: reference data (universities + World Bank).")
    university_counts: dict[str, int] = {}

    try:
        with UniversitiesClient(
            base_url=settings.hipolabs_base_url,
            max_retries=settings.http_max_retries,
            backoff_base=settings.http_backoff_base,
        ) as uni_client:
            records = uni_client.fetch_all()
        uni_rows, university_counts = parse_universities(records)
        session.query(University).delete()
        bulk_insert(session, University, uni_rows)
        logger.info("  universities: {} rows, {} countries.", len(uni_rows), len(university_counts))
    except Exception as exc:
        logger.warning("  universities load skipped ({}).", exc)

    wb_countries: list[dict] = []
    gdp: dict[str, tuple[float, int | None]] = {}
    population: dict[str, tuple[float, int | None]] = {}
    with WorldBankClient(
        base_url=settings.worldbank_base_url,
        max_retries=settings.http_max_retries,
        backoff_base=settings.http_backoff_base,
    ) as wb_client:
        for label, fn in (("countries", wb_client.get_countries),
                          ("gdp", wb_client.get_gdp),
                          ("population", wb_client.get_population)):
            try:
                result = fn()
            except Exception as exc:
                logger.warning("  World Bank {} load skipped ({}).", label, exc)
                continue
            if label == "countries":
                wb_countries = result
            elif label == "gdp":
                gdp = result
            else:
                population = result

    if wb_countries:
        country_rows = build_country_rows(wb_countries, gdp, population, university_counts)
        bulk_upsert(
            session,
            Country,
            country_rows,
            update_cols=["iso3", "name", "gdp_usd", "gdp_year", "population", "population_year", "num_universities"],
        )
        logger.info("  countries: {} rows (GDP={}, pop={}).", len(country_rows), len(gdp), len(population))
    else:
        logger.warning("  countries: no World Bank country list — table left as-is.")

    session.commit()


def _write_batch(session: Session, batch: list[ParsedWork]) -> int:
    authors: dict[str, dict] = {}
    institutions: dict[str, dict] = {}
    fields: dict[str, dict] = {}
    papers_full: dict[str, dict] = {}
    paper_authors: dict[tuple, dict] = {}
    paper_institutions: dict[tuple, dict] = {}
    paper_countries: dict[tuple, dict] = {}
    references: dict[tuple, dict] = {}
    referenced_ids: set[str] = set()
    country_codes: set[str] = set()

    for pw in batch:
        papers_full[pw.paper["id"]] = pw.paper
        for a in pw.authors:
            authors[a["id"]] = a
        for inst in pw.institutions:
            institutions[inst["id"]] = inst
        if pw.field:
            fields[pw.field["id"]] = pw.field
        for pa in pw.paper_authors:
            paper_authors[(pa["paper_id"], pa["author_id"])] = pa
        for pi in pw.paper_institutions:
            paper_institutions[(pi["paper_id"], pi["institution_id"])] = pi
        for pc in pw.paper_countries:
            paper_countries[(pc["paper_id"], pc["country_code"])] = pc
            country_codes.add(pc["country_code"])
        for rid in pw.referenced_ids:
            referenced_ids.add(rid)
            references[(pw.paper["id"], rid)] = {"citing_id": pw.paper["id"], "referenced_id": rid}

    stub_ids = [rid for rid in referenced_ids if rid not in papers_full]

    bulk_upsert(session, Author, list(authors.values()), update_cols=["display_name", "orcid"])
    bulk_upsert(session, Institution, list(institutions.values()),
                update_cols=["display_name", "country_code", "type", "ror"])
    bulk_upsert(session, Field, list(fields.values()),
                update_cols=["name", "domain_id", "domain_name"])
    bulk_upsert(session, Paper, list(papers_full.values()), update_cols=_PAPER_DATA_COLS)
    bulk_upsert(session, Country, [{"code": c} for c in country_codes], update_cols=None)
    bulk_upsert(session, Paper, [{"id": rid, "ingested": False} for rid in stub_ids], update_cols=None)
    bulk_upsert(session, PaperAuthor, list(paper_authors.values()), update_cols=None)
    bulk_upsert(session, PaperInstitution, list(paper_institutions.values()), update_cols=None)
    bulk_upsert(session, PaperCountry, list(paper_countries.values()), update_cols=None)
    bulk_upsert(session, PaperReference, list(references.values()), update_cols=None)

    session.commit()
    return len(papers_full)


def ingest_corpus(
    session: Session, client: OpenAlexClient, cfg: PipelineConfig, target_bytes: int
) -> int:
    filt = scope_to_filter(cfg.scope)
    per_page = min(cfg.batch_size, 200)
    logger.info(
        "Phase 2: corpus scope={!r} filter={!r} target={:.2f} GB max_papers={}.",
        cfg.scope, filt, target_bytes / 1024**3, cfg.max_papers,
    )

    total = 0
    batch: list[ParsedWork] = []
    batch_no = 0
    for work in client.iter_works(filter=filt, per_page=per_page, max_records=cfg.max_papers):
        batch.append(parse_work(work))
        if len(batch) >= cfg.batch_size:
            total += _write_batch(session, batch)
            batch = []
            batch_no += 1
            size = get_db_size_bytes(session)
            logger.info("  batch {} | papers={} | db_size={:.1f} MB", batch_no, total, size / 1e6)
            if target_bytes and size >= target_bytes:
                logger.info("  size target reached ({:.2f} GB) — stopping corpus.", size / 1024**3)
                return total

    if batch:
        total += _write_batch(session, batch)
    logger.info("Phase 2 done: {} papers fully ingested.", total)
    return total


def enrich_references(session: Session, client: OpenAlexClient, cfg: PipelineConfig) -> int:
    logger.info("Phase 3: enrich referenced (stub) papers (cap={}).", cfg.max_enrichment_ids)
    stub_ids = list(
        session.execute(
            select(Paper.id)
            .where(Paper.ingested.is_(False), Paper.title.is_(None))
            .limit(cfg.max_enrichment_ids)
        ).scalars()
    )
    if not stub_ids:
        logger.info("  nothing to enrich.")
        return 0

    enriched = 0
    chunk = 50
    for start in range(0, len(stub_ids), chunk):
        ids = stub_ids[start : start + chunk]
        works = client.fetch_works_by_ids(ids)
        paper_rows: list[dict] = []
        field_rows: dict[str, dict] = {}
        for work in works:
            row, fld = parse_stub(work)
            paper_rows.append(row)
            if fld:
                field_rows[fld["id"]] = fld
        bulk_upsert(session, Field, list(field_rows.values()),
                    update_cols=["name", "domain_id", "domain_name"])
        bulk_upsert(session, Paper, paper_rows, update_cols=_STUB_DATA_COLS)
        session.commit()
        enriched += len(paper_rows)

    logger.info("Phase 3 done: enriched {} stub papers.", enriched)
    return enriched


def run_pipeline(cfg: PipelineConfig) -> dict:
    configure_logging()
    settings = get_settings()
    init_db()

    target_bytes = int(cfg.target_gb * 1024**3)
    started = _utcnow()
    session = get_session_factory()()
    papers_ingested = 0
    enriched = 0
    status = "success"
    message = ""

    try:
        if not cfg.skip_reference_data:
            load_reference_data(session, settings)
        else:
            logger.info("Phase 1 skipped (--skip-reference-data).")

        with OpenAlexClient(
            email=settings.openalex_email,
            api_key=settings.openalex_api_key,
            base_url=settings.openalex_base_url,
            timeout=settings.http_timeout,
            max_retries=settings.http_max_retries,
            backoff_base=settings.http_backoff_base,
        ) as client:
            papers_ingested = ingest_corpus(session, client, cfg, target_bytes)
            if not cfg.skip_enrichment and cfg.max_enrichment_ids > 0:
                enriched = enrich_references(session, client, cfg)
            else:
                logger.info("Phase 3 skipped.")
    except Exception as exc:
        session.rollback()
        status = "failed"
        message = repr(exc)
        logger.exception("Pipeline failed: {}", exc)
        _record_run(session, cfg, started, papers_ingested, status, message)
        session.close()
        raise

    final_size = get_db_size_bytes(session)
    message = f"enriched={enriched}"
    _record_run(session, cfg, started, papers_ingested, status, message, final_size)
    summary = {
        "scope": cfg.scope,
        "papers_ingested": papers_ingested,
        "enriched": enriched,
        "db_size_bytes": final_size,
        "db_size_gb": round(final_size / 1024**3, 3),
        "status": status,
    }
    logger.info("Phase 4 done. Summary: {}", summary)
    session.close()
    return summary


def _record_run(
    session: Session,
    cfg: PipelineConfig,
    started: datetime,
    papers_ingested: int,
    status: str,
    message: str,
    db_size_bytes: int | None = None,
) -> None:
    try:
        session.add(
            IngestRun(
                scope=cfg.scope,
                started_at=started,
                finished_at=_utcnow(),
                papers_ingested=papers_ingested,
                db_size_bytes=db_size_bytes,
                status=status,
                message=message[:65535] if message else None,
            )
        )
        session.commit()
    except Exception as exc:
        logger.warning("Could not write ingest_runs row ({}).", exc)
        session.rollback()
