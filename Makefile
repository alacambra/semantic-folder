.PHONY: lint typecheck test requirements package deploy

DIST_DIR := dist/publish
POETRY := $(shell command -v .venv/bin/poetry 2>/dev/null || command -v poetry)

lint:
	$(POETRY) run ruff check src/ tests/ function_app.py
	$(POETRY) run ruff format --check src/ tests/ function_app.py

typecheck:
	$(POETRY) run pyright src/ tests/

test:
	$(POETRY) run pytest

requirements:
	$(POETRY) export --without-hashes --only main -o requirements.txt

package: requirements
	rm -rf $(DIST_DIR)
	mkdir -p $(DIST_DIR)
	cp function_app.py host.json requirements.txt $(DIST_DIR)/
	rsync -a --exclude='__pycache__' src/ $(DIST_DIR)/src/

deploy: package
	func azure functionapp publish $(FUNCTION_APP_NAME) --python --build remote -p $(DIST_DIR)
