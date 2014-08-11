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

import logging
logger = logging.getLogger('catfish_search')

import io
import os
import signal
import subprocess
from itertools import permutations

from mimetypes import guess_type

from sys import version_info
python3 = version_info[0] > 2

try:
    from zeitgeist.client import ZeitgeistDBusInterface
    from zeitgeist.datamodel import Event, TimeRange
    from zeitgeist import datamodel
    iface = ZeitgeistDBusInterface()
    zeitgeist_support = True
except Exception:
    zeitgeist_support = False


def string_regex(keywords, path):
    """Returns a string with the regular expression containing all combinations
    of the keywords."""
    keywords = keywords.split()
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

    def __init__(self, methods=['zeitgeist', 'locate', 'walk']):
        """Initialize the CatfishSearchEngine.  Provide a list of methods to
        be included in the search backends.  Available backends include:

         fulltext         'os.walk' and 'file.readline' to search inside files.
         locate           System 'locate' to search for files.
         walk             'os.walk' to search for files (like find).
         zeitgeist        Zeitgeist indexing service to search for files.
        """
        logger.debug("methods: %s", str(methods))
        self.methods = []
        if 'zeitgeist' in methods:
            if zeitgeist_support:
                self.add_method(CatfishSearchMethod_Zeitgeist)
        if 'locate' in methods:
            self.add_method(CatfishSearchMethod_Locate)
        if 'fulltext' in methods:
            self.add_method(CatfishSearchMethod_Fulltext)
        if 'walk' in methods:
            self.add_method(CatfishSearchMethod_Walk)

    def add_method(self, method_class):
        """Add a CatfishSearchMethod the the engine's search backends."""
        self.methods.append(method_class())

    def run(self, keywords, path, limit=-1, regex=False):
        """Run the CatfishSearchEngine.

        Each method is run sequentially in the order they are added.

        This function is a generator.  With each filename reviewed, the
        filename is yielded if it matches the query.  False is also yielded
        afterwards to guarantee the interface does not lock up."""

        logger.debug("path: %s", str(path))

        keywords = keywords.replace(',', ' ')
        self.keywords = keywords

        wildcard_chunks = []
        for key in self.keywords.split():
            if '*' in key:
                wildcard_chunks.append(key.split('*'))

        keywords = keywords.replace('*', ' ')

        # For simplicity, make sure the path contains a trailing '/'
        if not path.endswith('/'):
            path += '/'

        # Transform the keywords into a clean list.
        keys = []
        for key in keywords.split():
            keys.append(key.rstrip().lstrip())

        file_count = 0
        for method in self.methods:
            logger.debug(method.method_name)
            for filename in method.run(keywords, path, regex):
                if isinstance(filename, str) and path in filename:
                    if method.method_name == 'fulltext' or  \
                            all(key.lower() in
                                os.path.basename(filename).lower()
                                for key in keys):

                        # Remove the URI portion of the filename if present.
                        if filename.startswith('file://'):
                            filename = filename[7:]
                        if filename.startswith('mailbox://'):
                            filename = filename[10:]
                            filename = filename[:filename.index('?')]

                        # Remove whitespace from the filename.
                        filename = filename.rstrip().lstrip()

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

    def set_exact(self, exact):
        """Set method for exact"""
        # Only for fulltext engine
        for method in self.methods:
            method.exact = exact

    def stop(self):
        """Stop all running methods."""
        for method in self.methods:
            method.stop()


class CatfishSearchMethod:
    """The base CatfishSearchMethod class, to be inherited by defined
    methods."""

    def __init__(self, method_name):
        """Base CatfishSearchMethod Initializer."""
        self.method_name = method_name

    def run(self, keywords, path, regex=False):
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

    def run(self, keywords, path, regex=False):
        """Run the search method using keywords and path.  regex is not used
        by this search method.

        This function is a generator and will yield files as they are found or
        True if still running."""
        self.running = True
        if isinstance(keywords, str):
            keywords = keywords.replace(',', ' ')
            keywords = keywords.split()
        for root, dirs, files in os.walk(path):
            if not self.running:
                break
            for folder in dirs:
                if any(keyword.lower() in folder.lower()
                        for keyword in keywords):
                    yield os.path.join(root, folder)
            for filename in files:
                if any(keyword.lower() in filename.lower()
                        for keyword in keywords):
                    yield os.path.join(root, filename)
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

    def run(self, keywords, path, regex=False):
        """Run the search method using keywords and path.  regex is not used
        by this search method.

        This function is a generator and will yield files as they are found or
        True if still running."""
        self.running = True

        find_keywords_backup = []
        if not self.exact:
            # Split the keywords into a list if they are not already.
            if isinstance(keywords, str):
                keywords = keywords.replace(',', ' ')
                keywords = keywords.split()

            for keyword in keywords:
                if keyword.lower() not in find_keywords_backup:
                    find_keywords_backup.append(keyword.lower())

        # Start walking the folder structure.
        for root, dirs, files in os.walk(path):
            if self.force_stop:
                break

            for filename in files:
                if self.force_stop:
                    break

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
                                    if keywords in line:
                                        yield os.path.join(root, filename)
                                        break
                                else:
                                    if any(keyword.lower() in line.lower()
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

    def run(self, keywords, path, regex=False):
        """Run the Zeitgeist SearchMethod."""
        self.stop_search = False
        event_template = Event()
        time_range = TimeRange.from_seconds_ago(60 * 3600 * 24)
        # 60 days at most

        results = iface.FindEvents(
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

    def assemble_query(self, keywords, path):
        """Base assemble_query method."""
        return None

    def run(self, keywords, path, regex=False):
        """Run the search method using keywords and path.

        This function returns the process.stdout generator and will yield files
        as they are found."""
        # Start the command thread, and store the thread number so we can kill
        # it if necessary.
        command = None
        if regex:
            command = self.assemble_query(keywords, path)
        if not command:
            command = [item.replace('%keywords', keywords.lower())
                       for item in self.command]
        command = [item.replace('%path', path) for item in command]
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, shell=False)
        self.pid = self.process.pid
        return self.process_output(self.process.stdout)

    def process_output(self, output):
        """Return the output text."""
        if isinstance(output, io.BufferedReader):
            return map(lambda s: s.decode(encoding='UTF8').strip(),
                       output.readlines())
        else:
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
        self.command = ["locate", "-i", "%path*%keywords*", "--existing"]

    def assemble_query(self, keywords, path):
        """Assemble the search query."""
        return ["locate", "--regex", "-i", "{}".format(string_regex(keywords,
                                                                    path))]
