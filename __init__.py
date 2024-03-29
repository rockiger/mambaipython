"""iPython REPL for your Python files"""
__pluginname__ = "iPython REPL"
__author__ = "Marco Laspe"
__credits__ = ["Andrei Kopats", "Bryan A. Jones"]
__license__ = "GPL3"
__version__ = "0.1.0"
__maintainer__ = "Marco Laspe"
__email__ = "marco@rockiger.com"
__status__ = "Beta"
# This plugin is a copy of the Enki repl plugin
# https://github.com/andreikop/enki/tree/master/enki/plugins/repl

import os.path

from PyQt5.QtCore import QObject, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QLabel

from enki.core.core import core
from enki.core.uisettings import ChoiseOption, TextOption

# Constants
ICON_PATH = QIcon(os.path.join(os.path.dirname(__file__), 'terminal.svg'))

class _AbstractReplPlugin(QObject):
    """Base class for language-specific REPL sub-plugins
    """
    _LANGUAGE = None
    _FULL_NAME = None
    _MENU_PATH = None
    _DOCK_TITLE = None

    def __init__(self):
        QObject.__init__(self)

        self._installed = False
        self._evalAction = None
        self._activeInterpreterPath = None
        self._dock = None

        # TODO handle situation, when lexer changed for current document
        core.workspace().currentDocumentChanged.connect(self._installOrUninstallIfNecessary)
        core.workspace().currentDocumentChanged.connect(self._updateEvalActionEnabledState)
        core.workspace().languageChanged.connect(self._installOrUninstallIfNecessary)
        core.workspace().languageChanged.connect(self._updateEvalActionEnabledState)
        core.uiSettingsManager().aboutToExecute.connect(self._onSettingsDialogAboutToExecute)

        self._installOrUninstallIfNecessary()

    def terminate(self):
        self.uninstall()
        core.workspace().currentDocumentChanged.disconnect(self._installOrUninstallIfNecessary)
        core.workspace().currentDocumentChanged.disconnect(self._updateEvalActionEnabledState)
        core.workspace().languageChanged.disconnect(self._installOrUninstallIfNecessary)
        core.workspace().languageChanged.disconnect(self._updateEvalActionEnabledState)
        core.uiSettingsManager().aboutToExecute.disconnect(self._onSettingsDialogAboutToExecute)
        if self._dock:
            # See https://jupyter-client.readthedocs.io/en/stable/api/manager.html#jupyter_client.KernelManager.shutdown_kernel.
            self._dock.ipython_widget.kernel_manager.shutdown_kernel()

    def _icon(self):
        """Settings widget icon
        """
        return QIcon(':/enkiicons/transparent.png')

    def _createInterpreter(self):
        """Create interpreter instance
        """
        raise NotImplementedError()

    def _isSupportedFile(self, document):
        """Check if document is highlighted as Scheme
        """
        return document is not None and \
            document.qutepart.language() == self._LANGUAGE

    def _updateEvalActionEnabledState(self):
        """Update action enabled state
        """
        if self._evalAction is None:
            return

        currDoc = core.workspace().currentDocument()
        self._evalAction.setEnabled(currDoc is not None and self._isSupportedFile(currDoc))

    def _settingsGroup(self):
        """Get own settings group
        """
        return core.config().get("Modes/%s" % self._LANGUAGE)

    def _installOrUninstallIfNecessary(self):
        """Install or uninstall according to settings and availability of opened Scheme files
        """
        enabled = self._settingsGroup()["Enabled"]
        if enabled == 'always':
            if not self._installed:
                self._install()
        elif enabled == 'never':
            if self._installed:
                self.uninstall()
        else:
            assert enabled == 'whenOpened'
            document = core.workspace().currentDocument()
            if document is not None and \
               self._isSupportedFile(document):
                self._install()
            else:
                self.uninstall()

    def _onEvalTriggered(self):
        """Eval action triggered. Evaluate file or expression
        """
        document = core.workspace().currentDocument()
        if document is None:
            return

        selection = document.qutepart.selectedText
        if selection:
            # See https://jupyter-client.readthedocs.io/en/stable/api/client.html#jupyter_client.KernelClient.execute. But actually, no -- this is somewhere in the qt console source, https://github.com/jupyter/qtconsole/blob/master/qtconsole/frontend_widget.py#L289 ???
            self._dock.ipython_widget.execute(selection)
            self._dock.show()
        else:
            if document.qutepart.document().isModified():
                document.saveFile()
            if document.filePath():  # user may cancel saving document
                self._dock.ipython_widget.execute('run "{}"'.format(document.filePath()))
                self._dock.show()

    def _onBreakTriggered(self):
        """Break has been triggered. Stop the interpreter.
        """
        # See https://jupyter-client.readthedocs.io/en/stable/api/manager.html#jupyter_client.KernelManager.interrupt_kernel.
        self._dock.ipython_widget.interrupt_kernel()

    def _onSettingsDialogAboutToExecute(self, dialog):
        """UI settings dialogue is about to execute.
        Add own options
        """
        from .repl import SettingsWidget
        widget = SettingsWidget(dialog)


        # try to get REPL Page
        try:
            settingsPage = dialog._pageForItem['REPL']
            print(settingsPage)
        except KeyError:
            settingsPage = dialog.createSettingsPage("REPL Settings")
            dialog.appendPage("REPL", settingsPage,
                              QIcon.fromTheme("utilities-terminal",
                                              QIcon(ICON_PATH)))

        widget.header.setText("<h3>%s</h3>" % self._FULL_NAME)
        settingsPage.addWidget(widget)

        # Options
        dialog.appendOption(ChoiseOption(dialog, core.config(), "Modes/%s/Enabled" % self._LANGUAGE,
                                         {widget.rbWhenOpened: "whenOpened",
                                          widget.rbNever: "never",
                                          widget.rbAlways: "always"}))
        # not needed for iPython
        # dialog.appendOption(TextOption(dialog, core.config(),
        #                                "Modes/%s/InterpreterPath" % self._LANGUAGE, widget.leInterpreterPath))

    def _install(self):
        """Install the plugin to the core
        """
        if self._installed:
            return

        self._schemeMenu = core.actionManager().addMenu(self._MENU_PATH, self._FULL_NAME)
        self._evalAction = core.actionManager().addAction("%s/aEval" % self._MENU_PATH,
                                                          "Eval. selection/Save and eval.")
        self._evalAction.setStatusTip("Evaluate selection. If nothing is selected, then save and evaluate whole file.")
        self._evalAction.setShortcut("Ctrl+E")
        self._evalAction.triggered.connect(self._onEvalTriggered)
        self._breakAction = core.actionManager().addAction("%s/aBreak" % self._MENU_PATH, "Stop the interpreter")
        self._breakAction.setStatusTip("Use it as a restart action.")
        self._breakAction.setShortcut("Pause")
        self._breakAction.triggered.connect(self._onBreakTriggered)
        #self._breakAction.setEnabled(False)

        if self._dock is None:
            from .repl import ReplDock
            self._dock = ReplDock(self._DOCK_TITLE, self._icon())

        core.actionManager().addAction("mView/a%s" % self._LANGUAGE, self._dock.showAction())
        core.mainWindow().addDockWidget(Qt.BottomDockWidgetArea, self._dock)

        self._installed = True

    def uninstall(self):
        """Terminate the plugin. Method called by core, when closing Enki, and sometimes by plugin itself
        """
        if not self._installed:
            return
        core.actionManager().removeAction(self._evalAction)
        self._evalAction = None
        core.actionManager().removeAction(self._breakAction)
        self._breakAction = None
        core.actionManager().removeMenu(self._MENU_PATH)

        core.actionManager().removeAction("mView/a%s" % self._LANGUAGE)
        core.mainWindow().removeDockWidget(self._dock)

        self._installed = False


class _PythonReplPlugin(_AbstractReplPlugin):
    """Standard ML REPL sub-plugin
    """
    instance = None

    _LANGUAGE = "Python"
    _FULL_NAME = "iPython"
    _MENU_PATH = "mPython"
    _DOCK_TITLE = "iPython &Interpreter"

    def __init__(self):
        # if config file is old, add own settings
        if 'Python' not in core.config()['Modes']:
            core.config()['Modes']['Python'] = {'Enabled': 'whenOpened',
                                                'InterpreterPath': 'python -i'}

        _AbstractReplPlugin.__init__(self)


class Plugin:
    """Module implementation
    """

    def __init__(self):
        self._pythonSubPlugin = _PythonReplPlugin()

    def terminate(self):
        self._pythonSubPlugin.terminate()
