.PHONY: all
all: doc/xmp.txt

doc/xmp.txt: lib/xmp.py
	python -c 'import lib.xmp; print lib.xmp.__doc__.strip()' >> $(@)~
	mv $(@)~ $(@)

# vim:ts=4 sw=4 noet
