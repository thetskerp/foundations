"""Команды для проверки справочника и проектного файла без GUI."""

import argparse
import json

from .catalog import Catalog
from .domain import Project
from .project_io import load_project, save_project


def main() -> None:
    parser = argparse.ArgumentParser(prog="oif")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("new")
    create.add_argument("path")
    create.add_argument("--name", default="Новый проект")
    show = sub.add_parser("show")
    show.add_argument("path")
    catalog = sub.add_parser("catalog")
    catalog.add_argument("database")
    catalog.add_argument("kind", choices=["soil", "scheme", "load"])
    args = parser.parse_args()
    if args.command == "new":
        save_project(Project(name=args.name), args.path)
        print(args.path)
    elif args.command == "show":
        p = load_project(args.path)
        print(json.dumps({"id": p.id, "name": p.name, "profile": p.profile, "ready": p.is_ready_for_calculation}, ensure_ascii=False, indent=2))
    elif args.command == "catalog":
        print(json.dumps(Catalog(args.database).list(args.kind), ensure_ascii=False, indent=2))
