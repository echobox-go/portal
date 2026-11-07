PY   ?= python3
USER ?= niklas

.PHONY: test dev schema-check
test:
	$(PY) -m pytest -q

# Local development without Pangolin. Edits ../builder/profiles/users if present.
dev:
	EBOX_DEV_USER=$(USER) EBOX_ADMINS=$(USER) $(PY) -m uvicorn app.main:app --reload
