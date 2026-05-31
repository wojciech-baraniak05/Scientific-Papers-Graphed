from dataclasses import dataclass, field as dataclass_field

from app.ingestion.abstract import decode_abstract


def _clip(value, n: int):
    if isinstance(value, str) and len(value) > n:
        return value[:n]
    return value


def short_id(value: str | None) -> str | None:
    if not value:
        return None
    return value.rstrip("/").rsplit("/", 1)[-1]


@dataclass
class ParsedWork:
    paper: dict
    authors: list[dict] = dataclass_field(default_factory=list)
    institutions: list[dict] = dataclass_field(default_factory=list)
    paper_authors: list[dict] = dataclass_field(default_factory=list)
    paper_institutions: list[dict] = dataclass_field(default_factory=list)
    paper_countries: list[dict] = dataclass_field(default_factory=list)
    referenced_ids: list[str] = dataclass_field(default_factory=list)
    field: dict | None = None


def _parse_topic(work: dict) -> dict | None:
    topic = work.get("primary_topic") or {}
    field = topic.get("field") or {}
    field_id = short_id(field.get("id"))
    if not field_id:
        return None
    domain = topic.get("domain") or {}
    return {
        "id": _clip(field_id, 20),
        "name": _clip(field.get("display_name"), 255),
        "domain_id": _clip(short_id(domain.get("id")), 20),
        "domain_name": _clip(domain.get("display_name"), 255),
    }


def _base_paper_row(work: dict, *, ingested: bool, field: dict | None) -> dict:
    oa = work.get("open_access") or {}
    return {
        "id": short_id(work.get("id")),
        "doi": _clip(work.get("doi"), 255),
        "title": work.get("title") or work.get("display_name"),
        "publication_year": work.get("publication_year"),
        "cited_by_count": work.get("cited_by_count"),
        "referenced_works_count": work.get("referenced_works_count"),
        "is_open_access": oa.get("is_oa"),
        "oa_status": _clip(oa.get("oa_status"), 20),
        "oa_url": _clip(oa.get("oa_url"), 1024),
        "primary_field_id": field["id"] if field else None,
        "primary_field_name": field["name"] if field else None,
        "primary_domain_id": field["domain_id"] if field else None,
        "primary_domain_name": field["domain_name"] if field else None,
        "ingested": ingested,
    }


def parse_work(work: dict) -> ParsedWork:
    field = _parse_topic(work)
    paper = _base_paper_row(work, ingested=True, field=field)
    pid = paper["id"]
    paper["abstract"] = decode_abstract(work.get("abstract_inverted_index"))

    authors: dict[str, dict] = {}
    institutions: dict[str, dict] = {}
    paper_authors: list[dict] = []
    paper_institutions: dict[str, dict] = {}
    country_codes: set[str] = set()
    is_educational = False

    for authorship in work.get("authorships") or []:
        author = authorship.get("author") or {}
        aid = short_id(author.get("id"))
        if aid and aid not in authors:
            authors[aid] = {
                "id": aid,
                "display_name": _clip(author.get("display_name"), 512),
                "orcid": _clip(author.get("orcid"), 64),
            }
        if aid:
            paper_authors.append(
                {
                    "paper_id": pid,
                    "author_id": aid,
                    "author_position": authorship.get("author_position"),
                }
            )
        for inst in authorship.get("institutions") or []:
            iid = short_id(inst.get("id"))
            if not iid:
                continue
            itype = inst.get("type")
            if itype == "education":
                is_educational = True
            cc = (inst.get("country_code") or "").upper() or None
            if iid not in institutions:
                institutions[iid] = {
                    "id": iid,
                    "display_name": _clip(inst.get("display_name"), 512),
                    "country_code": cc,
                    "type": _clip(itype, 32),
                    "ror": _clip(inst.get("ror"), 255),
                }
            paper_institutions[iid] = {"paper_id": pid, "institution_id": iid}
            if cc and len(cc) == 2:
                country_codes.add(cc)

    paper["is_educational"] = is_educational

    return ParsedWork(
        paper=paper,
        authors=list(authors.values()),
        institutions=list(institutions.values()),
        paper_authors=_dedup_pairs(paper_authors, ("paper_id", "author_id")),
        paper_institutions=list(paper_institutions.values()),
        paper_countries=[{"paper_id": pid, "country_code": cc} for cc in sorted(country_codes)],
        referenced_ids=[
            sid for sid in (short_id(r) for r in work.get("referenced_works") or []) if sid
        ],
        field=field,
    )


def parse_stub(work: dict) -> tuple[dict, dict | None]:
    field = _parse_topic(work)
    return _base_paper_row(work, ingested=False, field=field), field


def _dedup_pairs(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for row in rows:
        key = tuple(row[k] for k in keys)
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out


def parse_universities(records: list[dict]) -> tuple[list[dict], dict[str, int]]:
    rows: list[dict] = []
    counts: dict[str, int] = {}
    for rec in records:
        code = (rec.get("alpha_two_code") or "").upper() or None
        web_pages = rec.get("web_pages") or []
        rows.append(
            {
                "name": _clip(rec.get("name") or "", 512),
                "country_code": code if (code and len(code) == 2) else None,
                "country_name": _clip(rec.get("country"), 128),
                "web_page": _clip(web_pages[0] if web_pages else None, 512),
                "domains": rec.get("domains") or None,
            }
        )
        if code and len(code) == 2:
            counts[code] = counts.get(code, 0) + 1
    return rows, counts


def build_country_rows(
    wb_countries: list[dict],
    gdp: dict[str, tuple[float, int | None]],
    population: dict[str, tuple[float, int | None]],
    university_counts: dict[str, int],
) -> list[dict]:
    rows: list[dict] = []
    for country in wb_countries:
        code = (country.get("iso2") or "").upper()
        iso3 = country.get("iso3")
        if not code or len(code) != 2:
            continue
        gdp_val, gdp_year = gdp.get(iso3, (None, None))
        pop_val, pop_year = population.get(iso3, (None, None))
        rows.append(
            {
                "code": code,
                "iso3": iso3,
                "name": _clip(country.get("name"), 128),
                "gdp_usd": gdp_val,
                "gdp_year": gdp_year,
                "population": int(pop_val) if pop_val is not None else None,
                "population_year": pop_year,
                "num_universities": university_counts.get(code, 0),
            }
        )
    return rows
