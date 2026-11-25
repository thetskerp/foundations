"""Версионированный SQLite-справочник; встроенные записи нельзя изменить."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class CatalogError(ValueError):
    pass


class Catalog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS catalog_records (
                    kind TEXT NOT NULL,
                    record_key TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK (version > 0),
                    data TEXT NOT NULL,
                    source TEXT NOT NULL,
                    builtin INTEGER NOT NULL CHECK (builtin IN (0,1)),
                    PRIMARY KEY (kind, record_key, version)
                );
                CREATE INDEX IF NOT EXISTS catalog_lookup ON catalog_records(kind, record_key, version DESC);
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path)
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def put(self, kind: str, key: str, version: int, data: dict, source: str, builtin: bool = False) -> None:
        if not kind or not key or version < 1 or not source:
            raise CatalogError("Не заполнены обязательные поля записи")
        with self._connect() as db:
            old = db.execute("SELECT builtin FROM catalog_records WHERE kind=? AND record_key=? ORDER BY version DESC LIMIT 1", (kind, key)).fetchone()
            if old and old[0]:
                raise CatalogError("Встроенную запись нельзя менять; создайте пользовательскую копию")
            try:
                db.execute("INSERT INTO catalog_records VALUES (?,?,?,?,?,?)", (kind, key, version, json.dumps(data, ensure_ascii=False, sort_keys=True), source, int(builtin)))
            except sqlite3.IntegrityError as exc:
                raise CatalogError("Версия записи уже существует") from exc

    def refresh_builtin(self, kind: str, key: str, version: int, data: dict, source: str) -> None:
        """Обновить поставляемую запись при обновлении приложения."""
        with self._connect() as db:
            result = db.execute(
                "UPDATE catalog_records SET data=?, source=? WHERE kind=? AND record_key=? AND version=? AND builtin=1",
                (json.dumps(data, ensure_ascii=False, sort_keys=True), source, kind, key, version),
            )
            if result.rowcount != 1:
                raise CatalogError("Для обновления встроенная запись не найдена")

    def get(self, kind: str, key: str, version: int | None = None) -> dict | None:
        query = "SELECT data,version,source,builtin FROM catalog_records WHERE kind=? AND record_key=?"
        args: tuple = (kind, key)
        if version is not None:
            query += " AND version=?"
            args += (version,)
        query += " ORDER BY version DESC LIMIT 1"
        with self._connect() as db:
            row = db.execute(query, args).fetchone()
        return None if row is None else {"kind": kind, "key": key, "version": row[1], "data": json.loads(row[0]), "source": row[2], "builtin": bool(row[3])}

    def list(self, kind: str) -> list[dict]:
        with self._connect() as db:
            keys = [row[0] for row in db.execute("SELECT DISTINCT record_key FROM catalog_records WHERE kind=? ORDER BY record_key", (kind,))]
        keys.sort(key=lambda key: (0, int(key)) if key.isdecimal() else (1, key))
        return [self.get(kind, key) for key in keys]

    def delete_user_record(self, kind: str, key: str) -> int:
        """Удалить все версии пользовательской записи; встроенный справочник неприкосновенен."""
        with self._connect() as db:
            flags = [row[0] for row in db.execute(
                "SELECT builtin FROM catalog_records WHERE kind=? AND record_key=?", (kind, key))]
            if not flags:
                raise CatalogError("Запись не найдена")
            if any(flags):
                raise CatalogError("Встроенную запись удалить нельзя")
            result = db.execute("DELETE FROM catalog_records WHERE kind=? AND record_key=?", (kind, key))
            return result.rowcount
