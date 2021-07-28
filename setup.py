#!/usr/bin/python3
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

import codecs
import os
import shutil
import sys
import subprocess
import site

__version__ = '4.16.1'
__url__ = 'https://docs.xfce.org/apps/catfish/start'

try:
    import DistUtilsExtra.auto
except ImportError:
    sys.stderr.write("To build catfish you need "
                     "https://launchpad.net/python-distutils-extra\n")
    sys.exit(1)
assert DistUtilsExtra.auto.__version__ >= '2.18', \
    'DistUtilsExtra.auto >= 2.18 required, found %s' \
        % DistUtilsExtra.auto.__version__

python_version = float("%i.%02i" % sys.version_info[:2])
assert python_version >= 3.02, \
    'Python >= 3.2 required, found %s' % str(python_version)

def update_config(libdir, values={}):
    """Update the configuration file at installation time."""
    filename = os.path.join(libdir, 'catfish_lib', 'catfishconfig.py')
    oldvalues = {}
    try:
        fin = codecs.open(filename, 'r', encoding='utf-8')
        fout = codecs.open(filename + '.new', 'w', encoding='utf-8')

        for line in fin:
            fields = line.split(' = ')  # Separate variable from value
            if fields[0] in values:
                oldvalues[fields[0]] = fields[1].strip()
                line = "%s = %s\n" % (fields[0], values[fields[0]])
            fout.write(line)

        fout.flush()
        fout.close()
        fin.close()
        os.rename(fout.name, fin.name)
    except (OSError, IOError):
        sys.stderr.write("ERROR: Can't find %s" % filename)
        sys.exit(1)
    return oldvalues


def get_icon_files(root, target_data):
    files = []
    for extension in ["png", "svg"]:
        icon_name = "org.xfce.catfish.%s" % extension
        filename = os.path.join(root, icon_name)
        if os.path.exists(filename):
            files.append(filename)
    if len(files) == 0:
        sys.stderr.write("ERROR: Can't find icons in %s" % root)
        sys.exit(1)
    return files


def move_icon_file(root, icon_size, target_data):
    """Move the icon files to their installation prefix."""
    old_icon_path = os.path.normpath(
        os.path.join(root, target_data, 'share', 'catfish', 'media', icon_size))

    for old_icon_file in get_icon_files(old_icon_path, target_data):
        icon_name = os.path.basename(old_icon_file)
        icon_path = os.path.normpath(
            os.path.join(root, target_data, 'share', 'icons',
                         'hicolor', icon_size, 'apps'))
        icon_file = os.path.join(icon_path, icon_name)

        # Get the real paths.
        old_icon_file = os.path.realpath(old_icon_file)
        icon_file = os.path.realpath(icon_file)

        if not os.path.exists(icon_path):
            os.makedirs(icon_path)
        if old_icon_file != icon_file:
            print("Moving icon file: %s -> %s" % (old_icon_file, icon_file))
            os.rename(old_icon_file, icon_file)

    # Media/icon_size is now empty
    if len(os.listdir(old_icon_path)) == 0:
        print("Removing empty directory: %s" % old_icon_path)
        os.rmdir(old_icon_path)

    return icon_file


def move_icon_files(root, target_data):
    """Move the icon files to their installation prefix."""
    files = []

    for icon_size in ["16x16", "48x48", "128x128", "scalable"]:
        files.append(move_icon_file(root, icon_size, target_data))
    media_path = os.path.normpath(
        os.path.join(root, target_data, 'share', 'catfish', 'media'))

    # Media is now empty
    if len(os.listdir(media_path)) == 0:
        print("Removing empty directory: %s" % media_path)
        os.rmdir(media_path)

    return files


def get_desktop_file(root, target_data):
    """Move the desktop file to its installation prefix."""
    desktop_path = os.path.realpath(
        os.path.join(root, target_data, 'share', 'applications'))
    desktop_file = os.path.join(desktop_path, 'org.xfce.Catfish.desktop')
    return desktop_file


def update_desktop_file(filename, script_path):
    """Update the desktop file with prefixed paths."""
    try:
        fin = codecs.open(filename, 'r', encoding='utf-8')
        fout = codecs.open(filename + '.new', 'w', encoding='utf-8')

        for line in fin:
            if 'Exec=' in line:
                cmd = line.split("=")[1].split(None, 1)
                line = "Exec=%s" % os.path.join(script_path, 'catfish')
                if len(cmd) > 1:
                    line += " %s" % cmd[1].strip()  # Add script arguments back
                line += "\n"
            fout.write(line)
        fout.flush()
        fout.close()
        fin.close()
        os.rename(fout.name, fin.name)
    except (OSError, IOError):
        sys.stderr.write("ERROR: Can't find %s" % filename)
        sys.exit(1)


def get_metainfo_file():
    """Prebuild the metainfo file so it can be installed."""
    source = "data/metainfo/catfish.appdata.xml.in"
    target = "data/metainfo/catfish.appdata.xml"
    cmd = ["intltool-merge", "-d", "po", "--xml-style", source, target]
    print(" ".join(cmd))
    subprocess.call(cmd)
    return target


def cleanup_metainfo_files(root, target_data):
    metainfo_dir = os.path.normpath(
        os.path.join(root, target_data, 'share', 'catfish', 'metainfo'))
    if os.path.exists(metainfo_dir):
        shutil.rmtree(metainfo_dir)


class InstallAndUpdateDataDirectory(DistUtilsExtra.auto.install_auto):

    """Command Class to install and update the directory."""

    def run(self):
        """Run the setup commands."""
        metainfo = get_metainfo_file()

        DistUtilsExtra.auto.install_auto.run(self)

        print(("=== Installing %s, version %s ===" %
               (self.distribution.get_name(),
                self.distribution.get_version())))

        using_pip = os.path.basename(os.path.dirname(__file__)).startswith('pip-')

        if not self.prefix:
            self.prefix = ''  # pylint: disable=W0201

        if self.root:
            target_data = os.path.relpath(
                self.install_data, self.root) + os.sep
            target_scripts = os.path.join(self.install_scripts, '')

            data_dir = os.path.join(self.prefix, 'share', 'catfish', '')
            script_path = os.path.join(self.prefix, 'bin')

            if using_pip:
                target_pkgdata = os.path.join(site.getuserbase(), 'share', 'catfish')
                target_pkgdata = os.path.realpath(target_pkgdata)
                data_dir = target_pkgdata

        else:
            # --user install
            self.root = ''  # pylint: disable=W0201
            target_data = os.path.relpath(self.install_data) + os.sep
            target_pkgdata = os.path.join(target_data, 'share', 'catfish', '')
            target_scripts = os.path.join(self.install_scripts, '')

            # Use absolute paths
            target_data = os.path.realpath(target_data)
            target_pkgdata = os.path.realpath(target_pkgdata)
            target_scripts = os.path.realpath(target_scripts)

            data_dir = target_pkgdata
            script_path = target_scripts

        print(("Root: %s" % self.root))
        print(("Prefix: %s\n" % self.prefix))

        print(("Target Data:    %s" % target_data))
        print(("Target Scripts: %s\n" % target_scripts))
        print(("Catfish Data Directory: %s" % data_dir))

        values = {'__catfish_data_directory__': "'%s'" % (data_dir),
                  '__version__': "'%s'" % self.distribution.get_version()}
        update_config(self.install_lib, values)

        desktop_file = get_desktop_file(self.root, target_data)
        print(("Desktop File: %s\n" % desktop_file))
        move_icon_files(self.root, target_data)
        update_desktop_file(desktop_file, script_path)

        cleanup_metainfo_files(self.root, target_data)
        os.remove(metainfo)


# Verify the build directory is clean
FOLDER = "dist/catfish-%s" % __version__
if os.path.exists(FOLDER):
    sys.stderr.write("Build directory 'dist' is not clean.\n"
                     "Please manually remove %s" % FOLDER)
    sys.exit(1)

# Hacky, default releases to bztar
DEFAULT_RELEASE_BUILD = False
if "sdist" in sys.argv:
    if "--formats" not in " ".join(sys.argv[1:]):
        sys.argv.append("--formats=bztar")
        DEFAULT_RELEASE_BUILD = True

DistUtilsExtra.auto.setup(
    name='catfish',
    version=__version__,
    license='GPL-2+',
    author='Sean Davis',
    author_email='bluesabre@xfce.org',
    description='file searching tool configurable via the command line',
    long_description='Catfish is a handy file searching tool for Linux and '
                     'UNIX. The interface is intentionally lightweight and '
                     'simple, using only Gtk+3. You can configure it to your '
                     'needs by using several command line options.',
    url=__url__,
    data_files=[
        ('share/man/man1', ['catfish.1']),
        ('share/metainfo/', ['data/metainfo/catfish.appdata.xml'])
    ],
    cmdclass={'install': InstallAndUpdateDataDirectory}
)

# Simplify Xfce release process by providing sums
if DEFAULT_RELEASE_BUILD:
    import hashlib
    import tarfile

    BZFILE = "dist/catfish-%s.tar.bz2" % __version__
    if not os.path.exists(BZFILE):
        sys.stderr.write("Expected file '%s' was not found.")
        sys.exit(1)

    CONTENTS = open(BZFILE, 'rb').read()

    print("")
    print("%s written" % BZFILE)
    print("  MD5:    %s" % hashlib.md5(CONTENTS).hexdigest())
    print("  SHA1:   %s" % hashlib.sha1(CONTENTS).hexdigest())
    print("  SHA256: %s" % hashlib.sha256(CONTENTS).hexdigest())
    print("")
    print("Contents:")

    CONTENTS = {}
    TAR = tarfile.open(BZFILE, "r:bz2")
    for tarinfo in TAR:
        if not tarinfo.isdir():
            basedir = os.path.dirname(tarinfo.name)
            if basedir not in CONTENTS.keys():
                CONTENTS[basedir] = []
            CONTENTS[basedir].append(tarinfo.name)
    TAR.close()

    for basedir in CONTENTS.keys():  # pylint: disable=C0201
        indent = ""
        for i in range(0, len(basedir.split("/"))):
            indent += "  "
        print("%s%s/" % (indent, basedir))
        indent += "  "
        for fname in CONTENTS[basedir]:
            print(indent + fname)
