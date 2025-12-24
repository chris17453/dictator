#!/usr/bin/env python3
"""
UI utility classes for Dictator
"""
import os
import time
import threading
from PyQt6.QtCore import QTimer


class UIWatchdog:
    """Watchdog to detect UI crashes and kill the process"""
    def __init__(self, window):
        self.window = window
        self.last_heartbeat = time.time()
        self.is_running = True
        
        # Start watchdog thread
        self.watchdog_thread = threading.Thread(target=self._watchdog_worker, daemon=True)
        self.watchdog_thread.start()
        
        # Start heartbeat timer
        self.heartbeat_timer = QTimer()
        self.heartbeat_timer.timeout.connect(self._heartbeat)
        self.heartbeat_timer.start(1000)  # Heartbeat every 1 second
    
    def _heartbeat(self):
        """Update heartbeat timestamp"""
        self.last_heartbeat = time.time()
    
    def _watchdog_worker(self):
        """Monitor heartbeat and kill process if UI becomes unresponsive"""
        while self.is_running:
            time.sleep(2)  # Check every 2 seconds
            
            # If no heartbeat for 5 seconds, UI is likely dead
            if time.time() - self.last_heartbeat > 5:
                log.error(" UI WATCHDOG: No heartbeat for 5+ seconds - UI appears dead!")
                log.error(" FORCE KILLING PROCESS...")
                os._exit(1)
    
    def stop(self):
        """Stop the watchdog"""
        self.is_running = False
        if hasattr(self, 'heartbeat_timer'):
            self.heartbeat_timer.stop()


class UIUpdateRequest:
    """UI update request like SAI"""
    def __init__(self, action, **kwargs):
        self.action = action
        self.kwargs = kwargs