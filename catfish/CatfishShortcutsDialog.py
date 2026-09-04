#!/usr/bin/env python
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
#   Catfish - a versatile file searching tool
#   Copyright (C) 2007-2012 Christian Dywan <christian@twotoasts.de>
#   Copyright (C) 2012-2022 Sean Davis <bluesabre@xfce.org>
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

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from catfish_lib import CatfishSettings

settings = CatfishSettings.CatfishSettings()
use_headerbar = settings.get_setting("use-headerbar")

if use_headerbar:
    window_type = Gtk.ShortcutsWindow
else:
    window_type = Gtk.Window

class CatfishShortcutsDialog(window_type):
    def __init__(self, parent_window, catfish_icon):
        super().__init__()

        self.window_title = _("Catfish Keyboard Shortcuts")
        self.set_icon_name(catfish_icon)
        self.set_transient_for(parent_window)
        self.set_modal(True)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)

        self.connect("delete-event", self.on_close)

        shortcut_sections = {
            _("Main Window"): [
                {"title": _("Open/Set Search Folder"), "accelerator": "<Primary>o <Primary>l"},
                {"title": _("Focus Search Box"), "accelerator": "<Primary>f"},
                {"title": _("Stop Ongoing Search"), "accelerator": "Escape"},
                {"title": _("Toggle Filter Sidebar"), "accelerator": "F9"},
                {"title": _("Toggle Hidden Files"), "accelerator": "<Primary>h"},
                {"title": _("Toggle Fullscreen Mode"), "accelerator": "F11"},
                {"title": _("Quit Catfish"), "accelerator": "<Primary>q"},
            ],
            _("Results"): [
                {"title": _("Select All Results"), "accelerator": "<Primary>a"},
                {"title": _("Deselect All, Return Focus to Search"), "accelerator": "slash"},
                {"title": _("Open Context Menu"), "accelerator": "Menu <Shift>F10"},
                {"title": _("Show in File Manager"), "accelerator": "<Primary>Return"},
                {"title": _("Rename Selected Item"), "accelerator": "F2"},
                {"title": _("Copy Selected Paths to Clipboard"), "accelerator": "<Primary><Shift>c"},
                {"title": _("Delete Selected Items"), "accelerator": "Delete"},
            ]
        }

        self.add_shortcuts_section(shortcut_sections)

        self.set_title(self.window_title)
        titlebar = self.get_titlebar()
        if titlebar:
            titlebar_label = Gtk.Label(label=self.window_title, visible=True)
            titlebar_label.get_style_context().add_class("title")
            titlebar.set_custom_title(titlebar_label)

    def add_shortcuts_section(self, shortcut_sections):
        section = Gtk.ShortcutsSection(visible=True)
        for group_title, items in shortcut_sections.items():
            group = Gtk.ShortcutsGroup(visible=True, title=group_title)
            for item in items:
                shortcut = Gtk.ShortcutsShortcut(
                    visible=True,
                    title=item["title"],
                    accelerator=item["accelerator"])
                group.add(shortcut)
            section.add(group)
        self.add(section)

    def on_close(self, widget, event):
        self.hide()
        return True 