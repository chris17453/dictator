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
import queue
from pathlib import Path

# Import logger
try:
    from logger import get_logger
except ImportError:
    from .logger import get_logger

log = get_logger(__name__)

# Try to import Whisper for local speech recognition
# Set CT2_USE_EXPERIMENTAL_PACKED_GEMM=0 to avoid potential cuDNN issues
os.environ.setdefault('CT2_USE_EXPERIMENTAL_PACKED_GEMM', '0')

# Check if cuDNN is available before trying to use CUDA
def check_cudnn_available():
    """Check if cuDNN libraries are available"""
    try:
        import ctypes
        import ctypes.util
        # Try to find cuDNN library
        cudnn_lib = ctypes.util.find_library('cudnn')
        if cudnn_lib:
            log.info("cuDNN library found - CUDA acceleration available")
            return True
        else:
            log.warning("cuDNN library not found - will use CPU mode")
            return False
    except Exception as e:
        log.warning(f"Error checking cuDNN: {e} - will use CPU mode")
        return False

# Force CPU mode if cuDNN is not available to prevent CTranslate2 crashes
if not check_cudnn_available():
    log.info("Setting CUDA_VISIBLE_DEVICES=-1 to force CPU mode")
    os.environ['CUDA_VISIBLE_DEVICES'] = '-1'

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
    log.info("Whisper available - using local speech recognition")
except Exception as e:
    WHISPER_AVAILABLE = False
    log.warning(f"Whisper not available: {e}")
    log.info("Will use Google Speech Recognition as fallback")

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
    log.info("SoundDevice available - audio functionality enabled")
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    log.warning("SoundDevice not available - audio functionality limited")


class PureRecorder:
    def __init__(self, thread_pool=None):
        log.debug("Initializing PureRecorder")
        self.is_recording = False
        self.is_paused = False
        self.current_microphone_index = None
        self.audio_data = []
        self.audio_segments = []  # List of temp file paths for pause/resume
        self.sample_rate = 44100
        self.configured_sample_rate = "auto"  # Can be "auto" or a specific rate like 16000, 44100, 48000

        # Preview functionality
        self.preview_audio_data = None  # Stores recorded audio for preview
        self.preview_sample_rate = None  # Stores sample rate for preview playback
        self.chunk_size = 1024
        self.supported_rates = [44100, 22050, 16000, 8000]
        self.max_recording_duration = 300  # Default: 5 minutes

        # Audio history - stores path to last recorded audio file for history
        self.last_recorded_audio_path = None
        self.last_recorded_sample_rate = None

        # Progress callback for transcription
        self.progress_callback = None  # Called with (percent, message) during transcription

        # Confidence score tracking
        self.last_confidence_score = None  # Stores confidence (0-100) from last transcription

        # Custom vocabulary for better recognition
        self.custom_vocabulary = []  # User-defined words/phrases

        # Thread pool for short-lived tasks (recording workers)
        self.thread_pool = thread_pool

        # WHISPER ONLY - no Google Speech Recognition
        self.whisper_model = None
        self.whisper_model_name = "tiny"
        self.use_openai_whisper = False

        # Whisper model configuration (set defaults, will be overridden from config)
        self.whisper_model_size = "tiny"
        self.whisper_model_dir = None  # Will use default if None
        self.whisper_device = "auto"
        self.whisper_language = "auto"  # auto-detect or specific language code

        # Thread safety locks
        self.audio_level_lock = threading.Lock()  # Protects audio_data and current_audio_level
        self.monitoring_lock = threading.Lock()  # Protects is_monitoring flag
        self.model_loading_lock = threading.Lock()  # Protects whisper_model loading
        self.subprocess_lock = threading.Lock()  # Protects active_subprocess

        # Callbacks for UI updates
        self.model_loading_started_callback = None
        self.model_loading_complete_callback = None
        self.recording_lock = threading.Lock()  # Protects recording state

        # Subprocess tracking for cleanup
        self.active_subprocess = None

        # Audio level monitoring
        self.current_audio_level = 0
        self.is_monitoring = False
        self.audio_queue = queue.Queue(maxsize=1000)  # Thread-safe bounded queue

        self.refresh_microphones()

        log.debug(f"WHISPER_AVAILABLE at init: {WHISPER_AVAILABLE}")
        if WHISPER_AVAILABLE:
            log.debug("Calling load_whisper_model...")
            self.load_whisper_model()
            log.debug(f"After loading, self.whisper_model = {self.whisper_model}")
        else:
            log.debug("WHISPER_AVAILABLE is False!")
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
        """
        Load Whisper model synchronously.
        Uses secure SSL by default. If certificate issues occur, install
        system certificates: sudo dnf install ca-certificates (or equivalent)
        """
        try:
            # Enable downloads globally for huggingface_hub
            import os
            import ssl
            import warnings
            os.environ.pop('HF_HUB_OFFLINE', None)  # Remove if set

            # Disable SSL verification if there are certificate issues
            # This is a workaround for systems with certificate problems
            try:
                ssl._create_default_https_context = ssl._create_unverified_context
                # Suppress SSL warnings since we're intentionally disabling verification
                warnings.filterwarnings('ignore', message='Unverified HTTPS request')
                log.debug("SSL verification disabled for model downloads (certificate issues)")
            except Exception:
                pass

            # Try to configure huggingface_hub to allow downloads
            try:
                from huggingface_hub import configure_http_backend
                import requests
                session = requests.Session()
                session.verify = False  # Disable SSL verification
                configure_http_backend(backend_factory=lambda: session)
                log.info("Configured huggingface_hub with SSL verification disabled")
            except Exception as e:
                log.debug(f"Could not configure huggingface_hub backend: {e}")
                pass  # Not critical if this fails

            # Notify UI that loading started
            if self.model_loading_started_callback:
                self.model_loading_started_callback()

            log.info(f"Loading Whisper model: {self.whisper_model_size}")

            # Determine device
            if self.whisper_device == "auto":
                try:
                    import torch
                    # Check if CUDA is available AND actually usable
                    if torch.cuda.is_available():
                        try:
                            # Try to actually use CUDA to verify it works
                            _ = torch.cuda.get_device_name(0)
                            device = "cuda"
                            log.info("CUDA detected and verified")
                        except Exception as cuda_error:
                            log.warning(f"CUDA detected but not usable: {cuda_error}")
                            log.info("Falling back to CPU")
                            device = "cpu"
                    else:
                        device = "cpu"
                except ImportError:
                    device = "cpu"
            else:
                device = self.whisper_device

            # Determine model directory
            if self.whisper_model_dir:
                model_path = self.whisper_model_dir
            else:
                model_path = self.get_whisper_model_path()

            log.debug(f"Using model directory: {model_path}")
            log.debug(f"Using device: {device}")

            # Create model directory if it doesn't exist
            Path(model_path).mkdir(parents=True, exist_ok=True)

            # Load the requested model size
            try:
                log.debug(f"Loading {self.whisper_model_size} Whisper model on {device}...")
                from faster_whisper import WhisperModel
                self.whisper_model = WhisperModel(
                    self.whisper_model_size,
                    device=device,
                    download_root=model_path,
                    local_files_only=False  # Allow downloading if not cached
                )
                self.whisper_model_name = self.whisper_model_size
                log.info(f"Whisper {self.whisper_model_size} model loaded successfully on {device}")
                log.debug(f"Model stored in: {model_path}")

                # Notify UI that loading completed
                if self.model_loading_complete_callback:
                    self.model_loading_complete_callback()
                return
            except Exception as e:
                log.error(f"Failed to load {self.whisper_model_size} model on {device}: {e}")

                # If CUDA failed, try CPU as fallback
                if device == "cuda":
                    log.warning("CUDA model loading failed, retrying with CPU...")
                    try:
                        self.whisper_model = WhisperModel(
                            self.whisper_model_size,
                            device="cpu",
                            download_root=model_path,
                            local_files_only=False
                        )
                        self.whisper_model_name = self.whisper_model_size
                        log.info(f"Whisper {self.whisper_model_size} model loaded successfully on CPU (fallback)")

                        if self.model_loading_complete_callback:
                            self.model_loading_complete_callback()
                        return
                    except Exception as cpu_error:
                        log.error(f"Failed to load {self.whisper_model_size} model on CPU: {cpu_error}")

                # Fallback to tiny model if requested model fails
                if self.whisper_model_size != "tiny":
                    log.warning("Falling back to tiny model...")
                    try:
                        self.whisper_model = WhisperModel(
                            "tiny",
                            device=device,
                            download_root=model_path,
                            local_files_only=False  # Allow downloading if not cached
                        )
                        self.whisper_model_name = "tiny"
                        log.info("Whisper tiny model loaded successfully (fallback)")

                        # Notify UI that loading completed
                        if self.model_loading_complete_callback:
                            self.model_loading_complete_callback()
                        return
                    except Exception as e2:
                        log.error(f"Failed to load fallback tiny model: {e2}")

            # If all fails, error out
            log.error("FATAL: Could not load any Whisper model")
            self.whisper_model = None

            # Notify UI that loading completed (even if failed)
            if self.model_loading_complete_callback:
                self.model_loading_complete_callback()

        except Exception as e:
            log.error(f"Whisper loading error: {e}")
            self.whisper_model = None

            # Notify UI that loading completed (even if failed)
            if self.model_loading_complete_callback:
                self.model_loading_complete_callback()
    
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
            
            log.debug(f"Found microphones using SoundDevice: {[mic['name'] for mic in self.available_microphones]}")
            
            if self.available_microphones and self.current_microphone_index is None:
                self.set_microphone(0)
                
        except Exception as e:
            log.error(f"Failed to enumerate microphones: {e}")
    
    def get_microphone_list(self):
        return self.available_microphones

    def get_audio_devices(self):
        """Refresh and return list of available audio devices"""
        self.refresh_microphones()
        return self.available_microphones
    
    def set_microphone(self, device_index):
        """Set microphone by device index (not array index)"""
        try:
            # Find the array index for this device index
            for i, mic in enumerate(self.available_microphones):
                if mic['index'] == device_index:
                    self.current_microphone_index = device_index  # Store actual device index
                    log.debug(f"RECORDER: Selected microphone: {mic['name']} (device index: {device_index})")
                    return True
            
            log.error(f"RECORDER: Device index {device_index} not found in available microphones")
            return False
        except Exception as e:
            log.error(f"RECORDER: Failed to set microphone {device_index}: {e}")
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
        """Start recording with device validation and error handling"""
        if self.is_recording:
            return

        # Validate device before starting
        try:
            if self.current_microphone_index is None:
                log.error("No microphone selected - cannot start recording")
                if callback:
                    callback("", "error")
                return

            # Check if device still exists
            current_mic = self.get_current_microphone()
            if not current_mic:
                log.error(f"Microphone device {self.current_microphone_index} no longer available")
                if callback:
                    callback("Device disconnected", "error")
                return

            # Log current preview_audio_data state before starting new recording
            log.debug(f"START_RECORDING: preview_audio_data before recording: {self.preview_audio_data is not None}, id={id(self.preview_audio_data)}")

            self.is_recording = True
            self.callback = callback
            log.debug(f"CALLBACK SET TO: {callback}")

            log.info(f"Starting recording with microphone index: {self.current_microphone_index}")

            # Use thread pool if available, otherwise fall back to creating thread
            if self.thread_pool:
                self.thread_pool.submit(self._record_worker)
            else:
                thread = threading.Thread(target=self._record_worker)
                thread.daemon = True
                thread.start()

        except Exception as e:
            log.error(f"Error starting recording: {e}")
            self.is_recording = False
            if callback:
                callback(f"Error: {e}", "error")
    
    def stop_recording(self):
        log.debug(" RECORDER: stop_recording called")
        self.is_recording = False
        log.debug(" RECORDER: is_recording set to False")
        
        # Clean up any active subprocess
        if self.active_subprocess:
            if self.active_subprocess.poll() is None:
                log.debug(f" RECORDER: Terminating active subprocess (pid={self.active_subprocess.pid})...")
                try:
                    self.active_subprocess.terminate()
                    # Give it a moment to terminate gracefully
                    try:
                        self.active_subprocess.wait(timeout=2)
                        log.debug(" RECORDER: Subprocess terminated gracefully")
                    except subprocess.TimeoutExpired:
                        log.warning(f" RECORDER: Subprocess (pid={self.active_subprocess.pid}) didn't terminate in 2s, killing...")
                        self.active_subprocess.kill()
                        self.active_subprocess.wait()
                        log.warning(" RECORDER: Subprocess killed with SIGKILL")
                except Exception as e:
                    log.error(f"RECORDER: Error cleaning up subprocess: {e}")
            else:
                log.debug(f" RECORDER: Subprocess already finished (returncode={self.active_subprocess.returncode})")

            # Always clear the subprocess reference
            self.active_subprocess = None

    def pause_recording(self):
        """Pause recording without stopping - saves current segment."""
        log.debug(" RECORDER: pause_recording called")

        if not self.is_recording or self.is_paused:
            log.debug(" RECORDER: Not recording or already paused, ignoring")
            return

        self.is_paused = True
        log.debug(" RECORDER: is_paused set to True")

        # Terminate subprocess and save current audio segment
        if self.active_subprocess and self.active_subprocess.poll() is None:
            log.debug(" RECORDER: Terminating subprocess to save segment...")
            try:
                self.active_subprocess.terminate()
                # Wait for subprocess to save audio
                try:
                    stdout, stderr = self.active_subprocess.communicate(timeout=5)
                    if self.active_subprocess.returncode == 0 and stdout.strip():
                        segment_path = stdout.decode().strip()
                        self.audio_segments.append(segment_path)
                        log.info(f" RECORDER: Saved audio segment: {segment_path}")
                    else:
                        log.warning(f" RECORDER: Subprocess didn't save segment: {stderr.decode()}")
                except subprocess.TimeoutExpired:
                    log.error(" RECORDER: Subprocess timeout on pause")
                    self.active_subprocess.kill()
            except Exception as e:
                log.error(f"RECORDER: Error pausing: {e}")
            finally:
                self.active_subprocess = None

        log.info(" RECORDER: Recording paused")

    def resume_recording(self):
        """Resume recording from paused state - starts new segment."""
        log.debug(" RECORDER: resume_recording called")

        if not self.is_recording or not self.is_paused:
            log.debug(" RECORDER: Not recording or not paused, ignoring")
            return

        self.is_paused = False
        log.debug(" RECORDER: is_paused set to False")

        # Resume will happen automatically when _record_worker continues
        # The worker should check is_paused and restart subprocess
        log.info(" RECORDER: Recording resumed")

    def calculate_confidence(self, avg_logprob):
        """Convert Whisper's average log probability to confidence score (0-100).

        Whisper returns avg_logprob typically in range of -2.0 (bad) to 0.0 (perfect).
        We map this to a 0-100 confidence score:
        - 0.0 or better → 100% (perfect)
        - -0.3 → 85% (very good)
        - -0.5 → 75% (good)
        - -1.0 → 50% (medium)
        - -2.0 or worse → 0% (very poor)

        Args:
            avg_logprob: Average log probability from Whisper

        Returns:
            int: Confidence score from 0-100
        """
        if avg_logprob is None:
            return 50  # Default to medium confidence if unknown

        # Clamp to reasonable range
        avg_logprob = max(-2.0, min(0.0, avg_logprob))

        # Linear mapping: -2.0 → 0%, 0.0 → 100%
        # Formula: confidence = 100 * (1 + avg_logprob / 2.0)
        confidence = 100 * (1 + avg_logprob / 2.0)

        # Round to integer
        return int(round(confidence))

    def get_vocabulary_prompt(self):
        """Generate initial prompt from custom vocabulary for Whisper.

        Whisper can use an initial_prompt parameter to guide transcription
        with specific terminology. This helps it recognize custom words.

        Returns:
            str: Prompt containing vocabulary terms, or None if no vocabulary
        """
        if not self.custom_vocabulary:
            return None

        # Join vocabulary with commas for natural prompt
        # Format: "Technical terms: PyQt6, Whisper, DICTATOR, API, JSON"
        vocab_text = ", ".join(self.custom_vocabulary)
        prompt = f"Technical terms and names: {vocab_text}"

        return prompt

    def preview_audio(self):
        """Play back the recorded audio for preview before transcription."""
        try:
            if self.preview_audio_data is None:
                log.warning("PREVIEW: No audio data available for preview")
                return False

            if not SOUNDDEVICE_AVAILABLE:
                log.error("PREVIEW: sounddevice not available")
                return False

            log.info(f"PREVIEW: Playing back {len(self.preview_audio_data)} samples at {self.preview_sample_rate}Hz")

            # Capture data in local variables for thread closure
            audio_data = self.preview_audio_data.copy()
            sample_rate = self.preview_sample_rate

            # Play audio in background thread to avoid blocking UI
            def play_and_wait():
                try:
                    # Convert int16 to float32 for playback (-1.0 to 1.0 range)
                    audio_float = audio_data.astype(np.float32) / 32768.0

                    import sounddevice as sd
                    sd.play(audio_float, samplerate=sample_rate)
                    sd.wait()  # Wait for playback to finish
                    log.info("PREVIEW: Playback completed")
                except Exception as e:
                    log.error(f"PREVIEW: Playback thread error: {e}")
                    import traceback
                    traceback.print_exc()

            # Use thread pool if available, otherwise create thread
            if self.thread_pool:
                self.thread_pool.submit(play_and_wait)
            else:
                import threading
                thread = threading.Thread(target=play_and_wait)
                thread.daemon = True
                thread.start()

            return True

        except Exception as e:
            log.error(f"PREVIEW: Error playing audio: {e}")
            return False

    def transcribe_preview_audio(self, callback):
        """Transcribe the stored preview audio data."""
        try:
            log.debug(f"TRANSCRIBE: Called on recorder instance id={id(self)}")
            log.debug(f"TRANSCRIBE: preview_audio_data={self.preview_audio_data is not None}, sample_rate={self.preview_sample_rate}")
            log.debug(f"TRANSCRIBE: preview_audio_data id={id(self.preview_audio_data)}, type={type(self.preview_audio_data)}")
            if self.preview_audio_data is None:
                log.error(f"TRANSCRIBE: No preview audio data available! preview_audio_data={self.preview_audio_data}, preview_sample_rate={self.preview_sample_rate}")
                log.error(f"TRANSCRIBE: id(self.preview_audio_data)={id(self.preview_audio_data)}")
                if callback:
                    callback("", "no_audio")
                return

            log.info("TRANSCRIBE: Processing preview audio with Whisper...")

            # Progress: Starting
            if self.progress_callback:
                self.progress_callback(10, "Loading model...")

            audio_array = self.preview_audio_data
            working_rate = self.preview_sample_rate

            # Process with Whisper
            log.debug("Processing audio with Whisper...")
            audio_float = audio_array.astype(np.float32) / 32768.0

            # Progress: Preparing audio
            if self.progress_callback:
                self.progress_callback(30, "Preparing audio...")

            # Resample to 16kHz if needed (Whisper's expected rate)
            if working_rate != 16000:
                log.debug(f"WHISPER_RECORD: Resampling from {working_rate}Hz to 16000Hz for Whisper...")
                try:
                    import librosa
                    audio_float = librosa.resample(audio_float, orig_sr=working_rate, target_sr=16000)
                    log.debug(" WHISPER_RECORD: Resampling successful")
                except ImportError:
                    log.error(" WHISPER_RECORD: librosa not available, using audio as-is")
                except Exception as e:
                    log.error(f"WHISPER_RECORD: Resampling failed: {e}, using audio as-is")

            # Check for minimum audio length
            if len(audio_float) < 0.1 * 16000:  # Less than 0.1 seconds
                log.debug("Audio too short")
                if callback:
                    callback("", "too_short")
                return

            # Transcribe directly with Whisper
            if self.whisper_model:
                log.info(" WHISPER: Starting transcription with faster-whisper...")
                log.debug(f"WHISPER: Audio length: {len(audio_float)} samples")

                # Progress: Processing audio
                if self.progress_callback:
                    self.progress_callback(50, "Processing audio...")

                # Determine language parameter (None for auto-detect)
                language_param = None if self.whisper_language == 'auto' else self.whisper_language
                log.debug(f"WHISPER: Using language: {self.whisper_language} (param: {language_param})")

                # Get vocabulary prompt for better recognition
                vocab_prompt = self.get_vocabulary_prompt()
                if vocab_prompt:
                    log.debug(f"WHISPER: Using vocabulary prompt: {vocab_prompt}")

                segments, info = self.whisper_model.transcribe(
                    audio_float,
                    language=language_param,
                    initial_prompt=vocab_prompt
                )

                # Progress: Finalizing
                if self.progress_callback:
                    self.progress_callback(90, "Finalizing transcription...")

                # Collect all segments and calculate confidence
                transcription = ""
                total_logprob = 0.0
                segment_count = 0

                for segment in segments:
                    transcription += segment.text + " "
                    # Extract confidence from segment
                    if hasattr(segment, 'avg_logprob'):
                        total_logprob += segment.avg_logprob
                        segment_count += 1

                transcription = transcription.strip()

                # Calculate overall confidence from average log probability
                if segment_count > 0:
                    avg_logprob = total_logprob / segment_count
                    self.last_confidence_score = self.calculate_confidence(avg_logprob)
                    log.info(f" WHISPER: Confidence: {self.last_confidence_score}% (avg_logprob: {avg_logprob:.3f})")
                else:
                    self.last_confidence_score = 50  # Default if no segments
                    log.warning(" WHISPER: No segments with confidence data, using default 50%")

                log.info(f" WHISPER: Transcription completed: '{transcription[:50]}...'")

                # Progress: Complete
                if self.progress_callback:
                    self.progress_callback(100, "Complete!")

                if callback:
                    # Pass confidence to callback if it accepts it
                    try:
                        callback(transcription, "success", self.last_confidence_score)
                    except TypeError:
                        # Fallback for old callback signature without confidence
                        callback(transcription, "success")
            else:
                log.error("WHISPER: No Whisper model available")
                if callback:
                    callback("", "error")

        except Exception as e:
            log.error(f"TRANSCRIBE: Error: {e}")
            import traceback
            traceback.print_exc()
            if callback:
                callback("", "error")

    def start_continuous_monitoring(self):
        """Start continuous audio monitoring like SAI"""
        if not SOUNDDEVICE_AVAILABLE:
            return

        # Use lock to prevent race condition
        with self.monitoring_lock:
            if self.is_monitoring:
                return

            self.is_monitoring = True

        # Start thread outside lock to avoid deadlock
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
            log.error(f"Continuous monitoring error: {e}")
    
    def stop_monitoring(self):
        """Stop continuous monitoring"""
        # Use lock to safely update flag
        with self.monitoring_lock:
            if hasattr(self, 'is_monitoring'):
                self.is_monitoring = False

        # Wait for thread to finish to avoid memory issues
        if hasattr(self, 'monitoring_thread') and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=1.0)
    
    def _record_worker(self):
        # FORCE WHISPER LOADING AND ONLY USE WHISPER
        log.debug(f"WHISPER_AVAILABLE: {WHISPER_AVAILABLE}")
        log.debug(f"self.whisper_model: {self.whisper_model}")
        
        # If Whisper is available but model not loaded, load it now
        # Use lock to prevent concurrent loading
        with self.model_loading_lock:
            if not self.whisper_model:
                log.info("Loading Whisper model on-demand")
                try:
                    # Disable SSL verification for downloads (workaround for certificate issues)
                    import ssl
                    try:
                        ssl._create_default_https_context = ssl._create_unverified_context
                    except Exception:
                        pass

                    from faster_whisper import WhisperModel
                    model_path = self.get_whisper_model_path()
                    self.whisper_model = WhisperModel(
                        "tiny",
                        device="cpu",
                        download_root=model_path,
                        local_files_only=False  # Allow downloading if not cached
                    )
                    log.info(" Whisper tiny model loaded successfully")
                    log.debug(f"Model stored in: {model_path}")
                except Exception as e:
                    error_msg = f"Failed to load Whisper model: {str(e)}"
                    log.error(f"FATAL: {error_msg}")
                    self.callback(f"ERROR: {error_msg}", "error")
                    return
        
        # ONLY USE WHISPER - NO GOOGLE
        log.debug("🎵 Using Whisper for transcription")
        self._record_with_whisper()
    
    def _record_with_whisper(self):
        log.debug("🎵 Recording with Whisper...")
        try:
            log.debug(" WHISPER_RECORD: Using isolated subprocess to prevent memory corruption")
            
            # Use selected microphone device
            current_mic = self.get_current_microphone()
            if current_mic:
                device_index = current_mic['index']
                device_name = current_mic['name']
                log.info(f"WHISPER_RECORD: Using selected microphone: {device_name} (index: {device_index})")
            else:
                device_index = None
                log.warning("WHISPER_RECORD: No microphone selected! Using default audio input")

            # Verify the device index is valid
            try:
                import sounddevice as sd
                devices = sd.query_devices()
                log.info(f"WHISPER_RECORD: Total available devices: {len(devices)}")

                if device_index is not None:
                    if device_index >= len(devices):
                        log.error(f"WHISPER_RECORD: Device index {device_index} is invalid (only {len(devices)} devices available)")
                        raise Exception(f"Invalid microphone index {device_index}")
                    else:
                        device_info = devices[device_index]
                        log.info(f"WHISPER_RECORD: Device {device_index} details: {device_info}")
                else:
                    default_device = sd.default.device[0] if hasattr(sd.default.device, '__iter__') else None
                    log.info(f"WHISPER_RECORD: Using default input device: {default_device}")
            except Exception as e:
                log.error(f"WHISPER_RECORD: Error verifying device: {e}")


            # Determine sample rate - use configured rate or auto-detect
            if self.configured_sample_rate != "auto":
                # Use the configured sample rate
                working_rate = int(self.configured_sample_rate)
                log.info(f"WHISPER_RECORD: Using configured sample rate: {working_rate}Hz")
            else:
                # Auto-detect device sample rate
                log.debug(f"WHISPER_RECORD: Auto-detecting device sample rate...")

                try:
                    import sounddevice as sd
                    devices = sd.query_devices()

                    if device_index is None or device_index >= len(devices):
                        device_index = sd.default.device[0] if hasattr(sd.default.device, '__iter__') else None
                        log.debug(f"WHISPER_RECORD: Using default device: {device_index}")

                    if device_index is not None and device_index < len(devices):
                        device_info = devices[device_index]
                        working_rate = int(device_info.get('default_samplerate', 44100))
                        log.debug(f"WHISPER_RECORD: Using device default rate: {working_rate}Hz")
                    else:
                        working_rate = 44100
                        log.debug(" WHISPER_RECORD: Using fallback rate: 44100Hz")

                except Exception as e:
                    log.error(f"WHISPER_RECORD: Error getting device rate: {e}, using 44100Hz")
                    working_rate = 44100
            
            temp_audio_path = None
            
            # Now just use the working rate we determined
            log.info(f"WHISPER_RECORD: Starting subprocess recording at {working_rate}Hz...")
            
            try:
                # Launch isolated SoundDevice audio recording subprocess
                recorder_script = os.path.join(os.path.dirname(__file__), 'audio_recorder_sd.py')

                # Use sys.executable to run with same Python interpreter
                # Pass environment to ensure UV/pip packages are available
                import sys
                env = os.environ.copy()
                # Ensure PYTHONPATH includes current packages
                if hasattr(sys, 'path'):
                    env['PYTHONPATH'] = os.pathsep.join(sys.path)

                process = subprocess.Popen([
                    sys.executable, recorder_script,
                    str(device_index) if device_index is not None else "None",
                    str(working_rate)
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                   env=env, cwd=os.path.dirname(__file__))
                
                # Store subprocess reference for cleanup
                self.active_subprocess = process

                # Let it start up and check if it's working
                import time
                import select

                # Read initial stderr output to see startup messages
                startup_messages = []
                for i in range(5):  # Check 5 times over 0.5 seconds
                    time.sleep(0.1)

                    # Check if process already died
                    if process.poll() is not None:
                        # Process died, get all output
                        stdout, stderr = process.communicate()
                        stderr_text = stderr.decode() if stderr else "No stderr"
                        stdout_text = stdout.decode() if stdout else "No stdout"
                        log.error(f"WHISPER_RECORD: Subprocess died during startup (returncode={process.returncode})")
                        log.error(f"WHISPER_RECORD: Startup stderr: {stderr_text}")
                        log.error(f"WHISPER_RECORD: Startup stdout: {stdout_text}")
                        break

                    # Read any stderr output (non-blocking)
                    if hasattr(select, 'select'):
                        ready, _, _ = select.select([process.stderr], [], [], 0.001)
                        if ready:
                            line = process.stderr.readline()
                            if line:
                                decoded = line.decode().strip()
                                startup_messages.append(decoded)
                                log.debug(f"WHISPER_RECORD: Startup: {decoded}")

                if startup_messages:
                    log.info(f"WHISPER_RECORD: Subprocess startup messages: {startup_messages}")

                # If process is still running, it worked
                if process.poll() is None:
                    log.debug(f"WHISPER_RECORD: Subprocess recording working at {working_rate}Hz")
                    
                    # Continue recording until stopped
                    log.debug(" WHISPER_RECORD: Recording audio...")
                    
                    # Monitor real audio levels from subprocess
                    start_time = time.time()
                    stderr_lines = []  # Collect all stderr output

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
                                            stderr_lines.append(line)  # Save all stderr output
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
                            log.error(f"Level reading error: {e}")
                            with self.audio_level_lock:
                                self.current_audio_level = 25
                        
                        if elapsed > self.max_recording_duration:
                            log.debug(f" WHISPER_RECORD: Maximum recording time reached ({self.max_recording_duration}s)")
                            break
                    
                    # Stop the subprocess
                    log.info(" WHISPER_RECORD: Stopping subprocess...")
                    process.terminate()

                    # Wait for output
                    try:
                        log.debug("WHISPER_RECORD: Waiting for subprocess to finish (timeout=10s)...")
                        stdout, stderr = process.communicate(timeout=10)
                        log.debug(f"WHISPER_RECORD: Subprocess finished with returncode={process.returncode}")

                        # Log all stderr we collected during recording
                        if stderr_lines:
                            log.info(f"WHISPER_RECORD: Subprocess stderr during recording ({len(stderr_lines)} lines):")
                            for line in stderr_lines:
                                if not line.startswith("LEVEL:"):  # Don't log the volume levels
                                    log.info(f"  {line}")

                        # Log any remaining stderr from communicate()
                        if stderr:
                            remaining_stderr = stderr.decode().strip()
                            if remaining_stderr:
                                log.info(f"WHISPER_RECORD: Additional stderr after terminate: {remaining_stderr}")

                        if process.returncode == 0 and stdout.strip():
                            temp_audio_path = stdout.decode().strip()
                            log.info(f"WHISPER_RECORD: Audio saved to {temp_audio_path}")
                        else:
                            log.error(f"WHISPER_RECORD: Subprocess failed with returncode {process.returncode}")
                            log.error(f"WHISPER_RECORD: stdout: {stdout.decode() if stdout else 'empty'}")
                    except subprocess.TimeoutExpired:
                        log.error(" WHISPER_RECORD: Subprocess timeout, killing...")
                        process.kill()
                        process.communicate()
                    finally:
                        # Clear subprocess reference
                        self.active_subprocess = None
                    
                else:
                    stdout, stderr = process.communicate()
                    stderr_text = stderr.decode() if stderr else "No error output"
                    stdout_text = stdout.decode() if stdout else "No stdout"
                    log.error(f"WHISPER_RECORD: Failed at {working_rate}Hz")
                    log.error(f"WHISPER_RECORD: Return code: {process.returncode}")
                    log.error(f"WHISPER_RECORD: STDERR: {stderr_text}")
                    log.error(f"WHISPER_RECORD: STDOUT: {stdout_text}")
                    temp_audio_path = None
                    # Clear subprocess reference
                    self.active_subprocess = None
                    
            except Exception as e:
                log.error(f"WHISPER_RECORD: Error testing {working_rate}Hz: {e}")
                temp_audio_path = None
                # Clear subprocess reference on error
                self.active_subprocess = None
            
            if not temp_audio_path:
                raise Exception(f"Could not record audio at {working_rate}Hz")
            
            # Load the recorded audio file
            log.debug(" WHISPER_RECORD: Loading recorded audio...")
            try:
                with open(temp_audio_path, 'rb') as f:
                    raw_data = f.read()

                # Store the temp audio path for later saving to history
                # (Don't delete yet - will be saved to audio_history after transcription)
                self.last_recorded_audio_path = temp_audio_path
                self.last_recorded_sample_rate = working_rate
                log.debug(f"WHISPER_RECORD: Stored temp audio path for history: {temp_audio_path}")
                
                if not raw_data:
                    log.debug("No audio data in file")
                    self.callback("", "no_audio")
                    return
                
                # Convert raw bytes to numpy array
                audio_array = np.frombuffer(raw_data, dtype=np.int16)
                log.info(f"WHISPER_RECORD: Loaded {len(audio_array)} audio samples")

            except Exception as e:
                log.error(f"WHISPER_RECORD: Error loading audio file: {e}")
                self.callback("", "file_error")
                return

            # Store preview data for playback before transcription
            log.debug(f"PREVIEW: About to store preview_audio_data on recorder instance id={id(self)}")
            log.debug(f"PREVIEW: Current value before store: {self.preview_audio_data is not None}")
            self.preview_audio_data = audio_array.copy()  # Make a copy to avoid reference issues
            self.preview_sample_rate = working_rate
            log.info(f"PREVIEW: Stored {len(audio_array)} samples at {working_rate}Hz for preview")
            log.debug(f"PREVIEW: preview_audio_data id={id(self.preview_audio_data)}, type={type(self.preview_audio_data)}, len={len(self.preview_audio_data)}")
            log.debug(f"PREVIEW: Verifying storage - self.preview_audio_data is not None: {self.preview_audio_data is not None}")
            log.debug(f"PREVIEW: Stored on recorder instance id={id(self)}")

            # Auto-transcribe immediately instead of waiting for user to click accept
            log.info("PREVIEW: Auto-transcribing immediately (skipping preview)")

            # Transcribe the audio we just stored
            def transcribe_callback(text, language):
                log.debug(f"AUTO_TRANSCRIBE: Got result: '{text}', language={language}")
                if self.callback:
                    self.callback(text, language)

            # Call transcribe in thread pool to avoid blocking
            if self.thread_pool:
                self.thread_pool.submit(self.transcribe_preview_audio, transcribe_callback)
            else:
                import threading
                thread = threading.Thread(target=self.transcribe_preview_audio, args=(transcribe_callback,))
                thread.daemon = True
                thread.start()

            return

            # ORIGINAL CODE BELOW - will be called from process_preview_audio after user accepts
            # Process with Whisper
            log.debug("Processing audio with Whisper...")
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Resample to 16kHz if needed (Whisper's expected rate)
            if working_rate != 16000:
                log.debug(f"WHISPER_RECORD: Resampling from {working_rate}Hz to 16000Hz for Whisper...")
                try:
                    import librosa
                    audio_float = librosa.resample(audio_float, orig_sr=working_rate, target_sr=16000)
                    log.debug(" WHISPER_RECORD: Resampling successful")
                except ImportError:
                    log.error(" WHISPER_RECORD: librosa not available, using audio as-is")
                    # Whisper can handle other sample rates, just not as optimal
                except Exception as e:
                    log.error(f"WHISPER_RECORD: Resampling failed: {e}, using audio as-is")
            
            # Check for minimum audio length
            if len(audio_float) < 0.1 * 16000:  # Less than 0.1 seconds
                log.debug("Audio too short")
                self.callback("", "too_short")
                return
            
            # Transcribe directly with Whisper (no temp file needed)
            try:
                if self.whisper_model:
                    log.info(" WHISPER: Starting transcription with faster-whisper...")
                    log.debug(f"WHISPER: Audio length: {len(audio_float)} samples")

                    # Determine language parameter (None for auto-detect)
                    language_param = None if self.whisper_language == 'auto' else self.whisper_language
                    log.debug(f"WHISPER: Using language: {self.whisper_language} (param: {language_param})")

                    # Get vocabulary prompt for better recognition
                    vocab_prompt = self.get_vocabulary_prompt()
                    if vocab_prompt:
                        log.debug(f"WHISPER: Using vocabulary prompt: {vocab_prompt}")

                    segments, info = self.whisper_model.transcribe(
                        audio_float,
                        language=language_param,
                        initial_prompt=vocab_prompt
                    )
                    log.debug(" WHISPER: Transcription completed, processing segments...")
                    
                    text = "".join([segment.text for segment in segments]).strip()
                    language = info.language if hasattr(info, 'language') else "en"
                    
                    log.debug(f"WHISPER: Result text: '{text}' (language: {language})")
                    log.debug(f"WHISPER: About to call callback...")
                    
                    if text:
                        log.debug(f"WHISPER: Calling callback with text: '{text}', '{language}'")
                        self.callback(text, language)
                        log.debug(f"WHISPER: Callback completed successfully")
                    else:
                        log.debug(f"WHISPER: Empty result, calling callback with no_speech")
                        self.callback("", "no_speech")
                        log.debug(f"WHISPER: No speech callback completed")
                else:
                    log.error(" WHISPER: Model not loaded!")
                    self.callback("", "model_error")
                    
            except Exception as e:
                log.error(f"WHISPER: Transcription error: {e}")
                import traceback
                traceback.print_exc()
                self.callback("", "transcription_error")
                
        except Exception as e:
            log.error(f"Whisper recording setup error: {e}")
            self.callback("ERROR: Whisper recording failed", "error")