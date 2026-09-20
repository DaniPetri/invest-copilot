"""scripts/tasks.py: the dev server command."""

import importlib.util
from pathlib import Path

TASKS = Path(__file__).resolve().parents[2] / "scripts" / "tasks.py"
spec = importlib.util.spec_from_file_location("tasks", TASKS)
tasks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tasks)


def test_api_reload_watches_only_the_app_source():
    """Without --reload-dir uvicorn watches the whole backend/ folder, including .venv: installed packages
    (.pyc writes, first imports) then trigger a reload right at startup."""
    cmd = tasks.api_dev_command()
    assert "--reload" in cmd
    dirs = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--reload-dir"]
    assert dirs == ["app"]
    assert (tasks.BACKEND / "app").is_dir()  # relative to the API's cwd


def test_api_dev_command_still_serves_the_app_on_8000():
    cmd = tasks.api_dev_command()
    assert "app.main:app" in cmd and cmd[cmd.index("--port") + 1] == "8000"
