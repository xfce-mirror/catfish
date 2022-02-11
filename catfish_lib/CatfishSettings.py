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

import os

import gi

gi.require_version('Xfconf', '0')
from gi.repository import Xfconf

Xfconf.init()

DEFAULT_SETTINGS_FILE = os.path.join(os.getenv('HOME'),
                                     '.config/catfish/catfish.rc')
DEFAULT_SETTINGS = {
    'use-headerbar': (bool, None),
    'show-hidden-files': (bool, False),
    'show-sidebar': (bool, True),
    'list-toggle': (bool, True),
    'show-thumbnails': (bool, None),
    'search-file-contents': (bool, False),
    'match-results-exactly': (bool, False),
    'close-after-select': (bool, False),
    'search-compressed-files': (bool, False),
    'file-size-binary': (bool, True),
    'window-width': (int, 650),
    'window-height': (int, 470),
    'window-x': (int, -1),
    'window-y': (int, -1),
    'exclude-paths': (str, '/dev;~/.cache;~/.gvfs;')
}


class CatfishSettings:

    """CatfishSettings settings management."""

    def __init__(self, settings_file=DEFAULT_SETTINGS_FILE):
        """Initialize the CatfishSettings instance."""
        self.channel = Xfconf.Channel.new("catfish")
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
            if key.startswith('window'):
                return int(self.settings[key])
            if key == "exclude-paths":
                exclude_directories = []
                for path in (self.settings[key].strip()).split(";"):
                    if len(path) > 0:
                        path = os.path.expanduser(path)
                        if not path.endswith("/"):
                            path = path + "/"
                        exclude_directories.append(path)
                exclude_directories.sort()
                return exclude_directories
            return self.settings[key]
        return None

    def set_setting(self, key, value):
        """Set the value for the specified key."""
        if key in self.settings:
            if key == "exclude-paths":
                value = ";".join(value)
            if key == 'use-headerbar':
                self.headerbar_configured = True
            self.settings[key] = value
        else:
            pass

    def read_from_settings_file(self):
        settings = {}
        if os.path.isfile(self.settings_file):
            try:
                for line in open(self.settings_file):
                    if not line.startswith('#'):
                        try:
                            prop, value = line.split('=')
                            if prop in self.settings:
                                if value.strip().lower() in ['true', 'false']:
                                    value = value.strip().lower() == 'true'
                                settings[prop] = value
                        except Exception:
                            pass
            except Exception:
                pass
        return settings

    def delete_settings_file(self):
        try:
            if os.path.isfile(self.settings_file):
                os.remove(self.settings_file)
        except Exception:
            pass

    def read(self):
        """Read the settings Xfconf channel into this settings instance."""
        self.settings = {}
        rc_settings = self.read_from_settings_file()
        for key, value in DEFAULT_SETTINGS.items():
            typing = value[0]
            xfconf_prop = "/%s" % key
            self.settings[key] = value[1]
            if self.channel.has_property(xfconf_prop):
                if typing == bool:
                    self.settings[key] = self.channel.get_bool(xfconf_prop, value[1])
                elif typing == int:
                    self.settings[key] = self.channel.get_int(xfconf_prop, value[1])
                elif typing == str:
                    self.settings[key] = self.channel.get_string(xfconf_prop, value[1])
            elif key in rc_settings.keys():
                self.settings[key] = rc_settings[key]

        if self.settings['use-headerbar'] is None:
            current_desktop = self.get_current_desktop()
            if current_desktop in ["budgie", "gnome", "pantheon"]:
                self.settings['use-headerbar'] = True
            else:
                self.settings['use-headerbar'] = False
        else:
            self.headerbar_configured = True
        
        self.delete_settings_file()

    def write(self):
        """Write the current settings to the settings Xfconf channel."""
        for key, value in DEFAULT_SETTINGS.items():
            if key == 'use-headerbar' and \
                    not self.headerbar_configured:
                continue
            typing = value[0]
            xfconf_prop = "/%s" % key
            if typing == bool:
                self.channel.set_bool(xfconf_prop, self.settings[key])
            elif typing == int:
                self.channel.set_int(xfconf_prop, self.settings[key])
            elif typing == str:
                self.channel.set_string(xfconf_prop, self.settings[key])
