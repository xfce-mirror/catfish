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

# pylint: disable=C0114
# pylint: disable=C0116
# pylint: disable=C0413

import logging

import gi
gi.require_version('Gtk', '3.0')  # noqa
from gi.repository import Gtk

from catfish_lib.PrefsDialog import PrefsDialog

LOGGER = logging.getLogger('catfish')


# See catfish_lib.PrefsDialog.py for more details about how this class works.
class CatfishPrefsDialog(PrefsDialog):

    """Creates the about dialog for catfish"""
    __gtype_name__ = "CatfishPrefsDialog"

    def finish_initializing(self, builder):
        """Set up the about dialog"""
        super(CatfishPrefsDialog, self).finish_initializing(builder)
        self.changed_properties = []
        self.process_events = False

    def connect_settings(self, settings):
        self.settings = settings
        if self.settings.get_setting("use-headerbar"):
            self.builder.get_object("wl_headerbar").set_active(True)
            self.builder.get_object("wl_headerbar_visible").set_active(True)
        if self.settings.get_setting("show-hidden-files"):
            self.builder.get_object("do_show_hidden").set_active(True)
        if self.settings.get_setting("show-sidebar"):
            self.builder.get_object("do_show_sidebar").set_active(True)
        if self.settings.get_setting("close-after-select"):
            self.builder.get_object("close_after_select").set_active(True)
        if self.settings.get_setting("search-compressed-files"):
            self.builder.get_object("search_in_compressed_files").set_active(True)
        self.set_exclude_directories(
            self.settings.get_setting("exclude-paths"))
        self.process_events = True

    def on_wl_titlebar_toggled(self, widget):
        if not self.process_events:
            return
        if widget.get_active():
            self.settings.set_setting("use-headerbar", False)
            self.builder.get_object("wl_titlebar_visible").set_active(True)
        else:
            self.settings.set_setting("use-headerbar", True)
            self.builder.get_object("wl_headerbar_visible").set_active(True)
        self.builder.get_object("wl_info").show()
        self.changed_properties.append("use-headerbar")

    def on_do_show_hidden_toggled(self, widget):
        if not self.process_events:
            return
        if widget.get_active():
            self.settings.set_setting("show-hidden-files", True)
        else:
            self.settings.set_setting("show-hidden-files", False)
        self.changed_properties.append("show-hidden-files")

    def on_do_show_sidebar_toggled(self, widget):
        if not self.process_events:
            return
        if widget.get_active():
            self.settings.set_setting("show-sidebar", True)
        else:
            self.settings.set_setting("show-sidebar", False)
        self.changed_properties.append("show-sidebar")

    def on_close_after_select_toggled(self, widget):
        if not self.process_events:
            return
        if widget.get_active():
            self.settings.set_setting("close-after-select", True)
        else:
            self.settings.set_setting("close-after-select", False)
        self.changed_properties.append("close-after-select")

    def on_search_in_compressed_files_toggled(self, widget):
        if not self.process_events:
            return
        if widget.get_active():
            self.settings.set_setting("search-compressed-files", True)
        else:
            self.settings.set_setting("search-compressed-files", False)
        self.changed_properties.append("search-compressed-files")

    def on_add_directory_clicked(self, widget):  # pylint: disable=W0613
        dlg = Gtk.FileChooserDialog("Add Excluded Directory",
                                    self,
                                    Gtk.FileChooserAction.SELECT_FOLDER,
                                    (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                     Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        response = dlg.run()
        if response == Gtk.ResponseType.OK:
            path = dlg.get_filename()
            treeview = self.builder.get_object("exclude_treeview")
            model = treeview.get_model()
            model.append([path])
            self.treemodel_to_settings(model)
        dlg.destroy()

    def on_remove_directory_clicked(self, widget):  # pylint: disable=W0613
        treeview = self.builder.get_object("exclude_treeview")
        model = treeview.get_model()
        sel = treeview.get_selection().get_selected()
        if sel is not None:
            model.remove(sel[1])
        self.treemodel_to_settings(model)

    def treemodel_to_settings(self, model):
        child = model.iter_children()

        rows = []
        while child is not None:
            path = model[child][0]
            if path not in rows and len(path) > 0:
                rows.append(path)
            child = model.iter_next(child)

        rows.sort()

        self.settings.set_setting("exclude-paths", rows)

    def set_exclude_directories(self, exclude_directories):
        treeview = self.builder.get_object("exclude_treeview")
        model = treeview.get_model()

        for path in exclude_directories:
            model.append([path])
