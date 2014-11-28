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

from gi.repository import Gtk, Gdk  # pylint: disable=E0611
import logging
logger = logging.getLogger('catfish_lib')

from . helpers import get_builder


# GtkBuilder Mappings
__builder__ = {
    # Builder name
    "ui_file": "CatfishWindow",
    
    "window": {
        "main": "catfish_window",
        "sidebar": "catfish_window_sidebar",
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
            "update": "application_menu_update"
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

        # AppMenu
        button = Gtk.MenuButton()
        button.set_size_request(32, 32)
        image = Gtk.Image.new_from_icon_name("emblem-system-symbolic",
                                             Gtk.IconSize.MENU)
        button.set_image(image)

        popup = builder.get_named_object("menus.application.menu")
        popup.set_property("halign", Gtk.Align.CENTER)
        button.set_popup(popup)

        box = builder.get_named_object("menus.application.placeholder")
        box.add(button)
        button.show_all()

    def on_mnu_about_activate(self, widget, data=None):
        """Display the about box for catfish."""
        if self.AboutDialog is not None:
            about = self.AboutDialog()  # pylint: disable=E1102
            about.run()
            about.destroy()

    def on_destroy(self, widget, data=None):
        """Called when the CatfishWindow is closed."""
        self.search_engine.stop()
        self.settings.write()
        Gtk.main_quit()

    def on_catfish_window_window_state_event(self, widget, event):
        """Properly handle window-manager fullscreen events."""
        self.window_is_fullscreen = bool(event.new_window_state &
                                         Gdk.WindowState.FULLSCREEN)

    def on_catfish_window_key_press_event(self, widget, event):
        """Handle keypresses for the Catfish window."""
        key_name = Gdk.keyval_name(event.keyval)
        if key_name == 'F9':
            self.sidebar_toggle_menu.activate()
            return True
        if key_name == 'F11':
            if self.window_is_fullscreen:
                self.unfullscreen()
            else:
                self.fullscreen()
            return True
        return False
