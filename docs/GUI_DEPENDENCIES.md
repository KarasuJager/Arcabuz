# Native GUI dependencies and distribution

The optional `gui` extra installs `PySide6-Essentials` and `jsonschema`. Essentials
contains required Qt Core/Gui/Widgets bindings and bundled Qt libraries; Shiboken is
its binding support dependency. The application does not require Qt Addons, WebEngine,
a browser, or an application server. The CLI installs without Qt. See official Qt
[package details](https://doc.qt.io/qtforpython-6/package_details.html).

Qt's native model/view and queued signal APIs fit large tables and background work.
Models stay on the GUI thread as required by the official
[table-model documentation](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QAbstractTableModel.html).

The tested Windows Essentials wheel was approximately 77 MB compressed; installed size
is larger and platform/version dependent. This is an explicitly selected GUI dependency,
not added to CLI-only installations. No frozen runtime is bundled in FuzzRank's own
source/wheel. Use an approved wheelhouse when installation must also occur offline.

Qt for Python has community and commercial licensing options, with LGPLv3/GPLv3 and
module/third-party terms requiring review for a specific distribution. The owner must
assess applicable terms, notices, source/relinking obligations where relevant, and any
commercial agreement before distributing a bundle. Consult official
[Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html) and license files
in the selected wheels. FuzzRank source code is [MIT licensed](../LICENSE.md).
That license does not relicense Qt, PySide6, Shiboken or other third-party components;
their own licensing terms continue to apply.

## Future standalone packaging

The supported distribution is a Python wheel plus optional GUI dependencies. A future
Windows executable can wrap `fuzzrank.gui.app:main` with a maintained Qt-aware bundler
such as PyInstaller or Qt deployment tooling. Use a separate packaging environment,
preserve Qt libraries/plugins, and include bundled profiles/rules/schema resources with
the bundler's resource hooks. Prefer an inspectable directory bundle initially.

Before releasing a bundle, repeat demo/import/watch/parity/export checks on a clean
Windows machine, verify cancellation and plugin discovery, inventory dependency notices,
and test installation/uninstallation and code signing. No frozen executable, bundler
configuration, signing, or redistribution review is validated or claimed here. The
application architecture does not need to change to add this packaging layer.
