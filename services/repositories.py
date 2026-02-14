from __future__ import annotations

from sqlalchemy import select


class Repository:
    def __init__(self, session, model):
        self.session = session
        self.model = model

    def list_all(self):
        return self.session.scalars(select(self.model)).all()

    def get(self, entity_id: int):
        return self.session.get(self.model, entity_id)

    def add(self, **kwargs):
        entity = self.model(**kwargs)
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return entity

    def upsert_by(self, unique_field: str, payload: dict):
        current = self.session.scalar(select(self.model).where(getattr(self.model, unique_field) == payload[unique_field]))
        if current:
            for k, v in payload.items():
                setattr(current, k, v)
            self.session.commit()
            self.session.refresh(current)
            return current, False
        created = self.model(**payload)
        self.session.add(created)
        self.session.commit()
        self.session.refresh(created)
        return created, True
