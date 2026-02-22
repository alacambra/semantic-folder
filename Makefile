.PHONY: lint typecheck test requirements deploy

lint:
	poetry run ruff check src/ tests/ function_app.py
	poetry run ruff format --check src/ tests/ function_app.py

typecheck:
	poetry run pyright src/ tests/

test:
	poetry run pytest

requirements:
	poetry export --without-hashes --only main -o requirements.txt

deploy: requirements
	func azure functionapp publish $(FUNCTION_APP_NAME)
