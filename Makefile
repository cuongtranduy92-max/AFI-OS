.PHONY: bootstrap dev test lint migrate seed package

bootstrap:
	./bootstrap.sh

dev:
	./run.sh

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check src tests

migrate:
	.venv/bin/alembic upgrade head

seed:
	.venv/bin/python -m afi_os.seed_demo

package:
	./scripts/package_review.sh
