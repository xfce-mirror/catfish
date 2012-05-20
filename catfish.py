#!/usr/bin/env python

# Copyright (C) 2007-2008 Christian Dywan <christian at twotoasts dot de>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# See the file COPYING for the full license text.

import sys

try:
    import os, stat, time, md5, optparse, subprocess, fnmatch, re, datetime, mimetypes

    from os.path import split as split_filename

    import locale, gettext
    from gi.repository import GObject, Gtk, Gdk, GdkPixbuf, Pango
except ImportError, msg:
    print 'Error: The required module %s is missing.' % str(msg).split()[-1]
    sys.exit(1)


try:
    import xdg.Mime
except ImportError, msg:
    print 'Warning: The optional module %s is missing.' % str(msg).split()[-1]

try:
    import dbus
except ImportError, msg:
    print 'Warning: The optional module %s is missing.' % str(msg).split()[-1]
    
try:
    from zeitgeist.client import ZeitgeistDBusInterface
    from zeitgeist.datamodel import Event, TimeRange
    from zeitgeist import datamodel
    iface = ZeitgeistDBusInterface()
except ImportError, msg:
    print 'Warning: The optional module %s is missing.' % str(msg).split()[-1]

app_name = 'catfish'
app_version = '0.4.0'

_ = gettext.gettext # i18n shortcut

def detach_cb(menu, widget):
	menu.detach()

def menu_position(self, menu, data=None, something_else=None):
    widget = menu.get_attach_widget()
    allocation = widget.get_allocation()
    window_pos = widget.get_window().get_position()
    x = window_pos[0] + allocation.x
    y = window_pos[1] + allocation.y + allocation.height
    return (x, y, True)


class suggestions:
    def __init__(self):
        self.zeitgeist_results = []
        self.locate_results = []
        self.max_results = 10

    def zeitgeist_query(self, keywords):
        self.zeitgeist_results = []
        event_template = Event()
        time_range = TimeRange.from_seconds_ago(60 * 3600 * 24) # 60 days at most
        
        results = iface.FindEvents(
            time_range, # (min_timestamp, max_timestamp) in milliseconds
            [event_template, ],
            datamodel.StorageState.Any,
            200,
            datamodel.ResultType.MostRecentSubjects
        )

        results = (datamodel.Event(result) for result in results)

        for event in results:
            for subject in event.get_subjects():
                if subject.uri[:7] == 'file://':
                    filename = split_filename(subject.uri)[1].lower()
                    if keywords.lower() in filename and filename not in self.zeitgeist_results:
                        self.zeitgeist_results.append(filename)
    
    def locate_query(self, keywords, folder):
        self.locate_results = []
        query = "locate -i %s -n 100" % os.path.join(folder, "*%s*" % keywords)
        self.process = subprocess.Popen(query, stdout=subprocess.PIPE, shell=True)
        for filepath in self.process.communicate()[0].split('\n'):
            filename = split_filename(filepath)[1].lower()
            if filename not in self.locate_results and keywords.lower() == filename[:len(keywords)]:
                self.locate_results.append(filename)
    
    def run(self, keywords, folder):
        results = []
        try:
            self.zeitgeist_query(keywords)
        except NameError:
            pass
        if len(self.zeitgeist_results) < self.max_results:
            self.locate_query(keywords, folder)
            results = self.zeitgeist_results
            index = 0
            try:
                while len(results) < self.max_results:
                    if self.locate_results[index] not in results:
                        results.append(self.locate_results[index])
                    index+=1
            except:
                return results
            return results
            

class dbus_query:
    def __init__(self, options):
        self.err = ''
        self.options = options
        method = options[0]
        try:
            bus = dbus.SessionBus()
        except Exception, msg:
            if 1: print 'Debug:', msg # DEBUG
            self.err = 'DBus is unavailable.'
            return
        if method == 'strigi':
            domain, service = 'vandenoever.strigi', '/search'
        elif method == 'pinot':
            domain, service = 'de.berlios.Pinot', '/de/berlios/Pinot'
        else:
            self.err = 'Program %s is unknown' % method
            return
        try:
            obj = bus.get_object(domain, service)
            self.interface = dbus.Interface(obj, domain)
        except Exception, msg:
            if 1: print 'Debug:', msg # DEBUG
            self.err = 'Program %s is unavailable' % method
    def run(self, keywords, folder, exact, hidden, limit):
        results = []
        if self.options[0] == 'strigi':
            for result in self.interface.getHits(keywords, limit, 0):
                results.append(result[0])
        elif self.options[0] == 'pinot':
            if limit < 0: limit = 32000
            if len(folder) > 1:
                keywords += ' dir:' + folder
            try:
                for result in self.interface.SimpleQuery(keywords, dbus.UInt32(limit)):
                    docinfo = self.interface.GetDocumentInfo(dbus.UInt32(result))
                    if type(docinfo) == 'str': # Support pinot <= 0.70
                        results.append(docinfo[1])
                    else:
                        fields = docinfo
                        for field in fields:
                            if field[0] == "url":
                                results.append(field[1])
                                break
            except Exception, msg:
                if 1: print 'Debug:', msg # DEBUG
                # pass # Nothing was found
        return results
    def status(self): return self.err

class shell_query:
    def __init__(self, options):
        self.err = ''
        self.options = options
        try:
            pass
        except Exception, msg:
            if 1: print 'Debug:', msg # DEBUG
            self.err = 'Program %s is unavailable' % options[0]
    def run(self, keywords, folder, exact, hidden, limit):
        (binary, daemon, default, case, nocase, limit_results, wildcards
            , file_manual, path_manual, exact_manual, errors_ignore
            ) = self.options
        command = default % binary
        if exact:
            command += ' ' + case
        else:
            command += ' ' + nocase
        if limit > 0:
            command += ' ' + limit_results
        if wildcards:
            keywords = keywords.replace(' ', '*')
        if file_manual:
            command += ' "*%s*"' % keywords
        else:
            command += ' "%s"' % keywords
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
        return self.process.stdout
    def status(self): return self.err or self.process.poll()

class generic_query:
    def __init__(self): return
    def run(self, keywords, folder, exact, hidden, limit): return []
    def status(self): return 1

class catfish:
    def __init__(self):
        """Create the main window."""

        # Check for a desktop environment
        desktop = os.environ.get('DESKTOP_SESSION', os.environ.get('GDMSESSION', ''))
        if desktop[:4] == 'xfce':
            # We assume this is Xfce4
            default_fileman = 'Thunar'
            self.open_wrapper = 'exo-open'
        elif desktop[:5] == 'gnome':
            # We assume this is Gnome
            default_fileman = 'Nautilus'
            self.open_wrapper = 'gnome-open'
        else:
            # Unknown desktop? Just see what we have then
            # Guess suitable fileman
            commands = ['Nautilus', 'Thunar', 'konqueror']
            default_fileman = ''
            for path in os.environ.get('PATH', '/usr/bin').split(os.pathsep):
                for command in commands:
                    if os.path.exists(os.path.join(path, command)):
                        default_fileman = command
                        break
            commands = ['gnome-open', 'exo-open', 'xdg-open']
            self.open_wrapper = ''
            # Guess suitable file open wrapper
            for path in os.environ.get('PATH', '/usr/bin').split(os.pathsep):
                for command in commands:
                    if os.path.exists(os.path.join(path, command)):
                        self.open_wrapper = command
                        break

        # Parse command line options
        parser = optparse.OptionParser(usage='usage: ' + app_name + ' [options] keywords',
            version=app_name + ' v' + app_version)
        parser.add_option('', '--large-icons', action='store_true'
            , dest='icons_large', help='Use large icons')
        parser.add_option('', '--thumbnails', action='store_true'
            , dest='thumbnails', help='Use thumbnails')
        parser.add_option('', '--iso-time', action='store_true'
            , dest='time_iso', help='Display time in iso format')
        parser.add_option('', '--limit', type='int', metavar='LIMIT'
            , dest='limit_results', help='Limit number of results')
        parser.add_option('', '--path', help='Search in folder PATH')
        parser.add_option('', '--fileman', help='Use FILEMAN as filemanager')
        parser.add_option('', '--wrapper', metavar='WRAPPER'
            , dest='open_wrapper', help='Use WRAPPER to open files')
        parser.add_option('', '--method', help='Use METHOD to search')
        parser.add_option('', '--exact', action='store_true'
            , help='Perform exact match')
        parser.add_option('', '--hidden', action='store_true'
            , help='Include hidden files')
        parser.add_option('', '--fulltext', action='store_true'
            , help='Perform fulltext search')
        parser.add_option('', '--file-action', metavar='ACTION'
            , dest='file_action', help='File action: "open" or "folder"')
        parser.add_option('', '--debug', action='store_true'
            , help='Show debugging messages.')
        parser.set_defaults(icons_large=0, thumbnails=0, time_iso=0, method='find'
            , limit_results=0, path='~', fileman=default_fileman, exact=0
            , hidden=0, fulltext=0, file_action='open', debug=0, open_wrapper=self.open_wrapper)
        self.options, args = parser.parse_args()
        keywords = ' '.join(args)

        if not self.options.file_action in ('open', 'folder'):
            print 'Error: Invalid value for "file-action".\n'
            print 'Use either "open" to open files by default or'
            print 'use "folder" to open the containing folder.'
            print '(The default is "open".)'
            sys.exit(1)

        if not self.options.fileman:
            print 'Warning: No file manager was found or specified.'

        # Prepare i18n using gettext
        try:
            locale.setlocale(locale.LC_ALL, '')
            locale.bindtextdomain(app_name, 'locale')
            gettext.bindtextdomain(app_name, 'locale')
            gettext.textdomain(app_name)
        except Exception, msg:
            if self.options.debug: print 'Debug:', msg
            print 'Warning: Invalid locale, i18n is disabled.'

        # Guess location of glade file
        glade_file = app_name + '.glade'
        glade_path = os.getcwd()
        if not os.path.exists(os.path.join(glade_path, glade_file)):
            glade_path = os.path.dirname(sys.argv[0])
            if not os.path.exists(os.path.join(glade_path, glade_file)):
                print 'Error: The glade file could not be found.'
                sys.exit()

        # Load interface from glade file and retrieve widgets
        self.load_interface(os.path.join(glade_path, glade_file))

        # Set some initial values
        self.icon_cache = {}
        self.icon_theme = Gtk.IconTheme.get_default()
        self.checkbox_find_exact.set_active(self.options.exact)
        self.checkbox_find_hidden.set_active(self.options.hidden)
        self.checkbox_find_fulltext.set_active(self.options.fulltext)
        if self.options.limit_results:
            self.checkbox_find_limit.set_active(1)
            self.checkbox_find_limit.toggled()
            self.spin_find_limit.set_value(self.options.limit_results)
        self.folder_thumbnails = os.path.expanduser('~/.thumbnails/normal/')
        self.options.path = os.path.abspath(self.options.path)
        if not os.path.isdir(self.options.path):
            self.options.path = os.path.dirname(self.options.path)
        if self.options.path != os.getcwd():
            self.button_find_folder.set_filename(os.path.expanduser(self.options.path))
        else:
            self.button_find_folder.set_current_folder( os.getenv("HOME") )
        self.link_color = None
        # TODO: FIX ME, LINK COLOR
        #try:
        #    self.link_color = GObject.Value()
        #    self.link_color.init(Gdk.Color)
        #    self.treeview_files.style_get_property('link-color', self.link_color)
        #    print self.link_color.get_gtype()
        #except Exception as err:
        #    print err
        #    self.link_color = None
        if self.link_color == None:
            self.link_color = 'blue'

        # Set up keywords completion
        completion = Gtk.EntryCompletion()
        self.entry_find_text.set_completion(completion)
        listmodel = Gtk.ListStore(str)
        completion.set_model(listmodel)
        completion.set_text_column(0)

        # Retrieve available search methods
        methods = ['find', 'locate', 'slocate', 'tracker', 'doodle', 'beagle']
        # DBus allows us to have two more methods
        if 'dbus' in globals():
            for method in ('strigi', 'pinot'):
                methods.append(method)
        bin_dirs = os.environ.get('PATH', '/usr/bin').split(os.pathsep)
        listmodel = Gtk.ListStore(GdkPixbuf.Pixbuf, str)
        method_default = -1
        icon = self.get_icon_pixbuf(Gtk.STOCK_EXECUTE)
        for method_name in methods:
            method_binary = self.get_find_options(method_name)[0]
            for path in bin_dirs:
                if os.path.exists(os.path.join(path, method_binary)):
                    listmodel.append([icon, method_name])
                    if self.options.method == method_name:
                        method_default = len(listmodel) - 1
                    break
        if method_default < 0:
            print 'Warning:', ('Method "%s" is not available.' %
             self.options.method)
            method_default = 0
        
        self.suggestions = suggestions()

        if self.options.icons_large or self.options.thumbnails:
            self.treeview_files.append_column(Gtk.TreeViewColumn(_('Preview'),
                Gtk.CellRendererPixbuf(), pixbuf=0))
            self.treeview_files.append_column(self.new_column(_('Filename'), 1, markup=1))
        else:
            self.treeview_files.append_column(self.new_column(_('Filename'), 1, 'icon', 1))
            self.treeview_files.append_column(self.new_column(_('Size'), 2, 'filesize'))
            self.treeview_files.append_column(self.new_column(_('Location'), 3, 'ellipsize'))
            self.treeview_files.append_column(self.new_column(_('Last modified'), 4, markup=1))

        self.entry_find_text.set_text(keywords)
        
        self.find_in_progress = False
        self.results = []
        
        self.window_search.show_all()

# -- helper functions --
    def get_find_infobar(self):
        """The latest version of glade and GtkBuilder do not support InfoBar
        in the glade file.  This is the code for InfoBar."""
        main_message = _("Did not find what you were looking for?")
        sub_message = _("Try searching with 'find' instead.")
        infobar = Gtk.InfoBar()
        infobar.set_no_show_all(True)
        infobar.set_message_type(Gtk.MessageType.QUESTION)
        icon = Gtk.Image()
        icon.set_from_stock(Gtk.STOCK_DIALOG_QUESTION, Gtk.IconSize.DIALOG)
        label = Gtk.Label("")
        label.set_markup( "<big><b>%s</b></big>\n%s" % (main_message, sub_message) )
        button_box = Gtk.Box()
        button_box.set_orientation(Gtk.Orientation.VERTICAL)
        ok_button = Gtk.Button()
        ok_button.set_use_stock(True)
        ok_button.set_label(Gtk.STOCK_OK)
        cancel_button = Gtk.Button()
        cancel_button.set_use_stock(True)
        cancel_button.set_label(Gtk.STOCK_CANCEL)
        button_box.pack_start(ok_button, False, False, 0)
        button_box.pack_end(cancel_button, False, False, 0)
        content = infobar.get_content_area()
        content.add(icon)
        content.add(label)
        content.pack_end(button_box, False, False, 0)
        
        icon.show()
        label.show()
        button_box.show_all()

        ok_button.connect("clicked", self.on_infobar_ok_clicked)
        cancel_button.connect("clicked", self.on_infobar_cancel_clicked)

        return infobar
        


    def load_interface(self, filename):
        """Load glade file and retrieve widgets."""

        # Load interface from the glade file
        self.builder = Gtk.Builder()
        self.builder.set_translation_domain(app_name)
        self.builder.add_from_file(filename)

        # Retrieve significant widgets
        self.window_search = self.builder.get_object('window_search')
        
        self.button_find_folder = self.builder.get_object('button_find_folder')
        self.entry_find_text = self.builder.get_object('entry_find_text')
        self.box_main_controls = self.builder.get_object('box_main_controls')
        
        # Info bar since it cannot be defined in Glade.
        self.infobar = self.get_find_infobar()
        self.box_main_controls.pack_start(self.infobar, False, False, 0)
        
        # Application Menu
        self.menu_button = self.builder.get_object('menu_button')
        self.application_menu = self.builder.get_object('application_menu')
        self.checkbox_find_exact = self.builder.get_object('checkbox_find_exact')
        self.checkbox_find_hidden = self.builder.get_object('checkbox_find_hidden')
        self.checkbox_find_fulltext = self.builder.get_object('checkbox_find_fulltext')
        self.application_menu.attach_to_widget(self.menu_button, detach_cb)
        
        # Treeview and Right-Click menu
        self.scrolled_files = self.builder.get_object('scrolled_files')
        self.treeview_files = self.builder.get_object('treeview_files')
        self.menu_file = self.builder.get_object('menu_file')
        self.menu_file_open = self.builder.get_object('menu_open')
        self.menu_file_goto = self.builder.get_object('menu_goto')
        self.menu_file_copy = self.builder.get_object('menu_copy')
        self.menu_file_save = self.builder.get_object('menu_save')
        
        self.statusbar = self.builder.get_object('statusbar')
        
        # Sidebar
        self.sidebar = self.builder.get_object('sidebar')
        self.box_type_filter = self.builder.get_object('box_type_filter')
        self.time_filter_any = self.builder.get_object('time_filter_any')
        self.time_filter_week = self.builder.get_object('time_filter_week')
        self.button_time_filter_custom = self.builder.get_object('button_time_filter_custom')
        self.button_type_filter_other = self.builder.get_object('button_type_filter_other')
        
        self.aboutdialog = self.builder.get_object('aboutdialog')

        self.builder.connect_signals(self)

    def compare_dates(self, model, row1, row2, user_data):
        """Compare 2 dates, used for sorting modification dates."""
        sort_column, _ = model.get_sort_column_id()
        if not self.options.time_iso:
            time_format = '%x %X'
        else:
            time_format = '%Y-%m-%d %H:%M'
        value1 = time.strptime(model.get_value(row1, sort_column), time_format)
        value2 = time.strptime(model.get_value(row2, sort_column), time_format)
        if value1 < value2:
            return -1
        elif value1 == value2:
            return 0
        else:
            return 1

    def new_column(self, label, id, special=None, markup=0):
        if special == 'icon':
            column = Gtk.TreeViewColumn(label)
            cell = Gtk.CellRendererPixbuf()
            column.pack_start(cell, True)
            column.add_attribute(cell, 'pixbuf', 0)
            cell = Gtk.CellRendererText()
            column.pack_start(cell, True)
            column.add_attribute(cell, 'markup', id)
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
                column.set_cell_data_func(cell, self.cell_data_func_filesize, id)
        column.set_sort_column_id(id)
        column.set_resizable(True)
        return column

    def cell_data_func_filesize(self, column, cell_renderer, tree_model, tree_iter, id):
        filesize = self.format_size(int(tree_model.get_value(tree_iter, id)))
        cell_renderer.set_property('text', filesize)
        return

    def format_size(self, size):
        """Make a file size human readable."""

        if size > 2 ** 30:
            return '%s GB' % (size / 2 ** 30)
        elif size > 2 ** 20:
            return '%s MB' % (size / 2 ** 20)
        elif size > 2 ** 10:
            return '%s kB' % (size / 2 ** 10)
        elif size > -1:
            return '%s B' % size
        else:
            return ''

    def get_error_dialog(self, msg, parent=None):
        """Display modal error dialog."""

        SaveFile = Gtk.MessageDialog(parent, 0,
            Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, msg)
        response = SaveFile.run()
        SaveFile.destroy()
        return response == Gtk.ResponseType.YES

    def get_yesno_dialog(self, msg, parent=None):
        """Display yes/ no dialog and return a boolean value."""

        SaveFile = Gtk.MessageDialog(parent, 0,
            Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, msg)
        SaveFile.set_default_response(Gtk.ResponseType.NO)
        response = SaveFile.run()
        SaveFile.destroy()
        return response == Gtk.ResponseType.YES

    def get_save_dialog(self, parent=None):
        """Display save dialog and return filename or None."""

        buttons = (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE, Gtk.ResponseType.REJECT)
        SaveFile = Gtk.FileChooserDialog(_('Save list to file'), parent,
            Gtk.FileChooserAction.SAVE, buttons)
        SaveFile.set_default_response(Gtk.ResponseType.REJECT)
        response = SaveFile.run()
        filename = SaveFile.get_filename()
        SaveFile.destroy()
        return [None, filename][response == Gtk.ResponseType.REJECT]

    def treeview_get_selection(self, treeview, event=None):
        """Retrieve the model and path of the selection."""

        model = treeview.get_model()
        if event == None:
            try:
                path = treeview.get_cursor()[0]
                return model, path
            except Exception:
                path = None
        if event <> None:
            # Select the entry at the mouse position
            pathinfo = treeview.get_path_at_pos(int(event.x), int(event.y))
            try:
                path, col, cellx, celly = pathinfo
                treeview.set_cursor(path)
            except Exception:
                path = None
        return model, path

    def get_selected_filename(self, treeview, treeiter=None):
        model, path = self.treeview_get_selection(treeview)
        if path == None:
            return None, None
        if treeiter == None:
            treeiter = model.get_iter(path)
        if model.get_value(treeiter, 3) == None:
            return None, None
        if not self.options.icons_large and not self.options.thumbnails:
            return model.get_value(treeiter, 3), model.get_value(treeiter, 1)
        return model.get_value(treeiter, 4), model.get_value(treeiter, 3)

    def open_file(self, filename):
        """Open the file with its default app or the file manager"""

        try:
            if stat.S_ISDIR(os.stat(filename).st_mode):
                command = [self.options.fileman, filename]
            else:
                command = [self.open_wrapper, filename]
            try:
                subprocess.Popen(command, shell=False)
            except Exception, msg:
                if self.options.debug: print 'Debug:', msg
                self.get_error_dialog(('Error: Could not open the file %s.'
                 % filename), self.window_search)
                print '* The wrapper was %s.' % self.open_wrapper
                print '* The filemanager was %s.' % self.options.fileman
                print 'Hint: Check wether the wrapper and filemanager exist.'
        except Exception, msg:
            if self.options.debug: print 'Debug:', msg
            self.get_error_dialog(('Error: Could not access the file %s.'
             % filename), self.window_search)

    def get_selected_find_method(self):
        model = self.combobox_find_method.get_model()
        treeiter = self.combobox_find_method.get_active_iter()
        try:
            return model.get_value(treeiter, 1)
        except Exception:
            return None

    def get_find_options(self, method, folder='~', limit=-1):
        folder = os.path.expanduser(folder)
        method_name = [method, 'locate'][method=='slocate']
        methods = {
            'find': (method, '', '%s "' + folder + '" -ignore_readdir_race -noleaf',
                '-wholename', '-iwholename', '', 1, 1, 0, 0, 0),
            'locate': (method, '', '%s', '', '-i', '-n %i' % limit,
                1, 0, 1, 0, 0),
            'tracker': ('tracker-search', 'trackerd', '%s', '', '', '-l %i' % limit,
                0, 0, 1, 1, 0),
            'doodle': (method, '', '%s', '', '-i', '',
                0, 0, 0, 0, 1),
            'beagle': ('beagle-query', 'beagled', '%s', '', '', '--max-hits=%i' % limit,
                0, 0, 1, 1, 0),
            'strigi': ('strigidaemon', 'strigidaemon', 'dbus://%s', '', '', '',
                1, 0, 1, 1, 0),
            'pinot': ('pinot', 'pinot-dbus-daemon', 'dbus://%s', '', '', '',
                1, 0, 1, 1, 0)
            }
        try:
            return methods[method_name]
        except Exception:
            return method, '', '%s', '', '', '', 0, 0, 0, 0, 0

    def string_wild_match(self, string, keyword, exact):
        if not exact: keyword = '*' + keyword + '*'
        return fnmatch.fnmatch(string.lower(), keyword.lower())
        
    def map_mimetype(self, mime):
        if mime == 'documents':
            return 'text'
        elif mime == 'images':
            return 'image'
        elif mime == 'music':
            return 'audio'
        elif mime == 'videos':
            return 'video'
        elif mime == 'applications':
            return 'application'

    def file_is_wanted(self, filename, mime_type, modification_date):
        mime_type_is_wanted = True
        modification_date_is_wanted = True
        
        # Mime Type Wanted
        wanted_types = []
        checkboxes = self.box_type_filter.get_children()
        #other = checkboxes[5].get_active()
        for checkbox in checkboxes:
            try:
                if checkbox.get_active():
                    wanted_types.append(self.map_mimetype(checkbox.get_label().lower()))
            except AttributeError: # button
                pass
                # TODO ADD SUPPORT FOR CUSTOM
        if not len(wanted_types):
            mime_type_is_wanted = True
        else:
            try:
                file_type = mime_type[0]
                mime_type_is_wanted = file_type in wanted_types
            except Exception:
                mime_type_is_wanted = True
            
        # Modification Date Wanted
        if self.time_filter_any.get_active():
            return mime_type_is_wanted
        else:
            if not self.options.time_iso:
                time_format = '%x %X'
            else:
                time_format = '%Y-%m-%d %H:%M'
            filetime = datetime.datetime.strptime(modification_date, time_format)
            if self.time_filter_week.get_active():
                weektime = datetime.datetime.today() - datetime.timedelta(days=7)
                modification_date_is_wanted = weektime < filetime
        if mime_type_is_wanted and modification_date_is_wanted:
            return True
        else:
            return False
        

    def get_mime_type(self, filename):
        try:
            mime = xdg.Mime.get_type(filename)
            return mime.media, mime.subtype
        except Exception:
            return None, None
            
    def load_mimetypes(self):
        mimetypes.init()
        mimes = mimetypes.types_maps.values()
        mimes.sort()

    def file_is_hidden(self, filename, current=None):
        """Determine if a file is hidden or in a hidden folder"""

        if filename == '': return False
        path, name = os.path.split(filename)
        if len(name) and name[0] == '.':
            return True
        if current <> None:
            if '.' in current:
                return False
        for folder in path.split(os.path.sep):
            if len(folder):
                if folder[0] == '.':
                    return True
        return False

    def find(self, widget=None, method='locate'):
        """Do the actual search."""
        self.infobar.hide()
        self.find_in_progress = True
        self.results = []
        self.window_search.get_window().set_cursor(Gdk.Cursor(Gdk.CursorType.WATCH))
        self.window_search.set_title(_('Searching for "%s"') % self.entry_find_text.get_text())
        self.statusbar.push(self.statusbar.get_context_id('results'), _('Searching...'))
        while Gtk.events_pending(): Gtk.main_iteration()

        # Reset treeview
        listmodel = Gtk.ListStore(GdkPixbuf.Pixbuf, str, long, str, str)
        self.treeview_files.set_model(listmodel)
        self.treeview_files.columns_autosize()

        # Retrieve search parameters
        keywords = self.entry_find_text.get_text()
        folder = self.button_find_folder.get_filename()
        exact = self.checkbox_find_exact.get_active()
        hidden = self.checkbox_find_hidden.get_active()
        fulltext = self.checkbox_find_fulltext.get_active()
        limit = -1

        if keywords != '':
            # Generate search command
            options = self.get_find_options(method, folder, limit)
            (a, daemon, default, a, a, a, wildcards, file_manual, path_manual
                , exact_manual, errors_ignore) = options

            # Set display options
            if not self.options.icons_large and not self.options.thumbnails:
                icon_size = Gtk.IconSize.SMALL_TOOLBAR
            else:
                icon_size = Gtk.IconSize.DIALOG
            if not self.options.time_iso:
                time_format = '%x %X'
            else:
                time_format = '%Y-%m-%d %H:%M'

            # Run search command and capture the results
            messages = []
            if ('*' in keywords or '?' in keywords) and not wildcards:
                status_icon = Gtk.STOCK_CANCEL
                messages.append([_('The search backend doesn\'t support wildcards.'), None])
                status = _('No files found for "%s".') % keywords
            else:
                try:
                    if default[:7] == 'dbus://':
                        query = dbus_query(options)
                    else:
                        query = shell_query(options)
                except Exception, msg:
                    if self.options.debug: print 'Debug:', msg
                    query = generic_query()
                for filename in query.run(keywords, folder, exact, hidden, limit):
                    if self.abort_find or len(listmodel) == limit: break
                    filename = filename.split(os.linesep)[0]
                    # Convert uris to filenames
                    if filename[:7] == 'file://':
                        filename = filename[7:]
                    # Handle mailbox uris like filenames as well
                    if filename[:10] == 'mailbox://':
                        filename = filename[10:]
                        filename = filename[:filename.index('?')]
                    path, name = os.path.split(filename)
                    if (path_manual or exact_manual) and not fulltext:
                        if not self.string_wild_match(name, keywords, exact):
                            yield True
                            continue
                    if path_manual and not folder in path:
                        yield True
                        continue
                    if not hidden and self.file_is_hidden(filename, folder):
                        yield True
                        continue
                    mime_type = self.get_mime_type(os.path.join(path, filename))
                    #if not self.file_is_wanted(filename, mime_type):
                    #    yield True
                    #    continue
                    if self.options.thumbnails:
                        icon = self.get_thumbnail(filename, icon_size, mime_type)
                    else:
                        icon = self.get_file_icon(filename, icon_size, mime_type)
                    try:
                        filestat = os.stat(filename)
                        size = filestat.st_size
                        modified = time.strftime(time_format, time.gmtime(filestat.st_mtime))
                        name = name.replace('&', '&amp;')
                        if not self.options.icons_large and not self.options.thumbnails:
                            if self.file_is_wanted(filename, mime_type, modified):
                                listmodel.append([icon, name, size, path, modified])
                            self.results.append([mime_type, icon, name, size, path, modified])
                        else:
                            path = path.replace('&', '&amp;')
                            if modified <> '':
                                modified = os.linesep + modified
                            if self.file_is_wanted(filename, mime_type, modified):
                                listmodel.append([icon, '%s %s%s%s%s' % (name
                                , self.format_size(size), os.linesep, path
                                , modified), -1, name, path])
                            self.results.append([mime_type, icon, '%s %s%s%s%s' % (name
                            , self.format_size(size), os.linesep, path
                            , modified), -1, name, path])
                    except Exception, msg:
                        if self.options.debug: print 'Debug:', msg
                        pass # Ignore inaccessible files
                    self.treeview_files.set_model(listmodel)
                    yield True
                if len(listmodel) == 0:
                    if errors_ignore and query.status():
                        status_icon = Gtk.STOCK_CANCEL
                        messages.append([_('Fatal error, search was aborted.'), None])
                        if daemon <> '':
                            link_format = '<u><span foreground="%s">%s</span></u>'
                            messages.append([link_format % (self.link_color,
                                _('Click here to start the search daemon.')),
                                '<span size="0">daemon:' + daemon + '</span>'])
                    else:
                        status_icon = Gtk.STOCK_INFO
                        messages.append([_('No files were found.'), None])
                    status = _('No files found for "%s".') % keywords
                else:
                    status = _('%s files found for "%s".') % (len(listmodel), keywords)
            for message, action in messages:
                icon = [None, self.get_icon_pixbuf(status_icon)][message == messages[0][0]]
                listmodel.append([icon, message, None, None, action])
            self.statusbar.push(self.statusbar.get_context_id('results'), status)
        self.treeview_files.set_model(listmodel)
        listmodel.set_sort_func(4, self.compare_dates, None)

        self.window_search.get_window().set_cursor(None)
        self.window_search.set_title( _('Search results for \"%s\"') % keywords )
        self.keywords = keywords
        self.find_in_progress = False
        self.entry_find_text.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, Gtk.STOCK_FIND)
        if method != 'find':
            self.infobar.show()
        yield False

    def get_icon_pixbuf(self, name, icon_size=Gtk.IconSize.MENU):
        try:
            return self.icon_cache[name]
        except KeyError:
            icon_size = Gtk.icon_size_lookup(icon_size)[1]
            icon = self.icon_theme.load_icon(name, icon_size, 0)
            self.icon_cache[name] = icon
            return icon

    def get_thumbnail(self, path, icon_size=0, mime_type=None):
        """Try to fetch a small thumbnail."""

        md5_hash = md5.new('file://' + path).hexdigest()
        filename = '%s%s.png' % (self.folder_thumbnails, md5_hash)
        try:
            return GdkPixbuf.Pixbuf.new_from_file(filename)
        except Exception:
            return self.get_file_icon(path, icon_size, mime_type)

    def get_file_icon(self, path, icon_size=0, mime_type=None):
        """Retrieve the file icon."""

        try:
            is_folder = stat.S_ISDIR(os.stat(path).st_mode)
        except Exception:
            is_folder = 0
        if is_folder:
            icon_name = Gtk.STOCK_DIRECTORY
        else:
            if mime_type <> None:
                try:
                    # Get icon from mimetype
                    media, subtype = mime_type
                    icon_name = 'gnome-mime-%s-%s' % (media, subtype)
                    return self.get_icon_pixbuf(icon_name, icon_size)
                except Exception:
                    try:
                        # Then try generic icon
                        icon_name = 'gnome-mime-%s' % media
                        return self.get_icon_pixbuf(icon_name, icon_size)
                    except Exception:
                        # Use default icon
                        icon_name = Gtk.STOCK_FILE
            else:
                icon_name = Gtk.STOCK_FILE
        return self.get_icon_pixbuf(icon_name, icon_size)

# -- events --

    def on_window_search_destroy(self, widget):
        Gtk.main_quit()

    def on_button_close_clicked(self, widget):
        self.window_search.destroy()

    def on_button_find_clicked(self, widget):
        """Initiate the search thread."""

        self.scrolled_files.set_visible(True)
        self.window_search.set_size_request(640, 400)
        # Add search term to the completion list
        keywords = self.entry_find_text.get_text()
        completion = self.entry_find_text.get_completion()
        listmodel = completion.get_model()
        listmodel.append([keywords])

        if not self.find_in_progress:
            self.entry_find_text.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, Gtk.STOCK_CANCEL)
            self.abort_find = 0
            task = self.find()
            GObject.idle_add(task.next)
        else:
            self.entry_find_text.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, Gtk.STOCK_FIND)
            self.abort_find = 1

    def on_treeview_files_row_activated(self, widget, path, column):
        try:
            if self.options.file_action == 'open':
                self.on_menu_open_activate(None)
            else:
                self.on_menu_goto_activate(None)
        except AttributeError:
            pass

    def on_treeview_files_button_pressed(self, treeview, event):
        """Show a popup menu for files or handle clicked links."""

        pri, sec = self.get_selected_filename(treeview)
        if event.button == 1:
            if pri == None:
                return
            model, path = self.treeview_get_selection(treeview, event)
            if path == None:
                return
            action = model.get_value(model.get_iter(path), 4)
            if sec == None and action <> None:
                try:
                    action = re.sub('<[^>]+>', '', action)
                    action_name, action_value = action.split(':')
                    subprocess.Popen([action_value])
                    icon, message = Gtk.STOCK_INFO, _('The search daemon was started.')
                except Exception, msg:
                    if self.options.debug: print 'Debug:', msg
                    icon, message = (Gtk.STOCK_CANCEL
                     , _('The search daemon could not be started.'))
                    print 'Error: %s could not be run.' % action_value
                listmodel = Gtk.ListStore(GdkPixbuf.Pixbuf, str, long, str, str, long)
                listmodel.append([self.get_icon_pixbuf(icon), message, -1, None, None, -1])
                self.treeview_files.set_model(listmodel)
        elif event.button == 2:
            if pri <> None:
                self.open_file(pri)
        elif event.button == 3:
            if sec <> None:
                self.menu_file.popup(None, None, None, None, event.button, event.time)

    def on_treeview_files_popup(self, treeview):
        pri, sec = self.get_selected_filename(treeview)
        if sec <> None:
            self.menu_file.popup(None, None, None, 3, Gtk.get_current_event_time())

    def on_menu_open_activate(self, menu):
        folder, filename = self.get_selected_filename(self.treeview_files)
        self.open_file(os.path.join(folder, filename))

    def on_menu_goto_activate(self, menu):
        folder, filename = self.get_selected_filename(self.treeview_files)
        self.open_file(folder)

    def on_menu_copy_activate(self, menu):
        folder, filename = self.get_selected_filename(self.treeview_files)
        clipboard = Gtk.clipboard_get('CLIPBOARD')
        clipboard.set_text(os.path.join(folder, filename), -1)

    def on_menu_save_activate(self, menu):
        """Show a save dialog and possibly write the results to a file."""

        filename = self.get_save_dialog(self.window_search)
        if os.path.exists(filename):
            if not self.get_yesno_dialog(('The file %s already exists. Do you '
             + 'want to overwrite it?') % filename, self.window_search):
                filename = None
        if filename <> None:
            try:
                save = open(filename, 'w')
                listmodel = self.treeview_files.get_model()
                for item in range(len(listmodel)):
                    treeiter = listmodel.iter_nth_child(None, item)
                    name, path = self.get_selected_filename(self.treeview_files, treeiter)
                    save.write(os.path.join(name, path) + os.linesep)
                save.close()
            except Exception, msg:
                if self.options.debug: print 'Debug:', msg
                self.get_error_dialog('The file %s could not be saved.'
                 % filename, self.window_search)
                 
    def on_entry_find_text_changed(self, widget):
        query = widget.get_text()
        results = self.suggestions.run(query, self.button_find_folder.get_filename())
        
        completion = self.entry_find_text.get_completion()
        listmodel = completion.get_model()
        listmodel.clear()
        try:
            for keyword in results:
                listmodel.append([keyword])
        except TypeError:
            pass
            
    def on_entry_find_text_activate(self, widget, event=None, data=None):
        self.on_button_find_clicked(widget)
        
    def on_menu_button_clicked(self, widget):
        self.application_menu.popup(None, None, menu_position, self.application_menu, 3, Gtk.get_current_event_time())
        
    def on_checkbox_advanced_toggled(self, widget):
        self.sidebar.set_visible(widget.get_active())
        
    def on_time_filter_custom_toggled(self, widget):
        self.button_time_filter_custom.set_sensitive(widget.get_active())
        
    def on_type_filter_other_toggled(self, widget):
        self.button_type_filter_other.set_sensitive(widget.get_active())
        
    def on_menu_about_activate(self, widget):
        self.aboutdialog.show()
        
    def on_aboutdialog_response(self, widget, event):
        self.aboutdialog.hide()
        
    def on_infobar_ok_clicked(self, widget):
        self.infobar.hide()
        keywords = self.entry_find_text.get_text()
        completion = self.entry_find_text.get_completion()
        listmodel = completion.get_model()
        listmodel.append([keywords])

        if not self.find_in_progress:
            self.entry_find_text.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, Gtk.STOCK_CANCEL)
            self.abort_find = 0
            task = self.find(method='find')
            GObject.idle_add(task.next)
        else:
            self.entry_find_text.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, Gtk.STOCK_FIND)
            self.abort_find = 1
        
    def on_infobar_cancel_clicked(self, widget):
        self.infobar.hide()
        
    def on_filter_changed(self, widget):
        if self.scrolled_files.get_visible():
            self.find_in_progress = True
            messages = []
            listmodel = Gtk.ListStore(GdkPixbuf.Pixbuf, str, long, str, str)
            self.treeview_files.set_model(listmodel)
            self.treeview_files.columns_autosize()
            for filegroup in self.results:
                mime_type = filegroup[0]
                filename = filegroup[2]
                try:
                    modified = filegroup[7]
                except IndexError:
                    modified = filegroup[5]
                if not self.options.icons_large and not self.options.thumbnails:
                    if self.file_is_wanted(filename, mime_type, modified):
                        listmodel.append(filegroup[1:])
                else:
                    if modified <> '':
                        modified = os.linesep + modified
                    if self.file_is_wanted(filename, mime_type, modified):
                        listmodel.append(filegroup[1:])
            if len(listmodel) == 0:
                status_icon = Gtk.STOCK_INFO
                messages.append([_('No files were found.'), None])
                status = _('No files found for "%s".') % self.keywords
            else:
                status = _('%s files found for "%s".') % (len(listmodel), self.keywords)
            for message, action in messages:
                icon = [None, self.get_icon_pixbuf(status_icon)][message == messages[0][0]]
                listmodel.append([icon, message, None, None, action])
            self.statusbar.push(self.statusbar.get_context_id('results'), status)
            self.treeview_files.set_model(listmodel)
            listmodel.set_sort_func(4, self.compare_dates, None)

            self.window_search.get_window().set_cursor(None)
            self.window_search.set_title( _('Search results for \"%s\"') % self.keywords )
            self.find_in_progress = False

catfish()
Gtk.main()
