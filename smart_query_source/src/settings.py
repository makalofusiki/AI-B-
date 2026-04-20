import json
import os
from pathlib import Path
from PySide6 import QtWidgets

LOCAL_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.local.json"


def load_local_llm_config() -> dict:
    try:
        if not LOCAL_CONFIG_PATH.exists():
            return {}
        with LOCAL_CONFIG_PATH.open('r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_local_llm_config(d: dict):
    try:
        with LOCAL_CONFIG_PATH.open('w', encoding='utf-8') as f:
            json.dump(d or {}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Settings')
        self.setMinimumWidth(480)
        layout = QtWidgets.QFormLayout(self)

        self.base_url = QtWidgets.QLineEdit()
        self.api_key = QtWidgets.QLineEdit()
        self.model = QtWidgets.QLineEdit()
        self.timeout = QtWidgets.QSpinBox()
        self.timeout.setRange(1, 120)
        self.timeout.setValue(20)
        self.local_model_path = QtWidgets.QLineEdit()
        self.use_local_model = QtWidgets.QCheckBox('Use local model')

        layout.addRow('LLM Base URL', self.base_url)
        layout.addRow('LLM API Key', self.api_key)
        layout.addRow('LLM Model', self.model)
        layout.addRow('Timeout (s)', self.timeout)
        layout.addRow('Local model path', self.local_model_path)
        layout.addRow('', self.use_local_model)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

        self.load()

    def load(self):
        cfg = load_local_llm_config()
        self.base_url.setText(cfg.get('base_url',''))
        self.api_key.setText(cfg.get('api_key',''))
        self.model.setText(cfg.get('model',''))
        try:
            self.timeout.setValue(int(cfg.get('timeout_sec',20)))
        except Exception:
            self.timeout.setValue(20)
        self.local_model_path.setText(cfg.get('local_model_path',''))
        self.use_local_model.setChecked(bool(cfg.get('use_local_model', False)))

    def save(self):
        d = {
            'base_url': self.base_url.text().strip(),
            'api_key': self.api_key.text().strip(),
            'model': self.model.text().strip(),
            'timeout_sec': int(self.timeout.value()),
            'local_model_path': self.local_model_path.text().strip(),
            'use_local_model': bool(self.use_local_model.isChecked()),
        }
        save_local_llm_config(d)
