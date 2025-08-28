.PHONY: setup lint test api format typecheck clean

setup:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && pip install -e .

lint:
	ruff check src && ruff format --check src

format:
	ruff format src

typecheck:
	mypy src

test:
	pytest -q --cov=quantdesk --cov-report=term-missing

api:
	uvicorn quantdesk.api.main:app --reload --port 8000

clean:
	rm -rf .pytest_cache .mypy_cache dist build *.egg-info
