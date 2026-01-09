.PHONY: build publish test-publish clean deps docs docs-serve docs-deploy

VENV = .venv
PYTHON = $(VENV)/bin/python
UV = uv

deps:
	$(UV) pip install hatchling twine

build: deps
	$(UV) run python -m hatchling build

publish: build
	$(UV) run twine upload dist/*

test-publish: build
	$(UV) run twine upload --repository testpypi dist/*

clean:
	rm -rf dist *.egg-info

# Documentation
docs:
	$(UV) run mkdocs build

docs-serve:
	$(UV) run mkdocs serve

docs-deploy:
	$(UV) run mkdocs gh-deploy --force