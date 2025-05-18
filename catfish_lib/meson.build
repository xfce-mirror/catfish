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
catfish_lib_defs_conf.set_quoted('REVISION', '@REVISION@')
catfish_lib_defs_conf.set_quoted('CATFISH_DATA_DIRECTORY', pkgdatadir)
catfish_lib_defs_conf.set_quoted('COPYRIGHT_YEAR', copyright_year)

catfish_lib_defs_in = configure_file(
  input: 'defs.py.in.in',
  output: 'defs.py.in',
  configuration: catfish_lib_defs_conf,
)

# {'install arg in vcs_tag', 'install_dir arg in vcs_tag'} is only supported in 1.7.0+.
if meson.version().version_compare('>= 1.7.0')
  vcs_tag(
    command: ['git', 'rev-parse', '--short', 'HEAD'],
    fallback: 'UNKNOWN',
    input: catfish_lib_defs_in,
    output: 'defs.py',
    replace_string: '@REVISION@',
    install: true,
    install_dir: python3.get_install_dir(subdir: 'catfish_lib'),
  )
else
  configure_file(
    input: catfish_lib_defs_in,
    output: 'defs.py',
    configuration: {'REVISION': 'UNKNOWN'},
    install: true,
    install_dir: python3.get_install_dir(subdir: 'catfish_lib'),
  )
endif

python3.install_sources(
  catfish_lib_sources,
  subdir: 'catfish_lib',
)
