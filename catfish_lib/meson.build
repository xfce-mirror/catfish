catfish_lib_sources = [
  '__init__.py',
  'Builder.py',
  'catfishconfig.py',
  'CatfishSettings.py',
  'FiletypeLists.py',
  'helpers.py',
  'PrefsDialog.py',
  'SudoDialog.py',
  'Thumbnailer.py',
  'Window.py',
]

catfish_lib_defs_conf = configuration_data()
catfish_lib_defs_conf.set_quoted('VERSION', meson.project_version())
catfish_lib_defs_conf.set_quoted('CATFISH_DATA_DIRECTORY', pkgdatadir)
catfish_lib_defs_conf.set_quoted('COPYRIGHT_YEAR', copyright_year)

catfish_lib_defs = configure_file(
  input: 'defs.py.in',
  output: '@BASENAME@',
  configuration: catfish_lib_defs_conf,
)

python3.install_sources(
  [ catfish_lib_sources, catfish_lib_defs ],
  subdir: 'catfish_lib',
)
