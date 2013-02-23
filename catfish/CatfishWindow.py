# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
### BEGIN LICENSE
# This file is in the public domain
### END LICENSE

from locale import gettext as _

from gi.repository import Gtk # pylint: disable=E0611
import logging
logger = logging.getLogger('catfish')

from catfish_lib import Window
from catfish.AboutCatfishDialog import AboutCatfishDialog
from catfish.PreferencesCatfishDialog import PreferencesCatfishDialog

# See catfish_lib.Window.py for more details about how this class works
class CatfishWindow(Window):
    __gtype_name__ = "CatfishWindow"
    
    def finish_initializing(self, builder): # pylint: disable=E1002
        """Set up the main window"""
        super(CatfishWindow, self).finish_initializing(builder)

        self.AboutDialog = AboutCatfishDialog
        self.PreferencesDialog = PreferencesCatfishDialog

        # Code for other initialization actions should be added here.

