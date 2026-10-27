PY ?= python3
CASE ?= examples/case_acme_health_multi.json
EU   ?= examples/case_acme_eu_transfers.json

.PHONY: help selfcheck test demo statutes parse precedents sources report clean

help:
	@echo "make selfcheck    - validate data files and run the parser + model end to end"
	@echo "make test         - run the unit tests (unittest, no dependencies)"
	@echo "make demo         - generate the two example reports into reports/"
	@echo "make statutes     - list every statutory penalty range in the registry"
	@echo "make precedents   - list decided matters used for calibration"
	@echo "make sources      - print every source URL behind the data"
	@echo "make report CASE=examples/case_acme_eu_transfers.json"

selfcheck:
	$(PY) -m penex selfcheck

test:
	$(PY) -m unittest discover -s tests -t . -v

statutes:
	$(PY) -m penex statutes

precedents:
	$(PY) -m penex precedents

sources:
	$(PY) -m penex sources

parse:
	$(PY) -m penex parse examples/complaint_fixture_ccpa_ag.txt --jurisdiction US-CA

demo: selfcheck
	@mkdir -p reports
	$(PY) -m penex model $(EU) --out reports/report_eu_transfers.md
	$(PY) -m penex model $(CASE) --out reports/report_us_health_multi.md
	$(PY) -m penex model $(CASE) --json > reports/report_us_health_multi.json
	@ls -l reports/

report:
	$(PY) -m penex model $(CASE) --out reports/report.md

clean:
	rm -rf reports/*.md reports/*.json
