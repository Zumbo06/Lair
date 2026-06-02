# tracker.py

import time
import os
import subprocess

try:
    import psutil
except ImportError:
    psutil = None

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from config import ConfigManager

class PlaytimeTracker(QObject):
    playtime_updated = pyqtSignal(str, float) # Returns (game_hash, duration)

    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self.active_sessions = {}  # {game_hash: { 'start_time': float, 'pids': [int], 'exe_target': str, 'game_dir': str }}
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_active_processes)
        self.timer.start(5000) # Check process tree every 5 seconds

    def start_tracking(self, game_hash, launch_result, tracking_exe=None, game_dir=None):
        if not psutil:
            print("Tracking disabled: psutil not installed.")
            return

        pids = []
        if isinstance(launch_result, subprocess.Popen):
            pids.append(launch_result.pid)
        elif isinstance(launch_result, int) and launch_result > 0:
            pids.append(launch_result)
            
        exe_target = tracking_exe
        if tracking_exe:
            exe_target = os.path.normpath(tracking_exe).lower()
            
        dir_target = game_dir
        if game_dir:
            dir_target = os.path.normpath(game_dir).lower()

        # Stop existing tracker for this game if any
        if game_hash in self.active_sessions:
            self.stop_tracking(game_hash)

        self.active_sessions[game_hash] = {
            'start_time': time.time(),
            'pids': pids,
            'exe_target': exe_target,
            'game_dir': dir_target,
            'grace_periods': -6  # Give 30s initial startup grace period (6 intervals * 5s) for games/launchers to boot
        }
        print(f"Started playtime tracking for game {game_hash} (PIDs: {pids}, Exe: {exe_target})")

    def check_active_processes(self):
        if not psutil or not self.active_sessions:
            return

        running_pids = set()
        try:
            for p in psutil.process_iter(['pid', 'name', 'exe']):
                running_pids.add(p.info['pid'])
        except Exception as e:
            print(f"Error listing system processes: {e}")
            return

        finished_games = []

        for game_hash, session in list(self.active_sessions.items()):
            is_running = False
            
            # 1. Check if tracked PIDs are still running
            for pid in session['pids']:
                if pid in running_pids:
                    try:
                        p_obj = psutil.Process(pid)
                        if p_obj.is_running() and p_obj.status() != psutil.STATUS_ZOMBIE:
                            is_running = True
                            # Proactively add all child PIDs recursively to track sub-processes
                            for child in p_obj.children(recursive=True):
                                if child.pid not in session['pids']:
                                    session['pids'].append(child.pid)
                    except:
                        pass

            # 2. Precise Scanning: If launcher exited, scan system for executables running in the game folder
            if not is_running:
                try:
                    for p in psutil.process_iter(['pid', 'exe', 'name']):
                        exe_path = p.info['exe']
                        if not exe_path:
                            continue
                        norm_exe = os.path.normpath(exe_path).lower()
                        
                        # Match by folder/directory path
                        if session['game_dir'] and norm_exe.startswith(session['game_dir']):
                            is_running = True
                            if p.info['pid'] not in session['pids']:
                                session['pids'].append(p.info['pid'])
                                
                        # Match by targeted executable filename
                        elif session['exe_target'] and norm_exe == session['exe_target']:
                            is_running = True
                            if p.info['pid'] not in session['pids']:
                                session['pids'].append(p.info['pid'])
                except:
                    pass

            if is_running:
                # Reset grace period if process found
                session['grace_periods'] = 0
            else:
                # Apply 15-second grace period (3 intervals * 5s) to prevent early closure when launchers restart games
                session['grace_periods'] += 1
                if session['grace_periods'] >= 3:
                    finished_games.append(game_hash)

        # Finalize finished tracking sessions
        for game_hash in finished_games:
            self.stop_tracking(game_hash)

    def stop_tracking(self, game_hash):
        session = self.active_sessions.pop(game_hash, None)
        if not session:
            return
            
        duration = time.time() - session['start_time']
        
        # Deduct grace period time (15s) from recorded duration
        duration = max(0, duration - (session['grace_periods'] * 5))
        
        if duration > 10:  # Only save sessions longer than 10 seconds to avoid noise
            # Update sessions database in config
            metadata = self.config_manager.config["game_metadata"].setdefault(game_hash, {})
            sessions = metadata.setdefault("sessions", [])
            sessions.append({
                "timestamp": time.time(),
                "duration": duration
            })
            
            # Recalculate total playtime
            total_playtime = sum(s.get("duration", 0) for s in sessions)
            metadata["playtime"] = total_playtime
            
            self.config_manager.save_config()
            self.playtime_updated.emit(game_hash, total_playtime)
            print(f"Finished tracking for game {game_hash}. Added session: {int(duration)} seconds. Total playtime: {total_playtime / 3600:.2f} hrs.")
        else:
            print(f"Tracking session discarded for game {game_hash} (duration too short: {int(duration)}s)")
