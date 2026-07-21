.PHONY: generate test check-env mesh smoke mann clean

generate:
	python3 tools/generate_case.py

test:
	python3 -m unittest discover -s tests -v
	python3 tools/generate_case.py --check
	python3 tools/generate_mann_inflow.py --dry-run

check-env:
	./scripts/check_environment.sh

mesh:
	./scripts/mesh.sh

smoke:
	./scripts/run_smoke.sh

mann:
	python3 tools/generate_mann_inflow.py

clean:
	./scripts/clean.sh

