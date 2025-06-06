#!/usr/bin/env python
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
#   Catfish - a versatile file searching tool
#   Copyright (C) 2007-2012 Christian Dywan <christian@twotoasts.de>
#   Copyright (C) 2012-2022 Sean Davis <bluesabre@xfce.org>
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
#   with this program.  If not, see <https://www.gnu.org/licenses/>.

import os

__all__ = [
    'project_path_not_found',
    'get_data_file',
    'get_data_path',
    'get_locate_db_path',
]

# Location of locate.db file
__locate_db_paths__ = ('/var/lib/plocate/plocate.db', '/var/lib/mlocate/mlocate.db')
__license__ = 'GPL-2+'
__url__ = 'https://docs.xfce.org/apps/catfish/start'

from catfish_lib import defs

class project_path_not_found(Exception):

    """Raised when we can't find the project directory."""


def get_data_file(*path_segments):
    """Get the full path to a data file.

    Returns the path to a file underneath the data directory (as defined by
    `get_data_path`). Equivalent to os.path.join(get_data_path(),
    *path_segments).
    """
    return os.path.join(get_data_path(), *path_segments)


def get_data_path():
    """Retrieve catfish data path

    This path is by default <catfish_lib_path>/../data/ in trunk
    and /usr/share/catfish in an installed version but this path
    is specified at installation time.
    """

    # Get pathname absolute or relative.
    path = os.path.join(
        os.path.dirname(__file__), defs.__catfish_data_directory__)

    abs_data_path = os.path.abspath(path)
    if not os.path.exists(abs_data_path):
        raise project_path_not_found

    return abs_data_path


def get_locate_db_path():
    """Return the location of the locate.db file
    """
    for path in __locate_db_paths__:
        if os.access(os.path.dirname(path), os.F_OK):
            return path
    return __locate_db_paths__[0]


def get_version():
    """Return the program version number."""
    if '-dev' in defs.__version__:
        return f"{defs.__version__}-{defs.__revision__}"
    else:
        return defs.__version__


def get_about():
    from locale import gettext as _

    return {
        'version': get_version(),
        'program_name': _('Catfish File Search'),
        'icon_name': 'org.xfce.catfish',
        'website': __url__,
        'comments': _('Catfish is a versatile file searching tool.'),
        'copyright': 'Copyright (C) 2007-2012 Christian Dywan <christian@twotoasts.de>\n'
                     'Copyright (C) 2012-2022 Sean Davis <bluesabre@xfce.org>\n'
                     f'Copyright (C) 2022-{defs.__copyright_year__} The Xfce development team',
        'authors': [
            'Christian Dywan <christian@twotoasts.de>',
            'Sean Davis <bluesabre@xfce.org>'],
        'artists': ['Nancy Runge <nancy@twotoasts.de>']}
