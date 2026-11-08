#!/usr/bin/env python
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
#   Catfish - a versatile file searching tool
#   Copyright (C) 2007-2012 Christian Dywan <christian@twotoasts.de>
#   Copyright (C) 2012-2022 Sean Davis <bluesabre@xfce.org>
#   Copyright (C) 2026 The Xfce Development Team
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
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk
from catfish_lib import CatfishSettings

settings = CatfishSettings.CatfishSettings()
use_headerbar = settings.get_setting("use-headerbar")

if use_headerbar:
    window_type = Gtk.ShortcutsWindow
else:
    window_type = Gtk.Window


class CatfishShortcutsDialog(window_type):
    def __init__(self, parent_window):
        super().__init__()

        self.window_title = _("Catfish Keyboard Shortcuts")
        self.set_transient_for(parent_window)
        self.set_modal(True)

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

        if window_type == Gtk.ShortcutsWindow:
            self.add_shortcuts_section_gtk_shortcuts_window(shortcut_sections)
            self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
            #Replace "Shortcuts" title label with self.window_title
            headerbar_title = self.get_titlebar().get_custom_title()
            if headerbar_title:
                headerbar_label = headerbar_title.get_child_by_name("title")
                if headerbar_label:
                    headerbar_label.set_text(self.window_title)
        else:
            self.add_shortcuts_section_gtk_window(shortcut_sections)
            self.set_position(Gtk.WindowPosition.CENTER)
            self.set_title(self.window_title)

        self.connect("delete-event", self.on_close)
        self.connect("key-press-event", self.on_key_press)

    def add_shortcuts_section_gtk_shortcuts_window(self, shortcut_sections):
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

    def add_shortcuts_section_gtk_window(self, shortcut_sections):
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=64, margin=16)
        main_box.set_halign(Gtk.Align.CENTER)
        main_box.set_valign(Gtk.Align.CENTER)

        for group_title, items in shortcut_sections.items():
            section_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

            group = Gtk.ShortcutsGroup(title=group_title)
            section_box.pack_start(group, False, False, 2)

            accel_space_evenly = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)

            for item in items:
                shortcut = Gtk.ShortcutsShortcut(
                    visible=True,
                    title=item["title"],
                    accelerator=item["accelerator"])
                shortcut.set_property("accel-size-group", accel_space_evenly)
                section_box.pack_start(shortcut, False, False, 0)

            main_box.pack_start(section_box, False, False, 0)

        self.add(main_box)

    def on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False

    def on_close(self, widget, event):
        self.hide()
        return True
