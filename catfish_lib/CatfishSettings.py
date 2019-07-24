#!/usr/bin/env python
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
#   Catfish - a versatile file searching tool
#   Copyright (C) 2007-2012 Christian Dywan <christian@twotoasts.de>
#   Copyright (C) 2012-2019 Sean Davis <bluesabre@xfce.org>
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

default_settings_file = os.path.join(os.getenv('HOME'),
                                     '.config/catfish/catfish.rc')
default_settings = {
    'use-headerbar': None,
    'show-hidden-files': False,
    'show-sidebar': False,
    'close-after-select': False,
    'window-width': 650,
    'window-height': 470,
    'window-x': -1,
    'window-y': -1
}


class CatfishSettings:

    """CatfishSettings rc-file management."""

    def __init__(self, settings_file=default_settings_file):
        """Initialize the CatfishSettings instance."""
        try:
            settings_dir = os.path.dirname(settings_file)
            if not os.path.exists(settings_dir):
                os.makedirs(settings_dir)
            self.settings_file = settings_file
        except Exception:
            self.settings_file = None
        self.headerbar_configured = False
        self.read()

    def get_current_desktop(self):
        current_desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
        current_desktop = current_desktop.lower()
        for desktop in ["budgie", "pantheon", "gnome"]:
            if desktop in current_desktop:
                return desktop
        if "kde" in current_desktop:
            kde_version = int(os.environ.get("KDE_SESSION_VERSION", "4"))
            if kde_version >= 5:
                return "plasma"
            return "kde"
        return current_desktop

    def get_setting(self, key):
        """Return current setting for specified key."""
        if key in self.settings:
            if (key.startswith('window')):
                return int(self.settings[key])
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
            try:
                for line in open(self.settings_file):
                    if not line.startswith('#'):
                        try:
                            prop, value = line.split('=')
                            if prop in self.settings:
                                if value.strip().lower() in ['true', 'false']:
                                    value = value.strip().lower() == 'true'
                                self.settings[prop] = value
                        except Exception:
                            pass
            except Exception:
                pass

        if self.settings['use-headerbar'] == None:
            current_desktop = self.get_current_desktop()
            if current_desktop in ["budgie", "gnome", "pantheon"]:
                self.settings['use-headerbar'] = True
            else:
                self.settings['use-headerbar'] = False
        else:
            self.headerbar_configured = True

    def write(self):
        """Write the current settings to the settings rc-file."""
        if self.settings_file:
            try:
                write_file = open(self.settings_file, 'w')
                for key in list(self.settings.keys()):
                    value = self.settings[key]
                    if key == 'use-headerbar' and not self.headerbar_configured:
                        continue
                    if isinstance(value, bool):
                        value = str(value).lower()
                    else:
                        value = str(value)
                    write_file.write('%s=%s\n' % (key, value))
                write_file.close()
            except PermissionError:
                pass
