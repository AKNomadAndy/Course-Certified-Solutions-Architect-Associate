from __future__ import annotations

from sqlalchemy import select

from db import models


def list_tasks(session, status: str | None = None):
    query = select(models.Task)
    if status:
        query = query.where(models.Task.status == status)
    return session.scalars(query.order_by(models.Task.created_at.desc())).all()


def mark_done(session, task_id: int, note: str | None = None, reference_id: str | None = None):
    task = session.get(models.Task, task_id)
    if not task:
        return None
    task.status = "done"
    if note:
        task.note = note
    if reference_id:
        task.reference_id = reference_id
    session.commit()
    return task
