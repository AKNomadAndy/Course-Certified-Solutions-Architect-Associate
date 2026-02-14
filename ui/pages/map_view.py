from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import select

from db import models


def render(session):
    st.header("Money Map")
    nodes = session.scalars(select(models.MoneyMapNode)).all()
    edges = session.scalars(select(models.MoneyMapEdge)).all()

    if st.button("Create quick edge"):
        if len(nodes) >= 2:
            session.add(models.MoneyMapEdge(source_node_id=nodes[0].id, target_node_id=nodes[1].id, label="manual"))
            session.commit()
            st.success("Edge created")

    try:
        from streamlit_agraph import Config, Edge, Node, agraph

        g_nodes = [Node(id=str(n.id), label=n.label, size=20) for n in nodes]
        g_edges = [Edge(source=str(e.source_node_id), target=str(e.target_node_id), label=e.label) for e in edges]
        config = Config(width="100%", height=500, directed=True, physics=True)
        selected = agraph(nodes=g_nodes, edges=g_edges, config=config)
        if selected:
            n = next((x for x in nodes if str(x.id) == str(selected)), None)
            if n:
                st.info(f"Selected {n.label} ({n.node_type})")
    except Exception:
        st.warning("Graph library unavailable, showing fallback table + adjacency list")
        st.dataframe(pd.DataFrame([{"id": n.id, "label": n.label, "type": n.node_type, "ref_id": n.ref_id} for n in nodes]))
        adj = []
        label_map = {n.id: n.label for n in nodes}
        for e in edges:
            adj.append({"from": label_map.get(e.source_node_id), "to": label_map.get(e.target_node_id), "label": e.label})
        st.dataframe(pd.DataFrame(adj))

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
