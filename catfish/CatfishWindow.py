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

# pylint: disable=W0201
# pylint: disable=C0103
# pylint: disable=C0114
# pylint: disable=C0116
# pylint: disable=C0413


import datetime
import logging
import mimetypes
import os
import subprocess
import time
import zipfile
import tempfile
from locale import gettext as _
from shutil import copy2, rmtree
from xml.sax.saxutils import escape

# Thunar Integration
import urllib
import dbus

import pexpect
import gi
gi.require_version('GLib', '2.0')  # noqa
gi.require_version('GObject', '2.0')  # noqa
gi.require_version('Pango', '1.0')  # noqa
gi.require_version('Gdk', '3.0')  # noqa
gi.require_version('GdkPixbuf', '2.0')  # noqa
gi.require_version('Gtk', '3.0')  # noqa
from gi.repository import GLib, GObject, Pango, Gdk, GdkPixbuf, Gtk, Gio

from catfish.CatfishPrefsDialog import CatfishPrefsDialog
from catfish.CatfishSearchEngine import CatfishSearchEngine, get_keyword_list
from catfish_lib import catfishconfig, helpers, get_about
from catfish_lib import CatfishSettings, SudoDialog, Window
from catfish_lib import Thumbnailer

LOGGER = logging.getLogger('catfish')


# Initialize Gtk, GObject, and mimetypes
if not helpers.check_gobject_version(3, 9, 1):
    GObject.threads_init()
    GLib.threads_init()
mimetypes.init()


def long(value):
    return int(value)


def get_application_path(application_name):
    for path in os.getenv('PATH').split(':'):
        if os.path.isdir(path):
            if application_name in os.listdir(path):
                return os.path.join(path, application_name)
    return None


def application_in_PATH(application_name):
    """Return True if the application name is found in PATH."""
    return get_application_path(application_name) is not None


def is_file_hidden(folder, filename):
    """Return TRUE if file is hidden or in a hidden directory."""
    folder = os.path.abspath(folder)
    filename = os.path.abspath(filename)
    relpath = os.path.relpath(filename, folder)
    for piece in relpath.split(os.sep):
        if piece.startswith("."):
            return True
    return False


def surrogate_escape(text, replace=False):
    """Replace non-UTF8 characters with something displayable.
    If replace is True, display (invalid encoding) after the text."""
    try:
        text.encode('utf-8')
    except UnicodeEncodeError:
        text = text.encode('utf-8', errors='surrogateescape').decode(
            'utf-8', errors='replace')
        if replace:
            # Translators: this text is displayed next to
            # a filename that is not utf-8 encoded.
            text = _("%s (invalid encoding)") % text
    except UnicodeDecodeError:
        text = text.decode('utf-8', errors='replace')
    return text


# See catfish_lib.Window.py for more details about how this class works
class CatfishWindow(Window):

    """The application window."""
    __gtype_name__ = "CatfishWindow"

    filter_timerange = (0.0, 9999999999.0)
    start_date = datetime.datetime.now()
    end_date = datetime.datetime.now()

    filter_formats = {'documents': False, 'folders': False, 'images': False,
                      'music': False, 'videos': False, 'applications': False,
                      'other': False, 'exact': False, 'hidden': False,
                      'fulltext': False}

    filter_custom_extensions = []
    filter_custom_use_mimetype = False

    mimetypes = dict()
    search_in_progress = False

    def get_about_dialog(self):
        about = get_about()

        dlg = GObject.new(Gtk.AboutDialog, use_header_bar=True)
        dlg.set_program_name(about['program_name'])
        dlg.set_version(about['version'])
        dlg.set_logo_icon_name(about['icon_name'])
        dlg.set_website(about['website'])
        dlg.set_comments(about['comments'])
        dlg.set_license_type(Gtk.License.GPL_2_0)
        dlg.set_copyright(about['copyright'])
        dlg.set_authors(about['authors'])
        dlg.set_artists(about['artists'])
        dlg.set_translator_credits(_("translator-credits"))
        dlg.set_transient_for(self)

        # Cleanup duplicate buttons
        hbar = dlg.get_header_bar()
        for child in hbar.get_children():
            if type(child) in [Gtk.Button, Gtk.ToggleButton]:
                child.destroy()

        return dlg

    def finish_initializing(self, builder):
        """Set up the main window"""
        super(CatfishWindow, self).finish_initializing(builder)

        self.AboutDialog = self.get_about_dialog

        self.settings = CatfishSettings.CatfishSettings()

        # -- Folder Chooser Combobox -- #
        self.folderchooser = builder.get_named_object("toolbar.folderchooser")

        # -- Search Entry and Completion -- #
        self.search_entry = builder.get_named_object("toolbar.search")
        self.suggestions_engine = CatfishSearchEngine(['zeitgeist'])
        completion = Gtk.EntryCompletion()
        self.search_entry.set_completion(completion)
        listmodel = Gtk.ListStore(str)
        completion.set_model(listmodel)
        completion.set_text_column(0)

        # -- App Menu -- #
        self.exact_match = builder.get_named_object("menus.application.exact")
        self.hidden_files = builder.get_named_object(
            "menus.application.hidden")
        self.fulltext = builder.get_named_object("menus.application.fulltext")
        self.sidebar_toggle_menu = builder.get_named_object(
            "menus.application.advanced")

        # -- Sidebar -- #
        css = Gtk.CssProvider()
        css.load_from_data(b".sidebar .view {background-color: transparent;}")
        screen = Gdk.Screen.get_default()
        style = Gtk.StyleContext()
        style.add_provider_for_screen(
            screen, css, Gtk.STYLE_PROVIDER_PRIORITY_SETTINGS)
        self.button_time_custom = builder.get_named_object(
            "sidebar.modified.options")
        self.button_format_custom = builder.get_named_object(
            "sidebar.filetype.options")

        # -- Status Bar -- *
        # Create a new GtkOverlay to hold the
        # results list and Overlay Statusbar
        overlay = Gtk.Overlay()

        # Move the results list to the overlay and
        # place the overlay in the window
        scrolledwindow = builder.get_named_object("results.scrolled_window")
        parent = scrolledwindow.get_parent()
        parent.remove(scrolledwindow)
        overlay.add(scrolledwindow)
        parent.add(overlay)
        overlay.show()

        # Create the overlay statusbar
        self.statusbar = Gtk.EventBox()
        self.statusbar.set_margin_start(2)
        self.statusbar.set_margin_end(3)
        self.statusbar.set_margin_bottom(3)
        self.statusbar.get_style_context().add_class("frame")
        self.statusbar.get_style_context().add_class("background")
        self.statusbar.get_style_context().add_class("floating-bar")
        self.statusbar.connect("draw", self.on_floating_bar_draw)
        self.statusbar.connect("enter-notify-event",
                               self.on_floating_bar_enter_notify)
        self.statusbar.set_halign(Gtk.Align.END)
        self.statusbar.set_valign(Gtk.Align.END)

        # Put the statusbar in the overlay
        overlay.add_overlay(self.statusbar)

        # Pack the spinner and label
        self.spinner = Gtk.Spinner()
        self.spinner.start()
        self.statusbar_label = Gtk.Label()
        self.statusbar_label.show()

        box = Gtk.Box()
        box.set_orientation(Gtk.Orientation.HORIZONTAL)
        box.pack_start(self.spinner, False, False, 0)
        box.pack_start(self.statusbar_label, False, False, 0)
        box.set_margin_start(8)
        box.set_margin_top(3)
        box.set_margin_end(8)
        box.set_margin_bottom(3)
        self.spinner.set_margin_end(3)
        box.show()

        self.statusbar.add(box)
        self.statusbar.set_halign(Gtk.Align.END)
        self.statusbar.hide()

        self.list_toggle = builder.get_named_object("toolbar.view.list")
        self.thumbnail_toggle = builder.get_named_object("toolbar.view.thumbs")

        # -- Treeview -- #
        self.treeview = builder.get_named_object("results.treeview")
        self.treeview.enable_model_drag_source(
            Gdk.ModifierType.BUTTON1_MASK,
            [('text/plain', Gtk.TargetFlags.OTHER_APP, 0),
             ('text/uri-list', Gtk.TargetFlags.OTHER_APP, 0)],
            Gdk.DragAction.DEFAULT | Gdk.DragAction.COPY)
        self.treeview.drag_source_add_text_targets()
        self.file_menu = builder.get_named_object("menus.file.menu")
        self.file_menu_save = builder.get_named_object("menus.file.save")
        self.file_menu_open = builder.get_object("file_menu_open")
        self.file_menu_open_with = builder.get_object("file_menu_open_with")
        self.file_menu_delete = builder.get_named_object("menus.file.delete")
        self.treeview_click_on = False

        # -- Update Search Index Dialog -- #
        menuitem = builder.get_named_object("menus.application.update")
        if SudoDialog.check_dependencies(['locate', 'updatedb']):
            self.update_index_dialog = \
                builder.get_named_object("dialogs.update.dialog")
            self.update_index_database = \
                builder.get_named_object("dialogs.update.database_label")
            self.update_index_modified = \
                builder.get_named_object("dialogs.update.modified_label")
            self.update_index_infobar = \
                builder.get_named_object("dialogs.update.status_infobar")
            self.update_index_icon = \
                builder.get_named_object("dialogs.update.status_icon")
            self.update_index_label = \
                builder.get_named_object("dialogs.update.status_label")
            self.update_index_close = \
                builder.get_named_object("dialogs.update.close_button")
            self.update_index_unlock = \
                builder.get_named_object("dialogs.update.unlock_button")
            self.update_index_active = False

            self.last_modified = 0

            now = datetime.datetime.now()
            self.today = datetime.datetime(now.year, now.month, now.day)
            locate_path, locate_date = self.check_locate()[1:3]

            self.update_index_database.set_label("<tt>%s</tt>" % locate_path)
            if not os.access(os.path.dirname(locate_path), os.R_OK):
                modified = _("Unknown")
            elif os.path.isfile(locate_path):
                modified = locate_date.strftime("%x %X")
            else:
                modified = _("Never")
            self.update_index_modified.set_label("<tt>%s</tt>" % modified)

            if locate_date < self.today - datetime.timedelta(days=7):
                infobar = builder.get_named_object("infobar.infobar")
                infobar.show()
        else:
            menuitem.hide()
            builder.get_named_object(
                "menus.application.update_separator").hide()

        self.format_mimetype_box = \
            builder.get_named_object("dialogs.filetype.mimetypes.box")
        self.extensions_entry = \
            builder.get_named_object("dialogs.filetype.extensions.entry")

        self.search_engine = CatfishSearchEngine(
            ['zeitgeist', 'locate', 'walk'],
            self.settings.get_setting("exclude-paths"))

        self.icon_theme = Gtk.IconTheme.get_default()
        self.icon_theme.connect('changed', self.changed_icon)
        self.changed_icon_theme = False
        self.selected_filenames = []
        self.rows = []

        paned = builder.get_named_object("window.paned")
        paned.set_property('height_request',
                           self.settings.get_setting('window-height'))
        paned.set_property('width_request',
                           self.settings.get_setting('window-width'))

        window_width = self.settings.get_setting('window-width')
        window_height = self.settings.get_setting('window-height')
        window_x = self.settings.get_setting('window-x')
        window_y = self.settings.get_setting('window-y')
        (screen_width, screen_height) = self.get_screen_size()
        (display_width, display_height) = self.get_display_size()

        if (screen_width, screen_height) == (-1, -1) or \
                (display_width, display_height) == (-1, -1):
            # Failed detection, likely using Wayland, don't resize
            pass
        else:
            if (window_height > screen_height or window_width > screen_width):
                window_width = min(display_width, 650)
                window_height = min(display_height, 470)

            paned.set_property('height_request', window_height)
            paned.set_property('width_request', window_width)

            if (window_x >= 0 and window_y >= 0):
                if (window_x + window_width <= screen_width) and \
                        (window_y + window_height <= screen_height):
                    self.move(window_x, window_y)

        self.refresh_search_entry()

        filetype_filters = builder.get_object("filetype_options")
        filetype_filters.connect(
            "row-activated", self.on_file_filters_changed, builder)

        modified_filters = builder.get_object("modified_options")
        modified_filters.connect(
            "row-activated", self.on_modified_filters_changed, builder)

        self.popovers = dict()

        extension_filter = builder.get_object("filter_extensions")
        extension_filter.connect(
            "search-changed", self.on_filter_extensions_changed)

        start_calendar = self.builder.get_named_object(
            "dialogs.date.start_calendar")
        end_calendar = self.builder.get_named_object(
            "dialogs.date.end_calendar")
        start_calendar.connect("day-selected", self.on_calendar_day_changed)
        end_calendar.connect("day-selected", self.on_calendar_day_changed)

        self.app_menu_event = False

        self.thumbnailer = Thumbnailer.Thumbnailer()
        self.configure_welcome_area(builder)
        self.add_mimetypes()
        self.tmpdir = tempfile.TemporaryDirectory(prefix='catfish-')
        self.toolbar_hotkeys()

    def add_mimetypes(self):
        """Copies MIME info generated by update-mime-database (from
           shared-mime-info) to Python's mimetypes module enabling it
           to match local MIME db results (xdg-mime from xdg-utils)."""

        glob2 = '/usr/share/mime/globs2'
        if not os.path.exists(glob2):
            return

        with open("/usr/share/mime/globs2") as f:
            lines = f.readlines()
            for line in reversed(lines):
                try:
                    if ':*.' in line:
                        s = line[3:].strip().split(':*')
                    elif ':' in line:
                        s = line[3:].strip('.*/\n').split(':')
                    else:
                        continue
                    mimetypes.add_type(s[0], s[1], strict=True)
                except IndexError:
                    continue

    def configure_welcome_area(self, builder):
        welcome_area = builder.get_object("welcome_area")
        content = _("Enter your query above to find your files\n"
                    "or click the %s icon for more options.")
        for line in content.split("\n"):
            if "%s" in line:
                row = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
                parts = line.split("%s")
                if len(parts[0].strip()) > 0:
                    label = Gtk.Label.new(parts[0])
                    row.pack_start(label, False, False, 0)
                image = Gtk.Image.new_from_icon_name("open-menu-symbolic",
                                                     Gtk.IconSize.BUTTON)
                image.set_property("use-fallback", True)
                row.pack_start(image, False, False, 0)
                if len(parts[1].strip()) > 0:
                    label = Gtk.Label.new(parts[1])
                    row.pack_start(label, False, False, 0)
            else:
                row = Gtk.Label.new(line)
            row.set_halign(Gtk.Align.CENTER)
            welcome_area.pack_start(row, False, False, 0)
        welcome_area.show_all()

    def get_screen_size(self):
        screen = Gdk.Screen.get_default()
        if screen is None:
            return (-1, -1)
        return (screen.width(), screen.height())

    def get_display_size(self):
        display = Gdk.Display.get_default()
        if display is None:
            return (-1, -1)
        window = Gdk.get_default_root_window()
        mon = display.get_monitor_at_window(window)
        monitor = mon.get_geometry()
        return (monitor.width, monitor.height)

    def on_calendar_day_changed(self, widget):  # pylint: disable=W0613
        start_calendar = self.builder.get_named_object(
            "dialogs.date.start_calendar")
        end_calendar = self.builder.get_named_object(
            "dialogs.date.end_calendar")

        start_date = start_calendar.get_date()
        self.start_date = datetime.datetime(start_date[0], start_date[1] + 1,
                                            start_date[2])

        end_date = end_calendar.get_date()
        self.end_date = datetime.datetime(end_date[0], end_date[1] + 1,
                                          end_date[2])
        self.end_date = self.end_date + datetime.timedelta(days=1, seconds=-1)

        self.filter_timerange = (time.mktime(self.start_date.timetuple()),
                                 time.mktime(self.end_date.timetuple()))

        self.refilter()

    def on_application_menu_row_activated(self, listbox, row):
        self.app_menu_event = not self.app_menu_event
        if not self.app_menu_event:
            return
        if listbox.get_row_at_index(8) == row:
            listbox.get_parent().hide()
            self.on_menu_update_index_activate(row)
        if listbox.get_row_at_index(10) == row:
            listbox.get_parent().hide()
            self.on_menu_preferences_activate(row)
        if listbox.get_row_at_index(11) == row:
            listbox.get_parent().hide()
            self.on_mnu_about_activate(row)

    def on_file_filters_changed(self, treeview, path, column, builder):
        model = treeview.get_model()
        treeiter = model.get_iter(path)
        row = model[treeiter]
        showPopup = row[2] == "other" and row[5] == 0
        if treeview.get_column(2) == column:
            if row[5]:
                popover = self.get_popover(row[2], builder)
                popover.show_all()
                return
            row[3], row[4] = row[4], row[3]
        else:
            row[3], row[4] = row[4], row[3]
        if row[2] == 'other' or row[2] == 'custom':
            row[5] = row[3]
        if showPopup and row[5]:
            popover = self.get_popover(row[2], builder)
            popover.show_all()
        self.filter_formats[row[2]] = row[3]
        self.refilter()

    def get_popover(self, name, builder):
        if name == "other":
            popover_id = "filetype"
        elif name == "custom":
            popover_id = "modified"
        else:
            return False
        if popover_id not in self.popovers.keys():
            builder.get_object(popover_id + "_popover")
            popover = Gtk.Popover.new()
            popover.connect("destroy", self.popover_content_destroy)
            popover.add(builder.get_object(popover_id + "_popover"))
            popover.set_relative_to(builder.get_object(name + "_helper"))
            popover.set_position(Gtk.PositionType.BOTTOM)
            self.popovers[popover_id] = popover
        return self.popovers[popover_id]

    def popover_content_destroy(self, widget):
        widget.hide()
        return False

    def on_modified_filters_changed(self, treeview, path, column, builder):
        model = treeview.get_model()
        treeiter = model.get_iter(path)
        selected = model[treeiter]
        showPopup = selected[2] == "custom" and selected[5] == 0
        treeiter = model.get_iter_first()
        while treeiter:
            row = model[treeiter]
            row[3], row[4], row[5] = 0, 1, 0
            treeiter = model.iter_next(treeiter)
        selected[3], selected[4] = 1, 0
        if selected[2] == "custom":
            selected[5] = 1
        if treeview.get_column(2) == column:
            if selected[5]:
                showPopup = True
        if showPopup:
            popover = self.get_popover(selected[2], builder)
            popover.show_all()
        self.set_modified_range(selected[2])
        self.refilter()

    def on_update_infobar_response(self, widget, response_id):
        if response_id == Gtk.ResponseType.OK:
            self.on_menu_update_index_activate(widget)
        widget.hide()

    def on_floating_bar_enter_notify(self, widget, event):  # pylint: disable=W0613
        """Move the floating statusbar when hovered."""
        if widget.get_halign() == Gtk.Align.END:
            widget.hide()
            widget.set_halign(Gtk.Align.START)
            widget.show()

        else:
            widget.hide()
            widget.set_halign(Gtk.Align.END)
            widget.show()

    def on_floating_bar_draw(self, widget, cairo_t):
        """Draw the floating statusbar."""
        context = widget.get_style_context()

        context.save()
        context.set_state(widget.get_state_flags())

        Gtk.render_background(context, cairo_t, 0, 0,
                              widget.get_allocated_width(),
                              widget.get_allocated_height())

        Gtk.render_frame(context, cairo_t, 0, 0,
                         widget.get_allocated_width(),
                         widget.get_allocated_height())

        context.restore()

        return False

    def get_path(self, arg):
        realpath = os.path.realpath(arg)
        if os.path.isdir(realpath):
            return realpath
        realpath = os.path.realpath(os.path.expanduser(arg))
        if os.path.isdir(realpath):
            return realpath
        return None

    def parse_path_option(self, args):  # pylint: disable=W0613
        # Set the selected folder path. Allow legacy --path option.
        path = None

        # New format, first argument
        if self.options.path is None:
            if len(args) > 0:
                path = self.get_path(args[0])
                if path:
                    args.pop(0)

        # Old format, --path
        else:
            path = self.get_path(self.options.path)

        # Try the user home directory
        if path is None:
            path = self.get_path("~")

        # Once all options are exhausted, return the root
        if path is None:
            path = "/"

        return path

    def parse_sort_option(self):
        column_id, order = None, Gtk.SortType.ASCENDING

        if self.options.sort:
            args = self.options.sort.lower().split(',')
            column = args[0]
            if column == 'name':
                column_id = 1
            elif column == 'size':
                column_id = 2
            elif column == 'path':
                column_id = 3
            elif column == 'date':
                column_id = 4
            elif column == 'type':
                column_id = 5

            if len(args) > 1 and args[1].startswith('d'):
                order = Gtk.SortType.DESCENDING

        return (column_id, order)

    def parse_options(self, options, args):
        """Parse commandline arguments into Catfish runtime settings."""
        self.options = options
        self.options.path = self.parse_path_option(args)

        self.folderchooser.set_filename(self.options.path)

        self.sort = self.parse_sort_option()

        # Set non-flags as search keywords.
        self.search_entry.set_text(' '.join(args))

        # Set the time display format.
        if self.options.time_iso:
            self.time_format = '%Y-%m-%d %H:%M'
        else:
            self.time_format = None

        # Set search defaults.
        self.exact_match.set_active(
            self.options.exact or
            self.settings.get_setting('match-results-exactly'))
        self.hidden_files.set_active(
            self.options.hidden or
            self.settings.get_setting('show-hidden-files'))
        self.fulltext.set_active(
            self.options.fulltext or
            self.settings.get_setting('search-file-contents'))
        self.sidebar_toggle_menu.set_active(
            self.settings.get_setting('show-sidebar'))

        self.show_thumbnail = self.options.thumbnails

        # Set the interface to standard or preview mode.

        if self.options.icons_large:
            self.show_thumbnail = False
            self.setup_large_view()
            self.list_toggle.set_active(True)
        elif self.settings.get_setting('show-thumbnails'):
            self.show_thumbnail = True
            self.setup_large_view()
            self.thumbnail_toggle.set_active(True)
        else:
            self.show_thumbnail = False
            self.setup_small_view()
            self.list_toggle.set_active(True)

        if self.options.start:
            self.on_search_entry_activate(self.search_entry)

    def preview_cell_data_func(self, col, renderer, model, treeiter, data):  # pylint: disable=W0613
        """Cell Renderer Function for the preview."""
        icon_name = model[treeiter][0]
        fullpath = os.path.join(model[treeiter][3], model[treeiter][1])
        emblem_icon = 'emblem-symbolic-link'
        if os.path.isfile(icon_name):
            # Load from thumbnail file.
            if self.show_thumbnail:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(icon_name)
                renderer.set_property('pixbuf', pixbuf)
                return
            else:
                mimetype = self.guess_mimetype(fullpath)
                icon_name = self.get_file_icon(fullpath, mimetype)

        if self.changed_icon_theme:
            mimetype = self.guess_mimetype(fullpath)
            icon_name = self.get_file_icon(fullpath, mimetype)

        if os.path.islink(fullpath) and self.icon_theme.has_icon(emblem_icon):
            pixbuf = self.create_symlink_icon(fullpath, icon_name, emblem_icon)
        else:
            pixbuf = self.get_icon_pixbuf(icon_name)

        renderer.set_property('pixbuf', pixbuf)

    def thumbnail_cell_data_func(self, col, renderer, model, treeiter, data):  # pylint: disable=W0613
        """Cell Renderer Function to Thumbnails View."""
        name, size, path, modified = model[treeiter][1:5]
        name = escape(name)
        size = self.format_size(size)
        path = escape(path)
        modified = self.get_date_string(modified)
        displayed = '<b>%s</b> %s%s%s%s%s' % (name, size, os.linesep, path,
                                              os.linesep, modified)
        renderer.set_property('markup', displayed)

    def load_symbolic_icon(self, icon_name, size, state=Gtk.StateFlags.ACTIVE):
        """Return the symbolic version of icon_name, or the non-symbolic
        fallback if unavailable."""
        context = self.sidebar.get_style_context()
        try:
            icon_lookup_flags = Gtk.IconLookupFlags.FORCE_SVG | \
                Gtk.IconLookupFlags.FORCE_SIZE
            icon_info = self.icon_theme.choose_icon([icon_name + '-symbolic'],
                                                    size,
                                                    icon_lookup_flags)
            color = context.get_color(state)
            icon = icon_info.load_symbolic(color, color, color, color)[0]
        except (AttributeError, GLib.GError):
            icon_lookup_flags = Gtk.IconLookupFlags.FORCE_SVG | \
                Gtk.IconLookupFlags.USE_BUILTIN | \
                Gtk.IconLookupFlags.GENERIC_FALLBACK | \
                Gtk.IconLookupFlags.FORCE_SIZE
            icon = self.icon_theme.load_icon(
                icon_name, size, icon_lookup_flags)
        return icon

    def check_locate(self):
        """Evaluate which locate binary is in use, its path, and modification
        date. Return these values in a tuple."""
        path = get_application_path('locate')
        if path is None:
            return None
        path = os.path.realpath(path)
        locate = os.path.basename(path)
        db = catfishconfig.get_locate_db_path()
        if not os.access(os.path.dirname(db), os.R_OK):
            modified = time.time()
        elif os.path.isfile(db):
            modified = os.path.getmtime(db)
        else:
            modified = 0

        changed = self.last_modified != modified
        self.last_modified = modified

        item_date = datetime.datetime.fromtimestamp(modified)
        return (locate, db, item_date, changed)

    def on_filters_changed(self, box, row, user_data=None):  # pylint: disable=W0613
        if row.is_selected():
            box.unselect_row(row)
        else:
            box.select_row(row)
        return True

    # -- Update Search Index dialog -- #
    def on_update_index_dialog_close(self, widget=None, event=None,  # pylint: disable=W0613
                                     user_data=None):  # pylint: disable=W0613
        """Close the Update Search Index dialog, resetting to default."""
        if not self.update_index_active:
            self.update_index_dialog.hide()

            # Restore Unlock button
            self.update_index_unlock.show()
            self.update_index_unlock.set_can_default(True)
            self.update_index_unlock.set_receives_default(True)
            self.update_index_unlock.grab_focus()
            self.update_index_unlock.grab_default()

            # Restore Cancel button
            self.update_index_close.set_label(_("Cancel"))
            self.update_index_close.set_can_default(False)
            self.update_index_close.set_receives_default(False)

            self.update_index_infobar.hide()

        return True

    def show_update_status_infobar(self, status_code):
        """Display the update status infobar based on the status code."""
        # Error
        if status_code in [1, 3, 127]:
            icon = "dialog-error"
            msg_type = Gtk.MessageType.WARNING
            if status_code == 1:
                status = _('An error occurred while updating the database.')
            elif status_code in [3, 127]:
                status = _("Authentication failed.")

        # Warning
        elif status_code in [2, 126]:
            icon = "dialog-warning"
            msg_type = Gtk.MessageType.WARNING
            status = _("Authentication cancelled.")

        # Info
        else:
            icon = "dialog-information"
            msg_type = Gtk.MessageType.INFO
            status = _('Search database updated successfully.')

        self.update_index_infobar.set_message_type(msg_type)
        self.update_index_icon.set_from_icon_name(icon, Gtk.IconSize.BUTTON)
        self.update_index_label.set_label(status)

        self.update_index_infobar.show()

    def on_update_index_unlock_clicked(self, widget):  # pylint: disable=W0613
        """Unlock admin rights and perform 'updatedb' query."""
        self.update_index_active = True

        # Get the password for sudo
        if not SudoDialog.prefer_pkexec() and \
                not SudoDialog.passwordless_sudo():
            sudo_dialog = SudoDialog.SudoDialog(
                parent=self.update_index_dialog,
                icon='catfish',
                name=get_about()['program_name'],
                retries=3)
            sudo_dialog.show_all()
            response = sudo_dialog.run()
            sudo_dialog.hide()
            password = sudo_dialog.get_password()
            sudo_dialog.destroy()

            if response in [Gtk.ResponseType.NONE, Gtk.ResponseType.CANCEL]:
                self.update_index_active = False
                self.show_update_status_infobar(2)
                return False

            if response == Gtk.ResponseType.REJECT:
                self.update_index_active = False
                self.show_update_status_infobar(3)
                return False

            if not password:
                self.update_index_active = False
                self.show_update_status_infobar(2)
                return False

        # Subprocess to check if query has completed yet, runs at end of func.
        def updatedb_subprocess():
            """Subprocess run for the updatedb command."""
            try:
                self.updatedb_process.expect(pexpect.EOF)
                done = True
            except pexpect.TIMEOUT:
                done = False
            if done:
                self.update_index_active = False
                locate_date, changed = self.check_locate()[2:]
                modified = locate_date.strftime("%x %X")
                self.update_index_modified.set_label("<tt>%s</tt>" % modified)

                # Hide the Unlock button
                self.update_index_unlock.set_sensitive(True)
                self.update_index_unlock.set_receives_default(False)
                self.update_index_unlock.hide()

                # Update the Cancel button to Close, make it default
                self.update_index_close.set_label(_("Close"))
                self.update_index_close.set_sensitive(True)
                self.update_index_close.set_can_default(True)
                self.update_index_close.set_receives_default(True)
                self.update_index_close.grab_focus()
                self.update_index_close.grab_default()

                return_code = self.updatedb_process.exitstatus
                if return_code not in [1, 2, 3, 126, 127] and not changed:
                    return_code = 1
                self.show_update_status_infobar(return_code)
            return not done

        # Set the dialog status to running.
        self.update_index_modified.set_label("<tt>%s</tt>" % _("Updating..."))
        self.update_index_close.set_sensitive(False)
        self.update_index_unlock.set_sensitive(False)

        if SudoDialog.prefer_pkexec():
            self.updatedb_process = SudoDialog.env_spawn('pkexec updatedb', 1)
        else:
            self.updatedb_process = SudoDialog.env_spawn('sudo updatedb', 1)
            try:
                # Check for password prompt or program exit.
                self.updatedb_process.expect(".*ssword.*")
                self.updatedb_process.sendline(password)
                self.updatedb_process.expect(pexpect.EOF)
            except pexpect.EOF:
                # shell already has password, or its not needed
                pass
            except pexpect.TIMEOUT:
                # Poll every 1 second for completion.
                pass
        GLib.timeout_add(1000, updatedb_subprocess)

    # -- Search Entry -- #
    def refresh_search_entry(self):
        """Update the appearance of the search entry based on the application's
        current state."""
        # Default Appearance, used for blank entry
        query = None
        icon_name = "edit-find-symbolic"
        sensitive = True
        button_tooltip_text = None
        css = Gtk.CssProvider()

        # Search running
        if self.search_in_progress:
            icon_name = "process-stop-symbolic"
            button_tooltip_text = _('Stop Search')
            entry_tooltip_text = _("Search is in progress...\nPress the "
                                   "cancel button or the Escape key to stop.")
            css.load_from_data(b".catfish_search_entry image:last-child \
                                  {color: @error_color;}")

        # Search not running
        else:
            entry_text = self.search_entry.get_text()
            entry_tooltip_text = None
            # Search not running, value in terms
            if len(entry_text) > 0:
                button_tooltip_text = _('Begin Search')
                query = entry_text
                css.load_from_data(b".catfish_search_entry image:last-child \
                                      {color: @theme_text_color;}")
            else:
                sensitive = False
                css.load_from_data(b".catfish_search_entry image:last-child \
                                      {color: @theme_unfocused_fg_color;}")

        self.search_entry.get_style_context().add_provider(
            css, Gtk.STYLE_PROVIDER_PRIORITY_SETTINGS)
        self.search_entry.set_icon_from_icon_name(
            Gtk.EntryIconPosition.SECONDARY, icon_name)
        self.search_entry.set_tooltip_text(entry_tooltip_text)
        self.search_entry.set_icon_tooltip_text(
            Gtk.EntryIconPosition.SECONDARY, button_tooltip_text)
        self.search_entry.set_icon_activatable(
            Gtk.EntryIconPosition.SECONDARY, sensitive)
        self.search_entry.set_icon_sensitive(
            Gtk.EntryIconPosition.SECONDARY, sensitive)

        return query

    def on_search_entry_activate(self, widget):
        """If the search entry is not empty, and there is no ongoing search, perform the query."""
        if len(widget.get_text()) > 0:

            # If a search is in progress, stop it
            if self.search_in_progress:
                self.stop_search = True
                self.search_engine.stop()

            self.statusbar.show()

            # Store search start time for displaying friendly dates
            now = datetime.datetime.now()
            self.today = datetime.datetime(now.year, now.month, now.day)
            self.yesterday = self.today - datetime.timedelta(days=1)
            self.this_week = self.today - datetime.timedelta(days=6)

            task = self.perform_query(widget.get_text())
            GLib.idle_add(next, task)

    def on_search_entry_icon_press(self, widget, event, user_data):  # pylint: disable=W0613
        """If search in progress, stop the search, otherwise, start."""
        if not self.search_in_progress:
            self.on_search_entry_activate(self.search_entry)
        else:
            self.stop_search = True
            self.search_engine.stop()

    def on_search_entry_changed(self, widget):  # pylint: disable=W0613
        """Update the search entry icon and run suggestions."""
        text = self.refresh_search_entry()

        if text is None:
            return

        task = self.get_suggestions(text)
        GLib.idle_add(next, task)

    def get_suggestions(self, keywords):
        """Load suggestions from the suggestions engine into the search entry
        completion."""
        self.suggestions_engine.stop()

        # Wait for an available thread.
        while Gtk.events_pending():
            Gtk.main_iteration()

        folder = self.folderchooser.get_filename()
        show_hidden = self.filter_formats['hidden']

        # If the keywords start with a hidden character, show hidden files.
        if len(keywords) != 0 and keywords[0] == '.':
            show_hidden = True

        completion = self.search_entry.get_completion()
        if completion is not None:
            model = completion.get_model()
            model.clear()
        results = []

        for filename in self.suggestions_engine.run(keywords, folder, 10):
            if isinstance(filename, str):
                name = os.path.split(filename)[1]
                if name not in results:
                    try:
                        # Determine if file is hidden
                        hidden = is_file_hidden(folder, filename)

                        if not hidden or show_hidden:
                            results.append(name)
                            model.append([name])
                    except OSError:
                        # file no longer exists
                        pass
            yield True
        yield False

    # -- Application Menu -- #
    def on_menu_exact_match_toggled(self, widget):
        """Toggle the exact match settings, and restart the search
        if a fulltext search was previously run."""
        self.settings.set_setting('match-results-exactly', widget.get_active())
        self.filter_format_toggled("exact", widget.get_active())
        if self.filter_formats['fulltext']:
            self.on_search_entry_activate(self.search_entry)

    def on_menu_hidden_files_toggled(self, widget):
        """Toggle the hidden files settings."""
        active = widget.get_active()
        self.filter_format_toggled("hidden", active)
        self.settings.set_setting('show-hidden-files', active)

    def open_file_dialog_ok(self, widget):
        fc_dialog = self.builder.get_object("fc_open_dialog")
        fc_toolbutton = self.builder.get_object("toolbar_folderchooser")
        fc_warning = self.builder.get_object("no_folder_warning")
        fc_warning_label = self.builder.get_object("no_folder_warning_label")
        fc_warning_hide = GLib.timeout_add_seconds(3, self.hide_fc_warning)
        folder = fc_dialog.get_filename()

        if folder is None:
            fc_warning_label.set_text(_("No folder selected."))
            fc_warning.show()
            fc_warning_hide
            return
        elif not os.path.isdir(folder):
            fc_warning_label.set_text(_("Folder not found."))
            fc_warning.show()
            fc_warning_hide
        elif os.path.isdir(folder):
            fc_toolbutton.set_filename(folder)
            fc_dialog.close()

    def hide_fc_warning(self):
        self.builder.get_object("no_folder_warning").hide()

    def open_folder_dialog(self, widget):
        self.builder.get_object("fc_open_dialog").show()

    def toolbar_hotkeys(self):
        window = self.builder.get_object("Catfish")
        search_entry = self.builder.get_object("toolbar_search")
        fc_toolbutton = self.builder.get_object("toolbar_folderchooser")

        fc_toolbutton.connect('grab_focus', self.open_folder_dialog)

        accelerators = Gtk.AccelGroup()
        window.add_accel_group(accelerators)

        signal = 'grab_focus'
        fc_hotkeys = ('<Control>l', '<Control>o')

        key, mod = Gtk.accelerator_parse('<Control>f')
        search_entry.add_accelerator(signal, accelerators,
                                     key, mod, Gtk.AccelFlags.VISIBLE)

        for key in fc_hotkeys:
            key, mod = Gtk.accelerator_parse(key)
            fc_toolbutton.add_accelerator(signal, accelerators,
                                          key, mod, Gtk.AccelFlags.VISIBLE)

    def on_menu_fulltext_toggled(self, widget):
        """Toggle the fulltext settings, and restart the search."""
        self.settings.set_setting('search-file-contents', widget.get_active())
        self.filter_format_toggled("fulltext", widget.get_active())
        self.on_search_entry_activate(self.search_entry)

    def on_menu_update_index_activate(self, widget):  # pylint: disable=W0613
        """Show the Update Search Index dialog."""
        self.update_index_dialog.show()

    def on_menu_preferences_activate(self, widget):  # pylint: disable=W0613
        dialog = CatfishPrefsDialog()
        dialog.set_transient_for(self)
        dialog.connect_settings(self.settings)
        dialog.run()
        changed_properties = dialog.changed_properties
        dialog.destroy()
        self.refresh_from_settings(changed_properties)

    def refresh_from_settings(self, changed_properties):
        for prop in changed_properties:
            setting = self.settings.get_setting(prop)
            if prop == "show-hidden-files":
                self.hidden_files.set_active(setting)
            if prop == "show-sidebar":
                self.set_sidebar_active(setting)
            if prop == 'file-size-binary':
                self.refilter()

    # -- Sidebar -- #
    def set_sidebar_active(self, active):
        if self.sidebar_toggle_menu.get_active() != active:
            self.sidebar_toggle_menu.set_active(active)
        if self.sidebar.get_visible() != active:
            self.sidebar.set_visible(active)

    def on_sidebar_toggle_toggled(self, widget):
        """Toggle visibility of the sidebar."""
        if isinstance(widget, Gtk.CheckButton):
            active = widget.get_active()
        else:
            active = not self.settings.get_setting('show-sidebar')
        self.settings.set_setting('show-sidebar', active)
        self.set_sidebar_active(active)

    def set_modified_range(self, value):
        if value == 'any':
            self.filter_timerange = (0.0, 9999999999.0)
            LOGGER.debug("Time Range: Beginning of time -> Eternity")
        elif value == 'today':
            now = datetime.datetime.now()
            today = time.mktime((
                datetime.datetime(now.year, now.month, now.day, 0, 0) -
                datetime.timedelta(1)).timetuple())
            self.filter_timerange = (today, 9999999999.0)
            LOGGER.debug(
                "Time Range: %s -> Eternity",
                time.strftime("%x %X", time.localtime(int(today))))
        elif value == 'week':
            now = datetime.datetime.now()
            week = time.mktime((
                datetime.datetime(now.year, now.month, now.day, 0, 0) -
                datetime.timedelta(7)).timetuple())
            self.filter_timerange = (week, 9999999999.0)
            LOGGER.debug(
                "Time Range: %s -> Eternity",
                time.strftime("%x %X", time.localtime(int(week))))
        elif value == 'month':
            now = datetime.datetime.now()
            month = time.mktime((
                datetime.datetime(now.year, now.month, now.day, 0, 0) -
                datetime.timedelta(31)).timetuple())
            self.filter_timerange = (month, 9999999999.0)
            LOGGER.debug(
                "Time Range: %s -> Eternity",
                time.strftime("%x %X", time.localtime(int(month))))
        elif value == 'custom':
            self.filter_timerange = (time.mktime(self.start_date.timetuple()),
                                     time.mktime(self.end_date.timetuple()))
            LOGGER.debug(
                "Time Range: %s -> %s",
                time.strftime("%x %X",
                              time.localtime(int(self.filter_timerange[0]))),
                time.strftime("%x %X",
                              time.localtime(int(self.filter_timerange[1]))))
        self.refilter()

    def on_calendar_today_button_clicked(self, calendar_widget):
        """Change the calendar widget selected date to today."""
        today = datetime.datetime.now()
        calendar_widget.select_month(today.month - 1, today.year)
        calendar_widget.select_day(today.day)

    # File Type toggles
    def filter_format_toggled(self, filter_format, enabled):
        """Update search filter when formats are modified."""
        self.filter_formats[filter_format] = enabled
        LOGGER.debug("File type filters updated: %s", str(self.filter_formats))
        self.refilter()

    def on_filter_extensions_changed(self, widget):
        """Update the results when the extensions filter changed."""
        self.filter_custom_extensions = []
        extensions = widget.get_text().replace(',', ' ')
        for ext in extensions.split():
            ext = ext.strip()
            if len(ext) > 0:
                if ext[0] != '.':
                    ext = "." + ext
                self.filter_custom_extensions.append(ext)

        # Reload the results filter.
        self.refilter()

    def thunar_display_path(self, path):
        try:
            bus = dbus.SessionBus()
            obj = bus.get_object('org.xfce.Thunar', '/org/xfce/FileManager')
            iface = dbus.Interface(obj, 'org.xfce.FileManager')

            method = iface.get_dbus_method('DisplayFolderAndSelect')
            dirname = os.path.dirname(path)
            filename = os.path.basename(path)
            method(dirname, filename, '', '')
            return True
        except:
            return False

    def get_exo_preferred_applications(self, filename):
        apps = {}
        if os.path.exists(filename):
            with open(filename, "r") as infile:
                for line in infile.readlines():
                    line = line.strip()
                    if "=" in line:
                        key, value = line.split("=", 2)
                        if len(value) > 0:
                            apps[key] = value
        return apps

    def get_exo_preferred_file_manager(self):
        config = [GLib.get_user_config_dir()] + GLib.get_system_config_dirs()
        data_dir = GLib.get_user_data_dir()
        custFM = data_dir+"/xfce4/helpers/custom-FileManager.desktop"
        config_dirs = sorted(set(config), reverse=True)

        for config_dir in config_dirs:
            cfg = "%s/xfce4/helpers.rc" % config_dir
            if os.path.exists(cfg):
                apps = self.get_exo_preferred_applications(cfg)
                if 'FileManager' in apps:
                    if 'custom-FileManager' in apps['FileManager']:
                        with open(custFM) as f:
                            for line in f:
                                CFM = line.replace(
                                    'X-XFCE-Commands=', '').strip()
                                if 'X-XFCE-Commands=' in line:
                                    return CFM
                    return apps['FileManager']

        return "Thunar"

    def get_preferred_file_manager(self):
        if helpers.xdg_current_desktop() == 'xfce':
            return self.get_exo_preferred_file_manager()

        app = Gio.AppInfo.get_default_for_type('inode/directory', False)

        if app is None:
            desktop = subprocess.check_output(['xdg-mime', 'query', 'default',
                                               'inode/directory'])
            desktop = desktop.decode("utf-8", errors="replace")
            desktop = desktop.strip()

            for appinfo in Gio.AppInfo.get_all():
                if appinfo.get_id() == desktop:
                    app = appinfo
                    break

        if app is None:
            return "xdg-open"

        if "exo-file-manager" in app.get_id().lower():
            return self.get_exo_preferred_file_manager()

        return app.get_executable()

    def open_file(self, filename):
        """Open the specified filename in its default application."""
        LOGGER.debug("Opening %s" % filename)

        if type(filename) is list:
            filename = filename[0]
        if filename.endswith('.AppImage') and os.access(filename, os.X_OK):
            command = [filename]
        elif os.path.isdir(filename) and \
                helpers.xdg_current_desktop() == 'xfce':
            command = ['exo-open', '--launch', 'FileManager', filename]
        else:
            try:
                uri = "file://" + filename
                Gio.AppInfo.launch_default_for_uri(uri)
            except:
                self.on_menu_open_with_activate(self)
            return
        try:
            subprocess.Popen(command, shell=False)
            if self.settings.get_setting('close-after-select'):
                self.destroy()
            return
        except Exception as msg:
            LOGGER.debug('Exception encountered while opening %s.' +
                         '\n  Exception: %s' +
                         filename, msg)
            self.get_error_dialog(_('\"%s\" could not be opened.') %
                                  os.path.basename(filename), str(msg))

    # -- File Popup Menu -- #
    def on_menu_open_activate(self, widget):  # pylint: disable=W0613
        """Open the selected file in its default application."""
        compressed_files = []
        for filename in self.selected_filenames:
            if '//ARCHIVE//' in filename:
                compressed_files.append(filename)
            else:
                self.open_file(filename)
        self.open_compressed_files(compressed_files)

    def open_compressed_files(self, compressed_files, open_method=None):
        for filename in compressed_files:
            archive, fname = filename.split('//ARCHIVE//')
            if fname.endswith('/'):
                if open_method == 'open_with':
                    return archive
                self.open_file(archive)
                continue
            with zipfile.ZipFile(archive) as z:
                fileinfo = z.getinfo(fname)
                fileinfo.filename = os.path.basename(fname)
                extract_dir = tempfile.mkdtemp(dir=self.tmpdir.name)
                tmpfile = z.extract(fname, path=extract_dir)
                if open_method == 'open_with':
                    return tmpfile
                self.open_file(tmpfile)

    def on_menu_open_with_activate(self, widget):
        file_set = set()
        filenames = self.selected_filenames
        for filename in filenames:
            if '//ARCHIVE//' in filename:
                file_set.add(self.open_compressed_files([filename],
                             'open_with'))
            else:
                file_set.add(filename)

        gfilename = Gio.File.new_for_path(next(iter(file_set)))
        app_chooser = Gtk.AppChooserDialog(gfile=gfilename)
        ac_widget = app_chooser.get_widget()
        ac_widget.set_show_fallback(True)

        if app_chooser.run() == Gtk.ResponseType.OK:
            LOGGER.debug("Opening %s" % file_set)
            app = app_chooser.get_app_info()
            for filename in file_set:
                gfile = Gio.File.new_for_path(filename)
                Gio.AppInfo.launch(app, [gfile])
            app_chooser.destroy()
        app_chooser.destroy()

    def on_menu_filemanager_activate(self, widget):  # pylint: disable=W0613
        """Open the selected file in the default file manager."""

        file_manager = self.get_preferred_file_manager()
        fm = file_manager.lower()
        files, dirs, nfiles = self.on_menu_filemanager_get_file_lists()
        num = len(files)

        if 'nemo' or 'io.elementary.files' in fm:
            num = len(nfiles)

        if 'thunar' in fm:
            for filename in files:
                if not self.thunar_display_path(filename):
                    subprocess.Popen([file_manager, filename])
        elif 'nautilus' in fm:
            for filename in files:
                subprocess.Popen([file_manager, '--select', filename])
        elif 'nemo' in fm:
            for nfilename in nfiles:
                subprocess.Popen([file_manager, nfilename])
        elif 'io.elementary.files' in fm:
            for nfilename in nfiles:
                subprocess.Popen([file_manager, '-n', nfilename])
        else:
            for dirname in dirs:
                subprocess.Popen([file_manager, dirname])

        LOGGER.debug("Opening file manager for %i path(s)" % num)
        return

    def on_menu_filemanager_get_file_lists(self):
        """Creates sets from selected files. Allows file managers to
        open and select file/folder when possible. If not it will open
        the parent folder of the file/folder. Sets prevent file manager
        from opening same location when multiple items are selected."""

        files = set()
        dirs = set()
        nfiles = set()

        for filename in self.selected_filenames:
            if '//ARCHIVE//' in filename:
                filename = filename.split('//ARCHIVE//')[0]

            files.add(filename)
            dirs.add(os.path.dirname(filename))

            if os.path.isfile(filename):
                nfiles.add(filename)
            elif os.path.isdir(filename):
                nfiles.add(os.path.dirname(filename))
        return files, dirs, nfiles

    def on_menu_copy_location_activate(self, widget):  # pylint: disable=W0613
        """Copy the selected file name to the clipboard."""
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        locations = []
        for filename in self.selected_filenames:
            if "//ARCHIVE//" in filename:
                # If file is in archive, copies archive location
                archive = filename.split("//ARCHIVE//")[0]
                if archive in locations:
                    continue
                locations.append(surrogate_escape(archive))
            else:
                locations.append(surrogate_escape(filename))
        text = str(os.linesep).join(locations)
        clipboard.set_text(text, -1)
        clipboard.store()
        LOGGER.debug("Copying %i filename(s) to the clipboard" %
                     len(locations))

    def on_menu_save_activate(self, widget):  # pylint: disable=W0613
        """Show a save dialog and possibly write the results to a file."""
        selected_file = self.selected_filenames[0]
        if "//ARCHIVE//" in selected_file:
            archive = selected_file.split("//ARCHIVE//")[0]
            archive_filename = selected_file.split("//ARCHIVE//")[1]
            with zipfile.ZipFile(archive) as z:
                save_as = self.get_save_dialog(archive_filename)
                if save_as:
                    saved_dir = os.path.dirname(save_as)
                    saved_name = os.path.basename(save_as)
                    archive_fileinfo = z.getinfo(archive_filename)
                    archive_fileinfo.filename = saved_name
                    z.extract(archive_filename, path=saved_dir)

        else:
            filename = self.get_save_dialog(
                surrogate_escape(selected_file))
            original = selected_file
            if filename:
                try:
                    # Try to save the file.
                    copy2(original, filename)

                except Exception as msg:
                    # If the file save fails, throw an error.
                    LOGGER.debug('Exception encountered while saving %s.' +
                                 '\n  Exception: %s', filename, msg)
                    self.get_error_dialog(_('\"%s\" could not be saved.') %
                                          os.path.basename(filename), str(msg))

    def delete_file(self, filename):
        try:
            # Delete the file.
            if not os.path.exists(filename):
                return True
            if os.path.isdir(filename):
                rmtree(filename)
            else:
                os.remove(filename)
            return True
        except Exception as msg:
            # If the file cannot be deleted, throw an error.
            LOGGER.debug('Exception encountered while deleting %s.' +
                         '\n  Exception: %s', filename, msg)
            self.get_error_dialog(_("\"%s\" could not be deleted.") %
                                  os.path.basename(filename),
                                  str(msg))
        return False

    def remove_filenames_from_treeview(self, filenames):
        removed = []
        model = self.treeview.get_model().get_model().get_model()
        treeiter = model.get_iter_first()
        while treeiter is not None:
            nextiter = model.iter_next(treeiter)
            row = model[treeiter]
            found = os.path.join(row[3], row[1])
            if found in filenames:
                model.remove(treeiter)
                removed.append(found)
            if len(removed) == len(filenames):
                return True
            treeiter = nextiter
        return False

    def on_menu_delete_activate(self, widget):  # pylint: disable=W0613
        """Show a delete dialog and remove the file if accepted."""
        filenames = []
        if self.get_delete_dialog(self.selected_filenames):
            delete = sorted(self.selected_filenames)
            delete.reverse()
            for filename in delete:
                if self.delete_file(filename):
                    filenames.append(filename)
        self.remove_filenames_from_treeview(filenames)
        self.refilter()

    def get_save_dialog(self, filename):
        """Show the Save As FileChooserDialog.

        Return the filename, or None if cancelled."""
        basename = os.path.basename(filename)

        dialog = Gtk.FileChooserDialog(title=_('Save "%s" as...') % basename,
                                       transient_for=self,
                                       action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT,
                           Gtk.STOCK_SAVE, Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.REJECT)
        dialog.set_current_name(basename.replace('�', '_'))
        dialog.set_do_overwrite_confirmation(True)
        response = dialog.run()
        save_as = dialog.get_filename()
        dialog.destroy()
        if response == Gtk.ResponseType.ACCEPT:
            return save_as
        return None

    def get_error_dialog(self, primary, secondary):
        """Show an error dialog with the specified message."""
        dialog_text = "<big><b>%s</b></big>\n\n%s" % (escape(primary),
                                                      escape(secondary))

        dialog = Gtk.MessageDialog(transient_for=self,
                                   modal=True,
                                   destroy_with_parent=True,
                                   message_type=Gtk.MessageType.ERROR,
                                   buttons=Gtk.ButtonsType.OK,
                                   text="")

        dialog.set_markup(dialog_text)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.run()
        dialog.destroy()

    def get_delete_dialog(self, filenames):
        """Show a delete confirmation dialog.  Return True if delete wanted."""
        if len(filenames) == 1:
            primary = _("Are you sure that you want to \n"
                        "permanently delete \"%s\"?") % \
                escape(os.path.basename(filenames[0]))
        else:
            primary = _("Are you sure that you want to \n"
                        "permanently delete the %i selected files?") % \
                len(filenames)
        secondary = _("If you delete a file, it is permanently lost.")

        dialog_text = "<big><b>%s</b></big>\n\n%s" % (primary, secondary)
        dialog = Gtk.MessageDialog(transient_for=self,
                                   modal=True,
                                   destroy_with_parent=True,
                                   message_type=Gtk.MessageType.QUESTION,
                                   buttons=Gtk.ButtonsType.NONE,
                                   text="")
        dialog.set_markup(surrogate_escape(dialog_text))

        cancel = dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.NO)
        delete = dialog.add_button(Gtk.STOCK_DELETE, Gtk.ResponseType.YES)

        cancel_image = Gtk.Image.new_from_icon_name("window-close-symbolic",
                                                    Gtk.IconSize.BUTTON)
        delete_image = Gtk.Image.new_from_icon_name("edit-delete-symbolic",
                                                    Gtk.IconSize.BUTTON)
        cancel_image.set_property("use-fallback", True)
        delete_image.set_property("use-fallback", True)

        cancel.set_image(cancel_image)
        delete.set_image(delete_image)
        delete.get_style_context().add_class("destructive-action")

        dialog.set_default_response(Gtk.ResponseType.NO)
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.YES

    def setup_small_view(self):
        """Prepare the list view in the results pane."""
        for column in self.treeview.get_columns():
            self.treeview.remove_column(column)
        self.treeview.append_column(self.new_column(_('Filename'), 1))
        self.treeview.append_column(self.new_column(_('Size'), 2))
        self.treeview.append_column(self.new_column(_('Location'), 3))
        self.treeview.append_column(self.new_column(_('Modified'), 4))
        self.icon_size = Gtk.IconSize.MENU

    def setup_large_view(self):
        """Prepare the extended list view in the results pane."""
        for column in self.treeview.get_columns():
            self.treeview.remove_column(column)
        # Make the Preview Column
        cell = Gtk.CellRendererPixbuf()
        column = Gtk.TreeViewColumn(_('Preview'), cell)
        self.treeview.append_column(column)
        column.set_cell_data_func(cell, self.preview_cell_data_func, None)

        # Make the Details Column
        cell = Gtk.CellRendererText()
        cell.set_property("ellipsize", Pango.EllipsizeMode.END)
        column = Gtk.TreeViewColumn(_("Details"), cell)

        column.set_sort_column_id(1)
        column.set_resizable(True)
        column.set_expand(True)

        column.set_cell_data_func(cell, self.thumbnail_cell_data_func, None)
        self.treeview.append_column(column)
        self.icon_size = Gtk.IconSize.DIALOG

    def on_treeview_list_toggled(self, widget):
        """Switch to the details view."""
        if widget.get_active():
            self.show_thumbnail = False
            self.settings.set_setting('list-toggle', True)
            self.settings.set_setting('show-thumbnails', False)
            if self.options.icons_large:
                self.setup_large_view()
            else:
                self.setup_small_view()

    def on_treeview_thumbnails_toggled(self, widget):
        """Switch to the preview view."""
        if widget.get_active():
            self.show_thumbnail = True
            self.settings.set_setting('list-toggle', False)
            self.settings.set_setting('show-thumbnails', True)
            self.setup_large_view()

    # -- Treeview -- #
    def on_treeview_row_activated(self, treeview, path, user_data):  # pylint: disable=W0613
        """Catch row activations by keyboard or mouse double-click."""
        # Get the filename from the row.
        model = treeview.get_model()
        file_path = self.treemodel_get_row_filename(model, path)
        self.selected_filenames = [file_path]
        # Open the selected file.
        if "//ARCHIVE//" in file_path:
            self.open_compressed_files([self.selected_filenames[0]])
        else:
            self.open_file(self.selected_filenames[0])

    def on_treeview_drag_begin(self, treeview, context):  # pylint: disable=W0613
        """Treeview DND Begin."""
        if len(self.selected_filenames) > 1:
            treesel = treeview.get_selection()
            for row in self.rows:
                treesel.select_path(row)
        return True

    def on_treeview_drag_data_get(self, treeview, context, selection, info,  # pylint: disable=W0613
                                  timestamp):  # pylint: disable=W0613
        """Treeview DND Get."""
        # Checks for archives in selection, disables DND if present
        if any("//ARCHIVE//" in arch for arch in self.selected_filenames):
            return False
        else:
            text = str(os.linesep).join(self.selected_filenames)
            selection.set_text(text, -1)

            uris = ['file://' + path for path in self.selected_filenames]
            selection.set_uris(uris)

            return True

    def treemodel_get_row_filename(self, model, row):
        """Get the filename from a specified row."""
        if zipfile.is_zipfile(model[row][3]):
            if model[row][5] == 'inode/directory':
                filename = model[row][3] + "//ARCHIVE//" + model[row][1] + '/'
            else:
                filename = model[row][3] + "//ARCHIVE//" + model[row][1]
        else:
            filename = os.path.join(model[row][3], model[row][1])
        return filename

    def treeview_get_selected_rows(self, treeview):
        """Get the currently selected rows from the specified treeview."""
        sel = treeview.get_selection()
        model, rows = sel.get_selected_rows()
        data = []
        for row in rows:
            data.append(self.treemodel_get_row_filename(model, row))
        return (model, rows, data)

    def check_treeview_stats(self, treeview):
        if len(self.rows) == 0:
            return -1
        rows = self.treeview_get_selected_rows(treeview)[1]
        for row in rows:
            if row not in self.rows:
                return 2
        if self.rows != rows:
            return 1
        return 0

    def update_treeview_stats(self, treeview, event=None):
        if event and hasattr(event, 'x'):
            self.treeview_set_cursor_if_unset(treeview,
                                              int(event.x),
                                              int(event.y))
        self.rows, self.selected_filenames = \
            self.treeview_get_selected_rows(treeview)[1:]

    def maintain_treeview_stats(self, treeview, event=None):
        if len(self.selected_filenames) == 0:
            self.update_treeview_stats(treeview, event)
        elif self.check_treeview_stats(treeview) == 2:
            self.update_treeview_stats(treeview, event)
        else:
            treesel = treeview.get_selection()
            for row in self.rows:
                treesel.select_path(row)

    def on_treeview_cursor_changed(self, treeview):
        if "Shift" in self.keys_pressed or "Control" in self.keys_pressed:
            self.update_treeview_stats(treeview)
        if "Up" in self.keys_pressed or "Down" in self.keys_pressed:
            self.update_treeview_stats(treeview)
        if len(self.selected_filenames) == 1:
            self.update_treeview_stats(treeview)

    def treeview_set_cursor_if_unset(self, treeview, x=0, y=0):
        if treeview.get_selection().count_selected_rows() < 1:
            self.treeview_set_cursor_at_pos(treeview, x, y)

    def treeview_set_cursor_at_pos(self, treeview, x, y):
        try:
            path = treeview.get_path_at_pos(int(x), int(y))[0]
            treeview.set_cursor(path)
        except TypeError:
            return False
        return True

    def treeview_left_click(self, treeview, event=None):
        self.update_treeview_stats(treeview, event)
        return False

    def treeview_middle_click(self, treeview, event=None):
        self.maintain_treeview_stats(treeview, event)
        self.treeview_set_cursor_if_unset(treeview, int(event.x), int(event.y))
        for filename in self.selected_filenames:
            self.open_file(filename)
        return True

    def treeview_right_click(self, treeview, event=None):
        self.maintain_treeview_stats(treeview, event)
        directory = os.path.isdir(self.selected_filenames[0]) or \
            self.selected_filenames[0].endswith("/")
        show_on_single_file = len(self.selected_filenames) == 1 and not \
            directory
        self.file_menu_save.set_visible(show_on_single_file)
        writeable = True
        for filename in self.selected_filenames:
            if not os.access(filename, os.W_OK):
                writeable = False
        self.file_menu_delete.set_sensitive(writeable)
        self.file_menu_open.set_label(self.set_right_click_open_label())
        self.file_menu.popup_at_pointer()
        return True

    def treeview_alt_clicked(self, treeview, event=None):
        self.update_treeview_stats(treeview, event)
        return False

    def on_treeview_button_press_event(self, treeview, event):
        """Catch single mouse click events on the treeview and rows.

            Left Click:     Ignore.
            Middle Click:   Open the selected file.
            Right Click:    Show the popup menu."""
        if "Shift" in self.keys_pressed or "Control" in self.keys_pressed:
            handled = self.treeview_alt_clicked(treeview, event)
        elif event.button == 1:
            handled = self.treeview_left_click(treeview, event)
        elif event.button == 2:
            handled = self.treeview_middle_click(treeview, event)
        elif event.button == 3:
            handled = self.treeview_right_click(treeview, event)
        else:
            handled = False
        return handled

    def set_right_click_open_label(self):
        try:
            self.file_menu_open.set_visible(True)
            if len(self.selected_filenames) > 1:
                return _('Open with default applications')

            filename = self.selected_filenames[0]

            if '//ARCHIVE//' in filename:
                if filename.endswith('/'):
                    filename = filename.split('//ARCHIVE//')[0]
                else:
                    mime = self.guess_mimetype(filename)
                    app = Gio.AppInfo.get_default_for_type(mime, False)

            if os.path.exists(filename):
                gfile = Gio.File.new_for_path(filename)
                app = Gio.File.query_default_handler(gfile)

            app_name = app.get_display_name()
            return (_('Open with') + ' "{}"'.format(app_name))
        except:
            self.file_menu_open.set_visible(False)
            return _('No application found')

    def on_treeview_key_press_event(self, treeview, event):
        if "Control" in self.keys_pressed and "a" in self.keys_pressed:
            sel = treeview.get_selection()
            sel.select_all()
            self.update_treeview_stats(treeview, event)
        return False

    def new_column(self, label, colid):
        """New Column function for creating TreeView columns easily."""
        if colid == 1:
            column = Gtk.TreeViewColumn(label)
            cell = Gtk.CellRendererPixbuf()
            column.pack_start(cell, False)
            column.set_cell_data_func(cell, self.preview_cell_data_func, None)
            cell = Gtk.CellRendererText()
            column.pack_start(cell, False)
            column.add_attribute(cell, 'text', colid)
        else:
            cell = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(label, cell)
            if colid == 2:
                cell.set_property('xalign', 1.0)
                column.set_cell_data_func(cell, self.cell_data_func_filesize, colid)
            elif colid == 3:
                column.set_min_width(120)
                column.set_expand(True)
                cell.set_property('ellipsize', Pango.EllipsizeMode.START)
                column.add_attribute(cell, 'text', colid)
            elif colid == 4:
                column.set_cell_data_func(cell, self.cell_data_func_modified, colid)
        column.set_sort_column_id(colid)
        column.set_resizable(True)
        return column

    def cell_data_func_filesize(self, column, cell_renderer,  # pylint: disable=W0613
                                tree_model, tree_iter, cellid):
        """File size cell display function."""
        size = long(tree_model.get_value(tree_iter, cellid))

        filesize = self.format_size(size)
        cell_renderer.set_property('text', filesize)

    def cell_data_func_modified(self, column, cell_renderer,  # pylint: disable=W0613
                                tree_model, tree_iter, cellid):
        """Modification date cell display function."""
        modification_int = int(tree_model.get_value(tree_iter, cellid))
        modified = self.get_date_string(modification_int)

        cell_renderer.set_property('text', modified)

    def get_date_string(self, modification_int):
        """Return the date string in the preferred format."""
        if self.time_format is not None:
            modified = time.strftime(self.time_format,
                                     time.localtime(modification_int))
        else:
            item_date = datetime.datetime.fromtimestamp(modification_int)
            if item_date >= self.today:
                modified = _("Today")
            elif item_date >= self.yesterday:
                modified = _("Yesterday")
            elif item_date >= self.this_week:
                modified = time.strftime("%A",
                                         time.localtime(modification_int))
            else:
                modified = time.strftime("%x",
                                         time.localtime(modification_int))
        return modified

    def results_filter_func(self, model, treeiter, user_data):  # pylint: disable=W0613
        """Filter function for search results."""
        # hidden
        if model[treeiter][6]:
            if not self.filter_formats['hidden']:
                return False

        # exact
        if not self.filter_formats['fulltext']:
            if not model[treeiter][7]:
                if self.filter_formats['exact']:
                    return False

        # modified
        modified = model[treeiter][4]
        if modified < self.filter_timerange[0]:
            return False
        if modified > self.filter_timerange[1]:
            return False

        # mimetype
        mimetype = model[treeiter][5]
        use_filters = False
        if self.filter_formats['folders']:
            use_filters = True
            if mimetype == 'inode/directory':
                return True
        if self.filter_formats['images']:
            use_filters = True
            if mimetype.startswith("image"):
                return True
        if self.filter_formats['music']:
            use_filters = True
            if mimetype.startswith("audio"):
                return True
        if self.filter_formats['videos']:
            use_filters = True
            if mimetype.startswith("video"):
                return True
        if self.filter_formats['documents']:
            use_filters = True
            if mimetype.startswith("text"):
                return True
        if self.filter_formats['applications']:
            use_filters = True
            if mimetype.startswith("application"):
                return True
        if self.filter_formats['other']:
            use_filters = True
            extension = os.path.splitext(model[treeiter][1])[1]
            if extension in self.filter_custom_extensions:
                return True

        if use_filters:
            return False

        return True

    def refilter(self):
        """Reload the results filter, update the statusbar to reflect count."""
        try:
            self.results_filter.refilter()
            n_results = len(self.treeview.get_model())
            self.show_results(n_results)
        except AttributeError:
            pass

    def show_results(self, count):
        if count == 0:
            self.builder.get_object("results_scrolledwindow").hide()
            self.builder.get_object("splash").show()
            self.builder.get_object(
                "splash_title").set_text(_("No files found."))
            self.builder.get_object("splash_status").set_text(
                _("Try making your search less specific\n"
                  "or try another directory."))
            self.builder.get_object("splash_status").show()
        else:
            self.builder.get_object("splash").hide()
            self.builder.get_object("results_scrolledwindow").show()
            if count == 1:
                self.statusbar_label.set_label(_("1 file found."))
            else:
                self.statusbar_label.set_label(_("%i files found.") % count)

    def format_size(self, size, precision=1):
        """Make a file size human readable."""
        if isinstance(size, str):
            size = int(size)
        show_binary_size = self.settings.get_setting('file-size-binary')
        if show_binary_size:
            div = 1024
            suffixes = [_('bytes'), 'KiB', 'MiB', 'GiB', 'TiB']
        else:
            div = 1000
            suffixes = [_('bytes'), 'kB', 'MB', 'GB', 'TB']
        suffixIndex = 0
        if size > div:
            while size > div:
                suffixIndex += 1
                size = size / float(div)
            return "%.*f %s" % (precision, size, suffixes[suffixIndex])
        return "%i %s" % (size, suffixes[0])

    def guess_mimetype(self, fullpath):
        """Guess the mimetype of the specified filename."""
        filename = os.path.basename(fullpath)
        mimetype = mimetypes.guess_type(filename)
        sub = mimetype[1]
        guess = mimetype[0]
        if os.path.isdir(fullpath) or fullpath.endswith('/'):
            return 'inode/directory'
        if filename in ['INSTALL', 'AUTHORS', 'COPYING', 'CHANGELOG',
                        'Makefile', 'Credits']:
            guess = 'text/x-%s' % filename.lower()
        if sub and 'x-tar' not in guess and sub in ['bzip2', 'gzip', 'xz']:
            guess = 'application/x-%s' % sub.strip('2')
        if guess is None:
            return 'text/plain'
        return guess

    def changed_icon(self, widget):
        self.changed_icon_theme = True
        return

    def create_symlink_icon(self, fullpath, icon_name, emblem_icon):
        """Creates a new transparent 22x21px image. Then centers and
        overlays/composites the mimetype icon. The emblem icon is then
        resized, offset and overlayed onto the 22x21px + mimetype image,
        creating the symbolic icon."""

        load = self.icon_theme.load_icon
        icon_size = Gtk.icon_size_lookup(self.icon_size)[1]

        icon = load(icon_name, icon_size, Gtk.IconLookupFlags.FORCE_SIZE)
        emblem = load(emblem_icon, icon_size, 0)

        # Set GdkPixbuf composite properties (icon sizes, offsets)
        filtr = GdkPixbuf.InterpType.BILINEAR
        if self.show_thumbnail is False:
            new_sizex, new_sizey = (22, 21)
            emb_resize = 12
            icon_destx, icon_desty, icon_offx, icon_offy = (3, 2, 3.0, 2.0)
            emb_destx, emb_desty, emb_offx, emb_offy = (10, 9, 10.0, 9.0)

        else:
            new_sizex, new_sizey = (50, 50)
            emb_resize = 24
            icon_destx, icon_desty, icon_offx, icon_offy = (2, 2, 2.0, 2.0)
            emb_destx, emb_desty, emb_offx, emb_offy = (26, 26, 26.0, 26.0)

        # Create new icon, overlay icon, scale emblem, overlay emblem on top
        new_icon = GdkPixbuf.Pixbuf.new(
            GdkPixbuf.Colorspace(0), True, 8, new_sizex, new_sizey)
        new_icon.fill(0)

        GdkPixbuf.Pixbuf.composite(
            icon, new_icon, icon_destx, icon_desty, icon_size,
            icon_size, icon_offx, icon_offy, 1.0, 1.0, filtr, 255)

        emb_scaled = GdkPixbuf.Pixbuf.scale_simple(
            emblem, emb_resize, emb_resize, filtr)

        GdkPixbuf.Pixbuf.composite(
            emb_scaled, new_icon, emb_destx, emb_desty, emb_resize,
            emb_resize, emb_offx, emb_offy, 1.0, 1.0, filtr, 255)

        return new_icon

    def get_icon_pixbuf(self, name):
        """Return a pixbuf for the icon name from the default icon theme."""
        icon_size = Gtk.icon_size_lookup(self.icon_size)[1]
        flags = Gtk.IconLookupFlags.FORCE_SIZE
        if self.icon_theme.has_icon(name):
            icon = self.icon_theme.load_icon(name, icon_size, flags)
        else:
            icon = self.icon_theme.load_icon('image-missing', icon_size,
                                             flags)
        return icon

    def get_thumbnail(self, path, mime_type=None):
        """Try to fetch a thumbnail."""
        thumb = self.thumbnailer.get_thumbnail(path, mime_type,
                                               self.show_thumbnail)
        if thumb:
            return thumb
        return self.get_file_icon(path, mime_type)

    def get_file_icon(self, fullpath, mime_type=None):  # pylint: disable=W0613
        """Retrieve the file icon."""
        path = os.path.basename(fullpath)
        if mime_type:
            if mime_type == 'inode/directory' or path.endswith('/'):
                return 'folder'
            mime_type = mime_type.split('/')
            if mime_type is not None:
                # Get icon from mimetype
                media, subtype = mime_type

                variations = ['%s-%s' % (media, subtype),
                              '%s-x-%s' % (media, subtype), subtype]

                variations.append('gnome-mime-%s-%s' % (media, subtype))
                if media == "application":
                    variations.append('application-x-executable')
                variations.append('%s-x-generic' % media)

                for icon_name in variations:
                    if self.icon_theme.has_icon(icon_name):
                        return icon_name
        return "text-x-generic"

    def size_sort_func(self, model, row1, row2, user_data):  # pylint: disable=W0613
        """Sort function used in Python 3."""
        sort_column = 2
        value1 = long(model.get_value(row1, sort_column))
        value2 = long(model.get_value(row2, sort_column))
        if value1 < value2:
            return -1
        if value1 == value2:
            return 0
        return 1

    def perform_zip_query(self, filename, keywords, search_exact):
        for member, uncompressed_size, date_time in \
                self.search_engine.search_zip(filename, keywords, search_exact):
            dt = datetime.datetime(*date_time).timestamp()
            mimetype = self.guess_mimetype(member)
            icon = self.get_file_icon(member, mimetype)
            displayed = surrogate_escape(member.rstrip("/"), True)
            zip_path = surrogate_escape(filename)
            exact = keywords in member
            yield [icon, displayed, uncompressed_size,
                   zip_path, dt, mimetype, False, exact]

    # -- Searching -- #
    def perform_query(self, keywords):  # noqa
        """Run the search query with the specified keywords."""
        self.stop_search = False

        # Update the interface to Search Mode
        self.builder.get_object("results_scrolledwindow").hide()
        self.builder.get_object("splash").show()
        self.builder.get_object("splash_title").set_text(_("Searching..."))
        self.builder.get_object("splash_status").set_text(
            _("Results will be displayed as soon as they are found."))
        self.builder.get_object("splash_status").show()
        self.builder.get_object("welcome_area").hide()
        show_results = False
        self.get_window().set_cursor(Gdk.Cursor.new_from_name(
            Gdk.Display.get_default(), "progress"))
        self.set_title(_("Searching for \"%s\"") % keywords)
        self.spinner.show()
        self.statusbar_label.set_label(_("Searching..."))

        self.search_in_progress = True
        self.refresh_search_entry()

        # Be thread friendly.
        while Gtk.events_pending():
            Gtk.main_iteration()

        # icon, name, size, path, modified, mimetype, hidden, exact
        model = Gtk.TreeStore(str, str, GObject.TYPE_INT64,
                              str, float, str, bool, bool)

        # Initialize the results filter.
        self.results_filter = model.filter_new()
        self.results_filter.set_visible_func(self.results_filter_func)
        sort = Gtk.TreeModelSort(model=self.results_filter)
        sort.set_sort_func(2, self.size_sort_func, None)
        if self.sort[0]:  # command-line sort method
            sort.set_sort_column_id(self.sort[0], self.sort[1])
        self.treeview.set_model(sort)
        sort.get_model().get_model().clear()
        self.treeview.columns_autosize()

        # Enable multiple-selection
        sel = self.treeview.get_selection()
        if sel is not None:
            sel.set_mode(Gtk.SelectionMode.MULTIPLE)

        folder = self.folderchooser.get_filename()

        results = []

        # Check if this is a fulltext query or standard query.
        if self.filter_formats['fulltext']:
            self.search_engine = \
                CatfishSearchEngine(['fulltext'],
                                    self.settings.get_setting("exclude-paths"))
            self.search_engine.set_exact(self.filter_formats['exact'])
        else:
            self.search_engine = CatfishSearchEngine(
                ['zeitgeist', 'locate', 'walk'],
                self.settings.get_setting("exclude-paths")
            )

        search_zips = self.settings.get_setting('search-compressed-files')
        search_exact = self.settings.get_setting('match-results-exactly')

        for filename in self.search_engine.run(keywords, folder, search_zips, regex=True):
            if self.stop_search:
                break
            if isinstance(filename, str) and filename not in results:
                try:
                    path, name = os.path.split(filename)
                    size = long(os.path.getsize(filename))
                    modified = os.path.getmtime(filename)

                    mimetype = self.guess_mimetype(filename)
                    icon_name = self.get_thumbnail(filename, mimetype)

                    hidden = is_file_hidden(folder, filename)

                    exact = keywords in name

                    results.append(filename)

                    displayed = surrogate_escape(name, True)
                    path = surrogate_escape(path)
                    if zipfile.is_zipfile(filename):
                        parent = None
                        if not self.filter_formats['fulltext']:
                            if self.search_engine.search_filenames(filename, keywords, search_exact):
                                parent = model.append(
                                    None, [icon_name, displayed, size, path, modified, mimetype, hidden, search_exact])
                        if not search_zips:
                            continue
                        try:
                            for row in self.perform_zip_query(filename, keywords, search_exact):
                                if not parent:
                                    parent = model.append(
                                        None, [icon_name, displayed, size, path, modified, mimetype, hidden, search_exact])
                                model.append(parent, row)
                        except zipfile.BadZipFile as e:
                            LOGGER.debug(f'{e}: {path}')
                    else:
                        model.append(None, [icon_name, displayed, size, path, modified,
                                            mimetype, hidden, exact])

                    if not show_results:
                        if len(self.treeview.get_model()) > 0:
                            show_results = True
                            self.builder.get_object("splash").hide()
                            self.builder.get_object(
                                "results_scrolledwindow").show()

                except OSError:
                    # file no longer exists
                    pass
                except Exception as e:
                    LOGGER.error("Exception encountered: %s" % str(e))

            yield True
            continue

        # Return to Non-Search Mode.
        window = self.get_window()
        if window is not None:
            window.set_cursor(None)
        self.set_title(_('Search results for \"%s\"') % keywords)
        self.spinner.hide()

        n_results = 0
        if self.treeview.get_model() is not None:
            n_results = len(self.treeview.get_model())
        self.show_results(n_results)

        self.search_in_progress = False
        self.refresh_search_entry()

        self.stop_search = False
        yield False
