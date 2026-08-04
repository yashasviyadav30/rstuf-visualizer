.PHONY: all tests clean purge run-dev stop build-dev reformat precommit \
	coverage fixtures chart-lint help

all: help

reformat:  ## Reformat code with black and isort
	black -l 79 .
	isort -l79 --profile black .

tests:  ## Run all tests
	tox -r

precommit:  ## Install and run pre-commit hooks
	pre-commit install
	pre-commit run --all-files --show-diff-on-failure

coverage:  ## Run tests with coverage
	coverage report
	coverage html -i

fixtures:  ## Generate local TUF repositories for development
	python scripts/gen_fixture.py

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
