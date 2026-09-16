# Convenience targets (macOS/Linux). Windows users: run the commands directly,
# see docs/commands.md for PowerShell equivalents.

.PHONY: install demo ingest ask test lint eval serve ui-install ui-dev ui-build icons sample-pdf clean

install:
	pip install -e ".[dev]"

ingest:
	rag ingest data/sample_docs

demo: ingest
	rag ask "What is the payload capacity of the Atlas P2?" --trace

test:
	pytest

lint:
	ruff check src tests

eval:
	rag eval

serve:
	rag serve --port 8000

ui-install:
	cd frontend && npm install

ui-dev:
	cd frontend && npm run dev

ui-build:
	cd frontend && npm run build

icons:
	python scripts/make_icons.py

sample-pdf:
	python scripts/make_sample_pdf.py

clean:
	rm -rf storage .pytest_cache .ruff_cache frontend/dist
