TEST_FILE ?= /sgoinfre/goinfre/Perso/achaisne/test/hello.c
TEST_ROOT := $(dir $(TEST_FILE))
TEST_WINDOW ?= 3600

basis:
	python3 poolingServer.py
once:
	python3 poolingServer.py --once
agressive:
	python3 poolingServer.py --window 30 --poll 0.5
dryrun:
	python3 poolingServer.py --dry-run --once
backup:
	python3 poolingServer.py --backup --once

# Tester for a specific file outside default 30s window constraints.
test-hello-dryrun:
	@test -f "$(TEST_FILE)" || (echo "Missing test file: $(TEST_FILE)" && exit 1)
	@touch "$(TEST_FILE)"
	python3 poolingServer.py --root "$(TEST_ROOT)" --window $(TEST_WINDOW) --dry-run --once --verbose

test-hello:
	@test -f "$(TEST_FILE)" || (echo "Missing test file: $(TEST_FILE)" && exit 1)
	@touch "$(TEST_FILE)"
	python3 poolingServer.py --root "$(TEST_ROOT)" --window $(TEST_WINDOW) --backup --once --verbose
