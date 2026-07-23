.PHONY: install test run-ml run-maps run-olx docker-build docker-run clean

install:
	pip install -r requirements.txt

test:
	python -m pytest tests/ -v

run-ml:
	python scripts/test_ml_real.py

run-maps:
	python scripts/test_maps_real.py --visible

run-olx:
	python scripts/test_olx_real.py --visible

run-all: run-ml run-maps run-olx

docker-build:
	docker compose build

docker-run:
	docker compose up bot

docker-ml:
	docker compose run bot --client-id demo_mercado_livre

docker-maps:
	docker compose run bot --client-id demo_google_maps

docker-olx:
	docker compose run bot --client-id demo_olx

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf data/logs/*.html data/logs/*.png 2>/dev/null || true
