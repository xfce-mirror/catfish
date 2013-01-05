# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
### BEGIN LICENSE
# Copyright (C) 2007-2012 Christian Dywan <christian@twotoasts.de>
# Copyright (C) 2012-2013 Sean Davis <smd.seandavis@gmail.com>
# This program is free software: you can redistribute it and/or modify it 
# under the terms of the GNU General Public License version 2, as published 
# by the Free Software Foundation.
# 
# This program is distributed in the hope that it will be useful, but 
# WITHOUT ANY WARRANTY; without even the implied warranties of 
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR 
# PURPOSE.  See the GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License along 
# with this program.  If not, see <http://www.gnu.org/licenses/>.
### END LICENSE

import optparse

from locale import gettext as _

from gi.repository import Gtk # pylint: disable=E0611

from catfish import CatfishWindow

from catfish_lib import set_up_logging, get_version

import os

def parse_options():
    """Support for command line options"""
    parser = optparse.OptionParser(version="%%prog %s" % get_version())
    parser.add_option(
        "-v", "--verbose", action="count", dest="verbose",
        help=_("Show debug messages (-vv debugs catfish_lib also)"))
        
    parser.add_option('', '--large-icons', action='store_true'
            , dest='icons_large', help='Use large icons')
    parser.add_option('', '--thumbnails', action='store_true'
        , dest='thumbnails', help='Use thumbnails')
    parser.add_option('', '--iso-time', action='store_true'
        , dest='time_iso', help='Display time in iso format')
    parser.add_option('', '--path', help='Search in folder PATH')
    parser.add_option('', '--fileman', help='Use FILEMAN as filemanager')
    parser.add_option('', '--wrapper', metavar='WRAPPER'
        , dest='open_wrapper', help='Use WRAPPER to open files')
    parser.add_option('', '--exact', action='store_true'
        , help='Perform exact match')
    parser.add_option('', '--hidden', action='store_true'
        , help='Include hidden files')
    parser.add_option('', '--fulltext', action='store_true'
        , help='Perform fulltext search')
    parser.set_defaults(icons_large=0, thumbnails=0, time_iso=0
                        , path=os.path.expanduser('~'), fileman='xdg-open'
                        , exact=0, hidden=0, fulltext=0, file_action='open'
                        , open_wrapper='xdg-open')
        
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
    Gtk.main()
