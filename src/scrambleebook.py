from __future__ import (unicode_literals, division, absolute_import, print_function)
import os
import random
import re
import shutil

from polyglot.builtins import iteritems, iterkeys, itervalues, unicode_type, as_unicode
from polyglot.binary import as_base64_unicode

try:
    from qt.webengine import QWebEngineView as Webview
    print('qt.webengine.QWebEngineView OK')
except ImportError:
    #print('qt.webengine.QWebEngineView failed')
    try:
        from PyQt5.QtWebEngineWidgets import QWebEngineView as Webview
        print('PyQt5.QtWebEngineWidgets.QWebEngineView OK')
    except ImportError:
        #print('PyQt5.QtWebEngineWidgets.QWebEngineView failed')
        try:
            from PyQt5.QtWebKitWidgets import QWebView as Webview
            print('PyQt5.QtWebKitWidgets.QWebView OK')        
        except ImportError:
            #print('PyQt5.QtWebKitWidgets.QWebView failed')
            Webview = None

try:
    from qt.core import (
        QApplication, QDialog, Qt, QLabel, QTextBrowser,
        QDialogButtonBox, QMessageBox, QImage, QCheckBox, QPushButton,
        QFont, QTextCursor, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
        QLineEdit, QIcon, QUrl, QListWidget, QSplitter,
        QTextEdit, QTextDocument)
except ImportError:
    from PyQt5.Qt import (
        QApplication, QDialog, Qt, QLabel, QTextBrowser,
        QDialogButtonBox, QMessageBox, QImage, QCheckBox, QPushButton,
        QFont, QTextCursor, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
        QLineEdit, QIcon, QUrl, QListWidget, QSplitter,
        QTextEdit, QTextDocument)

from calibre.library import db
from calibre.gui2 import (choose_dir, choose_files, error_dialog, warning_dialog)
from calibre.ptempfile import PersistentTemporaryDirectory
from calibre.utils.filenames import ascii_text
from calibre.utils.magick import Image
from calibre.ebooks.oeb.base import (OEB_DOCS, OEB_STYLES, NCX_MIME, SVG_MIME, OEB_RASTER_IMAGES)
from calibre.ebooks.oeb.polish.container import (get_container, clone_container, OEB_FONTS)
from calibre.ebooks.oeb.polish.check.main import run_checks
from calibre.ebooks.oeb.polish.cover import find_cover_image
from calibre.ebooks.oeb.polish.replace import rename_files

from calibre_plugins.scrambleebook_plugin import PLUGIN_NAME, PLUGIN_CAPTION

MR_SETTINGS = {
    'x_dgts': True,
    'x_html': True,
    'keep_num_link': True,
    'x_extlink': False,
    'x_toc': True,
    'x_imgs': True,
    'keep_cover': False,
    'x_fontsno': True,
    'x_fontsob': False,
    'x_meta': True,
    'x_meta_extra': False,
    'x_fnames': False
    }
        
CSSBG = 'background-color: #ebdbc8;'

class EbookScramble(QDialog):
    ''' Read an EPUB/KEPUB/AZW3 de-DRM'd ebook file and 
        scramble various contents '''

    def __init__(self, pathtoebook, book_id=None, from_calibre=False, dsettings={}, calibre_libpaths=[], parent=None):
        QDialog.__init__(self, parent=parent)
        self.gui = parent
        self.pathtoebook = pathtoebook
        self.book_id = book_id
        self.from_calibre = from_calibre
        self.calibre_libpaths = calibre_libpaths
        self.dsettings = MR_SETTINGS.copy()
        self.dsettings.update(dsettings)

        self.ebook = None
        self.eborig = None
        self.cleanup_dirs = []
        self.cleanup_files = []
        self.log = []
        
        self.rename_file_map = {}
        self.meta, self.errors = {}, {}
        self.is_scrambled = False
        self.dummyimg = None
        self.dummysvg = ''
            
        self.setWindowTitle(PLUGIN_CAPTION)
        icon = find_icon('images/plugin_icon.png')
        self.setWindowIcon(icon)
                
        # create widgets
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttonBox.button(QDialogButtonBox.Save).setText('Save scrambled ebook && Exit')
        self.buttonBox.button(QDialogButtonBox.Save).setIcon(icon)
            
        self.browser = QTextBrowser()
        self.browser.setText('')
        try:
            self.browser.setLineWrapMode(QTextBrowser.LineWrapMode.NoWrap)
        except AttributeError:
            self.browser.setLineWrapMode(QTextBrowser.NoWrap)
        self.browser.setMinimumWidth(600)
        self.browser.setMinimumHeight(150)
        self.browser.setReadOnly(True)

        self.savefile = QLineEdit()
        self.savefile.setReadOnly(True)

        self.sourcefile = QLineEdit()
        self.sourcefile.setMinimumWidth(100)
        self.sourcefile.setReadOnly(True)
        
        self.browsesource = QPushButton('...')
        self.browsesource.setMaximumWidth(30)
        
        aboutButton = QPushButton('About', self)
        self.runButton = QPushButton('Scramble now')
        previewButton = QPushButton('Preview content')
        if Webview is None:
            previewButton.setEnabled(False)
            previewButton.setToolTip('Preview not currently available for this book')
        
        configButton = QPushButton('Change rules *')
        configButton.setToolTip('Only available in standalone version, not calibre plugin')
        metadataButton = QPushButton('View metadata *')
        metadataButton.setToolTip('Only available in standalone version, not calibre plugin')
        errorsButton = QPushButton('View errors *')
        errorsButton.setToolTip('Only available in standalone version, not calibre plugin')
        
        # layout widgets
        gpsource = QGroupBox('Source ebook:')
        laysource = QGridLayout()
        gpsource.setLayout(laysource)
        laysource.addWidget(self.sourcefile, 0, 0)
        laysource.addWidget(self.browsesource, 0, 1)

        gptarget = QGroupBox('Scrambled ebook:')
        laytarget = QGridLayout()
        gptarget.setLayout(laytarget)
        laytarget.addWidget(self.savefile, 0, 0)
        
        gpaction = QGroupBox('Actions:')
        layaction = QVBoxLayout()
        gpaction.setLayout(layaction)
        layaction.addWidget(self.runButton)
        layaction.addStretch()
        layaction.addWidget(previewButton)
        layaction.addStretch()
        
        gpextras = QGroupBox('Extras:')
        layaction2 = QVBoxLayout()
        gpextras.setLayout(layaction2)
        layaction2.addWidget(configButton)
        layaction2.addWidget(metadataButton)
        layaction2.addWidget(errorsButton)
        
        layaction3 = QVBoxLayout()
        layaction3.addWidget(aboutButton)
        layaction3.addStretch()
        layaction3.addWidget(gpextras)
        
        grid = QGridLayout()
        grid.addWidget(self.browser, 0, 0)
        grid.addLayout(layaction3, 0, 1)
        grid.addWidget(gpsource, 2, 0)
        grid.addWidget(gptarget, 3, 0)
        grid.addWidget(gpaction, 2, 1, 2, 1)
        grid.addWidget(self.buttonBox, 5, 0, 1, 2)
        self.setLayout(grid)
        
        # create connect signals/slots
        aboutButton.clicked.connect(self.aboutButton_clicked)
        self.runButton.clicked.connect(self.create_scramble_book)
        previewButton.clicked.connect(self.preview_ebook)
        configButton.clicked.connect(self.change_rules)
        metadataButton.clicked.connect(self.view_metadata)
        errorsButton.clicked.connect(self.view_errors)
        self.browsesource.clicked.connect(self.choose_source_ebook)
        
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        if self.from_calibre:
            gpextras.setVisible(False) # Extras not available in calibre plugin
            self.browsesource.setVisible(False) # ebook file selection done by calibre
            
        self.initialise_new_file(self.pathtoebook)
        
    def initialise_new_file(self, pathtoebook):
        self.meta, self.errors = {}, {}
        self.rename_file_map = {}
        self.is_scrambled = False
        self.dummyimg = None
        self.dummysvg = ''
        self.runButton.setEnabled(True)
        self.buttonBox.button(QDialogButtonBox.Save).setEnabled(False)
        
        fileok = True
        if not os.path.isfile(pathtoebook):
            fileok = False
        else:
            try:
                self.ebook = get_container(pathtoebook)
            except:    
                fileok = False
                msg = "Source ebook must be de-DRM'd and in one of these formats:" \
                    "\n- azw3\n- epub\n- kepub\n- kepub.epub.\n\nPlease select another."
                error_dialog(self, PLUGIN_CAPTION,
                    msg, show=True, show_copy_button=True)
        
        if not fileok:
            self.log.append('No ebook selected yet')
        else:
            self.cleanup_dirs.append(self.ebook.root)
            tdir = PersistentTemporaryDirectory('_scramble_clone_orig')
            self.cleanup_dirs.append(tdir)
            self.eborig = clone_container(self.ebook, tdir)
            
            dirn, fname, ext, is_kepub_epub = get_fileparts(self.ebook.path_to_ebook)
            ext = ext.lower()
            format = 'kepub' if is_kepub_epub else ext
            
            if self.book_id is not None: 
                # calibre library book
                self.cleanup_files.append(self.ebook.path_to_ebook)
            sourcepath = self.ebook.path_to_ebook
            
            self.dummyimg = get_resources('images/' + format + '.png')
            self.dummysvg = get_resources('images/' + format + '.svg')

            if self.from_calibre:
                # calibre plugin
                self.dirout = ''
            else:    
                # standalone version
                self.dirout = dirn
                self.log.append('\n--- New ebook: %s' % sourcepath)
                
            fn = fname + '_scrambled.' 
            fn += 'kepub.' + ext if is_kepub_epub else ext
            self.fname_scrambled_ebook = ascii_text(fn)
            self.sourcefile.setText(sourcepath)
            self.savefile.setText(self.fname_scrambled_ebook)
            self.meta['orig'] = get_metadata(self.ebook)
            self.errors['orig'] = get_run_check_error(self.ebook)
            
        self.viewlog()
            
    def accept(self):
        # Any accept actions which need to be done before returning to caller
        savedir = self.choose_save_dir(self.dirout)
        if savedir is not None:
            self.buttonBox.button(QDialogButtonBox.Save).setText('Saving ...')
            self.buttonBox.button(QDialogButtonBox.Save).setEnabled(False)
            msg = ''
            if self.ebook.book_type.lower() == 'azw3':
                msg = '\n   ... please note, rebuilding an AZW3 may take a little longer ...'
            self.log.append('\nSaving now ... %s' % msg)
            self.viewlog()
            path_to_scrambled_ebook = os.path.join(savedir, self.fname_scrambled_ebook)
            self.ebook.commit(path_to_scrambled_ebook)
            self.cleanup()
            QDialog.accept(self)
            
    def reject(self):
        self.cleanup()
        QDialog.reject(self)
                
    def cleanup(self):
        # try to close down cleanly the calibre run_checks process
        try:
            from calibre.ebooks.oeb.polish.check.css import shutdown
            shutdown()
        except:
            pass
        
        # delete calibre plugin temp files
        if self.book_id:
            for f in self.cleanup_files:
                try:
                    os.remove(f)
                except:
                    pass
                    
        if self.from_calibre:            
            for d in self.cleanup_dirs:
                try:
                    shutil.rmtree(d)
                except:
                    pass
    
    def choose_save_dir(self, default_dir):
        savedir = None
        askagain = True
        no_save_dir = False
        exclude_dirs = tuple([path.lower() for path in self.calibre_libpaths])
        if default_dir:
            no_save_dir = True
        title = _('Choose destination directory for scrambled ebook')
        while askagain:
            savedir = choose_dir(window=self, name='', title=title, 
                default_dir=default_dir, no_save_dir=no_save_dir)
            askagain = False
            if savedir is not None:
                savedir = os.path.normpath(savedir)
                if savedir.lower().startswith(exclude_dirs):
                    askagain = True
                    msg = []
                    msg.append('You have selected a destination inside your Calibre library.')
                    msg.append(savedir)
                    msg.append('\nThis is NOT recommended. Try again.')
                    msg.append('\nPlease avoid the following:')
                    [msg.append(path) for path in sorted(self.calibre_libpaths)]
                    warning_dialog(self, 'Calibre library chosen', '\n'.join(msg), show=True, show_copy_button=True)
        return savedir            
        
    def choose_source_ebook(self):
        sf = self.sourcefile.text()
        seldir = get_fileparts(sf)[0] if sf else ''
        title = _('Select source ebook')
        selfiles = choose_files(self, name='', title=title, filters=[('Ebooks', ['epub', 'kepub', 'azw3'])], select_only_single_file=True, default_dir=seldir)
        if selfiles:
            self.pathtoebook = os.path.normpath(selfiles[0])
            self.initialise_new_file(self.pathtoebook)
        
    def create_scramble_book(self):    
        if self.ebook is None:
            return

        sf = self.sourcefile.text()
        
        self.log.append('\nScrambling %s ...' % sf)
        self.viewlog()
        
        scrambler = EbookScrambleAction(self.ebook, self.dsettings, self.dummyimg, self.dummysvg)
        self.rename_file_map = {k:v for (k,v) in iteritems(scrambler.file_map)}
        
        self.meta['scramb'] = get_metadata(self.ebook)
        self.errors['scramb'] = get_run_check_error(self.ebook)
        self.buttonBox.button(QDialogButtonBox.Save).setEnabled(True)
        self.runButton.setEnabled(False)
        self.is_scrambled = True
        
        self.log.append(scrambler.results)
        self.log.append('\n... finished')
        self.viewlog()
        
    def change_rules(self):    
        dlg = EbookScrambleRulesDlg(self.dsettings, parent=self.gui)
        if dlg.exec_():
            self.dsettings.update(dlg.dsettings)
            self.log.append('\n--- Scrambling rules updated ---')
        self.viewlog()
        
    def preview_ebook(self):    
        if self.ebook is None:
            return

        dlg = EbookScramblePreviewDlg(self.ebook, self.eborig, self.is_scrambled, self.rename_file_map, parent=self.gui)
        dlg.exec_()
        dlg.raise_()
        
    def view_metadata(self):    
        if self.ebook is None:
            return

        dlg = EbookScrambleMetadataDlg(self.meta, parent=self.gui)
        dlg.exec_()
        dlg.raise_()
        
    def view_errors(self):    
        if self.ebook is None:
            return

        dlg = EbookScrambleErrorsDlg(self.errors, parent=self.gui)
        dlg.exec_()
        dlg.raise_()
        
    def display_settings(self):
        self.log.append('\nCurrent Scramble rules:')
        [self.log.append('%s: %s' % (k, v)) for (k,v) in sorted(iteritems(self.dsettings))]
        
    def viewlog(self):
        self.browser.setText('\n'.join(self.log))
        try:
            self.browser.moveCursor(QTextCursor.MoveOperation.End)
        except AttributeError:
            self.browser.moveCursor(QTextCursor.End)
        QApplication.instance().processEvents()
            
    def aboutButton_clicked(self):
        # Get the about text from a file inside the plugin zip file
        # The get_resources function is a builtin function defined for all your
        # plugin code. It loads files from the plugin zip file. It returns
        # the bytes from the specified file.
        #
        # Note that if you are loading more than one file, for performance, you
        # should pass a list of names to get_resources. In this case,
        # get_resources will return a dictionary mapping names to bytes. Names that
        # are not found in the zip file will not be in the returned dictionary.
        
        source = 'commandline' if not self.from_calibre else ''
        text = as_unicode(get_resources('about.txt'))
        QMessageBox.about(self, 'About %s %s' % (PLUGIN_CAPTION, source), text)
   
   
class EbookScrambleAction():
    ''' Main scrambling routines '''
    def __init__(self, ebook, dsettings, dummyimg, dummysvg):
        self.eb = ebook
        
        self.dsettings = dsettings.copy()
        self.dummyimg, self.dummysvg = dummyimg, dummysvg
        
        self.lowers = list('abcdefghijklmnopqrstuvwxyz')
        self.uppers = [c.upper() for c in self.lowers]
        self.digits = list('0123456789')
        self.log = []
        self.file_map = {}
        
        self.scramble_main()
            
    @property
    def results(self):
        return '\n'.join(self.log)
        
    def scramble_main(self):
        # NB: an epub3 nav.xhtml file will currently be scrambled by HTML rules not NCX rules
        textnames = get_textnames(self.eb)
        if self.dsettings['x_html']:
            [self.scramble_html(n, scramble_dgts=self.dsettings['x_dgts']) for n in textnames]
            self.log.append('   Scrambled text content')
            
        self.ncxnames = get_ncxnames(self.eb)
        # no need to scramble digits in a TOC    
        if self.dsettings['x_toc']:
            if len(self.ncxnames) > 0:
                self.scramble_toc(self.ncxnames[0], scramble_dgts=False)
                self.log.append('   Scrambled TOC')
            
        svgnames = get_imgnames(self.eb, SVG_MIME)
        imgnames = get_imgnames(self.eb, OEB_RASTER_IMAGES)
        if self.dsettings['x_imgs']:
            cover_img_name = find_cover_image(self.eb, strict=True)
            cover_img_names = []
            if self.dsettings['keep_cover']:
                if cover_img_name:
                    cover_img_names.append(cover_img_name)
            [self.scramble_img(n) for n in imgnames if n not in cover_img_names]
            for svgn in [n for n in svgnames if n not in cover_img_names]:
                #self.eb.remove_item(svgn)
                data = self.eb.parsed(svgn)
                self.eb.replace(svgn, self.dummysvg)
            self.log.append('   Replaced images')
                
            
        fontnames = get_fontnames(self.eb)
        if len(fontnames) > 0 and (self.dsettings['x_fontsno'] or self.dsettings['x_fontsob']):
            self.log.append('   Removed these fonts:')
        if self.dsettings['x_fontsno']:
            # remove non-obfuscated embedded fonts
            for name in [n for n in fontnames if n not in self.eb.obfuscated_fonts]:
                self.eb.remove_item(name)
                self.log.append('      - non-obfuscated font: %s' % name)
        if self.dsettings['x_fontsob']:
            # remove obfuscated embedded fonts
            for name in [n for n in self.eb.obfuscated_fonts]:
                self.eb.remove_item(name)
                self.log.append('      - obfuscated font: %s' % name)
        
        if self.dsettings['x_meta']:
            self.scramble_metadata()
            msg = '   Removed basic metadata'
            if self.dsettings['x_meta_extra']:
                msg += ' & extra metadata'
            self.log.append(msg)
            
        if self.dsettings['x_fnames']:
            spine_names = tuple([n for n in get_spinenames(self.eb) if n not in self.eb.names_that_must_not_be_changed])
            self.scramble_filenames(spine_names, 'txcontent_')
            
            svgnames = get_imgnames(self.eb, SVG_MIME)
            img_names = tuple([n for n in imgnames + svgnames if n not in self.eb.names_that_must_not_be_changed])
            self.scramble_filenames(img_names, 'img_')
            
            css_names = tuple([n for n in get_cssnames(self.eb) if n not in self.eb.names_that_must_not_be_changed])
            self.scramble_filenames(css_names, 'style_')
            
        if self.file_map:        
            rename_files(self.eb, self.file_map)
            self.log.append('   Renamed internal files:')
            [self.log.append('      %s \t--> %s' % (old, self.file_map.get(old, old))) for old in spine_names + img_names + css_names]
        
    def scramble_html(self, name, scramble_dgts=False):
        root = self.eb.parsed(name)
        for e in root.xpath("//*[local-name()='title']"):
            e.text = 'Scrambled'
            
        bodys = root.xpath("//*[local-name()='body']")
        if len(bodys) == 0: return
        
        delinks = {}
        body0 = bodys[0]
        if self.dsettings['x_extlink'] or (self.dsettings['keep_num_link'] and self.dsettings['x_dgts']):
            for anch in body0.xpath('//*[local-name()="a" and @href]'):
                ahref = anch.get('href')
                ahrefname = name if ahref.startswith('#') else self.eb.href_to_name(ahref, name)
                if ahrefname is None:
                    if self.dsettings['x_extlink']:
                        anch.attrib.pop('href')
                elif self.dsettings['keep_num_link'] and self.dsettings['x_dgts']:
                    alltext = []
                    [alltext.append(tx) for tx in anch.itertext('*')]
                    atext = ''.join(alltext)
                    num = [c.lower() != c.upper() for c in atext].count(True)
                    if num < 1:
                        # scramble (text, tail)
                        delinks[anch] = (False, True)
                        for e in anch.iterdescendants('*'):
                            delinks[e] = (False, False)
        
        for be in body0.iterdescendants('*'):
            do_text_tail = delinks.get(be, (True, True))
            self.scramble_ele(be, scramble_dgts, do_text_tail=do_text_tail)
            
        self.eb.dirty(name)
                
    def scramble_toc(self, name, scramble_dgts=False):
        root = self.eb.parsed(name)
        [self.scramble_ele(e, scramble_dgts) for e in root.xpath("//*[local-name()='text']")]
        self.eb.dirty(name)
            
    def scramble_img(self, name, scramble_dgts=False):
        if self.eb.mime_map[name] in OEB_RASTER_IMAGES:
            data = self.eb.parsed(name)
            oldimg = Image()
            oldpath = self.eb.name_to_abspath(name)
            try:
                oldimg.load(data)
                wid, hgt = oldimg.size
            except:
                wid, hgt = (50, 50)
            try:
                fmt = oldimg.format
            except:
                x, x, fmt = get_nameparts(name)
            
            newimg = Image()
            newimg.load(self.dummyimg)
            newimg.size = (wid, hgt)
            
            self.eb.replace(name, newimg.export(fmt.upper()))

            
    def scramble_ele(self, ele, scramble_dgts, do_text_tail=(True, True)):
        do_text, do_tail = do_text_tail
        if do_text:
            ele.text = self.scramble_text(ele.text, scramble_dgts)
        if do_tail:
            ele.tail = self.scramble_text(ele.tail, scramble_dgts)

        
    def scramble_text(self, text, scramble_dgts):
    
        def scramble_char(char, scramble_dgts):
            newchar = char
            if char.upper() != char.lower():
                if char == char.lower():
                    newchar = random.choice(self.lowers)
                elif char == char.upper():
                    newchar = random.choice(self.uppers)
            elif scramble_dgts and char in self.digits:
                newchar = random.choice(self.digits)
            return newchar
            
        if not text: return text    
        return ''.join([scramble_char(char, scramble_dgts) for char in text])

        
    def scramble_filenames(self, names, base):  
        
        def get_newbase(base):
            alpha = 'xab'
            done = False
            i = 0
            newbase = base
            while not done:
                found = False
                for n in fns:
                    if n.startswith(newbase):
                        found = True
                        break
                if not found:
                    done = True
                    break
                else:
                    i += 1    
                    newbase = base + str(i)
            return newbase
            
        if len(names) == 0: return
        
        dgts = len(str(len(names)))
        fns = [get_nameparts(n)[1] for n in names]
        
        newbase = get_newbase(base)        
        
        i = 0
        for name in names:
            dir, fn, ext = get_nameparts(name)
            nname = newbase + str(i).zfill(dgts) + '.' + ext
            if dir:
                nname = '/'.join((dir, nname))
            self.file_map[name] = nname
            i += 1

            
    def scramble_metadata(self):
        
        def reset_package_uid(uidname, uidval): 
            idents = self.eb.opf_xpath('//*[local-name()="identifier" and @id]')
            ident = idents[0] if idents else None
            if pk is not None:
                pk.set('unique-identifier', uidname)
            if ident is not None:    
                ident.set('id', uidname)
                ident.text = uidval
            if len(self.ncxnames) > 0:
                ncxname = self.ncxnames[0]
                ncxroot = self.eb.parsed(ncxname)
                dtbuids = ncxroot.xpath('//*[local-name()="meta" and @name="dtb:uid"]')
                dtbuid = dtbuids[0] if dtbuids else None
                if dtbuid is not None:
                    dtbuid.set('content', uidval)
                    self.eb.dirty(ncxname)
            
        to_remove = []
        pk = None
        
        # remove <metadata> comments found in Amazon books
        for metadata in self.eb.opf_xpath('//opf:metadata'):
            for child in metadata:
                try:
                    tag = child.tag.rpartition('}')[-1]
                except:    
                    to_remove.append(child)
                
        # remove all calibre <meta> items
        for meta in self.eb.opf_xpath('//opf:metadata/opf:meta'):
            if [val for val in itervalues(meta.attrib) if val.startswith('calibre:')]:
                to_remove.append(meta)
                    
        if self.dsettings['x_meta_extra']:
            for meta in self.eb.opf_xpath('//opf:metadata/opf:meta[@property]'):
                if meta.get('property').startswith('dcterms:'):
                    # remove all dcterms <meta> @property items
                    to_remove.append(meta)
                elif meta.get('property')=='file-as':
                    # anonymise all <meta> with property "file-as"
                    meta.text = 'Anon'
            
            #get the <package> unique-identifier
            pk = self.eb.opf_xpath('//opf:package')[0]
            pk_uid = pk.get('unique-identifier')
            
            # remove all dc:identifier except the one which matches package unique-identifier
            for ident in self.eb.opf_xpath('//*[local-name()="metadata"]/*[local-name()="identifier"]'):
                if ident.get('id', '') != pk_uid:
                    to_remove.append(ident)
        
        # remove the elements from <metadata>
        #md = self.eb.opf_xpath('//opf:metadata')[0]
        [child.getparent().remove(child) for child in to_remove]
        
        # obscure some dc: items.
        dcitems = ('description',)
        searchpath = '//*[' + ' or '.join(['local-name()="%s"' % dc for dc in dcitems]) + ']'
        for elem in [e for e in self.eb.opf_xpath(searchpath)]:
            elem.text = '*removed*'
            elem.attrib.clear()
            
        if self.dsettings['x_meta_extra']:
            # obscure more dc: items
            dcitems = ('title', 'creator', 'rights', 'publisher', 'source', 'subject')
            searchpath = '//*[' + ' or '.join(['local-name()="%s"' % dc for dc in dcitems]) + ']'
            for elem in [e for e in self.eb.opf_xpath(searchpath)]:
                # do not remove all attribs. needed for epub3 creator/title
                #elem.attrib.clear()
                if elem.tag.lower().endswith(('title', 'creator')):
                    elem.text = 'Anon'
                elif elem.text is not None:
                    elem.text = '*removed*'
        
        if self.dsettings['x_meta_extra']:
            reset_package_uid('bookid', 'unknown')
            
        self.eb.dirty(self.eb.opf_name)

        
class EbookScrambleRulesDlg(QDialog):
    def __init__(self, dsettings, parent=None):
        QDialog.__init__(self, parent=parent)
        
        self.dsettings = dsettings.copy()
        self.cbkeys = ('x_html', 'x_dgts', 'keep_num_link', 'x_extlink', 'x_toc',
                'x_imgs', 'keep_cover', 'x_fontsno', 'x_fontsob',
                'x_meta', 'x_meta_extra', 'x_fnames')
                
        chkbox_labels = {
        'x_html': 'Scramble book alpha chars',
        'x_dgts': 'Scramble book digits',
        'keep_num_link': '... but keep non-alpha links\n(e.g. numeric footnote links)',
        'x_extlink': 'Remove links to external websites',
        'x_toc': 'Scramble TOC alpha chars (keep digits)',
        'x_imgs': 'Replace images with a dummy image',
        'keep_cover': '... but try to keep cover image',
        'x_fontsno': 'Remove non-obfuscated fonts',
        'x_fontsob': 'Remove obfuscated fonts',
        'x_meta': 'Remove some descriptive metadata\n(e.g. dc:description, calibre)',
        'x_meta_extra': 'Try to remove more metadata\n(e.g. ISBN)',
        'x_fnames': 'Rename to generic filenames (not AZW3)\n(HTML, images, CSS)'
        }
        
        self.setWindowTitle('%s: Configure rules' % PLUGIN_CAPTION)
        self.setWindowIcon(find_icon('images/plugin_icon.png'))
        
        buttonBox = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        
        defButton = QPushButton('Reset to defaults')
        defButton.setMaximumWidth(150)
        
        self.dcheckbox = {}
        for k in self.cbkeys:
            self.dcheckbox[k] = QCheckBox(chkbox_labels[k])
            self.dcheckbox[k].setChecked(self.dsettings[k])
        
        gpbox1 = QGroupBox('Book content')
        cblay1 = QGridLayout()
        gpbox1.setLayout(cblay1)
        gpbox2 = QGroupBox('TOC text')
        cblay2 = QVBoxLayout()
        gpbox2.setLayout(cblay2)
        gpbox3 = QGroupBox('Images')
        cblay3 = QGridLayout()
        gpbox3.setLayout(cblay3)
        gpbox4 = QGroupBox('Fonts')
        cblay4 = QVBoxLayout()
        gpbox4.setLayout(cblay4)
        gpbox5 = QGroupBox('Metadata')
        cblay5 = QGridLayout()
        gpbox5.setLayout(cblay5)
        gpbox6 = QGroupBox('Internal filenames')
        cblay6 = QVBoxLayout()
        gpbox6.setLayout(cblay6)
        
        cblay1.addWidget(self.dcheckbox['x_html'], 0, 0, 1, 3)
        cblay1.addWidget(self.dcheckbox['x_dgts'], 1, 1, 1, 2)
        cblay1.addWidget(self.dcheckbox['keep_num_link'], 2, 2)
        cblay1.addWidget(self.dcheckbox['x_extlink'], 3, 1, 1, 2)
        
        cblay2.addWidget(self.dcheckbox['x_toc'])
        
        cblay3.addWidget(self.dcheckbox['x_imgs'], 0, 0, 1, 2)
        cblay3.addWidget(self.dcheckbox['keep_cover'], 1, 1)
        
        cblay4.addWidget(self.dcheckbox['x_fontsno'])
        cblay4.addWidget(self.dcheckbox['x_fontsob'])
        
        cblay5.addWidget(self.dcheckbox['x_meta'], 0, 0, 1, 2)
        cblay5.addWidget(self.dcheckbox['x_meta_extra'], 1, 1)
        
        cblay6.addWidget(self.dcheckbox['x_fnames'])
        
        lay = QVBoxLayout()
        lay.addWidget(gpbox1)
        lay.addWidget(gpbox2)
        lay.addWidget(gpbox3)
        lay.addWidget(gpbox4)
        lay.addWidget(gpbox5)
        lay.addWidget(gpbox6)
        lay.addStretch()
        lay.addWidget(defButton)
        lay.addWidget(buttonBox)
        self.setLayout(lay)
        
        # create connect signals/slots
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        
        defButton.clicked.connect(self.defButton_clicked)
        self.dcheckbox['x_html'].toggled.connect(self.html_toggled)
        self.dcheckbox['x_dgts'].toggled.connect(self.digits_toggled)
        self.dcheckbox['x_meta'].toggled.connect(self.meta_toggled)
        self.dcheckbox['x_imgs'].toggled.connect(self.images_toggled)
        
    def html_toggled(self, bool):
        if not bool:
            self.dcheckbox['x_dgts'].setChecked(bool)
            self.dcheckbox['keep_num_link'].setChecked(not bool)
            self.dcheckbox['x_extlink'].setChecked(bool)
        else:
            for k in ('x_dgts', 'keep_num_link', 'x_extlink'):
                self.dcheckbox[k].setChecked(self.dsettings[k])
            
        for k in ('x_dgts', 'keep_num_link', 'x_extlink'):
            self.dcheckbox[k].setEnabled(bool)
        
    def meta_toggled(self, bool):
        if not bool:
            self.dcheckbox['x_meta_extra'].setChecked(bool)
        else:
            self.dcheckbox['x_meta_extra'].setChecked(self.dsettings['x_meta_extra'])
            
        for k in ('x_meta_extra',):
            self.dcheckbox[k].setEnabled(bool)
        
    def images_toggled(self, bool):
        if not bool:
            self.dcheckbox['keep_cover'].setChecked(not bool)
        else:
            self.dcheckbox['keep_cover'].setChecked(self.dsettings['keep_cover'])
            
        for k in ('keep_cover',):
            self.dcheckbox[k].setEnabled(bool)
        
    def digits_toggled(self, bool):
        if not bool:
            self.dcheckbox['keep_num_link'].setChecked(not bool)
        else:
            self.dcheckbox['keep_num_link'].setChecked(self.dsettings['keep_num_link'])
            
        for k in ('keep_num_link',):
            self.dcheckbox[k].setEnabled(bool)

    def save_settings(self):
        for k in self.cbkeys:
            self.dsettings[k] = self.dcheckbox[k].isChecked()

    def defButton_clicked(self):
        self.dsettings = MR_SETTINGS.copy()
        [self.dcheckbox[k].setChecked(v) for (k, v) in iteritems(MR_SETTINGS)]
        
    def accept(self):
        # Any accept actions which need to be done before returning to caller
        self.save_settings()
        QDialog.accept(self)

        
class EbookScramblePreviewDlg(QDialog):

    def __init__(self, ebook, orig, is_scrambled, fmap, parent=None):
        QDialog.__init__(self, parent=parent)
        
        try:
            self.setWindowFlags(Qt.WindowType.Window)
        except AttributeError:
            self.setWindowFlags(Qt.Window)
        
        self.orig = orig
        self.ebook = ebook
        self.revfmap = {v:k for (k, v) in iteritems(fmap)}
        
        # create widgets
        lay = QVBoxLayout()
        self.setLayout(lay)
        
        buttonBox = QDialogButtonBox(QDialogButtonBox.Close)
            
        self.webview_orig = Webview()
        self.webview_scram = Webview()
        settings = self.webview_orig.settings()

        # no longer does anything since Webkit replaced by WebEngine
        if hasattr(settings, 'setUserStyleSheetUrl'):
            # QWebView from QtWebKit
            style = 'body {%s}' % CSSBG
            cssurl = 'data:text/css;charset=utf-8;base64,'
            cssurl += as_base64_unicode(style)
            self.webview_orig.settings().setUserStyleSheetUrl(QUrl(cssurl))
            self.webview_scram.settings().setUserStyleSheetUrl(QUrl(cssurl))
        elif hasattr(self.webview_orig, 'setStyleSheet'):
            # QWebEngineView from QtWebEngine
            # setStyleSheet doesn't seem to work at the moment
            self.webview_orig.setStyleSheet('Webview {%s}' % CSSBG)
            self.webview_scram.setStyleSheet('Webview {%s}' % CSSBG)
       
        dummytext = '<body><p>*** Text content could not be displayed ...</p></body>'
        self.webview_orig.setHtml(dummytext)
        self.webview_scram.setHtml(dummytext)
        
        self.htmlList_orig = QListWidget()
        self.htmlList_scram = QListWidget()
        self.htmlList_orig.setMinimumWidth(300)
        self.htmlList_scram.setMinimumWidth(300)

        gpbox1 = QGroupBox()
        lay1 = QHBoxLayout()
        gpbox1.setLayout(lay1)
        lay1.addWidget(self.htmlList_orig)

        gpbox3 = QGroupBox()
        lay3 = QHBoxLayout()
        gpbox3.setLayout(lay3)
        lay3.addWidget(self.htmlList_scram)

        gpbox2 = QGroupBox('Original text content:')
        lay2 = QHBoxLayout()
        gpbox2.setLayout(lay2)
        lay2.addWidget(self.webview_orig)

        gpbox4 = QGroupBox('Original text content:')
        lay4 = QHBoxLayout()
        gpbox4.setLayout(lay4)
        lay4.addWidget(self.webview_scram)
        
        try:
            splitter = QSplitter(Qt.Orientation.Horizontal)
        except AttributeError:
            splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(gpbox1)
        splitter.addWidget(gpbox2)
        splitter.addWidget(gpbox3)
        splitter.addWidget(gpbox4)
        
        lay.addWidget(splitter)
        lay.addWidget(buttonBox)
        
        # create connect signals/slots
        buttonBox.rejected.connect(self.reject)
        self.htmlList_scram.currentRowChanged.connect(self.htmlList_currentRowChanged)
        self.htmlList_scram.itemDoubleClicked.connect(self.htmlList_itemDoubleClicked)
        
        self.htmlList_orig.setEnabled(False)
        self.htmlnames_scram = get_textnames(self.ebook)
        self.htmlnames_orig = tuple([self.revfmap.get(an, an) for an in self.htmlnames_scram])
        
        gpbox1.setTitle('Original HTML files: %s' % len(self.htmlnames_orig))
        gpbox3.setTitle('Original HTML files: %s' % len(self.htmlnames_scram))
        self.htmlList_orig.clear()
        self.htmlList_orig.addItems(self.htmlnames_orig)
        self.htmlList_scram.clear()
        self.htmlList_scram.addItems(self.htmlnames_scram)
        
        if not self.revfmap:
            gpbox1.setVisible(False)
            
        msg = '%s Preview: Original' % PLUGIN_CAPTION
        if not is_scrambled:
            self.setWindowTitle(msg)
            gpbox1.setVisible(False)
            gpbox2.setVisible(False)
        else:
            self.setWindowTitle(msg + ' vs. Scrambled')
            gpbox3.setTitle('Scrambled HTML files: %s' % len(self.htmlnames_scram))
            gpbox4.setTitle('Scrambled text content:')
            
        self.setWindowIcon(find_icon('images/plugin_icon.png'))
            
        self.htmlList_scram.setCurrentRow(0)
        
    def htmlList_currentRowChanged(self, row):
        if row < 0: return
        name = self.htmlList_scram.currentItem().text()
        self.htmlList_orig.setCurrentRow(row)
        self.webview_refresh(name)
        
    def htmlList_itemDoubleClicked(self, item):
        name = item.text()
        self.webview_refresh(name)
        
    def webview_refresh(self, name):
        name_orig = self.revfmap.get(name, name)
            
        abspath_orig = self.orig.name_to_abspath(name_orig)
        abspath = self.ebook.name_to_abspath(name)
        
        if isinstance(self.webview_orig, QTextBrowser):
            self.webview_orig.setSource(QUrl.fromLocalFile(abspath_orig))
            self.webview_scram.setSource(QUrl.fromLocalFile(abspath))
        else:
            self.webview_orig.load(QUrl.fromLocalFile(abspath_orig))
            self.webview_scram.load(QUrl.fromLocalFile(abspath))

        
class EbookScrambleMetadataDlg(QDialog):
    def __init__(self, metadata, parent=None):
        QDialog.__init__(self, parent=parent)
        
        try:
            self.setWindowFlags(Qt.WindowType.Window)
        except AttributeError:
            self.setWindowFlags(Qt.Window)
        
        buttonBox = QDialogButtonBox(QDialogButtonBox.Close)
        
        origbrowser = QTextBrowser()
        origbrowser.setText('')
        origbrowser.setReadOnly(True)
        
        browser = QTextBrowser()
        browser.setText('')
        browser.setReadOnly(True)

        gpbox2 = QGroupBox('Metadata: Original')
        lay2 = QHBoxLayout()
        gpbox2.setLayout(lay2)
        lay2.addWidget(origbrowser)

        gpbox4 = QGroupBox('Metadata: After scrambling')
        lay4 = QHBoxLayout()
        gpbox4.setLayout(lay4)
        lay4.addWidget(browser)
        
        try:
            splitter = QSplitter(Qt.Orientation.Horizontal)
        except AttributeError:
            splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(gpbox2)
        splitter.addWidget(gpbox4)
        splitter.setMinimumHeight(500)
        splitter.setMinimumWidth(1000)
        
        lay = QVBoxLayout()
        self.setLayout(lay)
        lay.addWidget(splitter)
        lay.addWidget(buttonBox)
        
        # create connect signals/slots
        buttonBox.rejected.connect(self.reject)
        
        metaorig = metadata.get('orig', '')
        metaorig = re.sub(r'\n\s*', r'\n     ', metaorig)
        origbrowser.setText(metaorig)
        browser.setText(metadata.get('scramb', ''))
            
        self.setWindowTitle('%s: Metadata' % PLUGIN_CAPTION)
        self.setWindowIcon(find_icon('images/plugin_icon.png'))
        
        if not 'scramb' in metadata:
            gpbox4.setVisible(False)

class EbookScrambleErrorsDlg(QDialog):
    def __init__(self, derrors, parent=None):
        QDialog.__init__(self, parent=parent)
        
        try:
            self.setWindowFlags(Qt.WindowType.Window)
        except AttributeError:
            self.setWindowFlags(Qt.Window)
        self.derrors = derrors
        
        buttonBox = QDialogButtonBox(QDialogButtonBox.Close)
        
        browser = QTextBrowser()
        browser.setText('')
        browser.setFontFamily("Courier")
        #browser.setFontWeight(QFont.Weight.Bold)
        try:
            browser.setLineWrapMode(QTextBrowser.LineWrapMode.NoWrap)
        except AttributeError:
            browser.setLineWrapMode(QTextBrowser.NoWrap)
        browser.setReadOnly(True)
        
        self.ctc_button = QPushButton('Copy to clipboard')
        self.ctc_button.setMaximumWidth(100)
        
        gpbox2 = QGroupBox()
        lay2 = QHBoxLayout()
        gpbox2.setLayout(lay2)
        lay2.addWidget(browser)
        gpbox2.setMinimumHeight(500)
        gpbox2.setMinimumWidth(1000)
        
        lay = QVBoxLayout()
        self.setLayout(lay)
        lay.addWidget(gpbox2)
        lay.addWidget(self.ctc_button)
        lay.addWidget(buttonBox)
        
        buttonBox.rejected.connect(self.reject)
        self.ctc_button.clicked.connect(self.copy_to_clipboard)
           
        self.setWindowTitle('%s: Calibre error checks' % PLUGIN_CAPTION)
        self.setWindowIcon(find_icon('images/plugin_icon.png'))
        
        if 'scramb' in self.derrors:
            msg = 'Original vs. After scrambling'
        else:
            msg = 'Original - ebook not yet scrambled'
            
        gpbox2.setTitle(msg)
        
        self.report = self.summarise_errors()
        browser.setText(self.report)

    def summarise_errors(self):
        log = []
        orig_errors = self.derrors.get('orig', {})
        scramb = self.derrors.get('scramb', {})
        allkeys = set(list(orig_errors.keys()) + list(scramb.keys()))

        if len(allkeys) > 0:
            log.append('Error\nLevel Original  After  Calibre error message')
        else:
            log.append('Calibre CheckBook found no errors')
            
        for lev, msg in sorted(allkeys, reverse=True):
            log.append('{0:5}{2:9}{3:7}  {1}'.format(lev, msg,
                orig_errors.get((lev, msg), 0), 
                scramb.get((lev, msg), 0)))
        return '\n'.join(log)
        
    def copy_to_clipboard(self, *args):
        QApplication.clipboard().setText(
            '%s\n\n%s' % (self.windowTitle(), self.report))
        if hasattr(self, 'ctc_button'):
            self.ctc_button.setText(_('Copied'))
            
# utilities #######################################################

def find_icon(ipath):
    # Find the best icon available for the plugin PNGname supplied
    #   by looking first in config/resources/images 
    #   for custom images for this plugin
    # If no custom image found, use the one in the plugin
    
    # handle nested dirs of plugin images
    pngname = '/'.join(ipath.split('/')[1:])
    pngname = pngname if pngname else ipath
    
    # use calibre standard I function to look for user custom images
    custname = '{0}/{1}'.format(PLUGIN_NAME, pngname)
    cname = I(custname)
    if os.path.exists(cname):
        # use custom image
        icon = QIcon(cname)
    else:
        # use plugin image
        icon = get_icons(ipath)
    return icon

def get_run_check_error(ebook):
    ans = []
    errors = run_checks(ebook)
    for err in errors:
        lev = err.level
        n = err.name
        msg = err.msg
        ans.append((lev, msg, n))
    
    dans = {}
    for lev, msg, n in ans:
        k = (lev, msg)
        dans[k] = dans.get(k, 0) + 1
    return dans

def get_metadata(ebook):
    opf_raw = ebook.raw_data(ebook.opf_name)
    res = re.findall(r'<[^<>]*package.+metadata>', opf_raw, re.I | re.S)
    return res[0] if res else ''
        
def get_textnames(ebook):
    # return doc names in spine order + any non-spine docs (e.g. nav.xhtml)
    names = list(get_spinenames(ebook))
    others = [n for (n, m) in sorted(iteritems(ebook.mime_map)) if m in OEB_DOCS and n not in names]
    return tuple(names + others)
    
def get_spinenames(ebook):
    return tuple([n for (n, lin) in ebook.spine_names])
    
def get_ncxnames(ebook):
    names = [n for (n, m) in iteritems(ebook.mime_map) if m == NCX_MIME]
    if not names:
        [names.append(n) for n in ebook.mime_map if n.rpartition('.')[-1] == 'ncx']
    return tuple(names)
    
def get_imgnames(ebook, mtypes):
    if isinstance(mtypes, unicode_type):
        mtypes = [mtypes]
    return tuple(sorted([n for (n, m) in iteritems(ebook.mime_map) if m in mtypes]))
    
def get_fontnames(ebook):
    # sometimes embedded fonts have an incorrect media-type
    names = set([n for (n, m) in iteritems(ebook.mime_map) if m in OEB_FONTS])
    [names.add(n) for n in ebook.mime_map if n.rpartition('.')[-1] in ('otf', 'ttf')]
    return tuple(sorted(names))
    
def get_cssnames(ebook):
    names = [n for (n, m) in iteritems(ebook.mime_map) if m in OEB_STYLES]
    [names.append(n) for n in ebook.mime_map if n.rpartition('.')[-1] == 'css' and n not in names]
    return tuple(sorted(names))
    
def get_nameparts(name):
    dirname, fe = name.rpartition('/')[0::2]
    fn, ext = fe.rpartition('.')[0::2]
    return (dirname, fn, ext)
    
def get_fileparts(path):
    abspath = os.path.normpath(os.path.abspath(path))
    dirname, basename = os.path.split(abspath)
    fn, ext1 = os.path.splitext(basename)
    ext = ext1.rpartition('.')[-1]
    is_kepub_epub = fn.rpartition('.')[-1].lower() == 'kepub'
    return (dirname, fn, ext, is_kepub_epub)

def main(prog, args):
    # Run the plugin
    
    ebook_path = ''
    if args:
        # Windows Send-to or drag-drop ebook onto .bat
        ebook_path = args[0]

    MY_SETTINGS = {}
    
    ''' un-comment & edit the following if you want your own default settings '''
    #MY_SETTINGS['x_html'] = True        # True = Scramble text content
    #MY_SETTINGS['x_dgts'] = True        # True = Scramble text content digits
    #MY_SETTINGS['keep_num_link'] = True # True = keep non-alpha links (eg footnote links)
    #MY_SETTINGS['x_extlink'] = False    # True = Remove links to external websites  
    #MY_SETTINGS['x_toc'] = True         # True = Scramble TOC text (except digits)
    #MY_SETTINGS['x_imgs'] = True        # True = Replace images with dummy img
    #MY_SETTINGS['keep_cover'] = False   # True = Keep cover img, even if other imgs are replaced
    #MY_SETTINGS['x_fontsno'] = True     # True = Remove non-obfuscated fonts  
    #MY_SETTINGS['x_fontsob'] = False    # True = Remove obfuscated fonts  
    #MY_SETTINGS['x_meta'] = True        # True = Remove basic descriptive metadata
    #MY_SETTINGS['x_meta_extra'] = False # True = Try to remove other metadata which identifies book
    #MY_SETTINGS['x_fnames'] = False     # True = Rename files (HTML, images, CSS) to generic filenames
    
    app = QApplication(args)
    w = EbookScramble(ebook_path, dsettings=MY_SETTINGS)
    w.show()
    w.raise_()
    app.exec_()

if __name__ == "__main__":
    import sys

    main(sys.argv[0], sys.argv[1:])    
    