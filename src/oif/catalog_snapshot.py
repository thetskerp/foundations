"""Приоритет за версионированными записями, сохранёнными внутри проекта."""

from .catalog import Catalog
from .domain import Project


class ProjectCatalog:
    def __init__(self, project: Project, fallback: Catalog):
        self.project = project
        self.fallback = fallback

    def get(self, kind: str, key: str, version: int | None = None) -> dict | None:
        snapshot = self.project.catalog_snapshot or {}
        if kind == "soil":
            record = snapshot.get("soils", {}).get(key)
        elif kind == "load":
            record = snapshot.get("loads", {}).get(key)
            if record is None and snapshot.get("load", {}).get("key") == key:
                record = snapshot["load"]
        elif kind == "scheme":
            scheme = snapshot.get("scheme") or {}
            record = scheme if scheme.get("key") == key else None
        else:
            record = None
        if record is not None and (version is None or record.get("version") == version):
            return record
        return self.fallback.get(kind, key, version)
