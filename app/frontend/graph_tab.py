import math

import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

from api_client import ApiError, get_paper, get_paper_graph, search_papers

_DIRECTION_LABELS = {"cites": "Cites (references)", "cited_by": "Is cited by"}


def _truncate(text: str | None, length: int = 60) -> str:
    if not text:
        return ""
    return text if len(text) <= length else text[: length - 1] + "…"


def _node_color(node: dict) -> str:
    if node.get("is_focus"):
        return "#e4572e"
    if not node.get("title"):
        return "#9aa0a6"
    if node.get("is_open_access"):
        return "#2e8b57"
    return "#4c78a8"


def _node_size(node: dict, focus_count: int) -> float:
    if node.get("is_focus"):
        return 28.0
    ratio = ((node.get("cited_by_count") or 0) + 1) / (focus_count + 1)
    size = 28.0 + 8 * math.log10(ratio)
    return max(6.0, min(48.0, size))


def _seed_picker() -> str | None:
    query = st.text_input("Search papers by title", key="graph_search_q")
    try:
        results = search_papers(query or None, None, None, 25)
    except ApiError as exc:
        st.error(str(exc))
        return None

    if not results:
        st.info("No papers matched. Try another title.")
        return None

    labels = {
        r["id"]: f"{_truncate(r.get('title'), 80)} — cited {r.get('cited_by_count') or 0:,}"
        for r in results
    }
    return st.selectbox(
        "Seed paper",
        options=list(labels.keys()),
        format_func=lambda pid: labels.get(pid, pid),
        key="graph_seed",
    )


def _render_graph(data: dict, direction: str) -> str | None:
    focus = data["focus"]
    shown = data.get("shown", 0)
    if direction == "cited_by":
        st.subheader(f"Cited by {focus.get('cited_by_count') or 0:,} papers — showing top {shown}")
    else:
        st.subheader(f"References {data.get('total_related') or 0:,} works — showing top {shown}")
    st.caption(_truncate(focus.get("title"), 110))

    focus_count = focus.get("cited_by_count") or 0
    nodes = [
        Node(
            id=n["id"],
            label=_truncate(n.get("title"), 28),
            size=_node_size(n, focus_count),
            color=_node_color(n),
            chosen={"label": True},
        )
        for n in data.get("nodes", [])
    ]
    edges = [Edge(source=e["source"], target=e["target"]) for e in data.get("edges", [])]

    if len(nodes) <= 1:
        st.info("No related papers to draw for this direction.")

    config = Config(
        width=720,
        height=600,
        directed=True,
        physics=True,
        nodeHighlightBehavior=True,
        highlightColor="#f6c85f",
        collapsible=False,
        interaction={"hover": True},
    )
    return agraph(nodes=nodes, edges=edges, config=config)


def _oa_badge(paper: dict) -> str:
    if paper.get("is_open_access"):
        status = paper.get("oa_status") or "open"
        label = f"Open Access · {status}"
        return (
            "<span style='background:#2e8b57;color:white;padding:2px 8px;"
            f"border-radius:10px;font-size:0.8rem'>{label}</span>"
        )
    return (
        "<span style='background:#888;color:white;padding:2px 8px;"
        "border-radius:10px;font-size:0.8rem'>Closed</span>"
    )


def _render_panel(paper_id: str) -> None:
    try:
        paper = get_paper(paper_id)
    except ApiError as exc:
        st.error(str(exc))
        return

    st.markdown(f"### {paper.get('title') or paper_id}")
    st.markdown(_oa_badge(paper), unsafe_allow_html=True)

    authors = ", ".join(a.get("display_name") or "" for a in paper.get("authors", []))
    if authors:
        st.markdown(f"**Authors:** {authors}")

    year = paper.get("publication_year")
    field = paper.get("primary_field_name")
    meta = " · ".join(str(x) for x in (year, field) if x)
    if meta:
        st.caption(meta)

    st.metric("Cited by", f"{paper.get('cited_by_count') or 0:,}")

    doi = paper.get("doi")
    if doi:
        url = doi if doi.startswith("http") else f"https://doi.org/{doi}"
        st.markdown(f"**DOI:** [{doi}]({url})")
    if paper.get("oa_url"):
        st.markdown(f"[Open-access full text]({paper['oa_url']})")

    abstract = paper.get("abstract")
    if abstract:
        with st.expander("Abstract", expanded=True):
            st.write(abstract if len(abstract) <= 1200 else abstract[:1200] + "…")
    else:
        st.caption("No abstract available.")


def render() -> None:
    seed = _seed_picker()
    if not seed:
        return

    controls = st.columns([3, 1])
    with controls[0]:
        direction = st.radio(
            "Direction",
            options=list(_DIRECTION_LABELS.keys()),
            format_func=lambda d: _DIRECTION_LABELS[d],
            horizontal=True,
            key="graph_direction",
        )
    with controls[1]:
        limit = st.slider("Max nodes", 10, 200, 50, step=5, key="graph_limit")

    if st.session_state.get("graph_focus_id") != seed:
        st.session_state["graph_focus_id"] = seed
        st.session_state["selected_node"] = None

    try:
        data = get_paper_graph(seed, direction, limit)
    except ApiError as exc:
        st.error(str(exc))
        return

    col_graph, col_panel = st.columns([2, 1])
    with col_graph:
        clicked = _render_graph(data, direction)
        if clicked:
            st.session_state["selected_node"] = clicked
    with col_panel:
        _render_panel(st.session_state.get("selected_node") or seed)
