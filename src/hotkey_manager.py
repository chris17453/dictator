#!/usr/bin/env python3
"""
Global hotkey management for Dictator
"""
import os


class HotkeyManager:
    def __init__(self, hotkey_combination=None):
        self.listener = None
        self.is_running = False
        self.pressed_keys = set()
        self.hotkey_active = False
        self.callback = None
        self.release_callback = None
        self.last_callback_success = True
        
        # Set default or provided hotkey combination
        self.hotkey_combination = hotkey_combination or ["Ctrl", "Space"]
        self.required_keys = self._parse_hotkey_combination()
        
    def set_hotkey(self, hotkey_combination):
        """Set a new hotkey combination"""
        print(f"🔥 HOTKEY: Setting hotkey to: {hotkey_combination}")
        self.hotkey_combination = hotkey_combination
        self.required_keys = self._parse_hotkey_combination()
        
        # Restart listener with new hotkey
        if self.is_running:
            self.stop()
            self.start(self.callback, self.release_callback)
    
    def get_hotkey_string(self):
        """Get current hotkey as display string"""
        return " + ".join(self.hotkey_combination)
    
    def _parse_hotkey_combination(self):
        """Parse hotkey combination into pynput key objects"""
        try:
            from pynput import keyboard
            keys = set()
            
            for key_name in self.hotkey_combination:
                key_name = key_name.lower()
                if key_name == "ctrl":
                    keys.add(keyboard.Key.ctrl_l)
                    keys.add(keyboard.Key.ctrl_r)  # Either ctrl key works
                elif key_name == "alt":
                    keys.add(keyboard.Key.alt_l)
                    keys.add(keyboard.Key.alt_r)
                elif key_name == "shift":
                    keys.add(keyboard.Key.shift_l)
                    keys.add(keyboard.Key.shift_r)
                elif key_name == "space":
                    keys.add(keyboard.Key.space)
                elif key_name == "enter":
                    keys.add(keyboard.Key.enter)
                elif key_name == "tab":
                    keys.add(keyboard.Key.tab)
                elif key_name.startswith("f") and key_name[1:].isdigit():
                    # Function keys F1-F12
                    fn_num = int(key_name[1:])
                    if 1 <= fn_num <= 12:
                        keys.add(getattr(keyboard.Key, f"f{fn_num}"))
                elif len(key_name) == 1:
                    # Single character keys
                    keys.add(keyboard.KeyCode.from_char(key_name.lower()))
            
            return keys
        except ImportError:
            return set()
    
    def start(self, callback, release_callback=None):
        if self.is_running:
            return

        self.callback = callback
        self.release_callback = release_callback
        self.is_running = True
        
        try:
            from pynput import keyboard
            self.listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release
            )
            self.listener.start()
            print(f"🔥 HOTKEY: Started listening for: {self.get_hotkey_string()}")
            
            # Test if hotkey detection is working by checking permissions
            self._test_permissions()
            
        except ImportError:
            print("pynput not available - no global hotkeys")
        except Exception as e:
            print(f"🚨 HOTKEY: Failed to start listener: {e}")
            self._show_permission_help()
    
    def stop(self):
        if not self.is_running:
            return
        
        self.is_running = False
        if self.listener:
            self.listener.stop()
            self.listener = None
        print("🔥 HOTKEY: Stopped listening")
    
    def _is_hotkey_pressed(self):
        """Check if the current hotkey combination is pressed"""
        # Check if at least one key from each modifier group is pressed
        required_groups = {}
        
        # Group the required keys by modifier type
        for key in self.required_keys:
            try:
                from pynput import keyboard
                if key in [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r]:
                    required_groups.setdefault('ctrl', []).append(key)
                elif key in [keyboard.Key.alt_l, keyboard.Key.alt_r]:
                    required_groups.setdefault('alt', []).append(key)
                elif key in [keyboard.Key.shift_l, keyboard.Key.shift_r]:
                    required_groups.setdefault('shift', []).append(key)
                else:
                    # Regular keys
                    required_groups.setdefault('regular', []).append(key)
            except ImportError:
                return False
        
        # Check that at least one key from each group is pressed
        for group_name, group_keys in required_groups.items():
            if not any(key in self.pressed_keys for key in group_keys):
                return False
        
        return True
    
    def _on_key_press(self, key):
        try:
            self.pressed_keys.add(key)
            
            # Mark that we detected a key (for permission testing)
            if hasattr(self, 'test_key_detected'):
                self.test_key_detected = True
            
            if self._is_hotkey_pressed() and not self.hotkey_active:
                self.hotkey_active = True
                print(f"🔥 HOTKEY: Activated - {self.get_hotkey_string()}")
                if self.callback:
                    try:
                        self.callback()
                        self.last_callback_success = True
                    except Exception as e:
                        print(f"Callback failed: {e}")
                        self.last_callback_success = False
                        if not self.last_callback_success:
                            print("UI appears to be dead, force quitting...")
                            os._exit(1)
        except Exception as e:
            print(f"Key press error: {e}")
    
    def _on_key_release(self, key):
        try:
            self.pressed_keys.discard(key)

            # Deactivate when any required key is released
            if self.hotkey_active and key in self.required_keys:
                self.hotkey_active = False
                print(f"🔥 HOTKEY: Deactivated")
                target = self.release_callback if self.release_callback else self.callback
                if target:
                    try:
                        target()
                        self.last_callback_success = True
                    except Exception as e:
                        print(f"Callback failed on release: {e}")
                        self.last_callback_success = False
        except Exception as e:
            print(f"Key release error: {e}")
    
    def _test_permissions(self):
        """Test if we have permissions to detect keyboard input"""
        import threading
        import time
        
        # Quick test to see if we can detect input
        self.test_key_detected = False
        
        def test_input():
            time.sleep(0.1)  # Give a moment
            if not self.test_key_detected:
                # No key events detected, likely a permission issue
                self._show_permission_help()
        
        # Start a background thread to check permissions
        test_thread = threading.Thread(target=test_input, daemon=True)
        test_thread.start()
    
    def _show_permission_help(self):
        """Show help for fixing permission issues"""
        import subprocess
        import os
        
        # Check if user is in input group
        try:
            groups_output = subprocess.check_output(['groups'], text=True)
            if 'input' not in groups_output:
                print()
                print("🚨 HOTKEY PERMISSIONS ISSUE:")
                print("   Global hotkeys require access to input devices.")
                print("   Your user is not in the 'input' group.")
                print()
                print("💡 To fix this, run the setup script:")
                print("   ~/.local/share/dictator/setup-permissions.sh")
                print("   OR manually: sudo usermod -a -G input $USER")
                print("   Then log out and back in.")
                print()
                print("🔧 Alternative: Run DICTATOR with sudo (not recommended)")
                print("   sudo dictator")
                print()
                print("ℹ️  DICTATOR will work without hotkeys, use the GUI buttons instead.")
                print()
        except Exception:
            print("🚨 HOTKEY: Permission check failed - hotkeys may not work")
            print("ℹ️  Try running: sudo usermod -a -G input $USER")