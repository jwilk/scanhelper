# Copyright © 2012-2018 Jakub Wilk <jwilk@jwilk.net>
#
# This file is part of scanhelper.
#
# scanhelper is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 2 as published
# by the Free Software Foundation.
#
# scanhelper is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.

PYTHON = python

PREFIX = /usr/local
DESTDIR =

bindir = $(PREFIX)/bin
basedir = $(PREFIX)/share/scanhelper

.PHONY: all
all: doc/xmp

doc/xmp: lib/xmp.py
	$(PYTHON) -m lib.xmp > $(@).tmp
	mv $(@).tmp $(@)

.PHONY: install
install: scanhelper
	install -d $(DESTDIR)$(bindir)
	python_exe=$$($(PYTHON) -c 'import sys; print(sys.executable)') && \
	sed \
		-e "1 s@^#![^ ]*@#!$$python_exe@" \
		-e "s#^basedir = .*#basedir = '$(basedir)/'#" \
		$(<) > $(DESTDIR)$(bindir)/$(<)
	chmod 0755 $(DESTDIR)$(bindir)/$(<)
	install -d $(DESTDIR)$(basedir)/lib
	install -p -m644 lib/*.py $(DESTDIR)$(basedir)/lib/

.PHONY: clean
clean: pyc-clean
	rm -f .coverage
	rm -f doc/xmp

.PHONY: pyc-clean
pyc-clean:  # used by private/build-source-tarball
	find . -name '*.py[co]' -delete

.error = GNU make is required

# vim:ts=4 sts=4 sw=4 noet
