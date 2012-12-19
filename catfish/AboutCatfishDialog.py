# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
### BEGIN LICENSE
# This file is in the public domain
### END LICENSE

from locale import gettext as _

import logging
logger = logging.getLogger('catfish')

from catfish_lib.AboutDialog import AboutDialog

# See catfish_lib.AboutDialog.py for more details about how this class works.
class AboutCatfishDialog(AboutDialog):
    __gtype_name__ = "AboutCatfishDialog"
    
    def finish_initializing(self, builder): # pylint: disable=E1002
        """Set up the about dialog"""
        super(AboutCatfishDialog, self).finish_initializing(builder)

        # Code for other initialization actions should be added here.

