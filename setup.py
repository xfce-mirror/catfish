#!/usr/bin/python3
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
#
# pylint: disable=attribute-defined-outside-init
# pylint: disable=missing-function-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-module-docstring
# pylint: disable=access-member-before-definition
# pylint: disable=import-outside-toplevel

import os
import re
import shutil
import sys
import subprocess

import setuptools
from setuptools.command.build import build
from setuptools.command.install import install
from setuptools.command.sdist import sdist

__version__ = '4.18.0'
__url__ = 'https://docs.xfce.org/apps/catfish/start'
GITLAB = 'https://gitlab.xfce.org/apps/catfish'
PKGNAME = 'catfish'
DESKTOP = 'org.xfce.Catfish.desktop'
APPDATA = 'catfish.appdata.xml'

if sys.version_info < (3, 7):
    raise SystemExit('Python >= 3.7 required')

class Build(build):
    user_options = build.user_options + [
        ('build-data', None, 'build directory for data'),
    ]
    def get_sub_commands(self):
        return super().get_sub_commands() + ['build_pot', 'build_i18n']

    def initialize_options(self):
        super().initialize_options()
        self.build_data = None

    def finalize_options(self):
        super().finalize_options()
        if self.build_data is None:
            self.build_data = os.path.join(self.build_base, 'share')

class BuildPot(setuptools.Command):
    description = 'Build POT files by xgettext'
    user_options = [
        ('build-pot=', 'b', "directory to write POT files to"),
    ]
    def initialize_options(self):
        self.build_pot = None

    def finalize_options(self):
        if self.build_pot is None:
            self.build_pot = 'po'

    def run(self):
        cmd = [
            'xgettext', f'--default-domain={PKGNAME}', '--from-code=UTF-8',
            '--files-from=po/POTFILES.in', '--directory=.',
            '--keyword=_', '--keyword=C_:1c,2', '--add-comments=TRANSLATORS:',
            '--copyright-holder=The Xfce development team.',
            f'--msgid-bugs-address={GITLAB}',
            f'--package-name={PKGNAME}',
            f'--output={self.build_pot}/{PKGNAME}.pot'
        ]
        print(" ".join(cmd))
        try:
            subprocess.check_call(cmd)
        except (OSError, subprocess.CalledProcessError):
            sys.stderr.write("Cannot generate thunar.pot.\n"
            "'xgettext' 0.19.8 or later is required.")


def get_linguas(filename):
    linguas = []
    with open(filename, 'r', encoding="utf-8") as f:
        for line in f:
            line = line.partition('#')[0]
            line = line.strip()
            linguas += re.split(r'\s+', line)
    return linguas

class BuildI18n(setuptools.Command):
    description = 'Build mo, desktop and xml files'
    user_options = [
        ('build-i18n=', 'b', "directory to write i18n files to"),
    ]
    def initialize_options(self):
        self.build_i18n = None

    def finalize_options(self):
        self.set_undefined_options(
            'build',
            ('build_data', 'build_i18n'),
        )
        self.build_lib = self.build_i18n
        self.linguas = get_linguas('po/LINGUAS')

    def get_mo_file(self, lang):
        return f'{self.build_i18n}/mo/{lang}.mo'

    def run(self):
        appdatacmd = [
            "msgfmt", "-d", "po", "--xml",
            "--template", f"data/metainfo/{APPDATA}.in",
            "-o", f"{self.build_i18n}/metainfo/{APPDATA}"
        ]
        desktopcmd = [
            "msgfmt", "-d", "po", "--desktop",
            "--template", f"{DESKTOP}.in",
            "-o", f"{self.build_i18n}/applications/{DESKTOP}"
        ]
        # Build mo files
        os.makedirs(f'{self.build_i18n}/mo', exist_ok=True)
        for ll in self.linguas:
            cmd = [
                'msgfmt', '-c', '--statistics', '--verbose',
                '-o', self.get_mo_file(ll), f'po/{ll}.po'
            ]
            print(" ".join(cmd))
            subprocess.check_call(cmd)

        # desktop and appdata files are already valid,
        # if we failed to msgfmt (because of old msgfmt),
        # just copy
        try:
            os.makedirs(f'{self.build_i18n}/applications', exist_ok=True)
            subprocess.check_call(desktopcmd)
        except (OSError, subprocess.CalledProcessError):
            shutil.copy(f"{DESKTOP}.in",
                f"{self.build_i18n}/applications/{DESKTOP}")
        try:
            os.makedirs(f'{self.build_i18n}/metainfo', exist_ok=True)
            subprocess.check_call(appdatacmd)
            shutil.copy(f"data/metainfo/{APPDATA}.in",
                f"{self.build_i18n}/metainfo/{APPDATA}")
        except (OSError, subprocess.CalledProcessError):
            shutil.copy(f"data/metainfo/{APPDATA}.in",
                f"{self.build_i18n}/metainfo/{APPDATA}")

    def get_source_files(self):
        result = [f'po/{ll}.po' for ll in self.linguas]
        return result + [
            f'{DESKTOP}.in',
            f'data/metainfo/{APPDATA}.in'
        ]

    def get_outputs(self):
        result = [self.get_mo_file(ll) for ll in self.linguas]
        return result + [
            f'{self.build_i18n}/applications/{DESKTOP}',
            f'{self.build_i18n}/metainfo/{APPDATA}',
        ]

    def get_output_mapping(self):
        result = {self.get_mo_file(ll): f'po/{ll}.po' for ll in self.linguas}
        result[f'{self.build_i18n}/applications/{DESKTOP}'] = \
            f'{DESKTOP}.in'
        result[f'{self.build_i18n}/{APPDATA}'] = f'data/{APPDATA}.in'
        return result



class Install(install):
    """Command Class to install and update the directory."""
    def finalize_options(self):
        super().finalize_options()
        if self.prefix is None:
            self.prefix = ''

    def run(self):
        """Run the setup commands."""
        super().run()
        distname = self.distribution.get_name()
        distver = self.distribution.get_version()
        print(f"=== Installing {distname}, version {distver} ===")

        share_dir = os.path.join(self.install_data, 'share')
        bin_dir = self.install_scripts

        if self.root:
            share_dir = os.sep + os.path.relpath(share_dir, self.root)
            bin_dir = os.sep + os.path.relpath(bin_dir, self.root)

        data_dir = os.path.join(share_dir, 'catfish')

        print(f"Root: {self.root}")
        print(f"Prefix: {self.prefix}\n")

        print(f"Target Data:    {share_dir}")
        print(f"Target Scripts: {bin_dir}\n")
        print(f"Catfish Data Directory: {data_dir}")

        values = {
            '__catfish_data_directory__': f"'{data_dir}'",
            '__version__': f"'{distver}'"
        }
        self.update_config(values)
        self.copy_tree('data/ui',
            os.path.join(self.install_data, 'share/catfish/ui'))
        self.copy_tree('data/media',
            os.path.join(self.install_data, 'share/icons/hicolor'))
        self.copy_file('catfish.1',
            os.path.join(self.install_data, 'share/man/man1'))
        self.copy_file(
            os.path.join(self.build_base, 'share/metainfo', APPDATA),
            os.path.join(self.install_data, 'share/metainfo'))
        self.install_desktop_file(bin_dir)
        for ll in get_linguas('po/LINGUAS'):
            dstdir = os.path.join(self.install_data, f'locale/{ll}/LC_MESSAGES')
            os.makedirs(dstdir, exist_ok=True)
            self.copy_file(
                os.path.join(self.build_base, 'share/mo', f"{ll}.mo"),
                os.path.join(dstdir, f'{PKGNAME}.mo'))

    def update_config(self, values):
        """Update the configuration file at installation time."""
        fname = os.path.join(self.install_lib, 'catfish_lib', 'catfishconfig.py')
        oldvalues = {}
        with open(fname, 'r', encoding='utf-8') as fin, \
                open(f'{fname}.tmp', 'w', encoding='utf-8') as fout:
            for line in fin:
                fields = line.partition(' = ')
                if fields[0] in values:
                    oldvalues[fields[0]] = fields[1].strip()
                    line = f'{fields[0]} = {values[fields[0]]}\n'
                fout.write(line)
            fout.flush()
        os.rename(f'{fname}.tmp', fname)
        return oldvalues

    def install_desktop_file(self, bin_dir):
        """Update the desktop file with prefixed paths."""
        build_ = os.path.join(self.build_base, 'share/applications', DESKTOP)
        tmp_ = f'{build_}.tmp'
        dstdir = os.path.join(self.install_data, 'share/applications')
        os.makedirs(dstdir, exist_ok=True)
        with open(build_, 'r', encoding='utf-8') as fin, \
                open(tmp_, 'w', encoding='utf-8') as fout:
            for line in fin:
                if line.startswith('Exec='):
                    delim = ''
                    args = ''
                    cmd = line.partition('=')[2].split(None, 1)
                    if len(cmd) > 1:
                        delim = ' '
                        args = cmd[1].strip()
                    catfish = os.path.join(bin_dir, 'catfish')
                    line = f'Exec={catfish}{delim}{args}\n'
                fout.write(line)

        self.copy_file(tmp_, dstdir)


class SDist(sdist):
    def initialize_options(self):
        super().initialize_options()
        self.formats = ['bztar']

    def run(self):
        folder = f"dist/catfish-{__version__}"
        if os.path.exists(folder):
            sys.stderr.write("Build directory 'dist' is not clean.\n")
            sys.stderr.write(f"Please manually remove {folder}")
            sys.exit(1)
        super().run()
        if self.formats == ['bztar']:
            bzfile = f"dist/catfish-{__version__}.tar.bz2"
            self.sign_release(bzfile)
            self.print_contents(bzfile)

    def sign_release(self, bzfile):
        import hashlib
        if not os.path.exists(bzfile):
            sys.stderr.write(f"Expected file '{bzfile}' was not found.")
            sys.exit(1)

        md5 = hashlib.md5()
        sha1 = hashlib.sha1()
        sha256 = hashlib.sha256()
        # Read in chunk, avoid OOM
        with open(bzfile, 'rb') as f:
            chunk = f.read(8192)
            while chunk:
                md5.update(chunk)
                sha1.update(chunk)
                sha256.update(chunk)
                chunk = f.read(8192)

        print("")
        print(f"{bzfile} written")
        print(f"  MD5:    {md5.hexdigest()}")
        print(f"  SHA1:   {sha1.hexdigest()}")
        print(f"  SHA256: {sha256.hexdigest()}")
        print("")

    def print_contents(self, bzfile):
        import tarfile

        print("Contents:")
        contents = {}
        with tarfile.open(bzfile, 'r:bz2') as tar:
            for tarinfo in tar:
                if not tarinfo.isdir():
                    basedir = os.path.dirname(tarinfo.name)
                    if basedir not in contents:
                        contents[basedir] = [tarinfo.name]
                    else:
                        contents[basedir].append(tarinfo.name)

        for basedir, files in contents.items():
            indent = ""
            indent = ' ' * len(basedir.split('/'))
            print(f"{indent}{basedir}/")
            indent += "  "
            for fname in files:
                print(indent + fname)

setuptools.setup(
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
    scripts=['bin/catfish'],
    packages = ['catfish', 'catfish_lib'],
    data_files=[
        ('share/man/man1', ['catfish.1']),
    ],
    cmdclass={
        'build': Build,
        'build_pot': BuildPot,
        'build_i18n': BuildI18n,
        'install': Install,
        'sdist': SDist
    }
)
