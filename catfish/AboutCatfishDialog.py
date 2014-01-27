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

import logging
logger = logging.getLogger('catfish')

from catfish_lib.AboutDialog import AboutDialog


# See catfish_lib.AboutDialog.py for more details about how this class works.
class AboutCatfishDialog(AboutDialog):
    """Creates the about dialog for catfish"""
    __gtype_name__ = "AboutCatfishDialog"

    def finish_initializing(self, builder):  # pylint: disable=E1002
        """Set up the about dialog"""
        super(AboutCatfishDialog, self).finish_initializing(builder)
