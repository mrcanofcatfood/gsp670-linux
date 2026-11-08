# gsp670-linux — developer and packaging entry points.
#
# The normal way to install is:  sudo ./scripts/install.sh
# These targets exist for packagers and CI.

PREFIX      ?= /usr
DESTDIR     ?=
LIBDIR      ?= $(PREFIX)/lib/gsp670
# Prefer a local virtualenv if one exists, so `make test` works out of the box.
PYTHON      ?= $(shell test -x .venv/bin/python && echo .venv/bin/python || echo python3)
PIP         ?= $(PYTHON) -m pip
INSTALL     ?= install

# The installer uses PIP too, so `make install PIP=...` works end to end.
export PIP

UDEV_DIR       ?= $(PREFIX)/lib/udev/rules.d
SYSTEMD_DIR    ?= $(PREFIX)/lib/systemd/system
WIREPLUMBER_DIR ?= $(PREFIX)/share/wireplumber/wireplumber.conf.d
PIPEWIRE_DIR    ?= $(PREFIX)/share/pipewire/pipewire.conf.d

.PHONY: help install uninstall install-python test lint format check \
        install-udev install-systemd install-config clean

help:
	@echo "gsp670-linux"
	@echo ""
	@echo "  make install          install everything (needs root)"
	@echo "  make uninstall        remove the installed files"
	@echo "  make install-python   install just the Python package"
	@echo "  make test             run the test suite"
	@echo "  make lint             run ruff (if available)"
	@echo "  make format           run ruff format (if available)"
	@echo "  make check            test + lint"
	@echo ""
	@echo "  sudo ./scripts/install.sh   interactive installer (recommended)"
	@echo "  ./scripts/install.sh --user per-user install, no root"

install: install-udev install-systemd install-config install-python

uninstall:
	rm -f $(DESTDIR)$(UDEV_DIR)/99-gsp670.rules
	rm -f $(DESTDIR)$(UDEV_DIR)/99-gsp670-audio.rules
	rm -f $(DESTDIR)$(SYSTEMD_DIR)/gsp670-audio-guard.service
	rm -f $(DESTDIR)$(SYSTEMD_DIR)/gsp670-daemon.service
	rm -f $(DESTDIR)$(SYSTEMD_DIR)/gsp670-monitor.service
	rm -f $(DESTDIR)$(LIBDIR)/gsp670-audio-guard.sh
	rm -f $(DESTDIR)$(WIREPLUMBER_DIR)/50-gsp670.conf
	rm -f $(DESTDIR)$(PIPEWIRE_DIR)/50-gsp670-surround.conf

install-udev:
	$(INSTALL) -D -m 0644 udev/99-gsp670.rules          $(DESTDIR)$(UDEV_DIR)/99-gsp670.rules
	$(INSTALL) -D -m 0644 udev/99-gsp670-audio.rules    $(DESTDIR)$(UDEV_DIR)/99-gsp670-audio.rules

install-systemd:
	$(INSTALL) -D -m 0755 scripts/gsp670-audio-guard.sh $(DESTDIR)$(LIBDIR)/gsp670-audio-guard.sh
	$(INSTALL) -D -m 0644 systemd/gsp670-audio-guard.service $(DESTDIR)$(SYSTEMD_DIR)/gsp670-audio-guard.service
	$(INSTALL) -D -m 0644 systemd/gsp670-daemon.service     $(DESTDIR)$(SYSTEMD_DIR)/gsp670-daemon.service
	$(INSTALL) -D -m 0644 systemd/gsp670-monitor.service    $(DESTDIR)$(SYSTEMD_DIR)/gsp670-monitor.service

install-config:
	$(INSTALL) -D -m 0644 contrib/wireplumber/50-gsp670.conf \
		$(DESTDIR)$(WIREPLUMBER_DIR)/50-gsp670.conf
	$(INSTALL) -D -m 0644 contrib/pipewire/gsp670-virtual-surround-7.1.conf \
		$(DESTDIR)$(PIPEWIRE_DIR)/50-gsp670-surround.conf

install-python:
	@# Modern distributions mark the system Python as externally managed
	@# (PEP 668), so a plain `pip install .` fails. Try the usual escapes.
	@$(PIP) install . || \
	  $(PIP) install --break-system-packages . || \
	  $(PIP) install --user --break-system-packages . || \
	  { echo "pip install failed; try: pipx install ."; exit 1; }

test:
	@$(PYTHON) -c 'import pytest' 2>/dev/null || { \
		echo "pytest not found. Install the dev dependencies:"; \
		echo "  python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'"; \
		exit 1; }
	@$(PYTHON) -m pytest tests/ -q

lint:
	@command -v ruff >/dev/null 2>&1 \
		&& ruff check src/ tests/ scripts/ \
		|| { \
			echo "ruff not installed; skipping (pip install ruff)"; \
			echo "  or: .venv/bin/ruff check src/ tests/ scripts/"; \
		}

format:
	@command -v ruff >/dev/null 2>&1 \
		&& ruff format src/ tests/ scripts/ \
		|| echo "ruff not installed; skipping (pip install ruff)"

check: test lint

clean:
	rm -rf build dist *.egg-info src/*.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	find . -name '*.pyc' -delete
