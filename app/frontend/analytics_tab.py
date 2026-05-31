import pandas as pd
import streamlit as st

from api_client import (
    ApiError,
    domain_country_ranking,
    field_country_ranking,
    get_fields,
)

_ORDER_BY = {
    "papers": "Papers",
    "citations": "Total citations",
    "universities": "Universities",
    "gdp": "GDP (USD)",
    "population": "Population",
    "papers_per_gdp": "Papers per 100B USD GDP",
    "papers_per_university": "Papers per university",
    "papers_per_capita": "Papers per million capita",
}

_METRIC_COLUMN = {
    "papers": "paper_count",
    "citations": "total_citations",
    "universities": "num_universities",
    "gdp": "gdp_usd",
    "population": "population",
    "papers_per_gdp": "papers_per_gdp",
    "papers_per_university": "papers_per_university",
    "papers_per_capita": "papers_per_capita",
}


def _top_paper_url(top: dict | None) -> str | None:
    if not top:
        return None
    doi = top.get("doi")
    if doi:
        return doi if doi.startswith("http") else f"https://doi.org/{doi}"
    return f"https://openalex.org/{top['id']}"


def _scope_choice() -> tuple[str, str] | None:
    try:
        data = get_fields()
    except ApiError as exc:
        st.error(str(exc))
        return None

    scope_type = st.radio("Group by", options=["Field", "Domain"], horizontal=True)
    if scope_type == "Field":
        entries = data.get("fields", [])
    else:
        entries = data.get("domains", [])

    entries = [e for e in entries if (e.get("paper_count") or 0) > 0]
    if not entries:
        st.info("No fields or domains available. Load the dataset first.")
        return None

    labels = {
        e["id"]: f"{e.get('name') or e['id']} ({e.get('paper_count') or 0:,} papers)"
        for e in entries
    }
    chosen = st.selectbox(
        scope_type,
        options=list(labels.keys()),
        format_func=lambda i: labels.get(i, i),
    )
    return scope_type.lower(), chosen


def _build_table(items: list[dict]) -> pd.DataFrame:
    rows = []
    for it in items:
        top = it.get("top_paper")
        rows.append(
            {
                "Country": it.get("country_name") or it["country_code"],
                "Papers": it.get("paper_count"),
                "Citations": it.get("total_citations"),
                "Universities": it.get("num_universities"),
                "GDP (USD)": it.get("gdp_usd"),
                "Population": it.get("population"),
                "Papers/100B GDP": it.get("papers_per_gdp"),
                "Papers/university": it.get("papers_per_university"),
                "Papers/M capita": it.get("papers_per_capita"),
                "Top paper": (top or {}).get("title"),
                "Top paper link": _top_paper_url(top),
            }
        )
    return pd.DataFrame(rows)


def render() -> None:
    scope = _scope_choice()
    if not scope:
        return
    scope_type, scope_id = scope

    controls = st.columns([2, 1])
    with controls[0]:
        order_by = st.selectbox(
            "Rank by",
            options=list(_ORDER_BY.keys()),
            format_func=lambda k: _ORDER_BY[k],
        )
    with controls[1]:
        limit = st.slider("Countries", 5, 100, 30, step=5)

    try:
        if scope_type == "field":
            payload = field_country_ranking(scope_id, order_by, limit)
        else:
            payload = domain_country_ranking(scope_id, order_by, limit)
    except ApiError as exc:
        st.error(str(exc))
        return

    items = payload.get("items", [])
    if not items:
        st.info("No countries found for this selection.")
        return

    df = _build_table(items)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "GDP (USD)": st.column_config.NumberColumn(format="$%.0f"),
            "Top paper link": st.column_config.LinkColumn("Link", display_text="open"),
        },
    )

    metric_col = _METRIC_COLUMN[order_by]
    chart_rows = [
        (it.get("country_name") or it["country_code"], it.get(metric_col))
        for it in items
    ]
    chart_df = pd.DataFrame(chart_rows, columns=["country", _ORDER_BY[order_by]]).dropna()
    if not chart_df.empty:
        st.bar_chart(chart_df.set_index("country"))
