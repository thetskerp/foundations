"""Атомарный обмен полным набором справочников в .oifcatalog."""

import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile

from .catalog import Catalog, CatalogError

CATALOG_SCHEMA_VERSION = 1
KINDS = ("soil", "scheme", "load")


def export_catalog(catalog: Catalog, path: str | Path, *, author: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payloads = {f"{kind}.json": json.dumps(catalog.list(kind), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") for kind in KINDS}
    manifest = {"format": "oifcatalog", "schema_version": CATALOG_SCHEMA_VERSION, "author": author, "members": {name: hashlib.sha256(body).hexdigest() for name, body in payloads.items()}}
    with NamedTemporaryFile(prefix="oifcatalog-", suffix=".tmp", dir=target.parent, delete=False) as temp:
        temporary = Path(temp.name)
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
            for name, body in payloads.items():
                archive.writestr(name, body)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def preview_catalog_import(path: str | Path, catalog: Catalog) -> dict:
    with ZipFile(path) as archive:
        required = {"manifest.json", *(f"{kind}.json" for kind in KINDS)}
        if set(archive.namelist()) != required:
            raise CatalogError("Неверный состав каталога")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != "oifcatalog" or manifest.get("schema_version") != CATALOG_SCHEMA_VERSION:
            raise CatalogError("Неподдерживаемая версия каталога")
        records = []
        for kind in KINDS:
            name = f"{kind}.json"
            if archive.getinfo(name).file_size > 25_000_000:
                raise CatalogError("Слишком большой файл каталога")
            body = archive.read(name)
            if hashlib.sha256(body).hexdigest() != manifest["members"].get(name):
                raise CatalogError(f"Нарушена целостность: {name}")
            entries = json.loads(body)
            if not isinstance(entries, list):
                raise CatalogError(f"Неверный формат: {name}")
            for entry in entries:
                if entry.get("kind") != kind or not isinstance(entry.get("data"), dict):
                    raise CatalogError(f"Неверная запись: {name}")
                records.append(entry)
    additions, conflicts = [], []
    for entry in records:
        existing = catalog.get(entry["kind"], entry["key"], int(entry["version"]))
        if existing is None:
            additions.append(entry)
        elif existing["data"] != entry["data"]:
            conflicts.append({"kind": entry["kind"], "key": entry["key"], "version": entry["version"]})
    return {"additions": additions, "conflicts": conflicts, "author": manifest.get("author")}


def import_catalog(path: str | Path, catalog: Catalog) -> dict:
    preview = preview_catalog_import(path, catalog)
    if preview["conflicts"]:
        raise CatalogError("Конфликт версий записей")
    # Один SQLite transaction: при ошибке не остаётся частичного импорта.
    with catalog._connect() as db:
        for entry in preview["additions"]:
            latest = db.execute("SELECT builtin FROM catalog_records WHERE kind=? AND record_key=? ORDER BY version DESC LIMIT 1", (entry["kind"], entry["key"])).fetchone()
            if latest and latest[0]:
                raise CatalogError("Встроенную запись нельзя обновить импортом")
            db.execute("INSERT INTO catalog_records VALUES (?,?,?,?,?,?)", (entry["kind"], entry["key"], int(entry["version"]), json.dumps(entry["data"], ensure_ascii=False, sort_keys=True), entry["source"], 0))
    return {"added": len(preview["additions"]), "author": preview["author"]}
