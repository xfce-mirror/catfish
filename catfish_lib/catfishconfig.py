#!/usr/bin/env python
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
#   Catfish - a versatile file searching tool
#   Copyright (C) 2007-2012 Christian Dywan <christian@twotoasts.de>
#   Copyright (C) 2012-2019 Sean Davis <smd.seandavis@gmail.com>
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

# Where your project will look for your data (for instance, images and ui
# files). By default, this is ../data, relative your trunk layout
__catfish_data_directory__ = '../data/'
# Location of locate.db file
__locate_db_path__ = '/var/lib/mlocate/mlocate.db'
__license__ = 'GPL-3+'
__version__ = '1.4.7'


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
        os.path.dirname(__file__), __catfish_data_directory__)

    abs_data_path = os.path.abspath(path)
    if not os.path.exists(abs_data_path):
        raise project_path_not_found

    return abs_data_path


def get_locate_db_path():
    """Return the location of the locate.db file
    """
    return __locate_db_path__


def get_version():
    """Return the program version number."""
    return __version__
