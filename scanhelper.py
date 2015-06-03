# encoding=UTF-8

'''
helper module that allows using the command-line tool without installing it
'''

import sys
import lib

sys.modules['scanhelper'] = lib

# vim:ts=4 sts=4 sw=4 et
