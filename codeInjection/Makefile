SHELL := /bin/sh

SCRIPT := poolingServer.py
PYTHON ?= python3
USER_NAME ?= $(or $(USER),$(shell id -u))

ROOT ?= /sgoinfre/goinfre/Perso/$(USER_NAME)
TEST_ACTION_DIR ?= /home/achaisne/sgoinfre/test
POLL ?= 2
EXCLUDE_DIR ?=

.PHONY: help deploy test

help:
	@echo "Usage:"
	@echo "  make deploy                  # watch full ROOT forever and inject on matching files"
	@echo "  make test                    # watch full ROOT, inject only in TEST_ACTION_DIR, stop after first injection"
	@echo ""
	@echo "Params (override with make VAR=value ...):"
	@echo "  ROOT=$(ROOT)"
	@echo "  TEST_ACTION_DIR=$(TEST_ACTION_DIR)"
	@echo "  POLL=$(POLL)"
	@echo "  EXCLUDE_DIR=$(EXCLUDE_DIR)"

deploy:
	PYTHONUNBUFFERED=1 $(PYTHON) $(SCRIPT) \
		--root "$(ROOT)" \
		--poll $(POLL) \
		--exclude-dir "$(EXCLUDE_DIR)"

test:
	PYTHONUNBUFFERED=1 $(PYTHON) $(SCRIPT) \
		--root "$(ROOT)" \
		--action-dir "$(TEST_ACTION_DIR)" \
		--stop-after-first \
		--poll $(POLL) \
		--exclude-dir "$(EXCLUDE_DIR)"
