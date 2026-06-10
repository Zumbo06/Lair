import json
from pathlib import Path
from PyQt6.QtCore import QStandardPaths
from PyQt6.QtWidgets import QApplication
import sys

app = QApplication(sys.argv)
config_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / "EmulatorHub"
config_path = config_dir / "config.json"

if config_path.exists():
    with open(config_path, 'r', encoding='utf-8') as f:
        print(f.read())
else:
    print(f"Config path does not exist: {config_path}")
