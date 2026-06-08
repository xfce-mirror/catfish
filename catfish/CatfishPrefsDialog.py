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

# pylint: disable=C0114
# pylint: disable=C0116
# pylint: disable=C0413

import logging

import gi
gi.require_version('Gtk', '3.0')  # noqa
from gi.repository import Gtk

from catfish_lib.PrefsDialog import PrefsDialog
from catfish_lib import CatfishColumn

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
            self.builder.get_object(
                "search_in_compressed_files").set_active(True)
        if self.settings.get_setting("file-size-binary"):
            self.builder.get_object("do_show_size_binary").set_active(True)
        self.set_exclude_directories(
            self.settings.get_setting("exclude-paths"))
        self.set_treeview_columns(
            self.settings.get_setting("columns"))
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

    def on_do_show_size_binary_toggled(self, widget):
        if not self.process_events:
            return
        if widget.get_active():
            self.settings.set_setting("file-size-binary", True)
        else:
            self.settings.set_setting("file-size-binary", False)
        self.changed_properties.append("file-size-binary")

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
            self.treemodel_to_settings(model, "exclude-paths", True)
        dlg.destroy()

    def on_remove_directory_clicked(self, widget):  # pylint: disable=W0613
        treeview = self.builder.get_object("exclude_treeview")
        model = treeview.get_model()
        sel = treeview.get_selection().get_selected()
        if sel is not None:
            model.remove(sel[1])
        self.treemodel_to_settings(model, "exclude-paths", True)

    def on_add_column_clicked(self, widget):
        treeview_all = self.builder.get_object("columns_nodisplay_treeview")
        model_all = treeview_all.get_model()
        sel = treeview_all.get_selection().get_selected()
        treeview_vis = self.builder.get_object("columns_display_treeview")
        model_vis = treeview_vis.get_model()
        if sel is not None:
            model_vis.append([sel[0][sel[1]][0],sel[0][sel[1]][1]])
        self.treemodel_to_settings(model_vis, "columns", False, True)

    def on_remove_column_clicked(self, widget):
        treeview_vis = self.builder.get_object("columns_display_treeview")
        model_vis = treeview_vis.get_model()
        sel = treeview_vis.get_selection().get_selected()
        if sel is not None:
            model_vis.remove(sel[1])
        self.treemodel_to_settings(model_vis, "columns", False, True)

    def on_move_column_up_clicked(self, widget):
        treeview_vis = self.builder.get_object("columns_display_treeview")
        model_vis = treeview_vis.get_model()
        sel = treeview_vis.get_selection().get_selected()
        if sel[1] is not None:
            iter_prev = model_vis.iter_previous(sel[1])
            if iter_prev:
                model_vis.move_before(sel[1], iter_prev)
        self.treemodel_to_settings(model_vis, "columns", False, True)

    def on_move_column_down_clicked(self, widget):
        treeview_vis = self.builder.get_object("columns_display_treeview")
        model_vis = treeview_vis.get_model()
        sel = treeview_vis.get_selection().get_selected()
        if sel[1] is not None:
            iter_next = model_vis.iter_next(sel[1])
            if iter_next:
                model_vis.move_after(sel[1], iter_next)
        self.treemodel_to_settings(model_vis, "columns", False, True)
        return

    def treemodel_to_settings(self, model, setting_name, sort, allow_dup=False):
        child = model.iter_children()

        rows = []
        while child is not None:
            path = model[child][0]
            if len(path) > 0:
                if path not in rows or allow_dup:
                    rows.append(path)
            child = model.iter_next(child)
        if sort:
            rows.sort()
        self.settings.set_setting(setting_name, rows)

    def set_exclude_directories(self, exclude_directories):
        treeview = self.builder.get_object("exclude_treeview")
        model = treeview.get_model()

        for path in exclude_directories:
            model.append([path])

    def set_treeview_columns(self, vis_columns):
        treeview_all = self.builder.get_object("columns_nodisplay_treeview")
        model_all = treeview_all.get_model()

        for col in CatfishColumn.all_columns:
            col_obj = CatfishColumn.all_columns[col]
            model_all.append([col_obj.colname, col_obj.display_name])

        treeview_vis = self.builder.get_object("columns_display_treeview")
        model_vis = treeview_vis.get_model()

        for col in vis_columns:
            model_vis.append([col.colname, col.display_name])
