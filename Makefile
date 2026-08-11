# One entry point for both halves of the project. `make setup` prepares a
# machine to work on it; `make test` runs everything.
#
# The real work lives in backend/Makefile, and this file delegates rather
# than repeating it. That matters: those targets build the image with
# `-f ../Dockerfile ..` and lint the chart at `../charts/`, and tox and
# pytest both read their configuration expecting to start from backend/.
# Copying the commands up here would quietly change every one of those paths.

.PHONY: all setup setup-backend setup-frontend test test-unit \
	test-integration test-docker lint fixtures run-local help

all: help

setup: setup-backend setup-frontend  ## Prepare this machine to work on the project

setup-backend:  ## Install the backend's dependencies
	$(MAKE) -C backend setup

setup-frontend:  ## Install the interface's dependencies
	@echo "The interface is plain HTML, CSS and JavaScript served by the"
	@echo "backend, so there is nothing to install yet. This target exists"
	@echo "so that setup stays one command once that changes."

test:  ## Run every test
	$(MAKE) -C backend test

test-unit:  ## Run only the tests that reach nothing outside the process
	$(MAKE) -C backend test-unit

test-integration:  ## Run only the tests driven against a real repository
	$(MAKE) -C backend test-integration

test-docker:  ## Run every test on Linux, where nothing skips
	$(MAKE) -C backend test-docker

lint:  ## Run the linters CI runs
	$(MAKE) -C backend lint

fixtures:  ## Generate the local TUF repositories used in development
	$(MAKE) -C backend fixtures

run-local:  ## Serve a generated repository and read it, without Docker
	$(MAKE) -C backend run-local

help:  ## Show this message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'
