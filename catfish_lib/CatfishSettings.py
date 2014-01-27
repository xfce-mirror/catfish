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

import os

default_settings_file = os.path.join(os.getenv('HOME'),
                                     '.config/catfish/catfish.rc')
default_settings = {'show-hidden-files': False, 'show-sidebar': False}


class CatfishSettings:
    """CatfishSettings rc-file management."""
    def __init__(self, settings_file=default_settings_file):
        """Initialize the CatfishSettings instance."""
        try:
            settings_dir = os.path.dirname(settings_file)
            if not os.path.exists(settings_dir):
                os.makedirs(settings_dir)
            self.settings_file = settings_file
        except:
            self.settings_file = None
        self.read()

    def get_setting(self, key):
        """Return current setting for specified key."""
        if key in self.settings:
            return self.settings[key]
        else:
            return None

    def set_setting(self, key, value):
        """Set the value for the specified key."""
        if key in self.settings:
            self.settings[key] = value
        else:
            pass

    def read(self):
        """Read the settings rc-file into this settings instance."""
        self.settings = default_settings.copy()
        if os.path.isfile(self.settings_file):
            for line in open(self.settings_file):
                if not line.startswith('#'):
                    try:
                        prop, value = line.split('=')
                        if prop in self.settings:
                            if value.strip().lower() in ['true', 'false']:
                                value = value.strip().lower() == 'true'
                            self.settings[prop] = value
                    except:
                        pass

    def write(self):
        """Write the current settings to the settings rc-file."""
        if self.settings_file:
            write_file = open(self.settings_file, 'w')
            for key in list(self.settings.keys()):
                value = self.settings[key]
                if isinstance(value, bool):
                    value = str(value).lower()
                else:
                    value = str(value)
                write_file.write('%s=%s\n' % (key, value))
            write_file.close()
