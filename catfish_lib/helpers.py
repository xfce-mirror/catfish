#!/usr/bin/env python
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
#   Catfish - a versatile file searching tool
#   Copyright (C) 2007-2012 Christian Dywan <christian@twotoasts.de>
#   Copyright (C) 2012-2014 Sean Davis <smd.seandavis@gmail.com>
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

"""Helpers for an Ubuntu application."""
import logging
import os
import sys
from gi.repository import Gtk, GObject

from . catfishconfig import get_data_file
from . Builder import Builder

python_version = sys.version_info[:3]
gobject_version = GObject.pygobject_version
gtk_version = (Gtk.get_major_version(),
               Gtk.get_minor_version(),
               Gtk.get_micro_version())


def check_python_version(major_version, minor_version, micro=0):
    """Return true if running python >= requested version"""
    return python_version >= (major_version, minor_version, micro)


def check_gtk_version(major_version, minor_version, micro=0):
    """Return true if running gtk >= requested version"""
    return gtk_version >= (major_version, minor_version, micro)


def check_gobject_version(major_version, minor_version, micro=0):
    """Return true if running gobject >= requested version"""
    return gobject_version >= (major_version, minor_version, micro)


def get_builder(builder_file_name):
    """Return a fully-instantiated Gtk.Builder instance from specified ui file

    :param builder_file_name: The name of the builder file, without extension.
        Assumed to be in the 'ui' directory under the data path.
    """
    # Look for the ui file that describes the user interface.
    ui_filename = get_data_file('ui', '%s.ui' % (builder_file_name,))
    if not os.path.exists(ui_filename):
        ui_filename = None

    builder = Builder()
    builder.set_translation_domain('catfish')
    builder.add_from_file(ui_filename)
    return builder


def get_media_file(media_file_name):
    """Return the path to the specified media file."""
    media_filename = get_data_file('media', '%s' % (media_file_name,))
    if os.path.exists(media_filename):
        return "file:///" + media_filename
    return None


class NullHandler(logging.Handler):
    """NullHander class."""
    def emit(self, record):
        """Prohibit emission of signals."""
        pass


def set_up_logging(opts):
    """Set up the logging formatter."""
    # add a handler to prevent basicConfig
    root = logging.getLogger()
    null_handler = NullHandler()
    root.addHandler(null_handler)

    formatter = logging.Formatter("%(levelname)s:%(name)s: "
                                  "%(funcName)s() '%(message)s'")

    logger = logging.getLogger('catfish')
    logger_sh = logging.StreamHandler()
    logger_sh.setFormatter(formatter)
    logger.addHandler(logger_sh)

    search_logger = logging.getLogger('catfish_search')
    search_logger_sh = logging.StreamHandler()
    search_logger_sh.setFormatter(formatter)
    search_logger.addHandler(search_logger_sh)

    lib_logger = logging.getLogger('catfish_lib')
    lib_logger_sh = logging.StreamHandler()
    lib_logger_sh.setFormatter(formatter)
    lib_logger.addHandler(lib_logger_sh)

    # Set the logging level to show debug messages.
    if opts.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug('logging enabled')
        search_logger.setLevel(logging.DEBUG)
        if opts.verbose > 1:
            lib_logger.setLevel(logging.DEBUG)


def get_help_uri(page=None):
    """Return the URI for the documentation."""
    # help_uri from source tree - default language
    here = os.path.dirname(__file__)
    help_uri = os.path.abspath(os.path.join(here, '..', 'help', 'C'))

    if not os.path.exists(help_uri):
        # installed so use gnome help tree - user's language
        help_uri = 'catfish'

    # unspecified page is the index.page
    if page is not None:
        help_uri = '%s#%s' % (help_uri, page)

    return help_uri


def show_uri(parent, link):
    """Open the specified URI."""
    from gi.repository import Gtk  # pylint: disable=E0611
    screen = parent.get_screen()
    Gtk.show_uri(screen, link, Gtk.get_current_event_time())


def alias(alternative_function_name):
    '''see http://www.drdobbs.com/web-development/184406073#l9'''
    def decorator(function):
        '''attach alternative_function_name(s) to function'''
        if not hasattr(function, 'aliases'):
            function.aliases = []
        function.aliases.append(alternative_function_name)
        return function
    return decorator
