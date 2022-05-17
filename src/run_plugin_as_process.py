from __future__ import (unicode_literals, division, absolute_import, print_function)

def main(path_to_ebook, book_id, from_calibre, calibre_libpaths):
    # This function is run in a separate process and can do anything 
    # it likes, including use QWebEngine.
    
    # See uiaction.py show_dialog() for the call which launches this function
    # via self.gui.job_manager.launch_gui_app()

    # This import must happen before creating the Application() object
    
    #from qt.webengine import QWebEngineView
    try:
        from qt.webengine import QWebEngineView
        #print('runproc qt.webengine.QWebEngineView OK')
    except ImportError:
        #print('runproc qt.webengine.QWebEngineView failed')
        from PyQt5.QtWebEngineWidgets import QWebEngineView
            
    from calibre.gui2 import Application
    from calibre_plugins.scrambleebook_plugin.scrambleebook import EbookScramble
    
    app = Application([])
    w = EbookScramble(path_to_ebook, book_id=book_id, from_calibre=from_calibre, calibre_libpaths=calibre_libpaths)
    w.show()
    w.raise_()
    app.exec_()
