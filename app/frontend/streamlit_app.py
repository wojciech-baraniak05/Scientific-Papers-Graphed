from __future__ import annotations

import streamlit as st

import analytics_tab
import graph_tab
from api_client import API_BASE_URL, get_health

st.set_page_config(
    page_title="Paper Citation Explorer",
    page_icon="📚",
    layout="wide",
)


def _render_sidebar() -> None:
    with st.sidebar:
        st.header("Paper Citation Explorer")
        st.caption("OpenAlex · World Bank · hipolabs")
        health = get_health()
        if health.get("database") == "up":
            st.success("API online · database up")
        elif health.get("status") == "down":
            st.error("API unreachable")
        else:
            st.warning(f"API status: {health.get('status', 'unknown')}")
        st.caption(f"Backend: {API_BASE_URL}")


def main() -> None:
    _render_sidebar()
    st.title("Paper Citation Explorer")
    tab_graph, tab_analytics = st.tabs(["Citation graph", "Country analytics"])
    with tab_graph:
        graph_tab.render()
    with tab_analytics:
        analytics_tab.render()


main()
