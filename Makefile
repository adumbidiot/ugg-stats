.PHONY: lint
lint:
	uv run ruff format
	uv run ruff check
	uv run ty check
	
.PHONY: lint-fix
lint-fix:
	uv run ruff format
	uv run ruff check --fix
	uv run ty check
	
.PHONY: mypy
mypy:
	uv run mypy .