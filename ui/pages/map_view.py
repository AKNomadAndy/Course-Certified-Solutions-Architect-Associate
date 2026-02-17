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


PALETTE = {"account": "#4dabf7", "pod": "#69db7c", "liability": "#ff8787"}


def _render_table_fallback(nodes, edges, reason: str):
    st.warning(f"Interactive graph unavailable. Showing table + adjacency list.\n{reason}")
    st.caption("Install optional graph deps to enable richer graph views: `pip install streamlit-agraph pyvis`")
    st.dataframe(pd.DataFrame([{"id": n.id, "label": n.label, "type": n.node_type, "ref_id": n.ref_id} for n in nodes]))
    label_map = {n.id: n.label for n in nodes}
    adj = [{"from": label_map.get(e.source_node_id), "to": label_map.get(e.target_node_id), "label": e.label} for e in edges]
    st.dataframe(pd.DataFrame(adj))


def _render_pyvis(nodes, edges):
    from pyvis.network import Network

    net = Network(height="520px", width="100%", directed=True, bgcolor="#0e1117", font_color="#e6edf3")

    for n in nodes:
        net.add_node(str(n.id), label=n.label, color=PALETTE.get(n.node_type, "#adb5bd"), title=n.node_type)
    for e in edges:
        net.add_edge(str(e.source_node_id), str(e.target_node_id), label=e.label)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
        net.save_graph(tmp.name)
        html = Path(tmp.name).read_text(encoding="utf-8")
    components.html(html, height=540, scrolling=False)


def _render_native_svg_graph(nodes, edges):
    if not nodes:
        st.info("No nodes yet. Add accounts/pods/liabilities to build your map.")
        return

    cx, cy, radius = 500, 260, 180
    positioned = []
    for idx, n in enumerate(nodes):
        ang = 2 * math.pi * idx / max(len(nodes), 1)
        x = cx + radius * math.cos(ang)
        y = cy + radius * math.sin(ang)
        positioned.append(
            {
                "id": n.id,
                "label": n.label,
                "node_type": n.node_type,
                "x": round(x, 1),
                "y": round(y, 1),
                "color": PALETTE.get(n.node_type, "#adb5bd"),
            }
        )

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

    if not nodes:
        return

    node_df = pd.DataFrame([{"type": n.node_type} for n in nodes])
    by_type = node_df.groupby("type", as_index=False).size().rename(columns={"size": "count"})

    edge_df = pd.DataFrame([{"label": e.label or "route"} for e in edges])
    if edge_df.empty:
        edge_df = pd.DataFrame([{"label": "route", "count": 0}])
    else:
        edge_df = edge_df.groupby("label", as_index=False).size().rename(columns={"size": "count"})

    col_a, col_b = st.columns(2)
    try:
        import altair as alt

        donut = (
            alt.Chart(by_type)
            .mark_arc(innerRadius=60)
            .encode(
                theta=alt.Theta(field="count", type="quantitative"),
                color=alt.Color(field="type", type="nominal", scale=alt.Scale(range=["#4dabf7", "#69db7c", "#ff8787"])),
                tooltip=["type", "count"],
            )
            .properties(height=300, title="Node Type Distribution")
        )
        bars = (
            alt.Chart(edge_df)
            .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
            .encode(
                x=alt.X("label:N", sort="-y", title="Edge Label"),
                y=alt.Y("count:Q", title="Count"),
                color=alt.value("#9775fa"),
                tooltip=["label", "count"],
            )
            .properties(height=300, title="Route Label Mix")
        )
        col_a.altair_chart(donut, use_container_width=True)
        col_b.altair_chart(bars, use_container_width=True)
    except Exception:
        col_a.bar_chart(by_type, x="type", y="count", color="#69db7c")
        col_b.bar_chart(edge_df, x="label", y="count", color="#9775fa")


def _edit_accounts(session):
    accounts = session.scalars(select(models.Account).order_by(models.Account.name)).all()
    if not accounts:
        st.info("No accounts yet.")
        return
    account_options = {f"{a.name} (#{a.id})": a.id for a in accounts}
    selected_label = st.selectbox("Account", list(account_options.keys()), key="edit_account_pick")
    picked_id = account_options[selected_label]
    picked = session.get(models.Account, picked_id)
    new_name = st.text_input("Account name", value=picked.name, key="edit_account_name")
    new_type = st.selectbox("Account type", ["checking", "savings", "cash", "credit", "loan"], index=["checking", "savings", "cash", "credit", "loan"].index(picked.type), key="edit_account_type")
    new_currency = st.text_input("Currency", value=picked.currency or "USD", key="edit_account_currency")
    if st.button("Save Account", key="save_account"):
        picked = session.get(models.Account, picked_id)
        picked.name = new_name.strip()
        picked.type = new_type
        picked.currency = new_currency.strip() or "USD"
        node = session.scalar(select(models.MoneyMapNode).where(models.MoneyMapNode.node_type == "account", models.MoneyMapNode.ref_id == picked.id))
        if node:
            node.label = picked.name
        session.commit()
        st.success("Account updated")
    if st.button("Delete Account", key="delete_account"):
        picked = session.get(models.Account, picked_id)
        if not picked:
            st.warning("Account already deleted.")
            return
        session.query(models.BalanceSnapshot).filter(models.BalanceSnapshot.source_type == "account", models.BalanceSnapshot.source_id == picked.id).delete()
        node = session.scalar(select(models.MoneyMapNode).where(models.MoneyMapNode.node_type == "account", models.MoneyMapNode.ref_id == picked.id))
        if node:
            session.query(models.MoneyMapEdge).filter((models.MoneyMapEdge.source_node_id == node.id) | (models.MoneyMapEdge.target_node_id == node.id)).delete()
            session.delete(node)
        session.delete(picked)
        session.commit()
        st.success("Account deleted")


def _edit_pods(session):
    pods = session.scalars(select(models.Pod).order_by(models.Pod.name)).all()
    if not pods:
        st.info("No pods yet.")
        return
    pod_options = {f"{p.name} (#{p.id})": p.id for p in pods}
    selected_label = st.selectbox("Pod", list(pod_options.keys()), key="edit_pod_pick")
    picked_id = pod_options[selected_label]
    picked = session.get(models.Pod, picked_id)
    new_name = st.text_input("Pod name", value=picked.name, key="edit_pod_name")
    target = st.number_input("Target balance", value=float(picked.target_balance or 0), key="edit_pod_target")
    current = st.number_input("Current balance", value=float(picked.current_balance or 0), key="edit_pod_current")
    if st.button("Save Pod", key="save_pod"):
        picked = session.get(models.Pod, picked_id)
        old = picked.name
        picked.name = new_name.strip()
        picked.target_balance = float(target)
        picked.current_balance = float(current)
        node = session.scalar(select(models.MoneyMapNode).where(models.MoneyMapNode.node_type == "pod", models.MoneyMapNode.ref_id == picked.id))
        if node:
            node.label = picked.name
        session.commit()
        st.success(f"Pod updated: {old} -> {picked.name}")
    if st.button("Delete Pod", key="delete_pod"):
        picked = session.get(models.Pod, picked_id)
        if not picked:
            st.warning("Pod already deleted.")
            return
        node = session.scalar(select(models.MoneyMapNode).where(models.MoneyMapNode.node_type == "pod", models.MoneyMapNode.ref_id == picked.id))
        if node:
            session.query(models.MoneyMapEdge).filter((models.MoneyMapEdge.source_node_id == node.id) | (models.MoneyMapEdge.target_node_id == node.id)).delete()
            session.delete(node)
        session.delete(picked)
        session.commit()
        st.success("Pod deleted")


def _edit_liabilities(session):
    items = session.scalars(select(models.Liability).order_by(models.Liability.name)).all()
    if not items:
        st.info("No liabilities yet.")
        return
    liability_options = {f"{l.name} (#{l.id})": l.id for l in items}
    selected_label = st.selectbox("Liability", list(liability_options.keys()), key="edit_liability_pick")
    picked_id = liability_options[selected_label]
    picked = session.get(models.Liability, picked_id)
    name = st.text_input("Liability name", value=picked.name, key="edit_liability_name")
    min_due = st.number_input("Min due", value=float(picked.min_due or 0), key="edit_liability_min_due")
    statement = st.number_input("Statement balance", value=float(picked.statement_balance or 0), key="edit_liability_statement")
    due = st.date_input("Due date", value=picked.due_date, key="edit_liability_due")
    apr = st.number_input("APR", value=float(picked.apr or 0), key="edit_liability_apr")
    if st.button("Save Liability", key="save_liability"):
        picked = session.get(models.Liability, picked_id)
        picked.name = name.strip()
        picked.min_due = float(min_due)
        picked.statement_balance = float(statement)
        picked.due_date = due
        picked.apr = float(apr) if apr else None
        node = session.scalar(select(models.MoneyMapNode).where(models.MoneyMapNode.node_type == "liability", models.MoneyMapNode.ref_id == picked.id))
        if node:
            node.label = picked.name
        session.commit()
        st.success("Liability updated")
    if st.button("Delete Liability", key="delete_liability"):
        picked = session.get(models.Liability, picked_id)
        if not picked:
            st.warning("Liability already deleted.")
            return
        node = session.scalar(select(models.MoneyMapNode).where(models.MoneyMapNode.node_type == "liability", models.MoneyMapNode.ref_id == picked.id))
        if node:
            session.query(models.MoneyMapEdge).filter((models.MoneyMapEdge.source_node_id == node.id) | (models.MoneyMapEdge.target_node_id == node.id)).delete()
            session.delete(node)
        session.delete(picked)
        session.commit()
        st.success("Liability deleted")

def _edit_edges(session):
    nodes = session.scalars(select(models.MoneyMapNode).order_by(models.MoneyMapNode.label)).all()
    edges = session.scalars(select(models.MoneyMapEdge).order_by(models.MoneyMapEdge.id)).all()
    if len(nodes) < 2:
        st.info("Add at least two nodes to manage edges.")
        return

    node_options = {f"{n.label} ({n.node_type} #{n.id})": n.id for n in nodes}

    st.markdown("**Create edge**")
    c1, c2, c3 = st.columns(3)
    source_label = c1.selectbox("From", list(node_options.keys()), key="edge_create_from")
    target_label = c2.selectbox("To", list(node_options.keys()), key="edge_create_to")
    edge_label = c3.text_input("Label", value="routes to", key="edge_create_label")
    if st.button("Add Edge", key="edge_create_btn"):
        source_id = node_options[source_label]
        target_id = node_options[target_label]
        if source_id == target_id:
            st.error("Source and target must be different nodes.")
        else:
            session.add(models.MoneyMapEdge(source_node_id=source_id, target_node_id=target_id, label=edge_label.strip() or "routes to"))
            session.commit()
            st.success("Edge added")

    st.markdown("**Edit / delete edge**")
    if not edges:
        st.info("No edges yet.")
        return

    edge_options = {f"Edge #{e.id}: {e.source_node_id} -> {e.target_node_id} ({e.label})": e.id for e in edges}
    picked_label = st.selectbox("Select edge", list(edge_options.keys()), key="edge_pick")
    picked = session.get(models.MoneyMapEdge, edge_options[picked_label])

    e1, e2, e3 = st.columns(3)
    new_source = e1.selectbox("New from", list(node_options.keys()), index=list(node_options.values()).index(picked.source_node_id), key="edge_edit_from")
    new_target = e2.selectbox("New to", list(node_options.keys()), index=list(node_options.values()).index(picked.target_node_id), key="edge_edit_to")
    new_label = e3.text_input("New label", value=picked.label or "routes to", key="edge_edit_label")

    s_col, d_col = st.columns(2)
    if s_col.button("Save Edge", key="edge_save_btn"):
        picked = session.get(models.MoneyMapEdge, edge_options[picked_label])
        picked.source_node_id = node_options[new_source]
        picked.target_node_id = node_options[new_target]
        picked.label = new_label.strip() or "routes to"
        session.commit()
        st.success("Edge updated")

    if d_col.button("Delete Edge", key="edge_delete_btn"):
        picked = session.get(models.MoneyMapEdge, edge_options[picked_label])
        session.delete(picked)
        session.commit()
        st.success("Edge deleted")


def render(session):
    st.header("Money Map")
    nodes = session.scalars(select(models.MoneyMapNode)).all()
    edges = session.scalars(select(models.MoneyMapEdge)).all()

    _render_overview(nodes, edges)

    rendered = False
    errors: list[str] = []

    try:
        from streamlit_agraph import Config, Edge, Node, agraph

        g_nodes = [Node(id=str(n.id), label=n.label, size=20, color=PALETTE.get(n.node_type, "#adb5bd")) for n in nodes]
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

    with st.expander("Create / Edit map entities"):
        create_col, edit_col = st.columns([1, 2])
        with create_col:
            st.markdown("**Create**")
            an = st.text_input("Account name")
            at = st.selectbox("Account type", ["checking", "savings", "cash", "credit", "loan"])
            if st.button("Add Account") and an:
                account = models.Account(name=an, type=at)
                session.add(account)
                session.flush()
                session.add(models.MoneyMapNode(node_type="account", ref_id=account.id, label=account.name))
                session.commit()
                st.success("Added account")

            pn = st.text_input("Pod name")
            if st.button("Add Pod") and pn:
                pod = models.Pod(name=pn)
                session.add(pod)
                session.flush()
                session.add(models.MoneyMapNode(node_type="pod", ref_id=pod.id, label=pod.name))
                session.commit()
                st.success("Added pod")

            ln = st.text_input("Liability name")
            md = st.number_input("Min due", min_value=0.0, step=1.0)
            if st.button("Add Liability") and ln:
                li = models.Liability(name=ln, min_due=md)
                session.add(li)
                session.flush()
                session.add(models.MoneyMapNode(node_type="liability", ref_id=li.id, label=li.name))
                session.commit()
                st.success("Added liability")

        with edit_col:
            st.markdown("**Edit Existing**")
            t1, t2, t3, t4 = st.tabs(["Accounts", "Pods", "Liabilities", "Edges"])
            with t1:
                _edit_accounts(session)
            with t2:
                _edit_pods(session)
            with t3:
                _edit_liabilities(session)
            with t4:
                _edit_edges(session)
