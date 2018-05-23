# Copyright © 2012-2018 Jakub Wilk <jwilk@jwilk.net>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 dated June, 1991.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.

PYTHON = python

.PHONY: all
all: doc/xmp

doc/xmp: lib/xmp.py
	$(PYTHON) -c 'import lib.xmp; print lib.xmp.__doc__.strip()' > $(@).tmp
	mv $(@).tmp $(@)

.PHONY: clean
clean: pyc-clean
	rm -f .coverage
	rm -f doc/xmp

.PHONY: pyc-clean
pyc-clean:  # used by private/build-source-tarball
	find . -name '*.py[co]' -delete

# vim:ts=4 sts=4 sw=4 noet
