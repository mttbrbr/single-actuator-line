.PHONY: generate check-env mesh smoke mann run resume postprocess

generate:
	python3 tools/generate_case.py

check-env:
	./scripts/check_environment.sh

mesh:
	./scripts/mesh.sh

smoke:
	./scripts/run_smoke.sh

mann:
	python3 tools/generate_mann_inflow.py

run:
	./scripts/run_production.sh

resume:
	./scripts/run_production.sh --resume

postprocess:
	$(if $(wildcard .venv/bin/python),.venv/bin/python,python3) scripts/postprocess.py all
