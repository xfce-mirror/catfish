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

from locale import gettext as _

from gi.repository import Gtk, Gdk, GdkPixbuf, GObject, GLib, Pango # pylint: disable=E0611
from gi.repository.GLib import GError
import logging
logger = logging.getLogger('catfish')

from catfish_lib import Window
from catfish.AboutCatfishDialog import AboutCatfishDialog

from catfish.CatfishSearchEngine import *

import datetime
from calendar import timegm

import os
import time
import hashlib

from shutil import copy2, rmtree

from xml.sax.saxutils import escape

import mimetypes
mimetypes.init()

from sys import version_info
python3 = version_info[0] > 2

GObject.threads_init()
GLib.threads_init()

# See catfish_lib.Window.py for more details about how this class works
class CatfishWindow(Window):
    __gtype_name__ = "CatfishWindow"
    
    folder_thumbnails = os.path.expanduser('~/.thumbnails/')
    
    filter_timerange = (0.0, 9999999999.0)
    start_date = datetime.datetime.now()
    end_date = datetime.datetime.now()
    
    filter_formats = {  'documents': False, 'images': False, 'music': False,
                        'videos': False, 'applications': False, 'other': False,
                        'exact': False, 'hidden': False, 'fulltext': False }
                        
    filter_custom_mimetype = {  'category_text': "", 'category_id': -1,
                                'type_text': "", 'type_id': -1 }
    filter_custom_extensions = []
    filter_custom_use_mimetype = True
    
    mimetypes = dict()
    search_in_progress = False
    
    def finish_initializing(self, builder): # pylint: disable=E1002
        """Set up the main window"""
        super(CatfishWindow, self).finish_initializing(builder)

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
        self.spinner = builder.get_object("spinner")
        self.statusbar = builder.get_object("statusbar_label")
        
        # -- Treeview -- #
        self.treeview = builder.get_object("treeview")
        self.file_menu = builder.get_object("file_menu")
        self.file_menu_save = builder.get_object("menu_save")
        self.file_menu_delete = builder.get_object("menu_delete")
        self.handle_single_button_press = False
        
        # -- Update Search Index dialog -- #
        self.update_index_dialog = builder.get_object("update_index_dialog")
        self.update_index_spinner = builder.get_object("update_index_spinner")
        self.update_index_updating = builder.get_object("update_index_updating")
        self.update_index_done = builder.get_object("update_index_done")
        self.update_index_close = builder.get_object("update_index_close")
        self.update_index_unlock = builder.get_object("update_index_unlock")
        self.update_index_active = False
        
        self.search_engine = CatfishSearchEngine()
        
        self.icon_cache = {}
        self.icon_theme = Gtk.IconTheme.get_default()
        
    def parse_options(self, options, args):
        """Parse commandline arguments into Catfish runtime settings."""
        self.options = options
        
        # Set the selected folder path.
        self.folderchooser.set_filename(self.options.path)
        
        # Set non-flags as search keywords.
        self.search_entry.set_text(' '.join(args))
        
        # Set the time display format.
        if self.options.time_iso:
            self.time_format = '%Y-%m-%d %H:%M'
        else:
            self.time_format = '%x %X'
            
        # Set search defaults.
        self.exact_match.set_active( self.options.exact )
        self.hidden_files.set_active( self.options.hidden )
        self.fulltext.set_active( self.options.fulltext )
        
        # Set the interface to standard or preview mode.
        if self.options.icons_large or self.options.thumbnails:
            self.treeview.append_column(Gtk.TreeViewColumn(_('Preview'),
                Gtk.CellRendererPixbuf(), pixbuf=0))
            self.treeview.append_column(self.new_column(_('Filename'), 1, markup=0))
            self.icon_size = Gtk.IconSize.DIALOG
        else:
            self.treeview.append_column(self.new_column(_('Filename'), 1, 'icon', 1))
            self.treeview.append_column(self.new_column(_('Size'), 2, 'filesize'))
            self.treeview.append_column(self.new_column(_('Location'), 3, 'ellipsize'))
            self.treeview.append_column(self.new_column(_('Last modified'), 4, 'date', 1))
            self.icon_size = Gtk.IconSize.MENU


    # -- Update Search Index dialog -- #
    def on_update_index_dialog_close(self, widget=None, event=None, user_data=None):
        """Close the Update Search Index dialog, resetting to default."""
        if not self.update_index_active:
            self.update_index_dialog.hide()
            self.update_index_close.set_label(Gtk.STOCK_CANCEL)
            self.update_index_unlock.show()
            self.update_index_updating.set_sensitive(True)
            self.update_index_updating.hide()
            self.update_index_done.hide()
        return True
        
    def on_update_index_unlock_clicked(self, widget):
        """Unlock admin rights and perform 'updatedb' query."""
        self.update_index_active = True
        
        # Subprocess to check if query has completed yet, runs at end of func.
        def updatedb_subprocess():
            done = self.updatedb_process.poll() != None
            if done:
                self.update_index_active = False
                self.update_index_close.set_label(Gtk.STOCK_CLOSE)
                self.update_index_updating.set_sensitive(False)
                self.update_index_spinner.hide()
                self.update_index_close.set_sensitive(True)
                self.update_index_unlock.hide()
                self.update_index_unlock.set_sensitive(True)
                return_code = self.updatedb_process.returncode
                if return_code == 0:
                    status = _('Locate database updated successfully.')
                elif return_code == 1:
                    status = _('An error occurred while updating locatedb.')
                elif return_code == 2: 
                    status = _("User aborted authentication.")
                elif return_code == 3:
                    status = _("Authentication failed.")
                else:
                    status = _("User aborted authentication.")
                self.update_index_done.set_label(status)
                self.update_index_done.show()
            return not done
            
        # Set the dialog status to running.
        self.update_index_spinner.show()
        self.update_index_updating.show()
        self.update_index_close.set_sensitive(False)
        self.update_index_unlock.set_sensitive(False)
        
        # Start the query.  Use catfish.desktop to make popup safer-looking.
        self.updatedb_process = subprocess.Popen(['gksudo', 'updatedb', '--desktop', '/usr/share/applications/catfish.desktop'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        
        # Poll every 1 second for completion.
        GLib.timeout_add(1000, updatedb_subprocess)


    # -- Search Entry -- #
    def on_search_entry_activate(self, widget):
        """If the search entry is not empty, perform the query."""
        if len( widget.get_text() ) > 0:
            task = self.perform_query(widget.get_text())
            GObject.idle_add(next, task)
            
    def on_search_entry_icon_press(self, widget, event, user_data):
        """If search in progress, stop the search, otherwise, clear the search
        entry field."""
        if not self.search_in_progress:
            widget.set_text("")
        else:
            self.stop_search = True
            self.search_engine.stop()
            
    def on_search_entry_changed(self, widget):
        """Update the search entry icon and run suggestions."""
        text = widget.get_text()
        
        if not self.search_in_progress:
            if len(text) == 0:
                widget.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, Gtk.STOCK_FIND)
                widget.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, _('Enter search terms and press ENTER') )
            else:
                widget.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, Gtk.STOCK_CLEAR)
                widget.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, _('Clear search terms') )
            
        task = self.get_suggestions(text)
        GObject.idle_add(next, task)
            
    def get_suggestions(self, keywords):
        """Load suggestions from the suggestions engine into the search entry
        completion."""
        self.suggestions_engine.stop()

        while Gtk.events_pending(): Gtk.main_iteration()
        folder = self.folderchooser.get_filename()
        show_hidden = self.filter_formats['hidden']
        
        # If the keywords start with a hidden character, show hidden files.
        if len(keywords) != 0 and keywords[0] == '.': show_hidden = True
        
        model = self.search_entry.get_completion().get_model()
        model.clear()
        results = []
        
        for filename in self.suggestions_engine.run(keywords, folder, 10):
            if isinstance(filename, str):
                path, name = os.path.split(filename)
                if name not in results:
                    try:
                        # Determine if file is hidden
                        hidden = False
                        splitpath = os.path.split(filename)
                        while splitpath[1] != '':
                            if splitpath[1][0] == '.':
                                hidden = True
                                break
                            splitpath = os.path.split(splitpath[0])

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
        self.on_filter_format_toggled("exact", widget.get_active())
        if self.filter_formats['fulltext']:
            self.on_search_entry_activate(self.search_entry)
        
    def on_menu_hidden_files_toggled(self, widget):
        self.on_filter_format_toggled("hidden", widget.get_active())
        
    def on_menu_fulltext_toggled(self, widget):
        self.on_filter_format_toggled("fulltext", widget.get_active())
        self.on_search_entry_activate(self.search_entry)
        
    def on_menu_update_index_activate(self, widget):
        self.update_index_dialog.show()
        
    def on_catfish_window_window_state_event(self, widget, event):
        self.window_is_fullscreen = bool(event.new_window_state & Gdk.WindowState.FULLSCREEN)

    def on_catfish_window_key_press_event(self, widget, event):
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

    # -- Sidebar -- #
    def on_sidebar_toggle_toggled(self, widget):
        """Toggle visibility of the sidebar."""
        active = widget.get_active()

        self.sidebar_toggle_menu.set_active(active)
        
        if active != self.sidebar.get_visible():
            if active:
                self.sidebar.show()
            else:
                self.sidebar.hide()
            
    def on_radio_time_any_toggled(self, widget):
        """Set the time range filter to allow for any modification time."""
        if widget.get_active():
            self.filter_timerange = (0.0, 9999999999.0)
            self.refilter()
            
    def on_radio_time_week_toggled(self, widget):
        """Set the time range filter to allow for files modified since one week
        ago until eternity (to account for newer files)."""
        # Subtract a week from beginning of today for lower, use eternity for upper.
        if widget.get_active():
            now = datetime.datetime.now()
            week = timegm( (datetime.datetime(now.year, now.month, now.day, 0, 0) -
                            datetime.timedelta(7)).timetuple() )
            self.filter_timerange = (week, 9999999999.0)
            self.refilter()
            
    def on_radio_time_custom_toggled(self, widget):
        """Set the time range filter to the custom settings chosen in the date
        chooser dialog."""
        if widget.get_active():
            self.button_time_custom.set_sensitive(True)
            self.filter_timerange = (   timegm( self.start_date.timetuple() ),
                                        timegm( self.end_date.timetuple() )
                                    )
            self.refilter()
        else:
            self.button_time_custom.set_sensitive(False)
            
    def on_button_time_custom_clicked(self, widget):
        """Show the custom time range dialog."""
        dialog = self.builder.get_object("custom_date_dialog")
        start_calendar = self.builder.get_object("start_calendar")
        end_calendar = self.builder.get_object("end_calendar")
        
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.APPLY:
            # Update the time range filter values.
            start_date = start_calendar.get_date()
            self.start_date = datetime.datetime(start_date[0], start_date[1]+1, start_date[2])
            
            end_date = end_calendar.get_date()
            self.end_date = datetime.datetime(end_date[0], end_date[1]+1, end_date[2])
            
            self.filter_timerange = (   timegm( self.start_date.timetuple() ),
                                        timegm( self.end_date.timetuple() )
                                    )
            
            # Reload the results filter.
            self.refilter()
        else:
            # Reset the calendar widgets to their previous values.
            start_calendar.select_month(self.start_date.month-1, self.start_date.year)
            start_calendar.select_day(self.start_date.day)
            
            end_calendar.select_month(self.end_date.month-1, self.end_date.year)
            end_calendar.select_day(self.end_date.day)
            
        dialog.hide()
        
    def on_calendar_today_button_clicked(self, calendar_widget):
        """Change the calendar widget selected date to today."""
        today = datetime.datetime.now()
        calendar_widget.select_month(today.month-1, today.year)
        calendar_widget.select_day(today.day)


    # File Type toggles
    def on_filter_format_toggled(self, filter_format, enabled):
        self.filter_formats[filter_format] = enabled
        self.refilter()
    
    def on_documents_toggled(self, widget):
        self.on_filter_format_toggled("documents", widget.get_active())
        
    def on_images_toggled(self, widget):
        self.on_filter_format_toggled("images", widget.get_active())
        
    def on_music_toggled(self, widget):
        self.on_filter_format_toggled("music", widget.get_active())
        
    def on_videos_toggled(self, widget):
        self.on_filter_format_toggled("videos", widget.get_active())
        
    def on_applications_toggled(self, widget):
        self.on_filter_format_toggled("applications", widget.get_active())
        
    def on_other_format_toggled(self, widget):
        self.on_filter_format_toggled("other", widget.get_active())
        self.button_format_custom.set_sensitive(widget.get_active())
        
    def on_button_format_custom_clicked(self, widget):
        """Show the custom formats dialog."""
        dialog = self.builder.get_object("custom_format_dialog")
        
        radio_mimetypes = self.builder.get_object("radio_custom_mimetype")
        categories = self.builder.get_object("mimetype_categories")
        types = self.builder.get_object("mimetype_types")
        
        radio_extensions = self.builder.get_object("radio_custom_extensions")
        extensions_entry = self.builder.get_object("extensions")
        
        # Lazily load the mimetypes.
        if len(self.mimetypes) == 0:
            mimes = mimetypes.types_map.values()
            if not isinstance(mimes, list):
                mimes = list(mimes)
            mimes.sort()
            for mime in mimes:
                category, mimetype = str(mime).split("/")
                if category not in self.mimetypes.keys():
                    self.mimetypes[category] = []
                if mimetype not in self.mimetypes[category]:
                    self.mimetypes[category].append(mimetype)
                
            keys = self.mimetypes.keys()
            if not isinstance(keys, list):
                keys = list(keys)
            keys.sort()
            for category in keys:
                categories.append_text(category)
                
            types.remove_all()
        
        # Load instance defaults.
        categories.set_active( self.filter_custom_mimetype['category_id'] )
        types.set_active( self.filter_custom_mimetype['type_id'] )
        extensions_entry.set_text( ', '.join(self.filter_custom_extensions) )
        
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
                                'type_id': types.get_active() }
                                            
            self.filter_custom_extensions = []
            extensions = extensions_entry.get_text()
            for ext in extensions.split(','):
                ext = ext.rstrip().lstrip()
                if len(ext) > 0:
                    if ext[0] != '.':
                        ext = "." + ext
                    self.filter_custom_extensions.append( ext )
                
            self.filter_custom_use_mimetype = radio_mimetypes.get_active()
            
            # Reload the results filter.
            self.refilter()
            
        dialog.hide()
        
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
        if os.path.isdir(filename):
            command = [self.options.fileman, filename]
        else:
            command = [self.options.open_wrapper, filename]
        try:
            subprocess.Popen(command, shell=False)
        except Exception as msg:
            if self.options.debug: print('Debug: %s' % msg)
            self.get_error_dialog( _('The file %s could not be opened.')
             % filename)
            print('* The wrapper was %s.' % self.open_wrapper)
            print('* The filemanager was %s.' % self.options.fileman)
            print('Hint: Check wether the wrapper and filemanager exist.')


    # -- File Popup Menu -- #
    def on_menu_open_activate(self, widget):
        """Open the selected file in its default application."""
        self.open_file(self.selected_filename)
        
    def on_menu_filemanager_activate(self, widget):
        """Open the selected file in the default file manager."""
        self.open_file( os.path.split(self.selected_filename)[0] )
        
    def on_menu_copy_activate(self, widget):
        """Copy the selected file name to the clipboard."""
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(self.selected_filename, -1)
        clipboard.store()
        
    def on_menu_save_activate(self, widget):
        """Show a save dialog and possibly write the results to a file."""
        filename = self.get_save_dialog(self.selected_filename)
        if filename:
            try:
                # Try to save the file.
                copy2(self.selected_filename, filename)
                
            except Exception as msg:
                # If the file save fails, throw an error.
                if self.options.debug: print('Debug: %s' % msg)
                self.get_error_dialog( _('The file %s could not be saved.')
                % filename)
            
    def on_menu_delete_activate(self, widget):
        """Show a delete dialog and remove the file if accepted."""
        if self.get_delete_dialog(self.selected_filename):
            try:
                # Delete the file.
                if os.path.isdir(self.selected_filename):
                    rmtree(self.selected_filename)
                else:
                    os.remove(self.selected_filename)
                
                # Remove the selected from from the treeview.
                model = self.treeview.get_model().get_model().get_model()
                path = self.treeview.get_cursor()[0]
                treeiter = model.get_iter(path)
                model.remove(treeiter)
                self.refilter()
                
            except Exception:
                # If the file cannot be deleted, throw an error.
                self.get_error_dialog( _("The file %s could not be deleted.") 
                                       % self.selected_filename )

    def get_save_dialog(self, filename):
        """Show the Save As FileChooserDialog.  
        
        Return the filename, or None if cancelled."""
        basename = os.path.basename(filename)
        
        buttons = ( Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT,
                    Gtk.STOCK_SAVE,   Gtk.ResponseType.ACCEPT)
        dialog = Gtk.FileChooserDialog(_('Save "%s" as…') % basename, self,
            Gtk.FileChooserAction.SAVE, buttons)
        dialog.set_default_response(Gtk.ResponseType.REJECT)
        dialog.set_current_name(basename)
        dialog.set_do_overwrite_confirmation(True)
        response = dialog.run()
        save_as = dialog.get_filename()
        dialog.destroy()
        if response == Gtk.ResponseType.ACCEPT:
            return save_as
        return None
            
    def get_error_dialog(self, msg):
        """Show an error dialog with the specified message."""
        dialog = Gtk.MessageDialog(self, 0,
            Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, msg)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.run()
        dialog.destroy()
        
    def get_delete_dialog(self, filename):
        """Show a delete confirmation dialog.  Return True if delete wanted."""
        msg = _("Are you sure you wish to delete %s?") % filename
        dialog = Gtk.MessageDialog(self, 0,
            Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, msg)
        dialog.set_default_response(Gtk.ResponseType.NO)
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.YES


    # -- Treeview -- #
    def on_treeview_row_activated(self, treeview, path, user_data):
        """Catch row activations by keyboard or mouse double-click."""
        # This event sends a signal twice.  We only want to process it once.
        if self.handle_single_button_press:
            self.handle_single_button_press = False
            return
        self.handle_single_button_press = True
        
        # Get the filename from the row.
        model = treeview.get_model()
        treeiter = model.get_iter(path)
        file_path = model.get_value(treeiter, 3)
        filename = model.get_value(treeiter, 1)
        if self.options.icons_large or self.options.thumbnails:
            filename = filename.split('\n')[0]
            filename = filename.split(' ')
            filename = ' '.join(filename[:len(filename)-2])
        self.selected_filename = os.path.join(file_path, filename)
    
        # Open the selected file.
        self.open_file(self.selected_filename)
        
    def on_treeview_button_press_event(self, treeview, event):
        """Catch single mouse click events on the treeview and rows.
        
            Left Click:     Ignore.
            Middle Click:   Open the selected file.
            Right Click:    Show the popup menu."""
        # This event sends a signal twice.  We only want to process it once.
        if self.handle_single_button_press:
            self.handle_single_button_press = False
            return
        self.handle_single_button_press = True
        
        # Get the selected row path, raises TypeError if dead space.
        try:
            path = treeview.get_path_at_pos(int(event.x), int(event.y))[0]
            treeview.set_cursor(path)
        except TypeError:
            return
        
        # If left click, ignore.
        if event.button == 1: return
        
        # Get the filename from the row.
        model = treeview.get_model()
        treeiter = model.get_iter(path)
        file_path = model.get_value(treeiter, 3)
        filename = model.get_value(treeiter, 1)
        if self.options.icons_large or self.options.thumbnails:
            filename = filename.split('\n')[0]
            filename = filename.split(' ')
            filename = ' '.join(filename[:len(filename)-2])
            
        self.selected_filename = os.path.join(file_path, filename)

        # If middle click, open the selected file.        
        if event.button == 2: self.open_file(filename)
        
        # If right click, show the popup menu.
        if event.button == 3:
            self.file_menu_save.set_visible( not os.path.isdir(self.selected_filename) )
            writeable = os.access(self.selected_filename, os.W_OK)
            self.file_menu_delete.set_sensitive(writeable)
            self.file_menu.popup(None, None, None, None, 
                                 event.button, event.time)

    def new_column(self, label, id, special=None, markup=0):
        """New Column function for creating TreeView columns easily."""
        if special == 'icon':
            column = Gtk.TreeViewColumn(label)
            cell = Gtk.CellRendererPixbuf()
            column.pack_start(cell, False)
            column.add_attribute(cell, 'pixbuf', 0)
            cell = Gtk.CellRendererText()
            column.pack_start(cell, False)
            #column.add_attribute(cell, 'markup', id)
            #column.set_cell_data_func(cell, self.cell_data_func_markup, id)
            column.add_attribute(cell, 'text', id)
        else:
            cell = Gtk.CellRendererText()
            if markup:
                column = Gtk.TreeViewColumn(label, cell, markup=id)
                column.set_cell_data_func(cell, self.cell_data_func_markup, id)
            else:
                column = Gtk.TreeViewColumn(label, cell, text=id)
            if special == 'ellipsize':
                column.set_min_width(120)
                cell.set_property('ellipsize', Pango.EllipsizeMode.START)
            elif special == 'filesize':
                column.set_cell_data_func(cell, self.cell_data_func_filesize, id)
            elif special == 'date':
                column.set_cell_data_func(cell, self.cell_data_func_modified, id)
        column.set_sort_column_id(id)
        column.set_resizable(True)
        if id == 3:
            column.set_expand(True)
        return column
        
    def cell_data_func_markup(self, column, cell_renderer, tree_model, tree_iter, id):
        """Markup cell display function."""
        markup = escape(tree_model.get_value(tree_iter, id))
        cell_renderer.set_property('markup', markup)
        return
        
    def cell_data_func_filesize(self, column, cell_renderer, tree_model, tree_iter, id):
        """File size cell display function."""
        if python3:
            size = int(tree_model.get_value(tree_iter, id))
        else:
            size = long(tree_model.get_value(tree_iter, id))
            
        filesize = self.format_size( size )
        cell_renderer.set_property('text', filesize)
        return
        
    def cell_data_func_modified(self, column, cell_renderer, tree_model, tree_iter, id):
        """Modification date cell display function."""
        modified = time.strftime(self.time_format, time.gmtime(int(tree_model.get_value(tree_iter, id))))
        cell_renderer.set_property('text', modified)
        return

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
        if modified < self.filter_timerange[0] or modified > self.filter_timerange[1]:
            return False
            
        # mimetype
        mimetype = model[iter][5]
        use_filters = False
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
                if mimetype == self.filter_custom_mimetype['category_text'] + "/" + self.filter_custom_mimetype['type_text']:
                    return True
            else:
                extension = os.path.splitext(model[iter][1])[1]
                if extension in self.filter_custom_extensions:
                    return True
            
        if use_filters: return False
        
        return True
        
    def refilter(self):
        """Reload the results filter, update the statusbar to reflect count."""
        try:
            self.results_filter.refilter()
            n_results = len(self.treeview.get_model())
            if n_results == 0:
                self.statusbar.set_label( _("No files found.") )
            else:
                self.statusbar.set_label( _("%i files found.") % n_results )
        except AttributeError:
            pass
        
    def format_size(self, size, precision=1):
        """Make a file size human readable."""
        if isinstance(size, str):
            size = int(size)
        suffixes = ['B', 'KB', 'MB', 'GB', 'TB']
        suffixIndex = 0
        while size > 1024:
            suffixIndex += 1
            size = size/1024.0
        return "%.*f %s" % (precision, size, suffixes[suffixIndex])

    def guess_mimetype(self, filename):
        """Guess the mimetype of the specified filename.
        
        Return a tuple containing (guess, override)."""
        override = None
        if os.path.isdir(filename):
            return ('inode/directory', override)
            
        extension = os.path.splitext(filename)[1]
        if extension in ['.abw', '.ai', '.chrt', '.doc', '.docm', '.docx', 
        '.dot', '.dotm', '.dotx', '.eps', '.gnumeric', '.kil', '.kpr', '.kpt', 
        '.ksp', '.kwd', '.kwt', '.latex', '.mdb', '.mm', '.nb', '.nbp', '.odb', 
        '.odc', '.odf', '.odm', '.odp', '.ods', '.odt', '.otg', '.oth', '.odp', 
        '.ots', '.ott', '.pdf', '.php', '.pht', '.phtml', '.potm', '.potx', 
        '.ppa', '.ppam', '.pps', '.ppsm', '.ppsx', '.ppt', '.pptm', '.pptx', 
        '.ps', '.pwz', '.rtf', '.sda', '.sdc', '.sdd', '.sds', '.sdw', '.stc', 
        '.std', '.sti', '.stw', '.sxc', '.sxd', '.sxg', '.sxi', '.sxm', '.sxw', 
        '.wiz', '.wp5', '.wpd', '.xlam', '.xlb', '.xls', '.xlsb', '.xlsm', 
        '.xlsx', '.xlt', '.xltm', '.xlsx', '.xml']:
            override = 'text/plain'
        elif extension in ['.cdy']:
            override = 'video/x-generic'
        elif extension in ['.odg', '.odi']:
            override = 'audio/x-generic'
        
        guess = mimetypes.guess_type(filename)
        if guess[0] == None:
            return ('text/plain', override)
        return (guess[0], override)
        
    def get_icon_pixbuf(self, name):
        """Return a pixbuf for the icon name from the default icon theme."""
        try:
            return self.icon_cache[name]
        except KeyError:
            icon_size = Gtk.icon_size_lookup(self.icon_size)[1]
            icon = self.icon_theme.load_icon(name, icon_size, 0)
            self.icon_cache[name] = icon
            return icon

    def get_thumbnail(self, path, mime_type=None):
        """Try to fetch a thumbnail."""
        uri = 'file://' + path
        if python3:
            uri = uri.encode()
        md5_hash = hashlib.md5(uri).hexdigest()
        filenames= [os.path.join( self.folder_thumbnails, 'normal', '%s.png' % md5_hash ),
                    os.path.join( self.folder_thumbnails, 'small',  '%s.png' % md5_hash ),
                    os.path.join( self.folder_thumbnails, 'large',  '%s.png' % md5_hash )]
        for filename in filenames:
            try:
                return GdkPixbuf.Pixbuf.new_from_file(filename)
            except GError:
                pass
        return self.get_file_icon(path, mime_type)

    def get_file_icon(self, path, mime_type=None):
        """Retrieve the file icon."""
        if mime_type:
            if mime_type == 'inode/directory':
                icon_name = Gtk.STOCK_DIRECTORY
            else:
                mime_type = mime_type.split('/')
                if mime_type != None:
                    try:
                        # Get icon from mimetype
                        media, subtype = mime_type
                        icon_name = 'gnome-mime-%s-%s' % (media, subtype)
                        return self.get_icon_pixbuf(icon_name)
                    except GError:
                        try:
                            # Then try generic icon
                            icon_name = 'gnome-mime-%s' % media
                            return self.get_icon_pixbuf(icon_name)
                        except GError:
                            # Use default icon
                            icon_name = Gtk.STOCK_FILE
                else:
                    icon_name = Gtk.STOCK_FILE
        else:
            icon_name = Gtk.STOCK_FILE
        return self.get_icon_pixbuf(icon_name)

    def python_three_size_sort_func(self, model, row1, row2, user_data):
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
        self.set_title( _("Searching for \"%s\"") % keywords )
        self.spinner.show()
        self.statusbar.set_label( _("Searching…") )
        self.search_entry.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, Gtk.STOCK_STOP)
        self.search_entry.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, _('Stop Search') )
        
        self.search_in_progress = True
        
        # Be thread friendly.
        while Gtk.events_pending(): Gtk.main_iteration()
        
        # icon, name, size, path, modified, mimetype, hidden, exact
        if python3:
            model = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str, str, float, str, bool, bool)
        else:
            model = Gtk.ListStore(GdkPixbuf.Pixbuf, str, long, str, float, str, bool, bool)
        
        # Initialize the results filter.
        self.results_filter = model.filter_new()
        self.results_filter.set_visible_func(self.results_filter_func)
        sort = Gtk.TreeModelSort(self.results_filter)
        if python3:
            sort.set_sort_func(2, self.python_three_size_sort_func, None)
        self.treeview.set_model(sort)
        self.treeview.columns_autosize()
        
        folder = self.folderchooser.get_filename()

        results = []
        
        # Check if this is a fulltext query or standard query.
        if self.filter_formats['fulltext']:
            fulltext = True
            self.search_engine = CatfishSearchEngine(['fulltext'])
            self.search_engine.set_exact( self.filter_formats['exact'] )
        else:
            fulltext = False
            self.search_engine = CatfishSearchEngine()
        
        for filename in self.search_engine.run(keywords, folder, regex=True):
            if isinstance(filename, str):
                if not self.stop_search:
                    if filename not in results:
                        try:
                            path, name = os.path.split(filename)
                            
                            if python3: # FIXME overflows happen with larger file sizes.
                                size = str(os.path.getsize(filename))
                            else:
                                size = long(os.path.getsize(filename))
                                
                            modified = os.path.getmtime(filename)
                            
                            mimetype, override = self.guess_mimetype(filename)
                            if self.options.thumbnails:
                                icon = self.get_thumbnail(filename, mimetype)
                            else:
                                icon = self.get_file_icon(filename, mimetype)
                            if override:
                                mimetype = override
                            
                            # Determine if file is hidden
                            hidden = False
                            splitpath = os.path.split(filename)
                            while splitpath[1] != '':
                                if splitpath[1][0] == '.':
                                    hidden = True
                                    break
                                splitpath = os.path.split(splitpath[0])
                                
                            exact = keywords in name
                            
                            results.append(filename)
                            
                            if self.options.icons_large or self.options.thumbnails:
                                displayed = '%s %s%s%s%s%s' % (name
                                            , self.format_size(size), os.linesep, path, os.linesep
                                            , time.strftime(self.time_format, time.gmtime(int(modified))))
                                model.append([icon, displayed, size, path, modified, mimetype, hidden, exact])
                            else:
                                model.append([icon, name, size, path, modified, mimetype, hidden, exact])
                        except OSError:
                            # file no longer exists
                            pass
            yield True
            continue
        
        # Return to Non-Search Mode.
        self.get_window().set_cursor(None)
        self.set_title( _('Search results for \"%s\"') % keywords )
        self.spinner.hide()
        
        n_results = len(self.treeview.get_model())
        if n_results == 0:
            self.statusbar.set_label( _("No files found.") )
        else:
            self.statusbar.set_label( _("%i files found.") % n_results )
            
        self.search_in_progress = False
        if len(self.search_entry.get_text()) == 0:
            self.search_entry.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, Gtk.STOCK_FIND)
            self.search_entry.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, _('Enter search terms and press ENTER') )
        else:
            self.search_entry.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, Gtk.STOCK_CLEAR)
            self.search_entry.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, _('Clear search terms') )
        
        self.stop_search = False
        yield False
