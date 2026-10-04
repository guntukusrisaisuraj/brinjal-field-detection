from __future__ import annotations

import ast
import os
from pathlib import Path

from app import config


def test_loads_backend_env_independent_of_current_directory(tmp_path, monkeypatch):
    backend_dir = tmp_path / "backend"
    app_dir = backend_dir / "app"
    app_dir.mkdir(parents=True)
    (backend_dir / ".env").write_text(
        "DATABASE_URL=sqlite+aiosqlite:///from-dotenv.db\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "__file__", str(app_dir / "config.py"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert config.load_backend_environment() is True
    assert os.environ["DATABASE_URL"] == "sqlite+aiosqlite:///from-dotenv.db"


def test_process_environment_takes_precedence_over_backend_env(tmp_path, monkeypatch):
    backend_dir = tmp_path / "backend"
    app_dir = backend_dir / "app"
    app_dir.mkdir(parents=True)
    (backend_dir / ".env").write_text(
        "DATABASE_URL=sqlite+aiosqlite:///from-dotenv.db\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "__file__", str(app_dir / "config.py"))
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///from-process.db")

    config.load_backend_environment()

    assert os.environ["DATABASE_URL"] == "sqlite+aiosqlite:///from-process.db"


def test_main_loads_environment_before_importing_environment_consumers():
    main_path = Path(__file__).resolve().parents[1] / "app" / "main.py"
    tree = ast.parse(main_path.read_text(encoding="utf-8"))
    statements = tree.body
    loader_call = next(
        index
        for index, statement in enumerate(statements)
        if isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and statement.value.func.id == "load_backend_environment"
    )
    consumer_imports = [
        index
        for index, statement in enumerate(statements)
        if isinstance(statement, ast.ImportFrom)
        and statement.module in {"app.api", "app.database", "app.earth_engine.ee_client"}
    ]

    assert consumer_imports
    assert loader_call < min(consumer_imports)
