project('catfish', version : '4.20.0-dev', meson_version : '>= 0.59.0')

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

# Declare runtime dependency versions here to make packaging more obvious
dependency('gdk-3.0')
dependency('gdk-pixbuf-2.0')
dependency('glib-2.0')
dependency('gobject-2.0')
dependency('gtk+-3.0', version: '>= 3.10.0')
dependency('libxfconf-0')
dependency('pango')
dependency('zeitgeist-2.0', required: false)

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

gnome.post_install(
  gtk_update_icon_cache: true,
  update_desktop_database: true,
)
