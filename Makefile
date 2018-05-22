.PHONY: all
all: doc/xmp.txt

doc/xmp.txt: lib/xmp.py
	python -c 'import lib.xmp; print lib.xmp.__doc__.strip()' > $(@)~
	mv $(@)~ $(@)

.PHONY: clean
clean: pyc-clean
	rm -f doc/xmp.txt

.PHONY: pyc-clean
pyc-clean:
	find . -name '*.py[co]' -delete

# vim:ts=4 sts=4 sw=4 noet
