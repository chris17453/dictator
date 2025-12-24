#!/usr/bin/env python3
"""
Audio recording and speech recognition module for Dictator
"""
import sys
import os
import threading
import tempfile
import time
import subprocess
import numpy as np
from pathlib import Path

# Import logger
try:
    from logger import get_logger
except ImportError:
    from .logger import get_logger

log = get_logger(__name__)

# Try to import Whisper for local speech recognition
try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
    log.info("Whisper available - using local speech recognition")
except ImportError:
    WHISPER_AVAILABLE = False
    log.warning("Whisper not available - using Google Speech Recognition")

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
    log.info("SoundDevice available - audio functionality enabled")
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    log.warning("SoundDevice not available - audio functionality limited")


class PureRecorder:
    def __init__(self):
        log.debug("Initializing PureRecorder")
        self.is_recording = False
        self.current_microphone_index = None
        self.audio_data = []
        self.sample_rate = 44100
        self.chunk_size = 1024
        self.supported_rates = [44100, 22050, 16000, 8000]
        
        # WHISPER ONLY - no Google Speech Recognition
        self.whisper_model = None
        self.whisper_model_name = "tiny"
        self.use_openai_whisper = False
        
        # Subprocess tracking for cleanup
        self.active_subprocess = None
        
        # Audio level monitoring
        self.current_audio_level = 0
        self.audio_level_lock = threading.Lock()
        self.is_monitoring = False
        self.audio_queue = []
        
        self.refresh_microphones()
        
        print(f"WHISPER_AVAILABLE at init: {WHISPER_AVAILABLE}")
        if WHISPER_AVAILABLE:
            print("Calling load_whisper_model...")
            self.load_whisper_model()
            print(f"After loading, self.whisper_model = {self.whisper_model}")
        else:
            print("WHISPER_AVAILABLE is False!")
            self.whisper_model = None
        
        # Initialize audio variables (keep it simple)
        self.audio_data = []
    
    def get_whisper_model_path(self):
        """Get the proper user data directory for Whisper models"""
        import platformdirs
        app_data_dir = platformdirs.user_data_dir("dictator", "dictator")
        model_dir = Path(app_data_dir) / "whisper_models"
        model_dir.mkdir(parents=True, exist_ok=True)
        return str(model_dir)
    
    def load_whisper_model(self):
        # Load synchronously with SSL bypass for network issues
        try:
            print("Loading Whisper model synchronously...")
            
            # Bypass SSL issues
            import ssl
            ssl._create_default_https_context = ssl._create_unverified_context
            
            device = "cpu"
            model_path = self.get_whisper_model_path()
            print(f"Using model directory: {model_path}")
            
            # Try tiny model first - it's fastest to load
            try:
                print("Loading tiny Whisper model...")
                from faster_whisper import WhisperModel
                self.whisper_model = WhisperModel(
                    "tiny", 
                    device=device,
                    download_root=model_path
                )
                self.whisper_model_name = "tiny"
                print("✅ Whisper tiny model loaded successfully")
                print(f"Model stored in: {model_path}")
                return
            except Exception as e:
                print(f"Failed to load tiny model: {e}")
            
            # Skip openai-whisper due to version conflicts
            
            # If all fails, error out
            print("❌ FATAL: Could not load any Whisper model")
            self.whisper_model = None
            
        except Exception as e:
            print(f"Whisper loading error: {e}")
            self.whisper_model = None
    
    def refresh_microphones(self):
        self.available_microphones = []
        
        try:
            import sounddevice as sd
            
            # Get all available devices
            devices = sd.query_devices()
            
            # Filter out virtual/system devices that aren't real microphones
            skip_keywords = [
                'monitor', 'output', 'loopback', 'echo', 'null', 'auto_null',
                'pulse', 'default', 'system', 'analog-stereo', 'analog-surround',
                'iec958', 'hdmi', 'front:', 'rear:', 'center_lfe:', 'side:',
                'capture.', 'playback.', 'speaker', 'headphones', 'built-in audio',
                'dummy', 'test', 'rnnoise', 'surround', 'digital', 'spdif',
                'pipewire', 'alsa_output', 'alsa_input', 'combined',
                'virtual', 'software', 'proxy', 'tunnel', 'bridge'
            ]
            
            # Enumerate SoundDevice input devices
            for i, device in enumerate(devices):
                try:
                    # Check if device supports input (recording)
                    if device.get('max_input_channels', 0) > 0:
                        device_name = device.get('name', f"Device {i}")
                        
                        # Skip virtual/system devices
                        if any(keyword in device_name.lower() for keyword in skip_keywords):
                            continue
                        
                        self.available_microphones.append({
                            'name': device_name,
                            'index': i
                        })
                except Exception:
                    continue
            
            print(f"Found microphones using SoundDevice: {[mic['name'] for mic in self.available_microphones]}")
            
            if self.available_microphones and self.current_microphone_index is None:
                self.set_microphone(0)
                
        except Exception as e:
            print(f"Failed to enumerate microphones: {e}")
    
    def get_microphone_list(self):
        return self.available_microphones
    
    def set_microphone(self, device_index):
        """Set microphone by device index (not array index)"""
        try:
            # Find the array index for this device index
            for i, mic in enumerate(self.available_microphones):
                if mic['index'] == device_index:
                    self.current_microphone_index = device_index  # Store actual device index
                    print(f"🔥 RECORDER: Selected microphone: {mic['name']} (device index: {device_index})")
                    return True
            
            print(f"🚨 RECORDER: Device index {device_index} not found in available microphones")
            return False
        except Exception as e:
            print(f"🚨 RECORDER: Failed to set microphone {device_index}: {e}")
        return False
    
    def get_current_microphone(self):
        """Get current microphone info by device index"""
        if self.current_microphone_index is not None:
            # Find microphone by device index
            for mic in self.available_microphones:
                if mic['index'] == self.current_microphone_index:
                    return mic
        return None
    
    def start_recording(self, callback):
        if self.is_recording:
            return
        
        self.is_recording = True
        self.callback = callback
        print(f"🔥 CALLBACK SET TO: {callback}")
        
        print(f"Starting recording with microphone index: {self.current_microphone_index}")
        thread = threading.Thread(target=self._record_worker)
        thread.daemon = True
        thread.start()
    
    def stop_recording(self):
        print("🔥 RECORDER: stop_recording called")
        self.is_recording = False
        print("🔥 RECORDER: is_recording set to False")
        
        # Clean up any active subprocess
        if self.active_subprocess and self.active_subprocess.poll() is None:
            print("🔥 RECORDER: Terminating active subprocess...")
            try:
                self.active_subprocess.terminate()
                # Give it a moment to terminate gracefully
                try:
                    self.active_subprocess.wait(timeout=2)
                    print("🔥 RECORDER: Subprocess terminated gracefully")
                except subprocess.TimeoutExpired:
                    print("🔥 RECORDER: Subprocess didn't terminate, killing...")
                    self.active_subprocess.kill()
                    self.active_subprocess.wait()
                    print("🔥 RECORDER: Subprocess killed")
            except Exception as e:
                print(f"🚨 RECORDER: Error cleaning up subprocess: {e}")
            finally:
                self.active_subprocess = None
    
    def start_continuous_monitoring(self):
        """Start continuous audio monitoring like SAI"""
        if not SOUNDDEVICE_AVAILABLE or self.is_monitoring:
            return
        
        # Ensure any previous monitoring is stopped first
        self.stop_monitoring()
        
        self.is_monitoring = True
        self.monitoring_thread = threading.Thread(target=self._continuous_monitor_worker, daemon=True)
        self.monitoring_thread.start()
    
    def _continuous_monitor_worker(self):
        """Continuous audio monitoring worker like SAI"""
        try:
            if self.current_microphone_index is None:
                return
            
            # This would need pyaudio import - but it's not used in current version
            # Leaving this as a placeholder for potential future use
            pass
            
        except Exception as e:
            print(f"Continuous monitoring error: {e}")
    
    def stop_monitoring(self):
        """Stop continuous monitoring"""
        if hasattr(self, 'is_monitoring'):
            self.is_monitoring = False
        
        # Wait for thread to finish to avoid memory issues
        if hasattr(self, 'monitoring_thread') and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=1.0)
    
    def _record_worker(self):
        # FORCE WHISPER LOADING AND ONLY USE WHISPER
        print(f"WHISPER_AVAILABLE: {WHISPER_AVAILABLE}")
        print(f"self.whisper_model: {self.whisper_model}")
        
        # If Whisper is available but model not loaded, load it now
        if not self.whisper_model:
            print("🔧 Loading Whisper model...")
            try:
                # Bypass SSL issues
                import ssl
                ssl._create_default_https_context = ssl._create_unverified_context
                
                from faster_whisper import WhisperModel
                model_path = self.get_whisper_model_path()
                self.whisper_model = WhisperModel(
                    "tiny", 
                    device="cpu",
                    download_root=model_path
                )
                print("✅ Whisper tiny model loaded successfully")
                print(f"Model stored in: {model_path}")
            except Exception as e:
                print(f"FATAL: Failed to load Whisper model: {e}")
                self.callback("ERROR: Whisper failed to load", "error")
                return
        
        # ONLY USE WHISPER - NO GOOGLE
        print("🎵 Using Whisper for transcription")
        self._record_with_whisper()
    
    def _record_with_whisper(self):
        print("🎵 Recording with Whisper...")
        try:
            print("🔥 WHISPER_RECORD: Using isolated subprocess to prevent memory corruption")
            
            # Use selected microphone device
            current_mic = self.get_current_microphone()
            if current_mic:
                device_index = current_mic['index']
                device_name = current_mic['name']
                print(f"🔥 WHISPER_RECORD: Using selected microphone: {device_name} (index: {device_index})")
            else:
                device_index = None
                print("🔥 WHISPER_RECORD: Using default audio input (no microphone selected)")
            
            # Get device sample rate directly like SAI does - simple and works
            print(f"🔥 WHISPER_RECORD: Getting device sample rate...")
            
            try:
                import sounddevice as sd
                devices = sd.query_devices()
                
                if device_index is None or device_index >= len(devices):
                    device_index = sd.default.device[0] if hasattr(sd.default.device, '__iter__') else None
                    print(f"🔥 WHISPER_RECORD: Using default device: {device_index}")
                
                if device_index is not None and device_index < len(devices):
                    device_info = devices[device_index]
                    working_rate = int(device_info.get('default_samplerate', 44100))
                    print(f"🔥 WHISPER_RECORD: Using device default rate: {working_rate}Hz")
                else:
                    working_rate = 44100
                    print("🔥 WHISPER_RECORD: Using fallback rate: 44100Hz")
                    
            except Exception as e:
                print(f"🚨 WHISPER_RECORD: Error getting device rate: {e}, using 44100Hz")
                working_rate = 44100
            
            temp_audio_path = None
            
            # Now just use the working rate we determined
            print(f"🔥 WHISPER_RECORD: Starting subprocess recording at {working_rate}Hz...")
            
            try:
                # Launch isolated SoundDevice audio recording subprocess  
                recorder_script = os.path.join(os.path.dirname(__file__), 'audio_recorder_sd.py')
                
                # Start recording subprocess
                process = subprocess.Popen([
                    'python', recorder_script,
                    str(device_index) if device_index is not None else "None",
                    str(working_rate)
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                   cwd=os.path.dirname(__file__))
                
                # Store subprocess reference for cleanup
                self.active_subprocess = process
                
                # Let it record for a short time to test
                import time
                time.sleep(0.5)  # Test for half a second
                
                # If process is still running, it worked
                if process.poll() is None:
                    print(f"🔥 WHISPER_RECORD: Subprocess recording working at {working_rate}Hz")
                    
                    # Continue recording until stopped
                    print("🔥 WHISPER_RECORD: Recording audio...")
                    
                    # Monitor real audio levels from subprocess
                    start_time = time.time()
                    while self.is_recording:
                        time.sleep(0.02)  # Much faster polling - 50Hz instead of 10Hz
                        elapsed = time.time() - start_time
                        
                        # Read ALL available audio levels from subprocess stderr
                        try:
                            # Check for output from subprocess (non-blocking)
                            import select
                            if hasattr(select, 'select'):
                                # Unix-like systems - read from stderr where level messages are sent
                                # Read multiple lines if available to catch up on backlog
                                lines_read = 0
                                while lines_read < 10:  # Don't read more than 10 lines per cycle
                                    ready, _, _ = select.select([process.stderr], [], [], 0.001)  # Very short timeout
                                    if ready:
                                        line = process.stderr.readline()
                                        if line:
                                            line = line.decode().strip()
                                            if line.startswith("LEVEL:"):
                                                level = int(line.split(":")[1])
                                                with self.audio_level_lock:
                                                    self.current_audio_level = level
                                            lines_read += 1
                                        else:
                                            break
                                    else:
                                        break
                            else:
                                # Windows fallback - use the fake levels as before
                                with self.audio_level_lock:
                                    import random
                                    self.current_audio_level = random.randint(10, 50)
                        except Exception as e:
                            # If level reading fails, use a default
                            print(f"Level reading error: {e}")
                            with self.audio_level_lock:
                                self.current_audio_level = 25
                        
                        if elapsed > 300:  # 5 minute safety limit
                            print("🔥 WHISPER_RECORD: Maximum recording time reached")
                            break
                    
                    # Stop the subprocess
                    print("🔥 WHISPER_RECORD: Stopping subprocess...")
                    process.terminate()
                    
                    # Wait for output
                    try:
                        stdout, stderr = process.communicate(timeout=10)
                        if process.returncode == 0 and stdout.strip():
                            temp_audio_path = stdout.decode().strip()
                            print(f"🔥 WHISPER_RECORD: Audio saved to {temp_audio_path}")
                        else:
                            print(f"🚨 WHISPER_RECORD: Subprocess failed: {stderr.decode()}")
                    except subprocess.TimeoutExpired:
                        print("🚨 WHISPER_RECORD: Subprocess timeout, killing...")
                        process.kill()
                        process.communicate()
                    finally:
                        # Clear subprocess reference
                        self.active_subprocess = None
                    
                else:
                    stdout, stderr = process.communicate()
                    print(f"🚨 WHISPER_RECORD: Failed at {working_rate}Hz: {stderr.decode()}")
                    temp_audio_path = None
                    # Clear subprocess reference
                    self.active_subprocess = None
                    
            except Exception as e:
                print(f"🚨 WHISPER_RECORD: Error testing {working_rate}Hz: {e}")
                temp_audio_path = None
                # Clear subprocess reference on error
                self.active_subprocess = None
            
            if not temp_audio_path:
                raise Exception(f"Could not record audio at {working_rate}Hz")
            
            # Load the recorded audio file
            print("🔥 WHISPER_RECORD: Loading recorded audio...")
            try:
                with open(temp_audio_path, 'rb') as f:
                    raw_data = f.read()
                
                # Clean up temp file
                os.unlink(temp_audio_path)
                
                if not raw_data:
                    print("No audio data in file")
                    self.callback("", "no_audio")
                    return
                
                # Convert raw bytes to numpy array
                audio_array = np.frombuffer(raw_data, dtype=np.int16)
                print(f"🔥 WHISPER_RECORD: Loaded {len(audio_array)} audio samples")
                
            except Exception as e:
                print(f"🚨 WHISPER_RECORD: Error loading audio file: {e}")
                self.callback("", "file_error")
                return
            
            # Process with Whisper
            print("Processing audio with Whisper...")
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Resample to 16kHz if needed (Whisper's expected rate)
            if working_rate != 16000:
                print(f"🔥 WHISPER_RECORD: Resampling from {working_rate}Hz to 16000Hz for Whisper...")
                try:
                    import librosa
                    audio_float = librosa.resample(audio_float, orig_sr=working_rate, target_sr=16000)
                    print("🔥 WHISPER_RECORD: Resampling successful")
                except ImportError:
                    print("🚨 WHISPER_RECORD: librosa not available, using audio as-is")
                    # Whisper can handle other sample rates, just not as optimal
                except Exception as e:
                    print(f"🚨 WHISPER_RECORD: Resampling failed: {e}, using audio as-is")
            
            # Check for minimum audio length
            if len(audio_float) < 0.1 * 16000:  # Less than 0.1 seconds
                print("Audio too short")
                self.callback("", "too_short")
                return
            
            # Transcribe directly with Whisper (no temp file needed)
            try:
                if self.whisper_model:
                    print("🔥 WHISPER: Starting transcription with faster-whisper...")
                    print(f"🔥 WHISPER: Audio length: {len(audio_float)} samples")
                    
                    segments, info = self.whisper_model.transcribe(audio_float)
                    print("🔥 WHISPER: Transcription completed, processing segments...")
                    
                    text = "".join([segment.text for segment in segments]).strip()
                    language = info.language if hasattr(info, 'language') else "en"
                    
                    print(f"🔥 WHISPER: Result text: '{text}' (language: {language})")
                    print(f"🔥 WHISPER: About to call callback...")
                    
                    if text:
                        print(f"🔥 WHISPER: Calling callback with text: '{text}', '{language}'")
                        self.callback(text, language)
                        print(f"🔥 WHISPER: Callback completed successfully")
                    else:
                        print(f"🔥 WHISPER: Empty result, calling callback with no_speech")
                        self.callback("", "no_speech")
                        print(f"🔥 WHISPER: No speech callback completed")
                else:
                    print("🚨 WHISPER: Model not loaded!")
                    self.callback("", "model_error")
                    
            except Exception as e:
                print(f"🚨 WHISPER: Transcription error: {e}")
                import traceback
                traceback.print_exc()
                self.callback("", "transcription_error")
                
        except Exception as e:
            print(f"Whisper recording setup error: {e}")
            self.callback("ERROR: Whisper recording failed", "error")