"""
Improved PySide6 desktop prototype for Smart Query Assistant.
Run: pip install PySide6
       python desktop_app.py

This version adds a simple stylesheet, improved table and chart behavior,
status bar and progress bar, and layout tweaks for a cleaner UI.
Also supports --raise-on-start CLI flag to temporarily keep the window on top and bring it forward.
"""
from __future__ import annotations
import sys, os
from PySide6 import QtWidgets, QtGui, QtCore

# ensure project src is importable
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from db_client import DBClient
from query_engine import QueryEngine
from config import DB_CONFIG, RESULT_DIR
from settings import load_local_llm_config, save_local_llm_config, SettingsDialog


class QueryWorker(QtCore.QThread):
    finished = QtCore.Signal(dict)

    def __init__(self, question_id: str, question: str, use_cloud: bool = True, parent=None):
        super().__init__(parent)
        self.question_id = question_id
        self.question = question
        self.use_cloud = use_cloud

    def run(self):
        import config
        orig_llm = config.LLM_CONFIG.copy()
        try:
            if not self.use_cloud:
                config.LLM_CONFIG = orig_llm.copy()
                config.LLM_CONFIG['api_key'] = ''
                config.LLM_CONFIG['base_url'] = ''
            db = DBClient(DB_CONFIG)
            engine = QueryEngine(db, RESULT_DIR)
            res = engine.answer(self.question_id, self.question, context={}, turn_index=1)
            db.close()
        except Exception as e:
            res = {
                "question_id": self.question_id,
                "turn_index": 1,
                "question": self.question,
                "status": "error",
                "analysis": f"Exception: {e}",
                "result": [],
                "charts": [],
            }
        finally:
            try:
                config.LLM_CONFIG = orig_llm
            except Exception:
                pass
        self.finished.emit(res)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, raise_on_start: bool = False):
        super().__init__()
        self.raise_on_start = raise_on_start
        self.setWindowTitle('Smart Query Assistant')
        self.resize(1100, 750)

        if self.raise_on_start:
            # keep on top briefly to help acceptance screenshots
            self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)

        # basic app stylesheet (simple, non-invasive)
        qss = '''
        QWidget { font-family: "Segoe UI", Arial, sans-serif; font-size: 10pt; color: #111; background-color: #f6f8fa; }
        QLabel { color: #111; }
        QLineEdit, QTextEdit { background: #ffffff; color: #111; }
        QTableWidget { background: #ffffff; color: #111; gridline-color: #e6e6e6; alternate-background-color: #f7f9fc; }
        QHeaderView::section { background: #f0f0f0; padding: 4px; color: #111; }
        QPushButton { background-color: #1976D2; color: white; border-radius: 4px; padding: 6px 10px; }
        QPushButton:disabled { background-color: #9E9E9E; color: #eee; }
        QProgressBar { height: 12px; border: 1px solid #ccc; border-radius: 6px; background: #fff; }
        '''
        self.setStyleSheet(qss)

        # menu + toolbar
        menubar = self.menuBar()
        file_menu = menubar.addMenu('File')
        settings_action = QtGui.QAction('Settings', self)
        settings_action.triggered.connect(self.open_settings)
        file_menu.addAction(settings_action)

        toolbar = self.addToolBar('Main')
        toolbar.setMovable(False)
        toolbar.addAction(settings_action)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        # top input row
        top = QtWidgets.QHBoxLayout()
        self.input = QtWidgets.QLineEdit()
        self.input.setPlaceholderText('输入问题，例如：2024年净利润前10名是谁')
        self.input.setMinimumHeight(30)
        top.addWidget(self.input)

        self.run_btn = QtWidgets.QPushButton('Run')
        self.run_btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        top.addWidget(self.run_btn)

        self.llm_checkbox = QtWidgets.QCheckBox('Use cloud LLM')
        try:
            from config import LLM_CONFIG
            self.llm_checkbox.setChecked(bool(LLM_CONFIG.get('api_key')))
        except Exception:
            self.llm_checkbox.setChecked(False)
        top.addWidget(self.llm_checkbox)

        self.progressbar = QtWidgets.QProgressBar()
        self.progressbar.setRange(0, 0)  # busy indicator
        self.progressbar.setVisible(False)
        self.progressbar.setFixedWidth(140)
        top.addWidget(self.progressbar)

        layout.addLayout(top)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.setHandleWidth(8)

        # left pane: analysis + table
        left = QtWidgets.QWidget()
        llay = QtWidgets.QVBoxLayout(left)
        llay.setSpacing(6)

        analysis_label = QtWidgets.QLabel('Analysis')
        analysis_label.setStyleSheet('font-weight:600')
        llay.addWidget(analysis_label)

        self.analysis = QtWidgets.QTextEdit()
        self.analysis.setReadOnly(True)
        self.analysis.setMinimumHeight(180)
        llay.addWidget(self.analysis)

        result_label = QtWidgets.QLabel('Result Table')
        result_label.setStyleSheet('font-weight:600')
        llay.addWidget(result_label)

        self.table = QtWidgets.QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        llay.addWidget(self.table)

        splitter.addWidget(left)

        # right pane: chart preview
        right = QtWidgets.QWidget()
        rlay = QtWidgets.QVBoxLayout(right)
        rlay.setSpacing(6)

        chart_label = QtWidgets.QLabel('Chart Preview')
        chart_label.setStyleSheet('font-weight:600')
        rlay.addWidget(chart_label)

        frame = QtWidgets.QFrame()
        frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        frame.setMinimumSize(320, 320)
        f_layout = QtWidgets.QVBoxLayout(frame)

        self.img_label = QtWidgets.QLabel()
        self.img_label.setAlignment(QtCore.Qt.AlignCenter)
        self.img_label.setScaledContents(False)
        f_layout.addWidget(self.img_label)

        rlay.addWidget(frame)
        splitter.addWidget(right)

        splitter.setSizes([700, 380])
        layout.addWidget(splitter)

        # status bar
        self.status = self.statusBar()
        self.status.showMessage('Ready')

        # connections
        self.run_btn.clicked.connect(self.on_run)
        self.current_worker = None

        # if requested, bring window to front shortly after show
        if self.raise_on_start:
            QtCore.QTimer.singleShot(200, self._bring_to_front)

    def _bring_to_front(self):
        try:
            self.raise_()
            self.activateWindow()
            # attempt Win32 topmost toggle to get above fullscreen overlays
            try:
                import ctypes, time
                hwnd = int(self.winId())
                SWP_NOSIZE = 0x0001
                SWP_NOMOVE = 0x0002
                HWND_TOPMOST = -1
                HWND_NOTOPMOST = -2
                # set topmost
                ctypes.windll.user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(HWND_TOPMOST), 0,0,0,0, SWP_NOMOVE | SWP_NOSIZE)
                ctypes.windll.user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
                time.sleep(0.25)
                # remove topmost
                ctypes.windll.user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(HWND_NOTOPMOST), 0,0,0,0, SWP_NOMOVE | SWP_NOSIZE)
            except Exception:
                # fallback to Qt-only approach
                try:
                    self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, False)
                    self.show()
                except Exception:
                    pass
            # ensure flags updated
            try:
                self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, False)
                self.show()
            except Exception:
                pass
        except Exception:
            pass

    def open_settings(self):
        try:
            dlg = SettingsDialog(self)
            if dlg.exec() == QtWidgets.QDialog.Accepted:
                dlg.save()
                try:
                    import config
                    from settings import load_local_llm_config
                    cfg = load_local_llm_config()
                    for k in ('base_url', 'api_key', 'model', 'timeout_sec'):
                        if k in cfg:
                            config.LLM_CONFIG[k if k != 'timeout_sec' else 'timeout_sec'] = cfg.get(k)
                    self.llm_checkbox.setChecked(bool(cfg.get('api_key')))
                except Exception:
                    pass
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Settings', f'Failed to open/save settings: {e}')

    def on_run(self):
        q = self.input.text().strip()
        if not q:
            QtWidgets.QMessageBox.warning(self, 'No question', '请输入查询问题')
            return
        self.run_btn.setEnabled(False)
        self.progressbar.setVisible(True)
        self.status.showMessage('Running...')
        qid = 'UI' + QtCore.QDateTime.currentDateTime().toString('yyyyMMddhhmmss')
        use_cloud = self.llm_checkbox.isChecked()
        self.current_worker = QueryWorker(qid, q, use_cloud=use_cloud)
        self.current_worker.finished.connect(self.on_result)
        self.current_worker.start()

    def on_result(self, res: dict):
        self.run_btn.setEnabled(True)
        self.progressbar.setVisible(False)
        status = res.get('status') or 'done'
        self.status.showMessage(status)

        analysis = res.get('analysis') or ''
        sql = res.get('sql') or ''
        self.analysis.setPlainText(f"SQL: {sql}\n\nAnalysis:\n{analysis}")

        # table
        rows = res.get('result') or []
        if rows and isinstance(rows, list) and len(rows) > 0:
            keys = list(rows[0].keys())
            self.table.setColumnCount(len(keys))
            self.table.setRowCount(len(rows))
            self.table.setHorizontalHeaderLabels(keys)
            for i, r in enumerate(rows):
                for j, k in enumerate(keys):
                    val = r.get(k, '')
                    item = QtWidgets.QTableWidgetItem(str(val))
                    item.setFlags(item.flags() ^ QtCore.Qt.ItemIsEditable)
                    self.table.setItem(i, j, item)
        else:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)

        # chart
        charts = res.get('charts') or []
        if charts:
            path = charts[0]
            if os.path.exists(path):
                pix = QtGui.QPixmap(path)
                # scale to fit while preserving aspect ratio
                w = self.img_label.width() or 320
                h = self.img_label.height() or 320
                self.img_label.setPixmap(pix.scaled(w, h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
            else:
                self.img_label.clear()
        else:
            self.img_label.clear()


if __name__ == '__main__':
    # handle --raise-on-start before creating QApplication (avoid Qt arg parsing)
    args = sys.argv[1:]
    raise_on_start = False
    if '--raise-on-start' in args:
        raise_on_start = True
        args.remove('--raise-on-start')
    sys.argv = [sys.argv[0]] + args

    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow(raise_on_start=raise_on_start)
    w.show()
    sys.exit(app.exec())
