import json
from pathlib import Path
from PyQt6.QtCore import QStandardPaths
from PyQt6.QtWidgets import QApplication
import sys

app = QApplication(sys.argv)
config_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / "Lair"
config_path = config_dir / "config.json"

if config_path.exists():
    with open(config_path, 'r', encoding='utf-8') as f:
        with open("dumped_config.json", 'w', encoding='utf-8') as out:
            out.write(f.read())
else:
    with open("dumped_config.json", 'w', encoding='utf-8') as out:
        out.write(f"Config path does not exist: {config_path}")
