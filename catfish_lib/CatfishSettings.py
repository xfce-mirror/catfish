#!/usr/bin/env python
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

import os

default_settings_file = os.path.join(os.getenv('HOME'), 
                                     '.config/catfish/catfish.rc')
default_settings = {'show-hidden-files': False, 'show-sidebar': False}

class CatfishSettings:
    def __init__(self, settings_file=default_settings_file):
        try:
            settings_dir = os.path.dirname(settings_file)
            if not os.path.exists(settings_dir):
                os.makedirs(settings_dir)
            self.settings_file = settings_file
        except:
            self.settings_file = None
        self.read()
            
    def get_setting(self, key):
        if key in self.settings:
            return self.settings[key]
        else:
            return None
            
    def set_setting(self, key, value):
        if self.settings.has_key(key):
            self.settings[key] = value
        else:
            pass
        
    def read(self):
        self.settings = default_settings.copy()
        if os.path.isfile(self.settings_file):
            for line in open(self.settings_file):
                if not line.startswith('#'):
                    try:
                        prop, value = line.split('=')
                        if self.settings.has_key(prop):
                            if value.strip().lower() in ['true', 'false']:
                                value = value.strip().lower() == 'true'
                            self.settings[prop] = value
                    except:
                        pass
                            
    def write(self):
        if self.settings_file:
            write_file = open(self.settings_file, 'w')
            for key in self.settings.keys():
                value = self.settings[key]
                if isinstance(value, bool):
                    value = str(value).lower()
                else:
                    value = str(value)
                write_file.write('%s=%s\n' % (key, value))
            write_file.close()
