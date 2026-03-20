PYTHON ?= python
INPUT ?= input/HORÁRIO TURMAS 2026 1.PDF
OUTPUT ?= dist
HOST ?= 127.0.0.1
PORT ?= 8000
EMAIL_BASE ?= input/professores_emails.csv

.PHONY: help install generate serve serve-only dev clean

help:
	@echo "Comandos disponíveis:"
	@echo "  make install      - Instala dependências"
	@echo "  make generate     - Gera HTML + JSON a partir do PDF"
	@echo "  make serve        - Gera e sobe servidor local"
	@echo "  make serve-only   - Sobe servidor local sem regenerar"
	@echo "  make dev          - Instala dependências, gera e sobe servidor local"
	@echo "  make clean        - Remove pasta de saída"
	@echo ""
	@echo "Variáveis opcionais:"
	@echo "  INPUT=<arquivo.pdf> OUTPUT=<pasta> HOST=<host> PORT=<porta> EMAIL_BASE=<arquivo.csv>"

install:
	$(PYTHON) -m pip install -r requirements.txt

generate:
	$(PYTHON) src/generate_site.py --input "$(INPUT)" --output "$(OUTPUT)" --email-base "$(EMAIL_BASE)"

serve:
	$(PYTHON) src/run_local_server.py --input "$(INPUT)" --output "$(OUTPUT)" --host "$(HOST)" --port "$(PORT)" --email-base "$(EMAIL_BASE)"

serve-only:
	$(PYTHON) src/run_local_server.py --output "$(OUTPUT)" --host "$(HOST)" --port "$(PORT)" --skip-generate

dev: install
	$(PYTHON) src/run_local_server.py --input "$(INPUT)" --output "$(OUTPUT)" --host "$(HOST)" --port "$(PORT)" --email-base "$(EMAIL_BASE)"

clean:
	rm -rf "$(OUTPUT)"