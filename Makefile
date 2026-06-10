.PHONY: install test demo help

install:  ## Install hop-core and dev dependencies
	pip install -e ".[dev]"

test:  ## Run the test suite
	./scripts/test.sh

test-v:  ## Run the test suite with verbose output
	./scripts/test.sh -v

demo:  ## Start the demo app (backend + frontend)
	$(MAKE) -C demo start

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
