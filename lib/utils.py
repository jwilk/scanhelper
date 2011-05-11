# encoding=UTF-8

# Copyright © 2011 Jakub Wilk <jwilk@jwilk.net>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 dated June, 1991.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.

import os
import re

debian = os.path.isdir('/var/lib/dpkg/info/')

def enhance_import_error(exception, package, debian_package, homepage):
    message = str(exception)
    format = '%(message)s; please install the %(package)s package'
    if debian:
        package = debian_package
    else:
        format += ' <%(homepage)s>'
    exception.args = [format % locals()]

def shell_escape(s, safe=re.compile('^[a-zA-Z0-9_+/=.,:%-]+$').match):
    if safe(s):
        return s
    return "'%s'" % s.replace("'", r"'\''")

def shell_escape_list(lst):
    return ' '.join(map(shell_escape, lst))

# vim:ts=4 sw=4 et
