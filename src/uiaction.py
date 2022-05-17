from __future__ import (unicode_literals, division, absolute_import, print_function)

__license__   = 'GPL v3'
__copyright__ = '2011, Kovid Goyal <kovid@kovidgoyal.net>'
__docformat__ = 'restructuredtext en'

'''if False:
    # This is here to keep my python error checker from complaining about
    # the builtin functions that will be defined by the plugin loading system
    # You do not need this code in your plugins
    get_icons = get_resources = None'''

import os

try:
    from qt.core import (
        QMenu, QToolButton, QIcon,
        QDialog, QLabel, QDialogButtonBox,
        QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton)
except ImportError:
    from PyQt5.Qt import (
        QMenu, QToolButton, QIcon,
        QDialog, QLabel, QDialogButtonBox,
        QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton)

# The class that all interface action plugins must inherit from
from calibre.gui2.actions import InterfaceAction
from calibre.gui2 import error_dialog

from calibre_plugins.scrambleebook_plugin import PLUGIN_NAME, PLUGIN_CAPTION, PLUGIN_DESCRIPTION
from calibre_plugins.scrambleebook_plugin.scrambleebook import get_fileparts, find_icon

OK_FORMATS = ('AZW3', 'EPUB', 'KEPUB')

class ScrambleEbookUiAction(InterfaceAction):
    name = PLUGIN_NAME

    # Declare the main action associated with this plugin
    # The keyboard shortcut can be None if you dont want to use a keyboard
    # shortcut. Remember that currently calibre has no central management for
    # keyboard shortcuts, so try to use an unusual/unused shortcut.
    
    # Create our top-level menu/toolbar action (text, icon_path, tooltip, keyboard shortcut)
    ttip = '%s\n(%s)' % (PLUGIN_DESCRIPTION, ','.join(OK_FORMATS))
    action_spec = (PLUGIN_NAME, None, ttip, ())
    popup_type = QToolButton.MenuButtonPopup
    #popup_type = QToolButton.InstantPopup
    action_type = 'current'
    dont_add_to = frozenset([])
    dont_remove_from = frozenset([])

    def genesis(self):
        # This method is called once per plugin, do initial setup here
        
        self.is_library_selected = True
        #self.menu = QMenu(self.gui)
        
        # Set the icon for this interface action
        # The get_icons function is a builtin function defined for all your
        # plugin code. It loads icons from the plugin zip file. It returns
        # QIcon objects, if you want the actual data, use the analogous
        # get_resources builtin function.
        #
        # Note that if you are loading more than one icon, for performance, you
        # should pass a list of names to get_icons. In this case, get_icons
        # will return a dictionary mapping names to QIcons. Names that
        # are not found in the zip file will result in null QIcons.
        
        self.icons = get_icons(['images/plugin_icon.png',
                                'images/azw3.png',
                                'images/epub.png',
                                'images/kepub.png',
                                'images/azw3.svg',
                                'images/epub.svg',
                                'images/kepub.svg'
                                ])
        # The qaction is automatically created from the action_spec defined above
        #self.rebuild_menu()
        #self.qaction.setMenu(self.menu)
        
        icon = find_icon('images/plugin_icon.png')
        self.qaction.setIcon(icon)
        if hasattr(self, 'shortcut_action_for_context_menu'):
            self.shortcut_action_for_context_menu.setIcon(icon)
        self.qaction.triggered.connect(self.show_dialog)
        
    def location_selected(self, loc):
        self.is_library_selected = loc == 'library'

    '''def library_changed(self, db):
        self.rebuild_menu()
            
    def rebuild_menu(self):
        m = self.menu
        m.clear()

    def apply_settings(self):
        # In an actual non trivial plugin, you would probably need to
        # do something based on the settings in prefs, e.g. rebuild menus
        # prefs
        pass
        
    def show_configuration(self):
        self.interface_action_base_plugin.do_user_config(self.gui)
    '''

    def show_dialog(self):
        #base_plugin_object = self.interface_action_base_plugin
        #do_user_config = base_plugin_object.do_user_config
        
        class SelectedBookError(Exception): pass
        
        # Selected book checks. If error raise SelectedBookError
        # Get book from currently selected row. Only single row is valid
        try:
            rows = self.gui.current_view().selectionModel().selectedRows()
            
            if not rows or len(rows) == 0:
                errmsg = 'No book selected'
                raise SelectedBookError(errmsg)
                
            if len(rows) > 1:
                errmsg = 'More than one book selected'
                raise SelectedBookError(errmsg)
                
            if self.is_library_selected:
                # book is in calibre library
                book_ids = self.gui.library_view.get_selected_ids()
                book_id = book_ids[0]
                
                db = self.gui.current_db.new_api
                
                # check which formats exist and select one
                avail_fmts = db.formats(book_id, verify_formats=True)
                valid_fmts = [f for f in OK_FORMATS if f in avail_fmts]
                
                if len(valid_fmts) > 1:
                    seldlg = EbookSelectFormat(self.gui, valid_fmts, self.gui)
                    if seldlg.exec_():
                        valid_fmts = seldlg.result
                    
                try:
                    fmt = valid_fmts[0]
                    path_to_ebook = db.format(book_id, fmt, as_path=True, preserve_filename=True)
                except:
                    path_to_ebook = None

                if path_to_ebook is None:
                    errmsg = 'No %s available for this book' % ','.join(OK_FORMATS)
                    raise SelectedBookError(errmsg)
            else:
                # book is on device
                paths = self.gui.current_view().model().paths(rows)
                path_to_ebook = paths[0]
                book_id = None
                
                x, x, ext, x = get_fileparts(path_to_ebook)
                if not ext.upper() in OK_FORMATS:
                    errmsg = 'Only books with file extensions %s are valid.\n\n' % ','.join(OK_FORMATS)
                    errmsg += '%s\nnot valid for this plugin' % path_to_ebook
                    raise SelectedBookError(errmsg)
            
        except SelectedBookError as err:
            return error_dialog(self.gui, 
                    '%s: Book selection error' % self.name,
                    str(err), show=True)
                                    
        # selection OK, proceed with action
            
        # get paths to all known calibre libraries
        excl = list(self.gui.iactions['Choose Library'].stats.stats.keys())
        calibre_libpaths = [os.path.abspath(k) for k in excl]
        
        # view main dialog via cli_main()
        #from calibre.debug import run_calibre_debug
        #run_calibre_debug('--run-plugin', 'ScrambleEbook', path_to_ebook, str(book_id), 'True')
        
        try:
            # calibre 4 beta onwards
            # view main dialog via launching a separate process which can access QtWebEngine
            # NB: if name of function in run_plugin_as_process.py is 'main' 
            #     then the 'func' parameter below is not needed
            self.gui.job_manager.launch_gui_app('webengine-dialog',
                kwargs={
                    'module':'calibre_plugins.scrambleebook_plugin.run_plugin_as_process',
                    # 'func': 'main',
                    'path_to_ebook':path_to_ebook,
                    'book_id':book_id,
                    'from_calibre':True,
                    'calibre_libpaths':calibre_libpaths
                    }
                )
        except:
            # calibre 3.x.x
            # view main dialog as standard UI plugin
            from calibre_plugins.scrambleebook_plugin.scrambleebook import EbookScramble
            dlg = EbookScramble(
                    path_to_ebook,
                    book_id=book_id,
                    from_calibre=True,
                    calibre_libpaths=calibre_libpaths,
                    parent=self.gui)
            dlg.exec_()


class EbookSelectFormat(QDialog):
    # select a single format if >1 suitable to be scrambled
    def __init__(self, gui, formats, parent=None):
        QDialog.__init__(self, parent=parent)
        
        self.gui = gui
        self.formats = formats
        buttonBox = QDialogButtonBox(QDialogButtonBox.Ok)
        
        msg = '\nThis book has multiple formats which could be scrambled.\n' \
            'Please select one of the following:\n'
        label = QLabel(msg)
        
        self.dradio = {}
        for k in self.formats:
            self.dradio[k] = QRadioButton(k)

        gpbox1 = QGroupBox('Formats available:')
        lay1 = QHBoxLayout()
        gpbox1.setLayout(lay1)
        
        for fmt in self.formats:
            lay1.addWidget(self.dradio[fmt])
            
        if 'EPUB' in self.formats:
            self.dradio['EPUB'].setChecked(True)
        else:
            self.dradio[self.formats[0]].setChecked(True)
        
        lay = QVBoxLayout()
        lay.addWidget(label)
        lay.addWidget(gpbox1)
        lay.addStretch()
        lay.addWidget(buttonBox)
        self.setLayout(lay)
        
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        
        self.setWindowTitle('ScrambleEbook: Select a single format')
        icon = find_icon('images/plugin_icon.png')
        self.setWindowIcon(icon)
        
    @property
    def result(self):
        return tuple([k for k in self.formats if self.dradio[k].isChecked()])
