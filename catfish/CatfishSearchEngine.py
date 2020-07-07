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

from mimetypes import guess_type

import gi
gi.require_version('GLib', '2.0')  # noqa
from gi.repository import GLib

try:
    from zeitgeist.client import ZeitgeistDBusInterface  # pylint: disable=E0401
    from zeitgeist.datamodel import Event, TimeRange  # pylint: disable=E0401
    from zeitgeist import datamodel  # pylint: disable=E0401
    IFACE = ZeitgeistDBusInterface()
    ZEITGEIST_SUPPORT = True
except ImportError:
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

    def run(self, keywords, path, limit=-1, regex=False):  # noqa
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
            for filename in method.run(keywords, path, regex,
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

                    if method.method_name == 'fulltext' or  \
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
                                method.method_name == 'fulltext':
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

    def run(self, keywords, path, regex=False, exclude_paths=[]):  # pylint: disable=W0613
        """Base CatfishSearchMethod run method."""
        return NotImplemented

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
        CatfishSearchMethod.__init__(self, "walk")
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

    def run(self, keywords, path, regex=False, exclude_paths=[]):
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
            GLib.get_user_special_dir(GLib.USER_DIRECTORY_DESKTOP),
            GLib.get_user_special_dir(GLib.USER_DIRECTORY_DOCUMENTS),
            GLib.get_user_special_dir(GLib.USER_DIRECTORY_DOWNLOAD),
            GLib.get_user_special_dir(GLib.USER_DIRECTORY_MUSIC),
            GLib.get_user_special_dir(GLib.USER_DIRECTORY_PICTURES),
            GLib.get_user_special_dir(
                GLib.USER_DIRECTORY_PUBLIC_SHARE),
            GLib.get_user_special_dir(GLib.USER_DIRECTORY_TEMPLATES),
            GLib.get_user_special_dir(GLib.USER_DIRECTORY_VIDEOS),
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
                if any(keyword in path.lower() for keyword in keywords):
                    yield os.path.join(root, path)
            yield True
        yield False

    def stop(self):
        """Stop the running search method."""
        self.running = False

    def is_running(self):
        """Poll the search method to see if it still running."""
        return self.running


class CatfishSearchMethod_Fulltext(CatfishSearchMethod):

    """Search Method utilizing python 'os.walk' and 'file.readline'.  This is
    used as a replacement for the 'find' search method, which is difficult to
    interrupt and is slower than os.walk."""

    def __init__(self):
        """Initialize the 'fulltext' search method."""
        CatfishSearchMethod.__init__(self, "fulltext")
        self.force_stop = False
        self.running = False
        self.exact = False

    def run(self, keywords, path, regex=False, exclude_paths=[]):  # noqa
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

            for filename in files:
                if self.force_stop:
                    break
                
                # Checks if regular file (excludes special files).
                if os.path.isfile(os.path.join(root, filename)):

                    # If the filetype is known to not be text, move along.
                    mime = guess_type(filename)[0]
                    if not mime or 'text' in mime:
                        try:
                            opened = open(os.path.join(root, filename), 'r')

                            find_keywords = find_keywords_backup

                            # Check each line.  If a keyword is found, yield.
                            try:
                                for line in opened:
                                    if self.force_stop:
                                        break

                                    if self.exact:
                                        if " ".join(keywords) in line:
                                            yield os.path.join(root, filename)
                                            break
                                    else:
                                        if any(keyword in line.lower()
                                               for keyword in keywords):
                                            found_keywords = []
                                            for find_keyword in find_keywords:
                                                if find_keyword in line.lower():
                                                    found_keywords.append(
                                                        find_keyword)
                                            for found_keyword in found_keywords:
                                                find_keywords.remove(found_keyword)

                                            if len(find_keywords) == 0:
                                                yield os.path.join(root, filename)
                                                break
                            except UnicodeDecodeError:
                                pass
                            opened.close()
                        except IOError:
                            pass
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
        CatfishSearchMethod.__init__(self, "zeitgeist")
        self.stop_search = False

    def run(self, keywords, path, regex=False, exclude_paths=[]):
        """Run the Zeitgeist SearchMethod."""
        self.stop_search = False
        event_template = Event()
        time_range = TimeRange.from_seconds_ago(60 * 3600 * 24)
        # 60 days at most

        results = IFACE.FindEvents(
            time_range,  # (min_timestamp, max_timestamp) in milliseconds
            [event_template, ],
            datamodel.StorageState.Any,
            1000,
            datamodel.ResultType.MostRecentSubjects
        )

        results = (datamodel.Event(result) for result in results)
        uniques = []

        for event in results:
            if self.stop_search:
                break
            for subject in event.get_subjects():
                uri = str(subject.uri)
                if uri.startswith('file://'):
                    fullname = str(uri[7:])
                    filepath, filename = os.path.split(fullname)
                    if keywords.lower() in filename and \
                            uri not in uniques and \
                            path in filepath:
                        uniques.append(uri)
                        yield fullname
        self.stop_search = True

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
        CatfishSearchMethod.__init__(self, method_name)
        self.pid = -1
        self.command = []
        self.process = None

    def assemble_query(self, keywords, path):  # pylint: disable=W0613
        """Base assemble_query method."""
        return False

    def run(self, keywords, path, regex=False, exclude_paths=[]):
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
        CatfishSearchMethodExternal.__init__(self, "locate")
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
