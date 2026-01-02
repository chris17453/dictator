#!/usr/bin/env python3
"""
SoundDevice-based audio recorder to avoid PyAudio memory corruption
"""
import sys
import numpy as np
import sounddevice as sd
import tempfile
import os
import time

try:
    from logger import get_logger
except ImportError:
    from .logger import get_logger
log = get_logger(__name__)

def record_audio_sounddevice(device_index, sample_rate, max_duration=300):
    """
    Record audio using SoundDevice instead of PyAudio
    Returns path to temporary audio file
    """
    try:
        print("SOUNDDEVICE_RECORDER: Importing sounddevice", file=sys.stderr, flush=True)
        import sounddevice as sd

        print("SOUNDDEVICE_RECORDER: Querying devices", file=sys.stderr, flush=True)
        # List available devices
        devices = sd.query_devices()
        log.debug(f"SOUNDDEVICE_RECORDER: Available devices: {len(devices)}")
        print(f"SOUNDDEVICE_RECORDER: Found {len(devices)} devices", file=sys.stderr, flush=True)
        
        if device_index is not None and device_index < len(devices):
            device_info = devices[device_index]
            log.debug(f"SOUNDDEVICE_RECORDER: Using device {device_index}: {device_info['name']}")
        else:
            device_index = None
            log.debug("SOUNDDEVICE_RECORDER: Using default device")
        
        # Calculate buffer size for recording
        chunk_size = int(sample_rate * 0.1)  # 100ms chunks
        max_chunks = int(max_duration * 10)  # 10 chunks per second
        
        log.debug(f"SOUNDDEVICE_RECORDER: Recording at {sample_rate}Hz, {chunk_size} samples per chunk")
        
        # Record audio using sounddevice
        audio_data = []
        
        def audio_callback(indata, frames, time, status):
            """Callback function for audio recording"""
            if status:
                log.debug(f"SOUNDDEVICE_RECORDER: Audio status: {status}")
            
            # Convert to int16 and store
            audio_chunk = (indata[:, 0] * 32767).astype(np.int16)
            audio_data.append(audio_chunk.copy())
            
            # Calculate real audio level (RMS) and send to parent via stderr
            rms = np.sqrt(np.mean(audio_chunk.astype(np.float64) ** 2))
            level_percent = min(100, int((rms / 10000) * 100))  # Scale to 0-100
            # Send directly to stderr for volume meter (not through logger)
            print(f"LEVEL:{level_percent}", file=sys.stderr, flush=True)
            
            # Progress indication
            if len(audio_data) % 50 == 0:  # Every 5 seconds
                log.debug(f"SOUNDDEVICE_RECORDER: Recorded {len(audio_data)} chunks ({len(audio_data) * chunk_size} samples)")
        
        # Set up signal handling for clean termination
        import signal
        terminated = False
        
        def signal_handler(sig, frame):
            nonlocal terminated
            log.debug("SOUNDDEVICE_RECORDER: Received termination signal")
            terminated = True
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        # Start recording
        log.info("SOUNDDEVICE_RECORDER: Starting recording...")
        print(f"SOUNDDEVICE_RECORDER: Opening stream - device={device_index}, rate={sample_rate}, channels=1", file=sys.stderr, flush=True)

        try:
            stream = sd.InputStream(
                device=device_index,
                channels=1,
                samplerate=sample_rate,
                blocksize=chunk_size,
                dtype=np.float32,
                callback=audio_callback
            )
        except Exception as e:
            print(f"SOUNDDEVICE_RECORDER: FAILED to open stream: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc(file=sys.stderr)
            return None

        print("SOUNDDEVICE_RECORDER: Stream created, starting...", file=sys.stderr, flush=True)

        with stream:
            print("SOUNDDEVICE_RECORDER: Stream opened successfully, recording started", file=sys.stderr, flush=True)
            # Keep recording until terminated or max duration
            for i in range(max_chunks):
                time.sleep(0.1)  # 100ms sleep
                
                # Check for termination signal
                if terminated:
                    log.debug("SOUNDDEVICE_RECORDER: Termination requested, stopping")
                    break
                    
                # Safety check for runaway recording
                if len(audio_data) > max_chunks:
                    break
        
        log.debug(f"SOUNDDEVICE_RECORDER: Recording stopped. Collected {len(audio_data)} chunks")

        if not audio_data:
            log.debug("SOUNDDEVICE_RECORDER: No audio data recorded")
            return None
        
        # Combine all chunks
        combined_audio = np.concatenate(audio_data)
        
        # Save to temporary file
        temp_fd, temp_path = tempfile.mkstemp(suffix='.raw', prefix='dictator_sd_')
        
        try:
            with os.fdopen(temp_fd, 'wb') as f:
                f.write(combined_audio.tobytes())
            
            log.info(f"SOUNDDEVICE_RECORDER: Saved {len(combined_audio)} samples to {temp_path}")
            return temp_path
            
        except Exception as e:
            log.error(f"SOUNDDEVICE_RECORDER: Error saving audio: {e}")
            try:
                os.unlink(temp_path)
            except (OSError, FileNotFoundError, PermissionError) as cleanup_error:
                log.warning(f"SOUNDDEVICE_RECORDER: Could not cleanup temp file {temp_path}: {cleanup_error}")
            return None
            
    except Exception as e:
        log.error(f"SOUNDDEVICE_RECORDER: Fatal error: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)
        return None

if __name__ == "__main__":
    # Immediate startup message to stderr to verify subprocess starts
    print("SOUNDDEVICE_RECORDER: Starting subprocess", file=sys.stderr, flush=True)

    try:
        if len(sys.argv) != 3:
            print(f"SOUNDDEVICE_RECORDER: ERROR - Wrong args: {sys.argv}", file=sys.stderr, flush=True)
            sys.exit(1)

        print("SOUNDDEVICE_RECORDER: Parsing arguments", file=sys.stderr, flush=True)
        device_index = int(sys.argv[1]) if sys.argv[1] != "None" else None
        sample_rate = int(sys.argv[2])

        print(f"SOUNDDEVICE_RECORDER: device={device_index}, rate={sample_rate}", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"SOUNDDEVICE_RECORDER: FATAL - Argument parsing failed: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    # Record audio and return path
    try:
        temp_path = record_audio_sounddevice(device_index, sample_rate)

        if temp_path:
            # Send path to stdout for parent process (not through logger)
            print(temp_path, flush=True)
            log.debug(f"Returned path to parent: {temp_path}")
            sys.exit(0)
        else:
            print("SOUNDDEVICE_RECORDER: ERROR - No audio recorded", file=sys.stderr, flush=True)
            sys.exit(1)
    except Exception as e:
        print(f"SOUNDDEVICE_RECORDER: FATAL ERROR - {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)