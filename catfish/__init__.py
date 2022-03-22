#!/usr/bin/env python
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
#   Catfish - a versatile file searching tool
#   Copyright (C) 2007-2012 Christian Dywan <christian@twotoasts.de>
#   Copyright (C) 2012-2020 Sean Davis <bluesabre@xfce.org>
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

# pylint: disable=C0413

import optparse
import signal
import sys

from locale import gettext as _

import gi
gi.require_version('Gtk', '3.0')  # noqa

from gi.repository import Gtk

from catfish import CatfishWindow

from catfish_lib import set_up_logging, get_version


def parse_options():
    """Support for command line options"""
    usage = _("Usage: %prog [options] path query")
    parser = optparse.OptionParser(version="catfish %s" % get_version(),
                                   usage=usage)
    parser.add_option(
        "-v", "--verbose", action="count", dest="verbose",
        help=_("Show debug messages (-vv will also debug catfish_lib)"))

    parser.add_option('', '--large-icons', action='store_true',
                      dest='icons_large', help=_('Use large icons'))
    parser.add_option('', '--thumbnails', action='store_true',
                      dest='thumbnails', help=_('Use thumbnails'))
    parser.add_option('', '--iso-time', action='store_true',
                      dest='time_iso', help=_('Display time in ISO format'))
    # Translators: Do not translate PATH, it is a variable.
    parser.add_option('', '--path', help=_("Set the default search path"))
    parser.add_option('', '--exact', action='store_true',
                      help=_('Perform exact match'))
    parser.add_option('', '--hidden', action='store_true',
                      help=_('Include hidden files'))
    parser.add_option('', '--fulltext', action='store_true',
                      help=_('Perform fulltext search'))
    parser.add_option('', '--start', action='store_true',
                      help=_("If path and query are provided, start searching "
                             "when the application is displayed."))
    parser.add_option('', '--sort', help=_("set a default column to sort by "
                             "(name|size|path|date|type),(asc|desc)"))
    parser.set_defaults(icons_large=0, thumbnails=0, time_iso=0,
                        path=None, start=False, sort=None,
                        exact=0, hidden=0, fulltext=0, file_action='open')

    (options, args) = parser.parse_args()

    set_up_logging(options)
    return (options, args)


def main():
    'constructor for your class instances'
    options, args = parse_options()

    # Run the application.
    window = CatfishWindow.CatfishWindow()
    window.parse_options(options, args)
    window.show()

    # Allow application shutdown with Ctrl-C in terminal
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    Gtk.main()
