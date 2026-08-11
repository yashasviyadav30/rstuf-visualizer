# Short names for long commands. `make help` prints them all: `make tests`
# runs the tests, `make run-local` starts the service on this machine.
# None of it is needed to build or ship the service; it only saves typing.

.PHONY: all setup test test-unit test-integration test-e2e test-docker \
	lint tests \
	clean purge run-dev run-local stop build-dev reformat \
	precommit coverage fixtures chart-lint help

all: help

setup:  ## Install the backend's dependencies
	pipenv install --dev --deploy

reformat:  ## Reformat code with black and isort
	black -l 79 .
	isort -l79 --profile black .

# Two sessions on purpose: see the note in pyproject.toml. The browser tests
# skip themselves where the interface is not built or no browser is installed,
# so this is safe to run anywhere.
test:  ## Run the tests
	pipenv run pytest
	pipenv run pytest tests/e2e

test-unit:  ## Run only the tests that reach nothing outside the process
	pipenv run pytest tests/unit

test-integration:  ## Run only the tests driven against a real repository
	pipenv run pytest tests/integration

# The interface has to be compiled and a browser installed before these can
# run; both are conditions they check and skip on rather than failing.
test-e2e:  ## Open the built interface in a real browser
	pipenv run playwright install chromium
	pipenv run pytest tests/e2e

# python-tuf caches its trust anchor behind a symbolic link, which Windows
# refuses without Developer Mode, so the integration tests skip themselves
# there. This runs the whole suite on Linux, where nothing skips, which is
# also what CI does.
test-docker:  ## Run every test on Linux, where nothing skips
	docker run --rm -v "$(CURDIR)/..:/w" -w /w/backend python:3.13-slim \
		bash -c "pip install --quiet --no-cache-dir pipenv \
		&& pipenv install --dev --deploy --system --quiet \
		&& pytest -q"

lint:  ## Run the linters CI runs, in the order it runs them
	flake8 app tests scripts
	black -l79 --check --diff app tests scripts
	isort -l79 --profile black --check --diff app tests scripts
	bandit -q -r app

tests:  ## Run the linters and tests in fresh environments, as CI does
	tox -r

precommit:  ## Install and run pre-commit hooks
	pre-commit install
	pre-commit run --all-files --show-diff-on-failure

coverage:  ## Run tests with coverage
	coverage report
	coverage html -i

fixtures:  ## Generate local TUF repositories for development
	python scripts/gen_fixture.py

run-local:  ## Serve a generated repository and read it, without Docker
	./scripts/run_local.sh

# The image carries the interface as well as the backend, so it is built from
# the repository root rather than from here.
build-dev:  ## Build the dev image
	docker build -t rstuf-visualizer:dev -f ../Dockerfile ..

run-dev:  ## Run the development environment
	$(MAKE) fixtures
	docker compose -f ../compose.yaml up --build --remove-orphans

stop:  ## Stop the development environment
	docker compose -f ../compose.yaml down -v

clean:  ## Clean up the environment
	$(MAKE) stop
	docker compose -f ../compose.yaml rm --force

purge:  ## Remove all images and containers
	$(MAKE) clean
	docker rmi rstuf-visualizer:dev --force

chart-lint:  ## Lint the Helm chart the way its CI does
	helm lint ../charts/rstuf-visualizer \
		--values ../charts/rstuf-visualizer/ci/default-values.yaml

help:  ## Show this message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'
