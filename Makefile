PYTHON := .venv/bin/python
APP_NAME := OIF-Foundations
APP_BUNDLE := dist/$(APP_NAME).app

.PHONY: help setup run test smoke check build install open

help:
	@echo "make setup   — создать/обновить виртуальное окружение"
	@echo "make run     — запустить исходники без сборки"
	@echo "make check   — запустить тесты и быструю проверку интерфейса"
	@echo "make build   — проверить и собрать macOS .app"
	@echo "make install — собрать и установить в ~/Applications"
	@echo "make open    — открыть установленное приложение"

setup:
	test -x $(PYTHON) || python3.12 -m venv .venv
	$(PYTHON) -m pip install -e '.[desktop,build]'

run:
	$(PYTHON) -m oif.ui

test:
	env PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s tests -v

smoke:
	env PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen $(PYTHON) scripts/ui_smoke.py

check: test smoke

build: check
	mkdir -p .pyinstaller-cache
	env PYINSTALLER_CONFIG_DIR="$(CURDIR)/.pyinstaller-cache" $(PYTHON) -m PyInstaller --noconfirm OIF-Foundations.spec

install: build
	bash scripts/install_macos.sh "$(CURDIR)/$(APP_BUNDLE)"

open:
	open "$$($(PYTHON) -c 'from pathlib import Path; print(Path.home() / "Applications" / "OIF-Foundations.app")')"
