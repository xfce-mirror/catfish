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

# pylint: disable=C0114
# pylint: disable=C0116

import logging
from locale import gettext as _

from gi.repository import Gtk, Gdk  # pylint: disable=E0611

from catfish_lib import CatfishSettings
from . helpers import get_builder

logger = logging.getLogger('catfish_lib')

# GtkBuilder Mappings
__builder__ = {
    # Builder name
    "ui_file": "CatfishWindow",

    "window": {
        "main": "Catfish",
        "sidebar": "catfish_window_sidebar",
        "paned": "catfish_window_paned"
    },

    # Toolbar
    "toolbar": {
        "folderchooser": "toolbar_folderchooser",
        "search": "toolbar_search",
        "view": {
            "list": "toolbar_view_list",
            "thumbs": "toolbar_view_thumbnails"
        },
    },

    # Menus
    "menus": {
        # Application (AppMenu)
        "application": {
            "menu": "application_menu",
            "placeholder": "toolbar_custom_appmenu",
            "exact": "application_menu_exact",
            "hidden": "application_menu_hidden",
            "fulltext": "application_menu_fulltext",
            "advanced": "application_menu_advanced",
            "update": "application_menu_update",
            "preferences": "application_menu_prefs",
        },
        # File Context Menu
        "file": {
            "menu": "file_menu",
            "save": "file_menu_save",
            "delete": "file_menu_delete"
        }
    },

    # Locate Infobar
    "infobar": {
        "infobar": "catfish_window_infobar"
    },

    # Sidebar
    "sidebar": {
        "modified": {
            "options": "sidebar_filter_custom_date_options",
            "icons": {
                "any": "sidebar_filter_modified_any_icon",
                "week": "sidebar_filter_modified_week_icon",
                "custom": "sidebar_filter_custom_date_icon",
                "options": "sidebar_filter_custom_date_options_icon"
            }
        },
        "filetype": {
            "options": "sidebar_filter_custom_options",
            "icons": {
                "documents": "sidebar_filter_documents_icon",
                "folders": "sidebar_filter_folders_icon",
                "photos": "sidebar_filter_images_icon",
                "music": "sidebar_filter_music_icon",
                "videos": "sidebar_filter_videos_icon",
                "applications": "sidebar_filter_applications_icon",
                "custom": "sidebar_filter_custom_filetype_icon",
                "options": "sidebar_filter_custom_options_icon"
            }
        }
    },

    # Results Window
    "results": {
        "scrolled_window": "results_scrolledwindow",
        "treeview": "results_treeview"
    },

    "dialogs": {
        # Custom Filetypes
        "filetype": {
            "dialog": "filetype_dialog",
            "mimetypes": {
                "radio": "filetype_mimetype_radio",
                "box": "filetype_mimetype_box",
                "categories": "filetype_mimetype_categories",
                "types": "filetype_mimetype_types"
            },
            "extensions": {
                "radio": "filetype_extension_radio",
                "entry": "filetype_extension_entry"
            }
        },

        # Custom Date Range
        "date": {
            "dialog": "date_dialog",
            "start_calendar": "date_start_calendar",
            "end_calendar": "date_end_calendar",
        },

        # Update Search Index
        "update": {
            "dialog": "update_dialog",
            "database_label": "update_dialog_database_details_label",
            "modified_label": "update_dialog_modified_details_label",
            "status_infobar": "update_dialog_infobar",
            "status_icon": "update_dialog_infobar_icon",
            "status_label": "update_dialog_infobar_label",
            "close_button": "update_close",
            "unlock_button": "update_unlock"
        }
    }
}


class Window(Gtk.Window):

    """This class is meant to be subclassed by CatfishWindow. It provides
    common functions and some boilerplate."""
    __gtype_name__ = "Window"

    # To construct a new instance of this method, the following notable
    # methods are called in this order:
    # __new__(cls)
    # __init__(self)
    # finish_initializing(self, builder)
    # __init__(self)
    #
    # For this reason, it's recommended you leave __init__ empty and put
    # your initialization code in finish_initializing

    def __new__(cls):
        """Special static method that's automatically called by Python when
        constructing a new instance of this class.

        Returns a fully instantiated BaseCatfishWindow object.
        """
        builder = get_builder(__builder__['ui_file'])
        builder.add_name_mapping(__builder__)
        new_object = builder.get_named_object("window.main")
        new_object.finish_initializing(builder)
        return new_object

    def finish_initializing(self, builder):
        """Called while initializing this instance in __new__

        finish_initializing should be called after parsing the UI definition
        and creating a CatfishWindow object with it in order to finish
        initializing the start of the new CatfishWindow instance.
        """
        # Get a reference to the builder and set up the signals.
        self.builder = builder
        self.ui = builder.get_ui(self, True)
        self.AboutDialog = None  # class

        self.sidebar = builder.get_named_object("window.sidebar")

        # Widgets
        # Folder Chooser
        chooser = self.builder.get_named_object("toolbar.folderchooser")
        # Search
        search = self.builder.get_named_object("toolbar.search")

        # AppMenu
        button = Gtk.MenuButton()
        button.set_size_request(32, 32)
        image = Gtk.Image.new_from_icon_name("emblem-system-symbolic",
                                             Gtk.IconSize.MENU)
        button.set_image(image)
        popover = Gtk.Popover.new(button)
        appmenu = self.builder.get_named_object("menus.application.menu")
        popover.add(appmenu)
        button.set_popover(popover)

        settings = CatfishSettings.CatfishSettings()
        if settings.get_setting('use-headerbar'):
            self.setup_headerbar(chooser, search, button)
        else:
            self.setup_toolbar(chooser, search, button)

        search.grab_focus()
        self.keys_pressed = []

        self.search_engine = None
        self.settings = None

    def on_sidebar_toggle_toggled(self, widget):
        pass

    def setup_headerbar(self, chooser, search, button):
        headerbar = Gtk.HeaderBar.new()
        headerbar.set_show_close_button(True)

        headerbar.pack_start(chooser)
        headerbar.set_title(_("Catfish"))
        headerbar.set_custom_title(search)
        headerbar.pack_end(button)

        self.set_titlebar(headerbar)
        headerbar.show_all()

    def setup_toolbar(self, chooser, search, button):
        toolbar = Gtk.Toolbar.new()

        toolitem = Gtk.ToolItem.new()
        toolitem.add(chooser)
        toolitem.set_margin_right(6)
        toolbar.insert(toolitem, 0)

        toolitem = Gtk.ToolItem.new()
        toolitem.add(search)
        search.set_hexpand(True)
        toolitem.set_expand(True)
        toolitem.set_margin_right(6)
        toolbar.insert(toolitem, 1)

        toolitem = Gtk.ToolItem.new()
        toolitem.add(button)
        toolbar.insert(toolitem, 2)

        self.get_children()[0].pack_start(toolbar, False, False, 0)
        self.get_children()[0].reorder_child(toolbar, 0)
        toolbar.show_all()

    def on_mnu_about_activate(self, widget, data=None):  # pylint: disable=W0613
        """Display the about box for catfish."""
        if self.AboutDialog is not None:
            about = self.AboutDialog()  # pylint: disable=E1102
            about.set_transient_for(self)
            about.run()
            about.destroy()

    def on_destroy(self, widget, data=None):  # pylint: disable=W0613
        """Called when the CatfishWindow is closed."""
        self.search_engine.stop()
        self.settings.write()
        Gtk.main_quit()

    def on_catfish_window_window_state_event(self, widget, event):  # pylint: disable=W0613
        """Properly handle window-manager fullscreen events."""
        self.window_is_fullscreen = bool(event.new_window_state &
                                         Gdk.WindowState.FULLSCREEN)

    def get_keys_from_event(self, event):
        keys = []
        keys.append(Gdk.keyval_name(event.keyval))
        if event.get_state() & Gdk.ModifierType.CONTROL_MASK:
            keys.append("Control")
        if event.get_state() & Gdk.ModifierType.SHIFT_MASK:
            keys.append("Shift")
        if event.get_state() & Gdk.ModifierType.SUPER_MASK:
            keys.append("Super")
        if event.get_state() & Gdk.ModifierType.MOD1_MASK:
            keys.append("Alt")
        return keys

    def map_key(self, key):
        if key.endswith("_L"):
            return key.replace("_L", "")
        if key.endswith("_R"):
            return key.replace("_R", "")
        return key

    def add_keys(self, keys):
        for key in keys:
            self.add_key(key)

    def add_key(self, key):
        if key is None:
            return
        key = self.map_key(key)
        if key in ["Escape"]:
            return
        if key not in self.keys_pressed:
            self.keys_pressed.append(key)

    def remove_keys(self, keys):
        for key in keys:
            if key in self.keys_pressed:
                self.remove_key(key)
                self.remove_key(key.upper())

    def remove_key(self, key):
        if key is None:
            return
        key = self.map_key(key)
        try:
            self.keys_pressed.remove(key)
        except ValueError:
            pass

    def on_catfish_window_key_press_event(self, widget, event):
        """Handle keypresses for the Catfish window."""
        keys = self.get_keys_from_event(event)
        self.add_keys(keys)

        if "Escape" in keys:
            self.search_engine.stop()
            return True
        if "Control" in keys and ("q" in keys or "Q" in keys):
            self.destroy()
        if 'F9' in keys:
            self.on_sidebar_toggle_toggled(widget)
            return True
        if 'F11' in keys:
            if self.window_is_fullscreen:
                self.unfullscreen()
            else:
                self.fullscreen()
            return True
        return False

    def on_catfish_window_key_release_event(self, widget, event):  # pylint: disable=W0613
        """Handle key releases for the Catfish window."""
        keys = self.get_keys_from_event(event)
        self.remove_keys(keys)
        return False

    def on_catfish_window_size_allocate(self, widget, allocation):  # pylint: disable=W0613
        paned = self.builder.get_named_object("window.paned")
        allocation = paned.get_allocation()
        self.settings.set_setting('window-height', allocation.height)
        self.settings.set_setting('window-width', allocation.width)
        paned.set_property('height_request', -1)
        paned.set_property('width_request', -1)

    def on_catfish_window_configure_event(self, widget, event):  # pylint: disable=W0613
        pos = self.get_position()
        self.settings.set_setting('window-x', pos.root_x)
        self.settings.set_setting('window-y', pos.root_y)
