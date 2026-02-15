from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy import select

from db import models


def _render_table_fallback(nodes, edges, reason: str):
    st.warning(f"Interactive graph unavailable. Showing table + adjacency list.\n{reason}")
    st.caption("Install optional graph deps to enable richer graph views: `pip install streamlit-agraph pyvis`")
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


def _render_native_svg_graph(nodes, edges):
    # Zero-dependency fallback graph (interactive hover + labels) using inline SVG.
    if not nodes:
        st.info("No nodes yet. Add accounts/pods/liabilities to build your map.")
        return

    palette = {"account": "#4dabf7", "pod": "#69db7c", "liability": "#ff8787"}
    cx, cy, radius = 500, 260, 180
    positioned = []
    for idx, n in enumerate(nodes):
        ang = 2 * math.pi * idx / max(len(nodes), 1)
        x = cx + radius * math.cos(ang)
        y = cy + radius * math.sin(ang)
        positioned.append({
            "id": n.id,
            "label": n.label,
            "node_type": n.node_type,
            "x": round(x, 1),
            "y": round(y, 1),
            "color": palette.get(n.node_type, "#adb5bd"),
        })

    html = f"""
    <div style='background:#0e1117;border:1px solid #1f2430;border-radius:10px;padding:8px;'>
      <svg viewBox='0 0 1000 520' width='100%' height='520'>
        <defs>
          <style>
            .node-label {{ fill: #e6edf3; font: 12px sans-serif; }}
            .edge-label {{ fill: #9aa4b2; font: 10px sans-serif; }}
            .edge {{ stroke: #5c6370; stroke-width: 1.5; opacity: 0.8; }}
            .node {{ stroke: #0b0f14; stroke-width: 2; cursor: pointer; }}
          </style>
        </defs>
        <g id='edges'></g>
        <g id='nodes'></g>
      </svg>
    </div>
    <script>
      const nodes = {json.dumps(positioned)};
      const edges = {json.dumps([{"source": e.source_node_id, "target": e.target_node_id, "label": e.label} for e in edges])};
      const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
      const edgeRoot = document.getElementById('edges');
      const nodeRoot = document.getElementById('nodes');

      edges.forEach(e => {{
        const s = byId[e.source];
        const t = byId[e.target];
        if (!s || !t) return;
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', s.x); line.setAttribute('y1', s.y);
        line.setAttribute('x2', t.x); line.setAttribute('y2', t.y);
        line.setAttribute('class', 'edge');
        edgeRoot.appendChild(line);

        const tx = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        tx.setAttribute('x', (s.x + t.x) / 2 + 6);
        tx.setAttribute('y', (s.y + t.y) / 2 - 6);
        tx.setAttribute('class', 'edge-label');
        tx.textContent = e.label || '';
        edgeRoot.appendChild(tx);
      }});

      nodes.forEach(n => {{
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', n.x); circle.setAttribute('cy', n.y);
        circle.setAttribute('r', 18); circle.setAttribute('fill', n.color);
        circle.setAttribute('class', 'node');
        circle.setAttribute('title', `${{n.label}} (${{n.node_type}})`);
        nodeRoot.appendChild(circle);

        const tx = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        tx.setAttribute('x', n.x + 24);
        tx.setAttribute('y', n.y + 4);
        tx.setAttribute('class', 'node-label');
        tx.textContent = n.label;
        nodeRoot.appendChild(tx);
      }});
    </script>
    """
    components.html(html, height=540, scrolling=False)


def _render_overview(nodes, edges):
    st.subheader("Map Overview")
    c1, c2, c3 = st.columns(3)
    c1.metric("Nodes", len(nodes))
    c2.metric("Edges", len(edges))
    liabilities = sum(1 for n in nodes if n.node_type == "liability")
    c3.metric("Liability Nodes", liabilities)

    if nodes:
        nd = pd.DataFrame([{"type": n.node_type} for n in nodes])
        count_by_type = nd.groupby("type", as_index=False).size().rename(columns={"size": "count"})
        st.bar_chart(count_by_type, x="type", y="count", color="#9775fa")


def render(session):
    st.header("Money Map")
    nodes = session.scalars(select(models.MoneyMapNode)).all()
    edges = session.scalars(select(models.MoneyMapEdge)).all()

    _render_overview(nodes, edges)

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

    if not rendered:
        try:
            _render_native_svg_graph(nodes, edges)
            st.info("Rendered with built-in SVG fallback (no extra graph packages required).")
            rendered = True
        except Exception as exc:
            errors.append(f"native svg fallback failed: {exc}")
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
