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

from locale import gettext as _

from gi.repository import Gtk, Gdk, GdkPixbuf, GObject, GLib, Pango

from xml.sax.saxutils import escape
from shutil import copy2, rmtree

from calendar import timegm
import datetime
import time

import mimetypes
import hashlib
import os

import logging
logger = logging.getLogger('catfish')

from catfish_lib import Window, CatfishSettings, SudoDialog, helpers
from catfish.AboutCatfishDialog import AboutCatfishDialog
from catfish.CatfishSearchEngine import *

import pexpect

# Initialize Gtk, GObject, and mimetypes
if not helpers.check_gobject_version(3, 9, 1):
    GObject.threads_init()
    GLib.threads_init()
mimetypes.init()


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
    relative = filename.lstrip(folder)
    splitpath = os.path.split(relative)
    while splitpath[1] != '':
        if splitpath[1][0] == '.':
            return True
        splitpath = os.path.split(splitpath[0])
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

    folder_thumbnails = os.path.expanduser('~/.thumbnails/')

    filter_timerange = (0.0, 9999999999.0)
    start_date = datetime.datetime.now()
    end_date = datetime.datetime.now()

    filter_formats = {'documents': False, 'folders': False, 'images': False,
                      'music': False, 'videos': False, 'applications': False,
                      'other': False, 'exact': False, 'hidden': False,
                      'fulltext': False}

    filter_custom_mimetype = {'category_text': "", 'category_id': -1,
                              'type_text': "", 'type_id': -1}
    filter_custom_extensions = []
    filter_custom_use_mimetype = True

    mimetypes = dict()
    search_in_progress = False

    def finish_initializing(self, builder):  # pylint: disable=E1002
        """Set up the main window"""
        super(CatfishWindow, self).finish_initializing(builder)
        self.set_wmclass("Catfish", "Catfish")

        self.AboutDialog = AboutCatfishDialog

        # -- Folder Chooser Combobox -- #
        self.folderchooser = builder.get_object("folderchooser")

        # -- Search Entry and Completion -- #
        self.search_entry = builder.get_object("search_entry")
        self.suggestions_engine = CatfishSearchEngine(['zeitgeist'])
        completion = Gtk.EntryCompletion()
        self.search_entry.set_completion(completion)
        listmodel = Gtk.ListStore(str)
        completion.set_model(listmodel)
        completion.set_text_column(0)

        # -- App Menu -- #
        self.exact_match = builder.get_object("menu_exact_match")
        self.hidden_files = builder.get_object("menu_hidden_files")
        self.fulltext = builder.get_object("menu_fulltext")

        # -- Sidebar -- #
        self.sidebar_toggle_menu = builder.get_object("menu_show_advanced")
        self.button_time_custom = builder.get_object("button_time_custom")
        self.button_format_custom = builder.get_object("button_format_custom")

        # -- Status Bar -- *
        # Create a new GtkOverlay to hold the
        # results list and Overlay Statusbar
        overlay = Gtk.Overlay()

        # Move the results list to the overlay and
        # place the overlay in the window
        scrolledwindow = builder.get_object("scrolledwindow2")
        parent = scrolledwindow.get_parent()
        scrolledwindow.reparent(overlay)
        parent.add(overlay)
        overlay.show()

        # Create the overlay statusbar
        self.statusbar = Gtk.EventBox()
        self.statusbar.get_style_context().add_class("background")
        self.statusbar.get_style_context().add_class("floating-bar")
        self.statusbar.connect("draw", self.on_floating_bar_draw)
        self.statusbar.connect("enter-notify-event",
                               self.on_floating_bar_enter_notify)
        self.statusbar.set_halign(Gtk.Align.START)
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
        box.set_margin_left(6)
        box.set_margin_top(3)
        box.set_margin_right(6)
        box.set_margin_bottom(3)
        self.spinner.set_margin_right(3)
        box.show()

        self.statusbar.add(box)
        self.statusbar.set_halign(Gtk.Align.END)
        self.statusbar.hide()

        self.icon_cache_size = 0

        self.list_toggle = builder.get_object('view_list')
        self.thumbnail_toggle = builder.get_object('view_thumbnails')

        # -- Treeview -- #
        self.row_activated = False
        self.treeview = builder.get_object("treeview")
        self.treeview.enable_model_drag_source(
            Gdk.ModifierType.BUTTON1_MASK,
            [('text/plain', Gtk.TargetFlags.OTHER_APP, 0)],
            Gdk.DragAction.DEFAULT | Gdk.DragAction.COPY)
        self.treeview.drag_source_add_text_targets()
        self.file_menu = builder.get_object("file_menu")
        self.file_menu_save = builder.get_object("menu_save")
        self.file_menu_delete = builder.get_object("menu_delete")
        self.treeview_click_on = False

        # -- Update Search Index Dialog -- #
        menuitem = builder.get_object('menu_update_index')
        if SudoDialog.check_dependencies(['locate', 'updatedb']):
            self.update_index_dialog = \
                builder.get_object("update_index_dialog")
            self.update_index_database = builder.get_object("database_label")
            self.update_index_modified = builder.get_object("updated_label")
            self.update_index_infobar = builder.get_object("update_status")
            self.update_index_icon = builder.get_object("update_status_icon")
            self.update_index_label = builder.get_object("update_status_label")
            self.update_index_close = builder.get_object("update_index_close")
            self.update_index_unlock = \
                builder.get_object("update_index_unlock")
            self.update_index_active = False

            now = datetime.datetime.now()
            self.today = datetime.datetime(now.year, now.month, now.day)
            locate, locate_path, locate_date = self.check_locate()

            self.update_index_database.set_label("<tt>%s</tt>" % locate_path)
            if os.path.isfile(locate_path):
                modified = locate_date.strftime("%x %X")
            else:
                modified = _("Never")
            self.update_index_modified.set_label("<tt>%s</tt>" % modified)

            if locate_date < self.today - datetime.timedelta(days=7):
                infobar = builder.get_object("locate_infobar")
                infobar.show()
        else:
            menuitem.hide()

        self.format_mimetype_box = builder.get_object("format_mimetype_box")
        self.extensions_entry = builder.get_object("extensions")

        self.search_engine = CatfishSearchEngine()

        self.icon_cache = {}
        self.icon_theme = Gtk.IconTheme.get_default()

        self.selected_filenames = []

        # Load the symbolic (or fallback) icons.
        self.reload_symbolic_icons(self.icon_theme, builder)

        # Update the symbolic icons when GTK or icon themes change.
        self.icon_theme.connect("changed", self.reload_symbolic_icons, builder)
        self.sidebar.get_style_context().connect("changed",
                                                 self.reload_symbolic_icons,
                                                 builder)

        self.settings = CatfishSettings.CatfishSettings()
        self.refresh_search_entry()

    def on_update_infobar_response(self, widget, response_id):
        if response_id == Gtk.ResponseType.OK:
            self.on_menu_update_index_activate(widget)
        widget.hide()

    def on_floating_bar_enter_notify(self, widget, event):
        """Move the floating statusbar when hovered."""
        if widget.get_halign() == Gtk.Align.START:
            widget.set_halign(Gtk.Align.END)
        else:
            widget.set_halign(Gtk.Align.START)

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

    def reload_symbolic_icons(self, widget, builder):
        """Reload the symbolic icons on GTK or icon theme change."""
        # Modification Time icons
        modified_icon = self.load_symbolic_icon('document-open-recent', 16)
        builder.get_object("image9").set_from_pixbuf(modified_icon)
        builder.get_object("image10").set_from_pixbuf(modified_icon)
        builder.get_object("image11").set_from_pixbuf(modified_icon)

        # Configuration icons
        settings_icon = self.load_symbolic_icon('document-properties', 16,
                                                Gtk.StateFlags.INSENSITIVE)
        self.modified_settings_image = builder.get_object("image8")
        self.document_settings_image = builder.get_object("image12")
        self.modified_settings_image.set_from_pixbuf(settings_icon)
        self.document_settings_image.set_from_pixbuf(settings_icon)

        # File format icons
        documents_icon = self.load_symbolic_icon('folder-documents', 16)
        photos_icon = self.load_symbolic_icon('folder-pictures', 16)
        music_icon = self.load_symbolic_icon('folder-music', 16)
        videos_icon = self.load_symbolic_icon('folder-videos', 16)
        apps_icon = self.load_symbolic_icon('applications-utilities', 16)
        folder_icon = self.load_symbolic_icon('folder', 16)
        custom_format_icon = self.load_symbolic_icon('list-add', 16)
        builder.get_object("image1").set_from_pixbuf(documents_icon)
        builder.get_object("image3").set_from_pixbuf(photos_icon)
        builder.get_object("image4").set_from_pixbuf(music_icon)
        builder.get_object("image5").set_from_pixbuf(videos_icon)
        builder.get_object("image6").set_from_pixbuf(apps_icon)
        builder.get_object("image7").set_from_pixbuf(custom_format_icon)
        builder.get_object("image19").set_from_pixbuf(folder_icon)

    def parse_options(self, options, args):
        """Parse commandline arguments into Catfish runtime settings."""
        self.options = options

        # Set the selected folder path. Allow legacy --path option.
        path = None

        # New format, first argument
        if self.options.path is None:
            if len(args) > 0:
                if os.path.isdir(os.path.realpath(args[0])):
                    path = args.pop(0)

        # Old format, --path
        else:
            if os.path.isdir(os.path.realpath(self.options.path)):
                path = self.options.path

        # Make sure there is a valid path.
        if path is None:
            path = os.path.expanduser("~")
            if os.path.isdir(os.path.realpath(path)):
                self.options.path = path
            else:
                path = "/"
        else:
            self.options.path = path

        self.folderchooser.set_filename(self.options.path)

        # Set non-flags as search keywords.
        self.search_entry.set_text(' '.join(args))

        # Set the time display format.
        if self.options.time_iso:
            self.time_format = '%Y-%m-%d %H:%M'
        else:
            self.time_format = None

        # Set search defaults.
        self.exact_match.set_active(self.options.exact)
        self.hidden_files.set_active(
            self.options.hidden or
            self.settings.get_setting('show-hidden-files'))
        self.fulltext.set_active(self.options.fulltext)
        self.sidebar_toggle_menu.set_active(
            self.settings.get_setting('show-sidebar'))

        self.show_thumbnail = self.options.thumbnails

        # Set the interface to standard or preview mode.

        if self.options.icons_large:
            self.show_thumbnail = False
            self.setup_large_view()
            self.list_toggle.set_active(True)
        elif self.options.thumbnails:
            self.show_thumbnail = True
            self.setup_large_view()
            self.thumbnail_toggle.set_active(True)
        else:
            self.show_thumbnail = False
            self.setup_small_view()
            self.list_toggle.set_active(True)

        if self.options.start:
            self.on_search_entry_activate(self.search_entry)

    def preview_cell_data_func(self, col, renderer, model, treeiter, data):
        """Cell Renderer Function for the preview."""
        icon_name = model[treeiter][0]
        filename = model[treeiter][1]

        if os.path.isfile(icon_name):
            # Load from thumbnail file.
            if self.show_thumbnail:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(icon_name)
                icon_name = None
            else:
                # Get the mimetype image..
                mimetype, override = self.guess_mimetype(filename)
                icon_name = self.get_file_icon(filename, mimetype)

        if icon_name is not None:
            pixbuf = self.get_icon_pixbuf(icon_name)

        renderer.set_property('pixbuf', pixbuf)
        return

    def thumbnail_cell_data_func(self, col, renderer, model, treeiter, data):
        """Cell Renderer Function to Thumbnails View."""
        icon, name, size, path, modified, mime, hidden, exact = \
            model[treeiter][:]
        name = escape(name)
        size = self.format_size(size)
        path = escape(path)
        modified = self.get_date_string(modified)
        displayed = '<b>%s</b> %s%s%s%s%s' % (name, size, os.linesep, path,
                                              os.linesep, modified)
        renderer.set_property('markup', displayed)
        return

    def load_symbolic_icon(self, icon_name, size, state=Gtk.StateFlags.ACTIVE):
        """Return the symbolic version of icon_name, or the non-symbolic
        fallback if unavailable."""
        context = self.sidebar.get_style_context()
        try:
            icon_lookup_flags = Gtk.IconLookupFlags.FORCE_SVG
            icon_info = self.icon_theme.choose_icon([icon_name + '-symbolic'],
                                                    size,
                                                    icon_lookup_flags)
            color = context.get_color(state)
            icon = icon_info.load_symbolic(color, color, color, color)[0]
        except (AttributeError, GLib.GError):
            icon_lookup_flags = Gtk.IconLookupFlags.FORCE_SVG | \
                Gtk.IconLookupFlags.USE_BUILTIN | \
                Gtk.IconLookupFlags.GENERIC_FALLBACK
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
        db = os.path.join('/var/lib', locate, locate + '.db')
        if os.path.isfile(db):
            modified = os.path.getmtime(db)
        else:
            modified = 0
        item_date = datetime.datetime.fromtimestamp(modified)
        return (locate, db, item_date)

    # -- Update Search Index dialog -- #
    def on_update_index_dialog_close(self, widget=None, event=None,
                                     user_data=None):
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
            self.update_index_close.set_label(Gtk.STOCK_CANCEL)
            self.update_index_close.set_can_default(False)
            self.update_index_close.set_receives_default(False)

            self.update_index_infobar.hide()

        return True

    def show_update_status_infobar(self, status_code):
        """Display the update status infobar based on the status code."""
        # Error
        if status_code in [1, 3]:
            icon = "dialog-error"
            msg_type = Gtk.MessageType.WARNING
            if status_code == 1:
                status = _('An error occurred while updating the database.')
            elif status_code == 3:
                status = _("Authentication failed.")

        # Warning
        elif status_code == 2:
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

    def on_update_index_unlock_clicked(self, widget):
        """Unlock admin rights and perform 'updatedb' query."""
        self.update_index_active = True

        # Get the password for sudo
        sudo_dialog = SudoDialog.SudoDialog(parent=self.update_index_dialog,
                                            icon='catfish',
                                            name=_("Catfish File Search"),
                                            retries=3)
        response = sudo_dialog.run()
        sudo_dialog.hide()
        password = sudo_dialog.get_password()
        sudo_dialog.destroy()

        if response in [Gtk.ResponseType.NONE, Gtk.ResponseType.CANCEL]:
            self.update_index_active = False
            self.show_update_status_infobar(2)
            return False

        elif response == Gtk.ResponseType.REJECT:
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
                modified = self.check_locate()[2].strftime("%x %X")
                self.update_index_modified.set_label("<tt>%s</tt>" % modified)

                # Hide the Unlock button
                self.update_index_unlock.set_sensitive(True)
                self.update_index_unlock.set_receives_default(False)
                self.update_index_unlock.hide()

                # Update the Cancel button to Close, make it default
                self.update_index_close.set_label(Gtk.STOCK_CLOSE)
                self.update_index_close.set_sensitive(True)
                self.update_index_close.set_can_default(True)
                self.update_index_close.set_receives_default(True)
                self.update_index_close.grab_focus()
                self.update_index_close.grab_default()

                return_code = self.updatedb_process.exitstatus
                self.show_update_status_infobar(return_code)
            return not done

        # Set the dialog status to running.
        self.update_index_modified.set_label("<tt>%s</tt>" % _("Updating..."))
        self.update_index_close.set_sensitive(False)
        self.update_index_unlock.set_sensitive(False)

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
        entry_tooltip_text = _("Enter search terms and press Enter to begin.")

        # Search running
        if self.search_in_progress:
            icon_name = "process-stop"
            button_tooltip_text = _('Stop Search')
            entry_tooltip_text = _("Search is in progress...\nPress the "
                                   "cancel button or the Escape key to stop.")

        # Search not running
        else:
            entry_text = self.search_entry.get_text()
            # Search not running, value in terms
            if len(entry_text) > 0:
                button_tooltip_text = _('Begin Search')
                query = entry_text
            else:
                sensitive = False

        self.search_entry.set_icon_from_icon_name(
            Gtk.EntryIconPosition.SECONDARY, icon_name)
        self.search_entry.set_icon_tooltip_text(
            Gtk.EntryIconPosition.SECONDARY, button_tooltip_text)
        self.search_entry.set_tooltip_text(entry_tooltip_text)
        self.search_entry.set_icon_activatable(
            Gtk.EntryIconPosition.SECONDARY, sensitive)
        self.search_entry.set_icon_sensitive(
            Gtk.EntryIconPosition.SECONDARY, sensitive)

        return query

    def on_search_entry_activate(self, widget):
        """If the search entry is not empty, perform the query."""
        if len(widget.get_text()) > 0:
            self.statusbar.show()

            # Store search start time for displaying friendly dates
            now = datetime.datetime.now()
            self.today = datetime.datetime(now.year, now.month, now.day)
            self.yesterday = self.today - datetime.timedelta(days=1)
            self.this_week = self.today - datetime.timedelta(days=6)

            task = self.perform_query(widget.get_text())
            GLib.idle_add(next, task)

    def on_search_entry_icon_press(self, widget, event, user_data):
        """If search in progress, stop the search, otherwise, start."""
        if not self.search_in_progress:
            self.on_search_entry_activate(self.search_entry)
        else:
            self.stop_search = True
            self.search_engine.stop()

    def on_search_entry_changed(self, widget):
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
                path, name = os.path.split(filename)
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
        self.filter_format_toggled("exact", widget.get_active())
        if self.filter_formats['fulltext']:
            self.on_search_entry_activate(self.search_entry)

    def on_menu_hidden_files_toggled(self, widget):
        """Toggle the hidden files settings."""
        active = widget.get_active()
        self.filter_format_toggled("hidden", active)
        self.settings.set_setting('show-hidden-files', active)

    def on_menu_fulltext_toggled(self, widget):
        """Toggle the fulltext settings, and restart the search."""
        self.filter_format_toggled("fulltext", widget.get_active())
        self.on_search_entry_activate(self.search_entry)

    def on_menu_update_index_activate(self, widget):
        """Show the Update Search Index dialog."""
        self.update_index_dialog.show()

    # -- Sidebar -- #
    def on_sidebar_toggle_toggled(self, widget):
        """Toggle visibility of the sidebar."""
        active = widget.get_active()
        self.settings.set_setting('show-sidebar', active)
        if active != self.sidebar.get_visible():
            self.sidebar.set_visible(active)

    def on_radio_time_any_toggled(self, widget):
        """Set the time range filter to allow for any modification time."""
        if widget.get_active():
            self.filter_timerange = (0.0, 9999999999.0)
            logger.debug("Time Range: Beginning of time -> Eternity")
            self.refilter()

    def on_radio_time_week_toggled(self, widget):
        """Set the time range filter to allow for files modified since one week
        ago until eternity (to account for newer files)."""
        # Use one week ago for lower bounds, use eternity for upper.
        if widget.get_active():
            now = datetime.datetime.now()
            week = timegm((
                datetime.datetime(now.year, now.month, now.day, 0, 0) -
                datetime.timedelta(7)).timetuple())
            self.filter_timerange = (week, 9999999999.0)
            logger.debug(
                "Time Range: %s -> Eternity",
                time.strftime("%x %X", time.gmtime(int(week))))
            self.refilter()

    def on_radio_time_custom_toggled(self, widget):
        """Set the time range filter to the custom settings chosen in the date
        chooser dialog."""
        active = widget.get_active()
        if active:
            pixbuf = self.load_symbolic_icon('document-properties', 16)

            self.filter_timerange = (timegm(self.start_date.timetuple()),
                                     timegm(self.end_date.timetuple()))
            logger.debug(
                "Time Range: %s -> %s",
                time.strftime("%x %X",
                              time.gmtime(int(self.filter_timerange[0]))),
                time.strftime("%x %X",
                              time.gmtime(int(self.filter_timerange[1]))))

            self.refilter()
        else:
            pixbuf = self.load_symbolic_icon('document-properties', 16,
                                             Gtk.StateFlags.INSENSITIVE)

        self.button_time_custom.set_sensitive(active)
        self.modified_settings_image.set_from_pixbuf(pixbuf)

    def on_button_time_custom_clicked(self, widget):
        """Show the custom time range dialog."""
        dialog = self.builder.get_object("custom_date_dialog")
        start_calendar = self.builder.get_object("start_calendar")
        end_calendar = self.builder.get_object("end_calendar")

        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.APPLY:
            # Update the time range filter values.
            start_date = start_calendar.get_date()
            self.start_date = datetime.datetime(start_date[0],
                                                start_date[1] + 1,
                                                start_date[2])

            end_date = end_calendar.get_date()
            self.end_date = datetime.datetime(end_date[0], end_date[1] + 1,
                                              end_date[2])

            self.filter_timerange = (timegm(self.start_date.timetuple()),
                                     timegm(self.end_date.timetuple()))

            logger.debug(
                "Time Range: %s -> %s",
                time.strftime("%x %X",
                              time.gmtime(int(self.filter_timerange[0]))),
                time.strftime("%x %X",
                              time.gmtime(int(self.filter_timerange[1]))))

            # Reload the results filter.
            self.refilter()
        else:
            # Reset the calendar widgets to their previous values.
            start_calendar.select_month(self.start_date.month - 1,
                                        self.start_date.year)
            start_calendar.select_day(self.start_date.day)

            end_calendar.select_month(self.end_date.month - 1,
                                      self.end_date.year)
            end_calendar.select_day(self.end_date.day)

        dialog.hide()

    def on_calendar_today_button_clicked(self, calendar_widget):
        """Change the calendar widget selected date to today."""
        today = datetime.datetime.now()
        calendar_widget.select_month(today.month - 1, today.year)
        calendar_widget.select_day(today.day)

    # File Type toggles
    def filter_format_toggled(self, filter_format, enabled):
        """Update search filter when formats are modified."""
        self.filter_formats[filter_format] = enabled
        logger.debug("File type filters updated: %s", str(self.filter_formats))
        self.refilter()

    def on_documents_toggled(self, widget):
        """Update search filter when documents is toggled."""
        self.filter_format_toggled("documents", widget.get_active())

    def on_folders_toggled(self, widget):
        """Update search filter when folders is toggled."""
        self.filter_format_toggled("folders", widget.get_active())

    def on_images_toggled(self, widget):
        """Update search filter when images is toggled."""
        self.filter_format_toggled("images", widget.get_active())

    def on_music_toggled(self, widget):
        """Update search filter when music is toggled."""
        self.filter_format_toggled("music", widget.get_active())

    def on_videos_toggled(self, widget):
        """Update search filter when videos is toggled."""
        self.filter_format_toggled("videos", widget.get_active())

    def on_applications_toggled(self, widget):
        """Update search filter when applications is toggled."""
        self.filter_format_toggled("applications", widget.get_active())

    def on_other_format_toggled(self, widget):
        """Update search filter when other format is toggled."""
        active = widget.get_active()
        self.filter_format_toggled("other", active)
        self.button_format_custom.set_sensitive(active)
        if active:
            pixbuf = self.load_symbolic_icon('document-properties', 16)

        else:
            pixbuf = self.load_symbolic_icon('document-properties', 16,
                                             Gtk.StateFlags.INSENSITIVE)
        self.document_settings_image.set_from_pixbuf(pixbuf)

    def on_button_format_custom_clicked(self, widget):
        """Show the custom formats dialog."""
        dialog = self.builder.get_object("custom_format_dialog")

        radio_mimetypes = self.builder.get_object("radio_custom_mimetype")
        categories = self.builder.get_object("mimetype_categories")
        types = self.builder.get_object("mimetype_types")

        radio_extensions = self.builder.get_object("radio_custom_extensions")

        # Lazily load the mimetypes.
        if len(self.mimetypes) == 0:
            mimes = list(mimetypes.types_map.values())
            if not isinstance(mimes, list):
                mimes = list(mimes)
            mimes.sort()
            for mime in mimes:
                category, mimetype = str(mime).split("/")
                if category not in list(self.mimetypes.keys()):
                    self.mimetypes[category] = []
                if mimetype not in self.mimetypes[category]:
                    self.mimetypes[category].append(mimetype)

            keys = list(self.mimetypes.keys())
            if not isinstance(keys, list):
                keys = list(keys)
            keys.sort()
            for category in keys:
                categories.append_text(category)

            types.remove_all()

        # Load instance defaults.
        if self.filter_custom_mimetype['category_id'] == -1:
            categories.set_active(0)
        else:
            categories.set_active(self.filter_custom_mimetype['category_id'])
        if self.filter_custom_mimetype['type_id'] == -1:
            types.set_active(0)
        else:
            types.set_active(self.filter_custom_mimetype['type_id'])
        extensions_str = ', '.join(self.filter_custom_extensions)
        self.extensions_entry.set_text(extensions_str)

        if self.filter_custom_use_mimetype:
            radio_mimetypes.set_active(True)
        else:
            radio_extensions.set_active(True)

        dialog.show_all()

        if dialog.run() == Gtk.ResponseType.APPLY:
            # Update filter settings and instance defaults.
            self.filter_custom_mimetype = {
                'category_text': categories.get_active_text(),
                'category_id': categories.get_active(),
                'type_text': types.get_active_text(),
                'type_id': types.get_active()}

            self.filter_custom_extensions = []
            extensions = self.extensions_entry.get_text().replace(',', ' ')
            for ext in extensions.split():
                ext = ext.rstrip().lstrip()
                if len(ext) > 0:
                    if ext[0] != '.':
                        ext = "." + ext
                    self.filter_custom_extensions.append(ext)

            self.filter_custom_use_mimetype = radio_mimetypes.get_active()

            logger.debug(
                "Updated file type settings:" +
                "\n  Mimetype:     " + str(self.filter_custom_mimetype) +
                "\n  Extensions:   " + str(self.filter_custom_extensions) +
                "\n  Use mimetype: " + str(self.filter_custom_use_mimetype))

            # Reload the results filter.
            self.refilter()

        dialog.hide()

    def on_radio_custom_mimetype_toggled(self, widget):
        """Make widgets sensitive when radio buttons are toggled."""
        self.format_mimetype_box.set_sensitive(widget.get_active())

    def on_radio_custom_extensions_toggled(self, widget):
        """Make widgets sensitive when radio buttons are toggled."""
        self.extensions_entry.set_sensitive(widget.get_active())

    def on_mimetype_categories_changed(self, combobox):
        """Update the mime subtypes when a different category is selected."""
        types = self.builder.get_object("mimetype_types")

        # Remove all existing rows.
        types.remove_all()

        # Add each mimetype.
        if combobox.get_active() != -1:
            for mime in self.mimetypes[combobox.get_active_text()]:
                types.append_text(mime)

        # Set the combobox to the first item.
        types.set_active(0)

    def open_file(self, filename):
        """Open the specified filename in its default application."""
        logger.debug("Opening %s" % filename)
        command = ['xdg-open', filename]
        try:
            subprocess.Popen(command, shell=False)
            return
        except Exception as msg:
            logger.debug('Exception encountered while opening %s.' +
                         '\n  Exception: %s' +
                         filename, msg)

        self.get_error_dialog(_('\"%s\" could not be opened.') %
                              os.path.basename(filename), str(msg))

    # -- File Popup Menu -- #
    def on_menu_open_activate(self, widget):
        """Open the selected file in its default application."""
        for filename in self.selected_filenames:
            self.open_file(filename)

    def on_menu_filemanager_activate(self, widget):
        """Open the selected file in the default file manager."""
        logger.debug("Opening file manager for %i path(s)" %
                     len(self.selected_filenames))
        dirs = []
        for filename in self.selected_filenames:
            path = os.path.split(filename)[0]
            if path not in dirs:
                dirs.append(path)
        for path in dirs:
            self.open_file(path)

    def on_menu_copy_location_activate(self, widget):
        """Copy the selected file name to the clipboard."""
        logger.debug("Copying %i filename(s) to the clipboard" %
                     len(self.selected_filenames))
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        locations = []
        for filename in self.selected_filenames:
            locations.append(surrogate_escape(filename))
        text = str(os.linesep).join(locations)
        clipboard.set_text(text, -1)
        clipboard.store()

    def on_menu_save_activate(self, widget):
        """Show a save dialog and possibly write the results to a file."""
        filename = self.get_save_dialog(
            surrogate_escape(self.selected_filenames[0]))
        if filename:
            try:
                # Try to save the file.
                copy2(self.selected_filenames[0], filename)

            except Exception as msg:
                # If the file save fails, throw an error.
                logger.debug('Exception encountered while saving %s.' +
                             '\n  Exception: %s', filename, msg)
                self.get_error_dialog(_('\"%s\" could not be saved.') %
                                      os.path.basename(filename), str(msg))

    def on_menu_delete_activate(self, widget):
        """Show a delete dialog and remove the file if accepted."""
        if self.get_delete_dialog(self.selected_filenames):
            for filename in self.selected_filenames:
                try:
                    # Delete the file.
                    if os.path.isdir(filename):
                        rmtree(filename)
                    else:
                        os.remove(filename)

                    # Remove the selected from from the treeview.
                    model = self.treeview.get_model().get_model().get_model()
                    path = self.treeview.get_cursor()[0]
                    treeiter = model.get_iter(path)
                    model.remove(treeiter)
                    self.refilter()

                except Exception as msg:
                    # If the file cannot be deleted, throw an error.
                    logger.debug('Exception encountered while deleting %s.' +
                                 '\n  Exception: %s', filename, msg)
                    self.get_error_dialog(_("\"%s\" could not be deleted.") %
                                          os.path.basename(filename),
                                          str(msg))

    def get_save_dialog(self, filename):
        """Show the Save As FileChooserDialog.

        Return the filename, or None if cancelled."""
        basename = os.path.basename(filename)

        dialog = Gtk.FileChooserDialog(title=_('Save "%s" as…') % basename,
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

        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.NO,
                           Gtk.STOCK_DELETE, Gtk.ResponseType.YES)

        dialog.set_default_response(Gtk.ResponseType.NO)
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.YES

    def setup_small_view(self):
        """Prepare the list view in the results pane."""
        for column in self.treeview.get_columns():
            self.treeview.remove_column(column)
        self.treeview.append_column(self.new_column(_('Filename'), 1,
                                                    'icon', 1))
        self.treeview.append_column(self.new_column(_('Size'), 2,
                                                    'filesize'))
        self.treeview.append_column(self.new_column(_('Location'), 3,
                                                    'ellipsize'))
        self.treeview.append_column(self.new_column(_('Modified'), 4,
                                                    'date', 1))
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
        column = Gtk.TreeViewColumn(_("Details"), cell, markup=1)

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
            if self.options.icons_large:
                self.setup_large_view()
            else:
                self.setup_small_view()

    def on_treeview_thumbnails_toggled(self, widget):
        """Switch to the preview view."""
        if widget.get_active():
            self.show_thumbnail = True
            self.setup_large_view()

    # -- Treeview -- #
    def on_treeview_row_activated(self, treeview, path, user_data):
        """Catch row activations by keyboard or mouse double-click."""
        if self.row_activated:
            self.row_activated = False
            return
        else:
            self.row_activated = True

        # Get the filename from the row.
        model = treeview.get_model()
        file_path = self.treemodel_get_row_filename(model, path)
        self.selected_filenames = [file_path]

        # Open the selected file.
        self.open_file(self.selected_filenames[0])

    def on_treeview_drag_begin(self, treeview, context):
        """Treeview DND Begin."""
        if len(self.selected_filenames) > 1:
            treesel = treeview.get_selection()
            for row in self.rows:
                treesel.select_path(row)
        return True

    def on_treeview_drag_data_get(self, treeview, context, selection, info,
                                  time):
        """Treeview DND Get."""
        text = str(os.linesep).join(self.selected_filenames)
        selection.set_text(text, -1)
        return True

    def treemodel_get_row_filename(self, model, row):
        """Get the filename from a specified row."""
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

    def on_treeview_button_press_event(self, treeview, event):
        """Catch single mouse click events on the treeview and rows.

            Left Click:     Ignore.
            Middle Click:   Open the selected file.
            Right Click:    Show the popup menu."""
        self.treeview_click_on = not self.treeview_click_on
        if self.treeview_click_on:
            return False

        model, self.rows, self.selected_filenames = \
            self.treeview_get_selected_rows(treeview)

        # If left click, ignore.
        if event.button == 1:
            return False

        # Get the selected row path, raises TypeError if dead space.
        if treeview.get_selection().count_selected_rows() <= 1:
            try:
                path = treeview.get_path_at_pos(int(event.x), int(event.y))[0]
                treeview.set_cursor(path)
            except TypeError:
                return False

        # If middle click, open the selected file.
        if event.button == 2:
            for filename in selected_filenames:
                self.open_file(filename)

        # If right click, show the popup menu.
        if event.button == 3:
            show_save_option = len(self.selected_filenames) == 1 and not \
                os.path.isdir(self.selected_filenames[0])
            self.file_menu_save.set_visible(show_save_option)
            writeable = True
            for filename in self.selected_filenames:
                if not os.access(filename, os.W_OK):
                    writeable = False
            self.file_menu_delete.set_sensitive(writeable)
            self.file_menu.popup(None, None, None, None,
                                 event.button, event.time)
        return True

    def new_column(self, label, id, special=None, markup=False):
        """New Column function for creating TreeView columns easily."""
        if special == 'icon':
            column = Gtk.TreeViewColumn(label)
            cell = Gtk.CellRendererPixbuf()
            column.pack_start(cell, False)
            column.set_cell_data_func(cell, self.preview_cell_data_func, None)
            cell = Gtk.CellRendererText()
            column.pack_start(cell, False)
            column.add_attribute(cell, 'text', id)
        else:
            cell = Gtk.CellRendererText()
            if markup:
                column = Gtk.TreeViewColumn(label, cell, markup=id)
            else:
                column = Gtk.TreeViewColumn(label, cell, text=id)
            if special == 'ellipsize':
                column.set_min_width(120)
                cell.set_property('ellipsize', Pango.EllipsizeMode.START)
            elif special == 'filesize':
                cell.set_property('xalign', 1.0)
                column.set_cell_data_func(cell,
                                          self.cell_data_func_filesize, id)
            elif special == 'date':
                column.set_cell_data_func(cell,
                                          self.cell_data_func_modified, id)
        column.set_sort_column_id(id)
        column.set_resizable(True)
        if id == 3:
            column.set_expand(True)
        return column

    def cell_data_func_filesize(self, column, cell_renderer,
                                tree_model, tree_iter, id):
        """File size cell display function."""
        if helpers.check_python_version(3, 0):
            size = int(tree_model.get_value(tree_iter, id))
        else:
            size = long(tree_model.get_value(tree_iter, id))

        filesize = self.format_size(size)
        cell_renderer.set_property('text', filesize)
        return

    def cell_data_func_modified(self, column, cell_renderer,
                                tree_model, tree_iter, id):
        """Modification date cell display function."""
        modification_int = int(tree_model.get_value(tree_iter, id))
        modified = self.get_date_string(modification_int)

        cell_renderer.set_property('text', modified)
        return

    def get_date_string(self, modification_int):
        """Return the date string in the preferred format."""
        if self.time_format is not None:
            modified = time.strftime(self.time_format,
                                     time.gmtime(modification_int))
        else:
            item_date = datetime.datetime.fromtimestamp(modification_int)
            if item_date >= self.today:
                modified = _("Today")
            elif item_date >= self.yesterday:
                modified = _("Yesterday")
            elif item_date >= self.this_week:
                modified = time.strftime("%A", time.gmtime(modification_int))
            else:
                modified = time.strftime("%x", time.gmtime(modification_int))
        return modified

    def results_filter_func(self, model, iter, user_data):
        """Filter function for search results."""
        # hidden
        if model[iter][6]:
            if not self.filter_formats['hidden']:
                return False

        # exact
        if not self.filter_formats['fulltext']:
            if not model[iter][7]:
                if self.filter_formats['exact']:
                    return False

        # modified
        modified = model[iter][4]
        if modified < self.filter_timerange[0] or \
                modified > self.filter_timerange[1]:
            return False

        # mimetype
        mimetype = model[iter][5]
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
            if self.filter_custom_use_mimetype:
                if mimetype == self.filter_custom_mimetype['category_text'] + \
                        "/" + self.filter_custom_mimetype['type_text']:
                    return True
            else:
                extension = os.path.splitext(model[iter][1])[1]
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
            if n_results == 0:
                self.statusbar_label.set_label(_("No files found."))
            elif n_results == 1:
                self.statusbar_label.set_label(_("1 file found."))
            else:
                self.statusbar_label.set_label(
                    _("%i files found.") % n_results)
        except AttributeError:
            pass

    def format_size(self, size, precision=1):
        """Make a file size human readable."""
        if isinstance(size, str):
            size = int(size)
        suffixes = [_('bytes'), 'kB', 'MB', 'GB', 'TB']
        suffixIndex = 0
        if size > 1024:
            while size > 1024:
                suffixIndex += 1
                size = size / 1024.0
            return "%.*f %s" % (precision, size, suffixes[suffixIndex])
        else:
            return "%i %s" % (size, suffixes[0])

    def guess_mimetype(self, filename):
        """Guess the mimetype of the specified filename.

        Return a tuple containing (guess, override)."""
        override = None
        if os.path.isdir(filename):
            return ('inode/directory', override)

        extension = os.path.splitext(filename)[1]
        if extension in [
                '.abw', '.ai', '.chrt', '.doc', '.docm', '.docx', '.dot',
                '.dotm', '.dotx', '.eps', '.gnumeric', '.kil', '.kpr', '.kpt',
                '.ksp', '.kwd', '.kwt', '.latex', '.mdb', '.mm', '.nb', '.nbp',
                '.odb', '.odc', '.odf', '.odm', '.odp', '.ods', '.odt', '.otg',
                '.oth', '.odp', '.ots', '.ott', '.pdf', '.php', '.pht',
                '.phtml', '.potm', '.potx', '.ppa', '.ppam', '.pps', '.ppsm',
                '.ppsx', '.ppt', '.pptm', '.pptx', '.ps', '.pwz', '.rtf',
                '.sda', '.sdc', '.sdd', '.sds', '.sdw', '.stc', '.std', '.sti',
                '.stw', '.sxc', '.sxd', '.sxg', '.sxi', '.sxm', '.sxw', '.wiz',
                '.wp5', '.wpd', '.xlam', '.xlb', '.xls', '.xlsb', '.xlsm',
                '.xlsx', '.xlt', '.xltm', '.xlsx', '.xml']:
            override = 'text/plain'
        elif extension in ['.cdy']:
            override = 'video/x-generic'
        elif extension in ['.odg', '.odi']:
            override = 'audio/x-generic'

        guess = mimetypes.guess_type(filename)
        if guess[0] is None:
            return ('text/plain', override)
        return (guess[0], override)

    def get_icon_pixbuf(self, name):
        """Return a pixbuf for the icon name from the default icon theme."""
        try:
            # Clear the icon cache if the current size is not the cached size.
            if self.icon_cache_size != self.icon_size:
                self.icon_cache.clear()
                self.icon_cache_size = self.icon_size
            return self.icon_cache[name]
        except KeyError:
            icon_size = Gtk.icon_size_lookup(self.icon_size)[1]
            if self.icon_theme.has_icon(name):
                icon = self.icon_theme.load_icon(name, icon_size, 0)
            else:
                icon = self.icon_theme.load_icon('image-missing', icon_size, 0)
            self.icon_cache[name] = icon
            return icon

    def get_thumbnail(self, path, mime_type=None):
        """Try to fetch a thumbnail."""
        thumbnails_directory = os.path.expanduser('~/.thumbnails/normal')
        uri = 'file://' + path
        if helpers.check_python_version(3, 0):
            uri = uri.encode('utf-8')
        md5_hash = hashlib.md5(uri).hexdigest()
        thumbnail_path = os.path.join(
            thumbnails_directory, '%s.png' % md5_hash)
        if os.path.isfile(thumbnail_path):
            return thumbnail_path
        if mime_type.startswith('image'):
            new_thumb = self.create_thumbnail(path, thumbnail_path)
            if new_thumb:
                return thumbnail_path
        return self.get_file_icon(path, mime_type)

    def create_thumbnail(self, filename, path):
        """Create a thumbnail image and save it to the thumbnails directory.
        Return True if successful."""
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(filename)
            pixbuf_w = pixbuf.get_width()
            pixbuf_h = pixbuf.get_height()
            if pixbuf_w < 128 and pixbuf_h < 128:
                pixbuf.savev(path, "png", [], [])
                return pixbuf
            if pixbuf_w > pixbuf_h:
                thumb_w = 128
                thumb_h = int(pixbuf_h / (pixbuf_w / 128.0))
            else:
                thumb_h = 128
                thumb_w = int(pixbuf_w / (pixbuf_h / 128.0))
            thumb_pixbuf = pixbuf.scale_simple(
                thumb_w, thumb_h, GdkPixbuf.InterpType.BILINEAR)
            thumb_pixbuf.savev(path, "png", [], [])
            return True
        except Exception as e:
            print (e)
            return False

    def get_file_icon(self, path, mime_type=None):
        """Retrieve the file icon."""
        if mime_type:
            if mime_type == 'inode/directory':
                return Gtk.STOCK_DIRECTORY
            else:
                mime_type = mime_type.split('/')
                if mime_type is not None:
                    # Get icon from mimetype
                    media, subtype = mime_type
                    for icon_name in ['gnome-mime-%s-%s' % (media, subtype),
                                      'gnome-mime-%s' % media]:
                        if self.icon_theme.has_icon(icon_name):
                            return icon_name
        return Gtk.STOCK_FILE

    def python_three_size_sort_func(self, model, row1, row2, user_data):
        """Sort function used in Python 3."""
        sort_column = 2
        value1 = int(model.get_value(row1, sort_column))
        value2 = int(model.get_value(row2, sort_column))
        if value1 < value2:
            return -1
        elif value1 == value2:
            return 0
        else:
            return 1

    # -- Searching -- #
    def perform_query(self, keywords):
        """Run the search query with the specified keywords."""
        self.stop_search = False

        # Update the interface to Search Mode
        self.get_window().set_cursor(Gdk.Cursor(Gdk.CursorType.WATCH))
        self.set_title(_("Searching for \"%s\"") % keywords)
        self.spinner.show()
        self.statusbar_label.set_label(_("Searching…"))

        self.search_in_progress = True
        self.refresh_search_entry()

        # Be thread friendly.
        while Gtk.events_pending():
            Gtk.main_iteration()

        # icon, name, size, path, modified, mimetype, hidden, exact
        model = Gtk.ListStore(str, str, GObject.TYPE_LONG,
                              str, float, str, bool, bool)

        # Initialize the results filter.
        self.results_filter = model.filter_new()
        self.results_filter.set_visible_func(self.results_filter_func)
        sort = Gtk.TreeModelSort(model=self.results_filter)
        if helpers.check_python_version(3, 0):
            sort.set_sort_func(2, self.python_three_size_sort_func, None)
        self.treeview.set_model(sort)
        sort.get_model().get_model().clear()
        self.treeview.columns_autosize()

        # Enable multiple-selection
        sel = self.treeview.get_selection()
        sel.set_mode(Gtk.SelectionMode.MULTIPLE)

        folder = self.folderchooser.get_filename()

        results = []

        # Check if this is a fulltext query or standard query.
        if self.filter_formats['fulltext']:
            self.search_engine = CatfishSearchEngine(['fulltext'])
            self.search_engine.set_exact(self.filter_formats['exact'])
        else:
            self.search_engine = CatfishSearchEngine()

        for filename in self.search_engine.run(keywords, folder, regex=True):
            if isinstance(filename, str) and not self.stop_search and \
                    filename not in results:
                try:
                    path, name = os.path.split(filename)

                    if helpers.check_python_version(3, 0):
                        size = int(os.path.getsize(filename))
                    else:
                        size = long(os.path.getsize(filename))

                    modified = os.path.getmtime(filename)

                    mimetype, override = self.guess_mimetype(filename)
                    icon = self.get_thumbnail(filename, mimetype)
                    if override:
                        mimetype = override

                    hidden = is_file_hidden(folder, filename)

                    exact = keywords in name

                    results.append(filename)

                    displayed = surrogate_escape(name, True)
                    path = surrogate_escape(path)
                    model.append([icon, displayed, size, path, modified,
                                  mimetype, hidden, exact])
                except OSError:
                    # file no longer exists
                    pass
                except Exception as e:
                    logger.error("Exception encountered: ", str(e))

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
        if n_results == 0:
            self.statusbar_label.set_label(_("No files found."))
        elif n_results == 1:
            self.statusbar_label.set_label(_("1 file found."))
        else:
            self.statusbar_label.set_label(_("%i files found.") % n_results)

        self.search_in_progress = False
        self.refresh_search_entry()

        self.stop_search = False
        yield False
