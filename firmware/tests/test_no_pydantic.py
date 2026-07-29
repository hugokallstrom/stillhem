"""Regression guard for slopstop-4sh.

pydantic-core is a Rust extension with no working ARMv6 build: importing it
SIGILLs on a Pi B+, which crash-looped stillhem-admin on the flashed image.
The admin app was ported off FastAPI to pure Starlette precisely to drop that
dependency. These tests fail loudly if FastAPI/pydantic ever creep back in, so
the box stays bootable on ARMv6.
"""

import sys

import pytest


def _build_admin_app():
    from pathlib import Path

    from stillhem.admin.app import create_app

    return create_app(db_path=Path("/nonexistent/stillhem.db"))


def test_building_the_app_imports_no_pydantic() -> None:
    # Drop any already-imported copies so we observe what building the app pulls
    # in, not what an earlier test happened to import.
    for name in list(sys.modules):
        if name == "pydantic_core" or name.startswith(("fastapi", "pydantic")):
            del sys.modules[name]

    _build_admin_app()

    leaked = sorted(
        name
        for name in sys.modules
        if name == "pydantic_core" or name.startswith(("fastapi", "pydantic"))
    )
    assert not leaked, f"admin app must not import FastAPI/pydantic; got {leaked}"


def test_fastapi_is_not_a_runtime_dependency() -> None:
    import importlib.metadata as md

    runtime_deps = md.requires("stillhem") or []
    names = {req.split(";")[0].split()[0].split(">")[0].split("=")[0].split("[")[0].strip().lower()
             for req in runtime_deps}
    assert "fastapi" not in names, f"fastapi must not be a declared dependency; deps={sorted(names)}"
    assert "pydantic" not in names, f"pydantic must not be a declared dependency; deps={sorted(names)}"
