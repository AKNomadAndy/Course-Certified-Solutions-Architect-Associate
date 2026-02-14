from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy import select

from db import models


def _render_table_fallback(nodes, edges, reason: str):
    st.warning(f"Interactive graph unavailable. Showing table + adjacency list.\n{reason}")
    st.caption("Install optional graph deps to enable interactive view: `pip install streamlit-agraph pyvis`")
    st.dataframe(pd.DataFrame([{"id": n.id, "label": n.label, "type": n.node_type, "ref_id": n.ref_id} for n in nodes]))
    label_map = {n.id: n.label for n in nodes}
    adj = [{"from": label_map.get(e.source_node_id), "to": label_map.get(e.target_node_id), "label": e.label} for e in edges]
    st.dataframe(pd.DataFrame(adj))


def _render_pyvis(nodes, edges):
    from pyvis.network import Network

    net = Network(height="520px", width="100%", directed=True)
    palette = {"account": "#4dabf7", "pod": "#69db7c", "liability": "#ff8787"}

    for n in nodes:
        net.add_node(str(n.id), label=n.label, color=palette.get(n.node_type, "#adb5bd"), title=n.node_type)
    for e in edges:
        net.add_edge(str(e.source_node_id), str(e.target_node_id), label=e.label)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
        net.save_graph(tmp.name)
        html = Path(tmp.name).read_text(encoding="utf-8")
    components.html(html, height=540, scrolling=False)


def render(session):
    st.header("Money Map")
    nodes = session.scalars(select(models.MoneyMapNode)).all()
    edges = session.scalars(select(models.MoneyMapEdge)).all()

    if st.button("Create quick edge"):
        if len(nodes) >= 2:
            session.add(models.MoneyMapEdge(source_node_id=nodes[0].id, target_node_id=nodes[1].id, label="manual"))
            session.commit()
            st.success("Edge created")

    rendered = False
    errors: list[str] = []

    try:
        from streamlit_agraph import Config, Edge, Node, agraph

        g_nodes = [Node(id=str(n.id), label=n.label, size=20) for n in nodes]
        g_edges = [Edge(source=str(e.source_node_id), target=str(e.target_node_id), label=e.label) for e in edges]
        config = Config(width="100%", height=520, directed=True, physics=True)
        selected = agraph(nodes=g_nodes, edges=g_edges, config=config)
        rendered = True
        if selected:
            n = next((x for x in nodes if str(x.id) == str(selected)), None)
            if n:
                st.info(f"Selected {n.label} ({n.node_type})")
    except Exception as exc:
        errors.append(f"streamlit-agraph failed: {exc}")

    if not rendered:
        try:
            _render_pyvis(nodes, edges)
            st.info("Rendered with PyVis fallback because streamlit-agraph is unavailable.")
            rendered = True
        except Exception as exc:
            errors.append(f"pyvis fallback failed: {exc}")
            _render_table_fallback(nodes, edges, reason="\n".join(errors))

    with st.expander("Create account / pod / liability"):
        col1, col2, col3 = st.columns(3)
        with col1:
            an = st.text_input("Account name")
            at = st.selectbox("Account type", ["checking", "savings", "cash", "credit", "loan"])
            if st.button("Add Account") and an:
                account = models.Account(name=an, type=at)
                session.add(account)
                session.flush()
                session.add(models.MoneyMapNode(node_type="account", ref_id=account.id, label=account.name))
                session.commit()
                st.success("Added account")
        with col2:
            pn = st.text_input("Pod name")
            if st.button("Add Pod") and pn:
                pod = models.Pod(name=pn)
                session.add(pod)
                session.flush()
                session.add(models.MoneyMapNode(node_type="pod", ref_id=pod.id, label=pod.name))
                session.commit()
                st.success("Added pod")
        with col3:
            ln = st.text_input("Liability name")
            md = st.number_input("Min due", min_value=0.0, step=1.0)
            if st.button("Add Liability") and ln:
                li = models.Liability(name=ln, min_due=md)
                session.add(li)
                session.flush()
                session.add(models.MoneyMapNode(node_type="liability", ref_id=li.id, label=li.name))
                session.commit()
                st.success("Added liability")
