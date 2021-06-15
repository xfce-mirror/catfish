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

# pylint: disable=C0413
# pylint: disable=C0114
# pylint: disable=C0116

import logging

import io
import os
import re
import signal
import subprocess
import time
from itertools import permutations
from json import dumps, loads

import mimetypes
import zipfile

import gi
gi.require_version('GLib', '2.0')  # noqa
from gi.repository import GLib

try:
    gi.require_version('Zeitgeist', '2.0')
    from gi.repository import Zeitgeist
    log_trial = Zeitgeist.Log.get_default()
    if log_trial.datapath() is None:
        ZEITGEIST_SUPPORT = False
    else:
        ZEITGEIST_SUPPORT = True
except ImportError:
    ZEITGEIST_SUPPORT = False
except ValueError:
    ZEITGEIST_SUPPORT = False

LOGGER = logging.getLogger('catfish_search')
ENGINE_COUNT = 0

FNULL = open(os.devnull, 'w')
if subprocess.call(['which', 'locate'],  # pylint: disable=R1703
                   stdout=FNULL, stderr=subprocess.STDOUT) == 0:
    LOCATE_SUPPORT = True
else:
    LOCATE_SUPPORT = False
FNULL.close()


def get_keyword_list(keywords):
    keywords = keywords.replace(",", " ").strip().lower()
    kwords = []
    matches = re.findall(r'\"(.+?)\"', keywords)
    for match in matches:
        newmatch = match.replace(" ", "\0")
        newmatch = newmatch.replace("\"", "")
        keywords = keywords.replace("\"%s\"" % match, newmatch)
    for keyword in keywords.split(" "):
        kwords.append(keyword.replace("\0", " "))
    return kwords


def string_regex(keywords, path):  # pylint: disable=W0613
    """Returns a string with the regular expression containing all combinations
    of the keywords."""
    if len(keywords) == 0:
        return ''
    if len(keywords) == 1:
        return keywords[0]
    regex = ""

    count = 0
    for p in permutations(keywords):
        if count != 0:
            regex += "|"
        for i in range(len(p)):
            if i == 0:
                string = p[i]
            else:
                string += "(.)*" + p[i]
        regex += string
        count += 1

    return regex


class CatfishSearchEngine:

    """CatfishSearchEngine is the collection of search backends that are used
    to perform a query.  Each backend is a CatfishSearchMethod"""

    def __init__(self, methods=['zeitgeist', 'locate', 'walk'],
                 exclude_paths=[]):
        """Initialize the CatfishSearchEngine.  Provide a list of methods to
        be included in the search backends.  Available backends include:

         fulltext         'os.walk' and 'file.readline' to search inside files.
         ripgrep          Ripgrep for faster fulltext search
         locate           System 'locate' to search for files.
         walk             'os.walk' to search for files (like find).
         zeitgeist        Zeitgeist indexing service to search for files.
        """
        self.stop_time = 0
        self.keywords = ""

        global ENGINE_COUNT
        ENGINE_COUNT += 1
        self.engine_id = ENGINE_COUNT
        LOGGER.debug(
            "[%i] engine initializing with methods: %s",
            self.engine_id, str(methods))
        self.methods = []
        if 'zeitgeist' in methods:
            if ZEITGEIST_SUPPORT:
                self.add_method(CatfishSearchMethod_Zeitgeist)
        if 'locate' in methods:
            if LOCATE_SUPPORT:
                self.add_method(CatfishSearchMethod_Locate)
        if 'fulltext' in methods:
            self.add_method(CatfishSearchMethod_Fulltext)
        if 'ripgrep' in methods:
            self.add_method(CatfishSearchMethod_Ripgrep)
        if 'walk' in methods:
            self.add_method(CatfishSearchMethod_Walk)
        self.exclude_paths = exclude_paths
        initialized = []
        for method in self.methods:
            initialized.append(method.method_name)
        LOGGER.debug(
            "[%i] engine initialized with methods: %s",
            self.engine_id, str(initialized))
        self.start_time = 0.0

    def __del__(self):
        LOGGER.debug("[%i] engine destroyed", self.engine_id)

    def add_method(self, method_class):
        """Add a CatfishSearchMethod the the engine's search backends."""
        self.methods.append(method_class())

    def run(self, keywords, path, search_zips, limit=-1, regex=False):  # noqa
        """Run the CatfishSearchEngine.

        Each method is run sequentially in the order they are added.

        This function is a generator.  With each filename reviewed, the
        filename is yielded if it matches the query.  False is also yielded
        afterwards to guarantee the interface does not lock up."""
        self.start_time = time.time()
        self.stop_time = 0

        keywords = get_keyword_list(keywords)
        self.keywords = " ".join(keywords)

        LOGGER.debug("[%i] path: %s, keywords: %s, limit: %i, regex: %s",
                     self.engine_id, str(path), str(keywords), limit,
                     str(regex))

        wildcard_chunks = []
        keys = []
        for key in keywords:
            if '*' in key:
                wildcard_chunks.append(key.split('*'))
            else:
                keys.append(key)

        # path may be empty when some "extension" scheme is used in URL
        if not path:
            self.stop()
            return

        # For simplicity, make sure the path contains a trailing '/'
        if not path.endswith('/'):
            path += '/'

        # Path exclusions for efficiency
        exclude = []
        maybe_exclude = self.exclude_paths
        for maybe_path in maybe_exclude:
            if not path.startswith(maybe_path):
                exclude.append(maybe_path)

        file_count = 0
        for method in self.methods:
            if self.stop_time > 0:
                LOGGER.debug("Engine is stopped")
                return
            LOGGER.debug(
                "[%i] Starting search method: %s",
                self.engine_id, method.method_name)
            for filename in method.run(keywords, path, search_zips, regex,
                                       self.exclude_paths):
                if isinstance(filename, str) and path in filename:
                    found_bad = False
                    for filepath in exclude:
                        if filename.startswith(filepath):
                            if self.stop_time > 0:
                                LOGGER.debug("Engine is stopped")
                                return
                            found_bad = True
                    if found_bad:
                        yield True
                        continue

                    if search_zips and method.method_name == 'walk':
                        if os.path.isfile(filename) and \
                                zipfile.is_zipfile(filename):
                            yield filename
                            continue

                    if method.method_name == 'fulltext' or \
                            method.method_name == 'ripgrep' or \
                            all(key in
                                os.path.basename(filename).lower()
                                for key in keys):

                        # Remove the URI portion of the filename if present.
                        if filename.startswith('file://'):
                            filename = filename[7:]
                        if filename.startswith('mailbox://'):
                            filename = filename[10:]
                            filename = filename[:filename.index('?')]

                        # Remove whitespace from the filename.
                        filename = filename.strip()

                        if len(wildcard_chunks) == 0 or \
                                method.method_name == 'fulltext' or \
                                method.method_name == 'ripgrep':
                            yield filename
                            file_count += 1
                        else:
                            try:
                                file_pass = True
                                for chunk in wildcard_chunks:
                                    last_index = -1

                                    for portion in chunk:
                                        lower = filename.lower()
                                        str_index = lower.index(
                                            portion.lower())
                                        if last_index < str_index:
                                            last_index = str_index
                                        elif portion == '':
                                            pass
                                        else:
                                            file_pass = False
                                            break
                                if file_pass:
                                    yield filename
                                    file_count += 1
                            except ValueError:
                                pass

                    # Stop running if we've reached the optional limit.
                    if file_count == limit:
                        self.stop()
                        return
                yield False
        self.stop()

    def search_zip(self, fullpath, keywords, search_exact):
        keyword_list = get_keyword_list(keywords)
        with zipfile.ZipFile(fullpath, 'r') as z:
            for member in z.infolist():
                for method in self.methods:
                    if method.method_name == 'walk':
                        if self.search_filenames(
                                member.filename, keywords, search_exact):
                            yield (member.filename, member.file_size, member.date_time)
                    if method.method_name == 'fulltext':
                        if method.search_zip(z, member, keyword_list):
                            yield (member.filename, member.file_size, member.date_time)

    def search_filenames(self, filename, keywords, search_exact):
        keywords = get_keyword_list(keywords)
        fname = os.path.basename(filename.rstrip("/"))
        if search_exact:
            if " ".join(keywords) in fname.lower():
                return True
        else:
            fname = fname.lower()
            for kword in set(keywords):
                if kword not in fname:
                    return False
            return True

    def set_exact(self, exact):
        """Set method for exact"""
        # Only for fulltext engine
        for method in self.methods:
            method.exact = exact

    def stop(self):
        """Stop all running methods."""
        for method in self.methods:
            method.stop()
        self.stop_time = time.time()
        clock = self.stop_time - self.start_time
        LOGGER.debug("[%i] Last query: %f seconds", self.engine_id, clock)


class CatfishSearchMethod:

    """The base CatfishSearchMethod class, to be inherited by defined
    methods."""

    def __init__(self, method_name):
        """Base CatfishSearchMethod Initializer."""
        self.method_name = method_name

    def run(self, keywords, path, search_zips, regex=False, exclude_paths=[]):  # pylint: disable=W0613
        """Base CatfishSearchMethod run method."""
        return NotImplemented

    def search_zip(self, z, member, keywords):
        """Base CatfishSearchMethod search_zip method."""
        return False

    def stop(self):
        """Base CatfishSearchMethod stop method."""
        return NotImplemented

    def is_running(self):
        """Base CatfishSearchMethod is_running method."""
        return False


class CatfishSearchMethod_Walk(CatfishSearchMethod):

    """Search Method utilizing python 'os.walk'.  This is used as a replacement
    for the 'find' search method, which is difficult to interrupt and is slower
    than os.walk."""

    def __init__(self):
        """Initialize the 'walk' Search Method."""
        super().__init__("walk")
        self.running = False

    def get_dir_list(self, root, dirs, xdg_list,
                     exclude_list, processed_links):
        dirs = sorted(dirs, key=lambda s: s.lower())

        # Prioritize: XDG, Visible (Linked), Dotfile (Linked)
        xdgdirs = []
        dotdirs = []
        dotlinks = []
        notdotdirs = []
        notdotlinks = []

        realroot = os.path.realpath(root)

        for path in dirs:
            path = os.path.join(root, path)
            # Remove trailing slashes to ensure that calling os.path.basename()
            # will not cut the path to an empty string
            path = os.path.normpath(path)
            if path in exclude_list:
                continue
            if path in xdg_list:
                xdgdirs.append(path)
                continue
            islink = os.path.islink(path)
            if islink:
                realpath = os.path.realpath(path)
                if realpath in processed_links:
                    continue
                # Respect the user's settings
                if realpath in exclude_list:
                    continue
                # Sandbox search results to the starting path, don't allow:
                # Start: /home/username/
                # Link: ~/.wine/dosdevices/z:/ -> /
                if realroot.startswith(realpath):
                    continue
            if os.path.basename(path).startswith("."):
                if islink:
                    dotlinks.append(path)
                else:
                    dotdirs.append(path)
            else:
                if islink:
                    notdotlinks.append(path)
                else:
                    notdotdirs.append(path)

        dirlist = xdgdirs + notdotdirs + notdotlinks + dotdirs + dotlinks
        return dirlist

    def run(self, keywords, path, search_zips, regex=False, exclude_paths=[]):
        """Run the search method using keywords and path.  regex is not used
        by this search method.

        This function is a generator and will yield files as they are found or
        True if still running."""
        exclude = []
        maybe_exclude = exclude_paths
        for maybe_path in maybe_exclude:
            if not path.startswith(maybe_path):
                exclude.append(maybe_path)

        self.running = True
        if isinstance(keywords, str):
            keywords = keywords.replace(',', ' ').strip().split()

        # Enable symbolic link directories, but process once
        processed_links = []

        # Grab the special directory list to get them precedence
        xdgdirlist = [
            GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP),
            GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS),
            GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD),
            GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_MUSIC),
            GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES),
            GLib.get_user_special_dir(
                GLib.UserDirectory.DIRECTORY_PUBLIC_SHARE),
            GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_TEMPLATES),
            GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS),
        ]

        for root, dirs, files in os.walk(top=path, topdown=True,
                                         onerror=None,
                                         followlinks=True):
            # Bail once the search has been canceled
            if not self.running:
                break

            # Check if we've already processed symbolic paths
            if os.path.islink(root):
                realpath = os.path.realpath(root)
                if realpath in processed_links:
                    yield True
                    continue
                processed_links.append(realpath)

            # Prioritize and drop excluded paths
            dirs[:] = self.get_dir_list(
                root, dirs, xdgdirlist, exclude, processed_links)

            paths = sorted(dirs + files)

            # Check paths in the second and deeper levels of the selected
            # directory
            for path in paths:
                fullpath = os.path.join(root, path)
                if self.search_path(path, keywords):
                    yield fullpath
                if search_zips and \
                   os.path.isfile(fullpath) and zipfile.is_zipfile(fullpath):
                    yield fullpath
            yield True
        yield False

    def search_path(self, path, keywords):
        if any(keyword in path.lower() for keyword in keywords):
            return True

    def search_zip(self, z, member, keywords):
        if member.is_dir():
            return self.search_path(member.filename, keywords)
        return self.search_path(os.path.basename(member.filename), keywords)

    def stop(self):
        """Stop the running search method."""
        self.running = False

    def is_running(self):
        """Poll the search method to see if it still running."""
        return self.running


class CatfishSearchMethod_Ripgrep(CatfishSearchMethod):

    """Search Method utilizing python ripgrepy interface of ripgrep."""
    """Needs exact vs all word search"""

    def __init__(self):
        """Initialize the 'ripgrep' Search Method."""
        CatfishSearchMethod.__init__(self, "ripgrep")
        self.running = False
        self.hidden = False
        self.exact = False  
        self.cancel_search = False
        self.processes = []

    def run(self, keywords, path, search_zips, regex=False, exclude_paths=[]):
        """Run the search method using keywords and path."""

        self.running = True

        paths = []

        args = []
        args.append('rg')
        # Return in json format
        args.append('--json')
        # Include hidden files
        if not self.hidden:
            args.append('--hidden')
        # Include zip files
        if search_zips:
            args.append('--search-zip')
        # Do not obey gitignore and other files
        args.append('--no-ignore')
        # Return the filename in the results
        args.append('--with-filename')
        # Stop searching the file at one match
        args.append('--max-count')
        args.append('1')

        # If exact query, concatenate all keywords, else, ignore case
        if self.exact:
            joined_keyword = '"{}"'.format(' '.join(keywords))
            keywords = [joined_keyword]
        # If not exact query remove keyword duplicates and sort
        else:
            args.append('--ignore-case')

            keywords = list(dict.from_keys(keywords))

            # Sort keywords by length
            # longest keywords first improves speed of ripgrep multi-word search
            keywords = sorted(keywords, key=len, reverse=True)

        # Create new variable for the first keyword query
        first_keyword_args = args.copy()

        # Add the query to the args list
        first_keyword_args.append(keywords[0])
        # Add the path to the args list
        first_keyword_args.append(path)
        first_keyword_results = self.rg_search(first_keyword_args)

        # If there is only one keyword, return results
        if len(keywords) == 1:
            for result in first_keyword_results:
                yield result

        # For more than one search term, run ripgrep on the longest term,
        # and then scan each resulting file for other matches.
        else:
            for possible_file in first_keyword_results:
                found_match = True

                for keyword in keywords[1:]:
                    if found_match == False:
                        break
                    else:
                        found_match = False
                        # Compile the args list for this keyword and this possible match file
                        new_keyword_args = args.copy()
                        new_keyword_args.append(keyword)
                        new_keyword_args.append(possible_file)
                        matches = self.rg_search(new_keyword_args)
                        new_keyword_args = []
                        for match in matches:
                            if isinstance(match, str):
                                found_match = True
                if found_match:
                    yield possible_file
                else:
                    yield True

        self.running = False

    def rg_search(self, args_list):
        """Runs the search, yielding paths as they are found."""
        # Put path in quotes in case of whitespaces
        args_list[-1] = '"{}"'.format(args_list[-1])
        # Compile the args into a string to excecute
        command = ' '.join(args_list)

        process = subprocess.Popen(command, stdout = subprocess.PIPE, shell = True)
        self.processes.append(process)

        while not self.cancel_search:

            subprocess_still_running = (process.poll() == None)

            # Read the next line from the output
            line = process.stdout.readline()

            if line:
                # Try to convert from json to dict
                try:
                    json_value = line.strip().decode()
                    data = loads(json_value)
                    if data['type'] == 'match':
                        full_path = data['data']['path']['text']
                        yield full_path
                except ValueError as err:
                    pass
                    #print('Json Decode Error: {} on line "{}"'.format(err, line))

            elif subprocess_still_running:
                yield True
            else:
                # If the line is empty and the process is not running,
                # remove the process from the list of currently running processes and break out
                self.processes.remove(process)
                break

    def stop(self):
        """Stop the running search method."""
        self.cancel_search = True
        for process in self.processes:
            process.kill()

    def is_running(self):
        """Poll the search method to see if it still running."""
        return self.running

class CatfishSearchMethod_Fulltext(CatfishSearchMethod):

    """Search Method utilizing python 'os.walk' and 'file.readline'.  This is
    used as a replacement for the 'find' search method, which is difficult to
    interrupt and is slower than os.walk."""

    def __init__(self):
        """Initialize the 'fulltext' search method."""
        super().__init__("fulltext")
        self.force_stop = False
        self.running = False
        self.exact = False

    def check_charset(self, root, filename):
        """Checks file for BOM to detect UTF encodings.
        Also checks file for null byte. Most files containing
        a null byte will be binary. UTF-16 and UTF-32 without
        BOM can contain null bytes, support for that can be
        added by checking the line ending."""
        file = open(os.path.join(root, filename), 'rb')
        try:
            data = file.read(64).lower()

            if data.startswith(b'\x00\x00\xfe\xff'):
                return 'utf-32-be'

            elif data.startswith(b'\xff\xfe\x00\x00'):
                return 'utf-32-le'

            elif data.startswith(b'\x2b\x2f\x76'):
                return 'utf-7'

            elif data.startswith(b'\xfe\xff'):
                return 'utf-16-be'

            elif data.startswith(b'\xff\xfe'):
                return 'utf-16-le'

            elif b'\0' in data:
                return 'binary'

            else:
                return 'utf-8'

        finally:
            file.close()

    def is_txt(self, filename):
        """Checks if text mimetype."""
        mime = str(mimetypes.guess_type(filename)[0])
        text_list = ('ardour', 'audacity', 'desktop', 'document',
                     'fontforge', 'java', 'json', 'm4', 'mbox',
                     'message', 'mimearchive', 'msg', 'none', 'perl',
                     'pgp-keys', 'php', 'postscript', 'rtf',
                     'ruby', 'shellscript', 'spreadsheet', 'sql',
                     'subrip', 'text', 'troff', 'url', 'winhlp',
                     'x-bittorent', 'x-cue', 'x-extension-cfg',
                     'x-glade', 'x-mpegurl', 'x-sami', 'x-theme',
                     'x-trash', 'xml', 'xpixmap', 'yaml')
        for filetype in text_list:
            if filetype in mime.lower():
                return True

    def search_pdf(self, fullpath, keywords):
        command = ['pdftotext', '-q', '-nopgbrk', fullpath, '-']
        with subprocess.Popen(command, stdout=subprocess.PIPE, text=True) as pdf:
            if self.search_text(pdf.stdout, keywords):
                return True

    def search_text(self, lines, keywords):
        if self.exact:
            for line in lines:
                if " ".join(keywords) in line.lower():
                    return True
        else:
            keywords = list(set(keywords))
            match_found = [False for i in range(len(keywords))]
            match_found_count = 0
            for line in lines:
                for i in range(len(keywords)):
                    if (not match_found[i]) and keywords[i] in line.lower():
                        match_found[i] = True
                        match_found_count += 1
                if match_found_count == len(keywords):
                    return True

    def search_zip(self, z, member, keywords):
        with z.open(member) as f:
            lines = io.TextIOWrapper(f, encoding='utf-8')
            try:
                if self.search_text(lines, keywords):
                    return True
            except UnicodeError:
                return False

    def run(self, keywords, path, search_zips, regex=False, exclude_paths=[]):  # noqa
        """Run the search method using keywords and path.  regex is not used
        by this search method.

        This function is a generator and will yield files as they are found or
        True if still running."""
        self.running = True

        find_keywords_backup = []
        if not self.exact:
            # Split the keywords into a list if they are not already.
            if isinstance(keywords, str):
                keywords = keywords.replace(',', ' ').strip().split()

            for keyword in keywords:
                if keyword not in find_keywords_backup:
                    find_keywords_backup.append(keyword)

        # Start walking the folder structure.
        for root, dirs, files in os.walk(path):  # pylint: disable=W0612
            if self.force_stop:
                break
            # Don't search user excluded directories.
            if root.startswith(tuple(exclude_paths)):
                dirs[:] = []
                continue

            for filename in files:
                try:
                    fullpath = os.path.join(root, filename)

                    # Skip if special file.
                    if not os.path.isfile(fullpath):
                        continue
                    if os.path.getsize(fullpath) == 0:
                        continue
                    if fullpath.lower().endswith('.pdf'):
                        if self.search_pdf(fullpath, keywords):
                            yield fullpath
                    if zipfile.is_zipfile(fullpath):
                        yield fullpath
                    # Skip if not text file.
                    if not self.is_txt(filename):
                        continue
                    # Check character encoding, skip if binary.
                    charset = self.check_charset(root, filename)
                    if charset == 'binary':
                        continue

                    # Check each line. If a keyword is found, yield.
                    open_file = open(fullpath, 'r', encoding=charset)
                    with open_file as file_text:
                        if self.search_text(file_text, keywords):
                            yield fullpath
                # Skips on errors, move on to next in list.
                except UnicodeDecodeError:
                    continue
                except UnicodeError:
                    continue
                except FileNotFoundError:
                    continue
                except PermissionError:
                    continue
                except OSError:
                    continue
            yield True
        yield False
        self.force_stop = False
        self.running = False

    def stop(self):
        """Stop the running search method."""
        self.force_stop = True

    def is_running(self):
        """Poll the search method to see if it still running."""
        return self.running


class CatfishSearchMethod_Zeitgeist(CatfishSearchMethod):

    """Search Method utilziing python's Zeitgeist integration.  This is used
    to provide the fastest results, usually benefitting search suggestions."""

    def __init__(self):
        """Initialize the Zeitgeist SearchMethod."""
        super().__init__("zeitgeist")
        self.stop_search = False
        self.events = []

    def result_callback(self, log, result, data):
        events = log.find_events_finish(result)
        for i in range(events.size()):  # cannot iterate events directly
            event = events.next_value()
            if event is None:
                continue
            self.events.append(event)
        self.stop_search = True

    def run(self, keywords, path, search_zips, regex=False, exclude_paths=[]):
        """Run the Zeitgeist SearchMethod."""
        keywords = " ".join(keywords).lower()
        self.stop_search = False
        event_template = Zeitgeist.Event()

        # 60 days at most
        end = int(time.time() * 1000)
        start = end - (60 * 3600 * 24 * 1000)
        time_range = Zeitgeist.TimeRange.new(start, end)

        self.events = []
        log = Zeitgeist.Log.get_default()
        log.find_events(
            time_range,
            [event_template, ],
            Zeitgeist.StorageState.ANY,
            1000,
            Zeitgeist.ResultType.MOST_RECENT_SUBJECTS,
            None, self.result_callback, None
        )

        while self.stop_search == False:
            yield False

        uniques = []

        for event in self.events:
            for subject in event.get_subjects():
                uri = subject.get_uri()
                if uri.startswith('file://'):
                    fullname = str(uri[7:])
                    filepath, filename = os.path.split(fullname)
                    if keywords in filename and \
                            uri not in uniques and \
                            path in filepath:
                        uniques.append(uri)
                        yield fullname

    def stop(self):
        """Stop the Zeitgeist SearchMethod."""
        self.stop_search = True

    def is_running(self):
        """Return True if the Zeitgeist SearchMethod is running."""
        return self.stop_search is False


class CatfishSearchMethodExternal(CatfishSearchMethod):

    """The base CatfishSearchMethodExternal class, which is used for getting
    results from shell queries."""

    def __init__(self, method_name):
        """Initialize the external method class."""
        super().__init__(method_name)
        self.pid = -1
        self.command = []
        self.process = None

    def assemble_query(self, keywords, path):  # pylint: disable=W0613
        """Base assemble_query method."""
        return False

    def run(self, keywords, path, search_zips, regex=False, exclude_paths=[]):
        """Run the search method using keywords and path.

        This function returns the process.stdout generator and will yield files
        as they are found."""
        # Start the command thread, and store the thread number so we can kill
        # it if necessary.
        command = None
        if regex:
            command = self.assemble_query(keywords, path)
        if not command:
            command = [item.replace('%keywords', keywords)
                       for item in self.command]
        command = [item.replace('%path', path) for item in command]
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, shell=False)
        self.pid = self.process.pid
        return self.process_output(self.process.stdout)

    def process_output(self, output):
        """Return the output text."""
        if isinstance(output, io.BufferedReader):
            return map(lambda s: s.decode(encoding='UTF8',
                                          errors='replace').strip(),
                       output.readlines())
        return output

    def status(self):
        """Return the current search status."""
        try:
            return self.process.poll()
        except AttributeError:
            return None

    def stop(self):
        """Stop the command thread."""
        if self.process:
            self.process.terminate()
        if self.pid > 0:
            try:
                os.kill(self.pid, signal.SIGKILL)
            except OSError:
                pass
            self.pid = 0

    def is_running(self):
        """Return True if the query is running."""
        return self.status() is not None


class CatfishSearchMethod_Locate(CatfishSearchMethodExternal):

    """External Search Method utilizing the system command 'locate'."""

    def __init__(self):
        """Initialize the Locate SearchMethod."""
        super().__init__("locate")
        self.caps = self.get_capabilities()
        if self.caps["existing"]:
            self.command = ["locate", "-i", "%path*%keywords*", "--existing"]
        else:
            self.command = ["locate", "-i", "%path*%keywords*"]

    def get_capabilities(self):
        caps = {
            "existing": False,
            "regex": False
        }
        try:
            details = subprocess.check_output(["locate", "--help"])
            details = details.decode("utf-8")
            if "--existing" in details:
                caps["existing"] = True
            if "--regex" in details or "--regexp" in details:
                caps["regex"] = True

        except subprocess.CalledProcessError:
            pass
        return caps

    def assemble_query(self, keywords, path):
        """Assemble the search query."""
        if self.caps["regex"]:
            return ["locate", "--regex", "--basename", "-i",
                    "{}".format(string_regex(keywords, path))]
        return ["locate", "-i", "%path*", str(keywords)]
