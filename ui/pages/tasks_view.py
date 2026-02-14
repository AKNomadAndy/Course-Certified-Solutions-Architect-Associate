from __future__ import annotations

import streamlit as st
from services.tasks import list_tasks, mark_done


def render(session):
    st.header("Next Actions")
    status_filter = st.selectbox("Filter", ["all", "open", "done"])
    tasks = list_tasks(session, None if status_filter == "all" else status_filter)
    for task in tasks:
        with st.container(border=True):
            st.write(f"#{task.id} {task.title} ({task.status})")
            st.caption(f"type: {task.task_type} due: {task.due_date}")
            note = st.text_input(f"Note for {task.id}", key=f"note_{task.id}")
            ref = st.text_input(f"Reference for {task.id}", key=f"ref_{task.id}")
            if task.status != "done" and st.button(f"Mark done {task.id}"):
                mark_done(session, task.id, note, ref)
                st.success("Updated")
