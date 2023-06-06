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

def text_list():
    txt_list = ('ardour', 'audacity', 'desktop', 'document',
                'fontforge', 'gtk-builder', 'javascript', 'json',
                'm4', 'mbox', 'message', 'mimearchive', 'msg',
                'none', 'perl', 'pgp-keys', 'php', 'postscript',
                'rtf', 'ruby', 'shellscript', 'spreadsheet', 'sql',
                'subrip', 'text', 'troff', 'url', 'winhlp',
                'x-bittorent', 'x-cue', 'x-extension-cfg',
                'x-designer', 'x-glade', 'x-mpegurl', 'x-sami',
                'x-theme', 'x-trash', 'xbel', 'xml', 'xpixmap', 'yaml')
    return txt_list

def document_list():
    doc_list = ('pdf', 'ebook', 'epub', 'msword')
    return doc_list
