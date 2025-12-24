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

from logger import get_logger
log = get_logger(__name__)

def record_audio_sounddevice(device_index, sample_rate, max_duration=300):
    """
    Record audio using SoundDevice instead of PyAudio
    Returns path to temporary audio file
    """
    try:
        import sounddevice as sd
        
        # List available devices
        devices = sd.query_devices()
        log.debug(f"SOUNDDEVICE_RECORDER: Available devices: {len(devices)}")
        
        if device_index is not None and device_index < len(devices):
            device_info = devices[device_index]
            log.debug(f"SOUNDDEVICE_RECORDER: Using device {device_index}: {device_info['name']}")
        else:
            device_index = None
            log.debug("SOUNDDEVICE_RECORDER: Using default device", file=sys.stderr)
        
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
            
            # Calculate real audio level (RMS) and send to parent
            rms = np.sqrt(np.mean(audio_chunk.astype(np.float64) ** 2))
            level_percent = min(100, int((rms / 10000) * 100))  # Scale to 0-100
            log.debug(f"LEVEL:{level_percent}")
            
            # Progress indication
            if len(audio_data) % 50 == 0:  # Every 5 seconds
                log.debug(f"SOUNDDEVICE_RECORDER: Recorded {len(audio_data)} chunks ({len(audio_data) * chunk_size} samples)")
        
        # Set up signal handling for clean termination
        import signal
        terminated = False
        
        def signal_handler(sig, frame):
            nonlocal terminated
            log.debug("SOUNDDEVICE_RECORDER: Received termination signal", file=sys.stderr)
            terminated = True
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        # Start recording
        log.info("SOUNDDEVICE_RECORDER: Starting recording...", file=sys.stderr)
        
        with sd.InputStream(
            device=device_index,
            channels=1,
            samplerate=sample_rate,
            blocksize=chunk_size,
            dtype=np.float32,
            callback=audio_callback
        ):
            # Keep recording until terminated or max duration
            for i in range(max_chunks):
                time.sleep(0.1)  # 100ms sleep
                
                # Check for termination signal
                if terminated:
                    log.debug("SOUNDDEVICE_RECORDER: Termination requested, stopping", file=sys.stderr)
                    break
                    
                # Safety check for runaway recording
                if len(audio_data) > max_chunks:
                    break
        
        log.debug(f"SOUNDDEVICE_RECORDER: Recording stopped. Collected {len(audio_data)} chunks")
        
        if not audio_data:
            log.debug("SOUNDDEVICE_RECORDER: No audio data recorded", file=sys.stderr)
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
            except:
                pass
            return None
            
    except Exception as e:
        log.error(f"SOUNDDEVICE_RECORDER: Fatal error: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)
        return None

if __name__ == "__main__":
    if len(sys.argv) != 3:
        log.debug("Usage: audio_recorder_sd.py <device_index> <sample_rate>", file=sys.stderr)
        sys.exit(1)
    
    device_index = int(sys.argv[1]) if sys.argv[1] != "None" else None
    sample_rate = int(sys.argv[2])
    
    # Record audio and return path
    temp_path = record_audio_sounddevice(device_index, sample_rate)
    
    if temp_path:
        log.debug(temp_path)
        sys.exit(0)
    else:
        sys.exit(1)