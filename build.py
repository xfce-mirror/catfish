#!/usr/bin/env python
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
#   Catfish - a versatile file searching tool
#   Copyright (C) 2007-2012 Christian Dywan <christian@twotoasts.de>
#   Copyright (C) 2012-2015 Sean Davis <smd.seandavis@gmail.com>
#
#   This program is free software: you can redistribute it and/or modify it
#   under the terms of the GNU General Public License version 2, as published
#   by the Free Software Foundation.
#
#   This program is distributed in the hope that it will be useful, but
#   WITHOUT ANY WARRANTY; without even the implied warranties of
#   MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
#   PURPOSE.  See the GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License along
#   with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
import os

if len(sys.argv) < 2:
    print('No arguments supplied.')
    sys.exit(1)

# lint:disable
if sys.argv[1] == 'check':
    print('Checking module dependencies...')
    try:
        import optparse
        import locale
        import hashlib
        import shutil
        import mimetypes
        import itertools
        import inspect
        import functools
        import logging
        import calendar
        import datetime
        import time
        from xml.sax.saxutils import escape, unescape
        from gi.repository import GObject, Gtk, Gdk, GdkPixbuf, Pango
        import zeitgeist  # optional
# lint:enable

    except ImportError as msg:
        print((str(msg)))
        module = str(msg).split()[-1]
        if module != 'zeitgeist':
            print(('...Error: The required module %s is missing.' % module))
            sys.exit(1)
        else:
            print(('...Warning: The optional module %s is missing.' % module))
    print ('...OK')

elif sys.argv[1] == 'build':
    import py_compile

    for filename in os.listdir('catfish_lib'):
        filename = 'catfish_lib/' + filename
        if filename.endswith('.py'):
            print(('Compiling %s ...' % filename))
            py_compile.compile(filename, filename + 'c')

    for filename in os.listdir('catfish'):
        filename = 'catfish/' + filename
        if filename.endswith('.py'):
            print(('Compiling %s ...' % filename))
            py_compile.compile(filename, filename + 'c')

    print ('Compiling bin/catfish ...')
    py_compile.compile('bin/catfish.py', 'bin/catfish.pyc')
