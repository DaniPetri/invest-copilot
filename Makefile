# Thin wrappers: all logic lives in scripts/tasks.py (works on Windows without make too:
#   uv run python scripts/tasks.py <target>)
PY ?= uv run python

.PHONY: setup data ingest dev test eval eval-ci contracts record

setup data ingest dev test eval eval-ci contracts record:
	$(PY) scripts/tasks.py $@
