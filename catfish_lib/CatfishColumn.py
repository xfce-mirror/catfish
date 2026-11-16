#!/usr/bin/env python
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
#   Catfish - a versatile file searching tool
#   Copyright (C) 2018-2022 Sean Davis <bluesabre@xfce.org>
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


class CatfishColumn:
    def __init__(self, colid, colname, display_name):
        self.colid = colid
        self.colname = colname
        self.display_name = display_name
        self.col_rend_func = None

    def set_col_render_func(self, func):
        self.col_rend_func = func

all_columns = {
# 'icon'   : CatfishColumn(0, 'icon',   'Icon',        None),
'name'   : CatfishColumn(1, 'name',   'Filename'),
'size'   : CatfishColumn(2, 'size',   'Size'),
'path'   : CatfishColumn(3, 'path',   'Location'),
'date'   : CatfishColumn(4, 'date',   'Modified'),
'mime'   : CatfishColumn(5, 'mime',   'Filetype'),
'hidden' : CatfishColumn(6, 'hidden', 'Hidden'),
'exact'  : CatfishColumn(7, 'exact',  'Exact Match')
}
