project(
  'catfish',
  version: '4.20.0-dev',
  license: 'GPL-2.0-or-later',
  meson_version: '>= 0.56.0',
)

gnome = import('gnome')
i18n = import('i18n')
python = import('python')

python3_required_modules = ['dbus', 'gi', 'pexpect']

python3 = python.find_installation(
  'python3',
  modules: python3_required_modules,
)

if not python3.language_version().version_compare('>= 3.7')
  error('Python 3.7 or newer is required.')
endif

dependency_versions = {
  'glib': '>= 2.50.0',
  'gtk': '>= 3.22.0',
  'gdk-pixbuf': '>= 2.42.8',
  'pango': '>= 1.38.0',
  'xfce4': '>= 4.16.0',
  'zeitgeist': '>= 1.0',
}

# Declare runtime dependency versions here to make packaging more obvious
dependency('gdk-3.0', version: dependency_versions['gtk'])
dependency('gdk-pixbuf-2.0', version: dependency_versions['gdk-pixbuf'])
dependency('glib-2.0', version: dependency_versions['glib'])
dependency('gobject-2.0', version: dependency_versions['glib'])
dependency('gtk+-3.0', version: dependency_versions['gtk'])
dependency('libxfconf-0', version: dependency_versions['xfce4'])
dependency('pango', version: dependency_versions['pango'])
# Since this is detected at runtime, meson option is probably not useful here.
dependency('zeitgeist-2.0', version: dependency_versions['zeitgeist'], required: false)

prefix = get_option('prefix')
bindir = prefix / get_option('bindir')
datadir = prefix / get_option('datadir')
pkgdatadir = datadir / meson.project_name()

subdir('bin')
subdir('catfish')
subdir('catfish_lib')
subdir('data')
subdir('po')

desktop_file = i18n.merge_file(
  input: 'org.xfce.Catfish.desktop.in',
  output: '@BASENAME@',
  type: 'desktop',
  po_dir: meson.project_source_root() / 'po',
  install: true,
  install_dir: datadir / 'applications',
)

install_man('catfish.1')

doc_files = [
  'NEWS',
  'README.md',
]

install_data(
  doc_files,
  install_dir: datadir / 'doc' / meson.project_name(),
)
