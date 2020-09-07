#!/usr/bin/env python
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
#   Catfish - a versatile file searching tool
#   Copyright (C) 2018-2020 Sean Davis <bluesabre@xfce.org>
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

import hashlib
import mimetypes
import os
import sys

from gi.repository import GLib, Gio, GdkPixbuf

from . catfishconfig import get_version


class Thumbnailer:

    def __init__(self):
        self._glib_version = self._get_glib_version()
        if self._make_thumbnail_directories():
            self._normal_dir = self._get_normal_directory()
            self._fail_dir = self._get_fail_directory()
        else:
            self._normal_dir = None
            self._fail_dir = None

    def _get_glib_version(self):
        try:
            major = GLib.MAJOR_VERSION
            minor = GLib.MINOR_VERSION
            version = float("%i.%i" % (major, minor))
        except AttributeError:
            try:
                major, minor = list(GLib.glib_version)[:2]
                version = float("%i.%i" % (major, minor))
            except Exception:
                version = 2.32
        return version

    def _get_expected_thumbnail_directory(self):
        if self._glib_version > 2.34:
            return os.path.join(GLib.get_user_cache_dir(), 'thumbnails/')
        return os.path.join(GLib.get_home_dir(), '.thumbnails/')

    def _get_normal_directory(self):
        expected = self._get_expected_thumbnail_directory()
        return os.path.join(expected, 'normal')

    def _get_fail_directory(self):
        expected = self._get_expected_thumbnail_directory()
        faildir = "catfish-%s" % get_version()
        return os.path.join(expected, faildir)

    def _make_thumbnail_directory(self, path):
        # All the directories including the $XDG_CACHE_HOME/thumbnails
        # directory must have set their permissions to 700
        if os.path.exists(path):
            return True
        try:
            os.makedirs(path, 0o700)
            return True
        except os.error:
            return False

    def _make_thumbnail_directories(self):
        # $XDG_CACHE_HOME/thumbnails/
        # $XDG_CACHE_HOME/thumbnails/normal (128x128)
        # $XDG_CACHE_HOME/thumbnails/large/ (256x256)
        # $XDG_CACHE_HOME/thumbnails/fail/  (failed generation)
        # All the directories including the $XDG_CACHE_HOME/thumbnails
        # directory must have set their permissions to 700 (this means
        # only the owner has read, write and execute permissions, see
        # "man chmod" for details). Similar,  all the files in the thumbnail
        # directories should have set their permissions to 600.
        if not self._make_thumbnail_directory(self._get_normal_directory()):
            return False
        return True

    def _get_file_md5(self, filename):
        gfile = Gio.File.new_for_path(filename)
        uri = gfile.get_uri()
        uri = uri.encode('utf-8')
        md5_hash = hashlib.md5(uri).hexdigest()
        return md5_hash

    def _get_shared_file_md5(self, filename):
        basename = os.path.basename(filename)
        basename = basename.encode('utf-8')
        md5_hash = hashlib.md5(basename).hexdigest()
        return md5_hash

    def _get_thumbnail_basename(self, filename):
        return "%s.png" % self._get_file_md5(filename)

    def _get_shared_thumbnail_basename(self, filename):
        return "%s.png" % self._get_shared_file_md5(filename)

    def _get_normal_filename(self, filename):
        thumbs = self._normal_dir
        if filename.startswith(thumbs):
            return filename
        basename = self._get_thumbnail_basename(filename)
        return os.path.join(thumbs, basename)

    def _get_shared_normal_filename(self, filename):
        dirname = os.path.dirname(filename)
        basename = self._get_shared_thumbnail_basename(filename)
        return os.path.join(dirname, ".sh_thumbnails", "normal", basename)

    def _get_failed_filename(self, filename):
        thumbs = self._fail_dir
        basename = self._get_thumbnail_basename(filename)
        return os.path.join(thumbs, basename)

    def _touch(self, fname, mode=0o600, dir_fd=None, **kwargs):
        flags = os.O_CREAT | os.O_APPEND
        with os.fdopen(os.open(fname, flags=flags, mode=mode,
                               dir_fd=dir_fd)) as f:
            os.utime(f.fileno() if os.utime in os.supports_fd else fname,
                     dir_fd=None if os.supports_fd else dir_fd, **kwargs)

    def _get_attributes(self, filename):
        gfile = Gio.File.new_for_path(filename)
        uri = gfile.get_uri()
        mtime = str(int(os.path.getmtime(filename)))
        mime_type = self._get_mime_type(filename)

        options = {
            "tEXt::Thumb::URI": uri,
            "tEXt::Thumb::MTime": mtime,
            "tEXt::Thumb::Size": str(os.path.getsize(filename)),
            "tEXt::Thumb::Mimetype": mime_type,
            "tEXt::Software": "Catfish"
        }

        return options

    def _set_attributes(self, filename, thumbnail):
        options = self._get_attributes(filename)

        try:
            thumb_pb = GdkPixbuf.Pixbuf.new_from_file(thumbnail)
            thumb_pb.savev(thumbnail, "png", list(options.keys()),
                           list(options.values()))
        except GLib.GError:
            pass

    def _write_fail(self, filename):
        if self._make_thumbnail_directory(self._fail_dir):
            thumb = self._get_failed_filename(filename)
            self._touch(thumb)
            self._set_attributes(filename, thumb)

    def _get_mime_type(self, filename):
        if os.path.isdir(filename):
            return 'inode/directory'
        guess = mimetypes.guess_type(filename)
        return guess[0]

    def _create_thumbnail(self, filename, thumbnail):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(filename)
            if pixbuf is None:
                return False

            pixbuf_w = pixbuf.get_width()
            pixbuf_h = pixbuf.get_height()
            if pixbuf_w < 1 or pixbuf_h < 1:
                return False

            if pixbuf_w < 128 and pixbuf_h < 128:
                options = self._get_attributes(filename)
                pixbuf.savev(thumbnail, "png", list(options.keys()),
                             list(options.values()))
                os.chmod(thumbnail, 0o600)
                return True

            if pixbuf_w > pixbuf_h:
                thumb_w = 128
                thumb_h = int(pixbuf_h / (pixbuf_w / 128.0))
            else:
                thumb_h = 128
                thumb_w = int(pixbuf_w / (pixbuf_h / 128.0))
            if thumb_w < 1 or thumb_h < 1:
                return False

            thumb_pixbuf = pixbuf.scale_simple(
                thumb_w, thumb_h, GdkPixbuf.InterpType.BILINEAR)
            if thumb_pixbuf is None:
                return False

            options = self._get_attributes(filename)
            thumb_pixbuf.savev(thumbnail, "png", list(options.keys()),
                               list(options.values()))
            os.chmod(thumbnail, 0o600)
            return True
        except Exception as e:
            print("Exception: ", e)
            return False

    def get_thumbnail(self, filename, mime_type=None, buildit=True):
        thumb = self._get_normal_filename(filename)
        if os.path.exists(thumb):
            return thumb

        thumb = self._get_shared_normal_filename(filename)
        if os.path.exists(thumb):
            return thumb

        failed = self._get_failed_filename(filename)
        if os.path.exists(failed):
            return None

        if self._normal_dir is None:
            return False

        if mime_type is None:
            mime_type = self._get_mime_type(filename)

        if mime_type.startswith('image'):
            if mime_type in ["image/x-photoshop"]:
                return False
        else:
            return False

        if not buildit:
            return False

        normal = self._get_normal_filename(filename)
        if self._create_thumbnail(filename, normal):
            return normal
        self._write_fail(filename)
        return False
