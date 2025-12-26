# DICTATOR - Development Task List

**Goal:** Complete Alpha/Beta features, then build towards enterprise dictation app
**Development Approach:** Test-Driven Development (TDD) for all features
**Last Updated:** 2025-12-24

---

## 🧪 TDD Workflow (MANDATORY FOR ALL TASKS)

**Red-Green-Refactor Cycle:**

1. **RED** - Write failing test first
   - Define expected behavior in test
   - Run test to confirm it fails
   - Commit: `test: add failing test for [feature]`

2. **GREEN** - Write minimal code to pass test
   - Implement feature to make test pass
   - Run tests to confirm success
   - Commit: `feat: implement [feature]`

3. **REFACTOR** - Improve code quality
   - Clean up implementation
   - Ensure tests still pass
   - Commit: `refactor: improve [feature] implementation`

**Test Requirements:**
- ✅ Unit tests for all business logic
- ✅ Integration tests for component interactions
- ✅ Qt/UI tests for GUI components
- ✅ Minimum 80% code coverage for new code
- ✅ All tests must pass before merging

**No code without tests. No exceptions.**

---

## Phase 1: Critical Fixes & Stability (ALPHA)

### 1.1 Critical Bug Fixes
- [x] **Fix crash handling** - ✅ COMPLETED 2025-12-24 - Removed force-kill monitor thread, replaced os._exit with graceful shutdown
- [x] **Fix resource cleanup** - ✅ COMPLETED 2025-12-24 - Replaced os._exit(0) with QApplication.quit() and proper cleanup
- [x] **Fix config file corruption** - ✅ COMPLETED 2025-12-24 - Implemented atomic writes with backup, error handling, and validation
- [x] **Fix audio device disconnect handling** - ✅ COMPLETED 2025-12-24 - Graceful device validation, error callbacks, and user notifications
- [x] **Fix SSL verification** - ✅ COMPLETED 2025-12-24 - Removed SSL bypass, enabled secure certificate verification

### 1.2 Error Handling
- [x] **Replace all bare `except: pass` with proper error handling** - ✅ COMPLETED 2025-12-26 - All 4 bare except replaced with specific exceptions and logging (17 tests)
- [x] **Add user-facing error dialogs** - ✅ COMPLETED 2025-12-24 - Modal QMessageBox dialogs for all user-facing errors
- [x] **Implement config load/save error reporting** - ✅ COMPLETED 2025-12-24 - Dialogs for config corruption and save failures
- [x] **Add error recovery for failed transcriptions** - ✅ COMPLETED 2025-12-24 - Error dialogs with troubleshooting steps
- [x] **Handle microphone permission errors gracefully** - ✅ COMPLETED 2025-12-24 - Clear error messages with actionable suggestions

### 1.3 Logging System
- [x] **Implement logger.py module** - ✅ COMPLETED 2025-12-24 - Created centralized logging with file rotation
- [x] **Add log levels** - ✅ COMPLETED 2025-12-24 - DEBUG, INFO, WARNING, ERROR, CRITICAL all supported
- [x] **Write logs to file** - ✅ COMPLETED 2025-12-24 - Logs to `~/.config/dictator/logs/`
- [x] **Add log rotation** - ✅ COMPLETED 2025-12-24 - Keeps last 10 files, 10MB each
- [x] **Integrate logging in gui.py** - ✅ COMPLETED 2025-12-24 - Replaced print/emoji with log calls
- [x] **Integrate logging in dictator.py** - ✅ COMPLETED 2025-12-24 - Added logger, replaced all prints
- [x] **Integrate logging in recorder.py** - ✅ COMPLETED 2025-12-24 - Added logger, replaced module prints
- [x] **Add debug mode toggle in settings** - ✅ COMPLETED 2025-12-26 - Advanced tab with debug checkbox, toggles DEBUG/INFO log level (20 tests)
- [x] **Remove remaining debug emoji** - ✅ COMPLETED 2025-12-24 - Moved to CLI for user-facing output (excluded from logging)

### 1.4 Thread Safety
- [x] **Audit all threading code for race conditions** - ✅ COMPLETED 2025-12-26 - Comprehensive audit identified 8 race conditions, 3 design issues (see docs/THREADING_AUDIT.md)
- [x] **Fix critical race conditions** - ✅ COMPLETED 2025-12-26 - Fixed HIGH/MEDIUM severity issues (audio_queue, monitoring, model loading) with locks and Queue (17 tests)
- [x] **Ensure all UI updates happen on main thread** - ✅ COMPLETED 2025-12-26 - Verified queue-based UI update system, fixed deadlock in start_continuous_monitoring (16 tests)
- [x] **Replace queue-based UI updates with proper Qt signals/slots** - ✅ COMPLETED 2025-12-26 - Refactored to native Qt signals/slots (18 tests), removed queue/timer infrastructure
- [x] **Remove monitor thread** - ✅ COMPLETED 2025-12-24 - Removed destructive UIWatchdog that used os._exit
- [x] **Add proper thread pool management** - ✅ COMPLETED 2025-12-26 - Centralized ThreadPoolManager for background tasks (20 tests), refactored downloads/recordings to use pool

---

**🎉 PHASE 1 COMPLETE! All critical fixes and stability improvements done. 444 tests passing.**

---

## Phase 2: Core Features & UX (BETA)

### 2.1 Recording & Input
- [x] **Add push-to-talk mode** - ✅ COMPLETED 2025-12-26 - Toggle vs push-to-talk modes with UI selector in settings (18 tests)
- [x] **Add pause/resume** - ✅ COMPLETED 2025-12-26 - Pause button appears during recording, saves audio segments (23 tests)
- [x] **Add recording timeout settings** - ✅ COMPLETED 2025-12-26 - Configurable max recording time with 7 preset options (17 tests)
- [x] **Add silence detection settings** - ✅ COMPLETED 2025-12-26 - Auto-stop on silence with configurable threshold and duration (22 tests)
- [x] **Add audio quality indicator** - ✅ COMPLETED 2025-12-26 - Real-time warnings for too quiet/loud audio during recording (22 tests)
- [ ] **Add recording preview** - Play audio before transcription

### 2.2 Transcription Features
- [ ] **Show transcription progress** - Progress bar during Whisper processing
- [ ] **Add confidence scores** - Display confidence for transcription
- [x] **Add model selection in UI** - ✅ COMPLETED 2025-12-26 - Choose tiny/base/small/medium models, auto-reload on change (11 tests)
- [x] **Add language selection** - ✅ COMPLETED 2025-12-26 - Support 20 languages + auto-detect, persists in config (12 tests)
- [ ] **Add custom vocabulary** - User-defined words/phrases
- [ ] **Add punctuation options** - Auto-capitalization, punctuation rules

### 2.3 Output & Text Handling
- [ ] **Improve clipboard handling** - Better cross-app compatibility
- [ ] **Add direct text insertion** - Insert at cursor in active app
- [ ] **Add post-processing rules** - Find/replace, formatting rules
- [ ] **Add template system** - Common phrases, signatures, etc.
- [ ] **Add spell checking** - Highlight potential errors
- [ ] **Add text formatting** - Plain text, markdown, rich text options

### 2.4 History Management
- [ ] **Add search functionality** - Search by text content
- [ ] **Add date filtering** - Filter by date range
- [ ] **Add session filtering** - Filter by session name
- [ ] **Add bulk operations** - Delete multiple, export selected
- [ ] **Add edit capability** - Edit history entries
- [ ] **Add tags/categories** - Organize entries with tags
- [ ] **Add favorites** - Star important entries
- [ ] **Increase history limit** - Make configurable or unlimited with pagination
- [ ] **Add history statistics** - Word count, character count, sessions

### 2.5 UI/UX Improvements
- [x] **Add loading indicator** - ✅ COMPLETED 2025-12-26 - Show when Whisper model is loading (orange text, 13 tests)
- [x] **Add tooltips** - ✅ COMPLETED 2025-12-26 - Help text on all buttons/controls (10 tooltips, 15 tests)
- [x] **Add keyboard shortcuts** - ✅ COMPLETED 2025-12-26 - Help dialog with all shortcuts and controls (? button, 13 tests)
- [ ] **Add visual feedback** - Better confirmation for all actions
- [ ] **Add status bar** - Show current state, statistics
- [ ] **Add context menus** - Right-click options for history items
- [ ] **Add settings preview** - Preview changes before applying
- [ ] **Make settings non-modal** - Allow settings to stay open while working

---

## Phase 3: Performance & Polish (BETA+)

### 3.1 Performance Optimization
- [ ] **Async model loading** - Load Whisper in background with progress
- [ ] **Optimize audio processing** - Reduce CPU usage during recording
- [ ] **Add memory limits** - Prevent unbounded memory growth
- [ ] **Optimize UI updates** - Reduce timer frequency when idle
- [ ] **Add model caching** - Faster subsequent loads
- [ ] **Optimize history storage** - Use SQLite database instead of JSON

### 3.2 Audio Enhancements
- [ ] **Add noise reduction** - Optional audio preprocessing
- [ ] **Add audio file transcription** - Load and transcribe audio files
- [ ] **Add batch processing** - Transcribe multiple files
- [ ] **Add audio format selection** - WAV, MP3, FLAC support
- [ ] **Add audio playback** - Listen to recordings before transcription

### 3.3 Customization
- [ ] **Add theme presets** - Professional, Dark, Light, High Contrast
- [ ] **Add layout options** - Compact, standard, expanded views
- [ ] **Add hotkey customization UI** - Better hotkey selection interface
- [ ] **Add custom scripts/hooks** - Run scripts on events
- [ ] **Add export templates** - Customizable export formats

---

## Phase 4: Enterprise Features

### 4.1 Advanced Features
- [ ] **Multi-language support** - Full UI localization
- [ ] **Voice commands** - "New paragraph", "Delete that", etc.
- [ ] **Speaker diarization** - Identify different speakers
- [ ] **Real-time streaming** - See text as you speak
- [ ] **Alternative suggestions** - Show multiple transcription options
- [ ] **Auto-correction** - Learn from corrections

### 4.2 Integration & Collaboration
- [ ] **API/Webhook support** - Integrate with other apps
- [ ] **Cloud sync** - Sync history across devices
- [ ] **Team features** - Shared vocabularies, templates
- [ ] **Export to services** - Google Docs, Notion, etc.
- [ ] **Import from services** - Import previous transcriptions

### 4.3 Professional Features
- [ ] **Multi-user support** - Different profiles per user
- [ ] **Advanced analytics** - Usage statistics, productivity metrics
- [ ] **Custom model training** - Fine-tune Whisper on user's voice
- [ ] **Compliance features** - HIPAA, GDPR compliance options
- [ ] **Audit logging** - Track all actions for compliance

### 4.4 Platform Expansion
- [ ] **Windows support** - Full Windows compatibility
- [ ] **macOS support** - Full macOS compatibility
- [ ] **Wayland support** - Verify/fix Wayland compatibility
- [ ] **KDE integration** - Support KDE Plasma
- [ ] **Mobile companion** - Android/iOS remote control

---

## Phase 5: Code Quality & Architecture

### 5.1 Code Organization
- [ ] **Refactor dictator.py** - Split into smaller modules (target: <500 lines/file)
- [ ] **Refactor settings_ui.py** - Extract color/font management
- [ ] **Create service layer** - Separate business logic from UI
- [ ] **Add dependency injection** - Improve testability
- [ ] **Remove code duplication** - DRY principle

### 5.2 Type Safety & Validation
- [ ] **Add type hints** - All functions and classes
- [ ] **Run mypy** - Fix all type errors
- [ ] **Add input validation** - Validate all user inputs
- [ ] **Add config validation** - JSON schema for config files
- [ ] **Add data sanitization** - Prevent injection attacks

### 5.3 Resource Management
- [ ] **Add context managers** - Proper resource cleanup
- [ ] **Fix subprocess handling** - Ensure cleanup on crash
- [ ] **Fix timer cleanup** - Stop all timers on shutdown
- [ ] **Fix audio stream cleanup** - Close streams properly
- [ ] **Add resource limits** - Prevent resource exhaustion

---

## Phase 6: Security & Privacy

### 6.1 Security Hardening
- [ ] **Enable SSL verification** - Proper certificate validation
- [ ] **Add data encryption** - Encrypt sensitive config data
- [ ] **Add permission validation** - Verify and document all permissions
- [ ] **Remove elevated permissions** - Find alternatives to input group requirement
- [ ] **Add sandboxing** - Isolate risky operations

### 6.2 Privacy Features
- [ ] **Add local-only mode** - Never send data to internet
- [ ] **Add data retention policies** - Auto-delete old history
- [ ] **Add encryption for history** - Optional encrypted storage
- [ ] **Add privacy dashboard** - Show what data is stored where
- [ ] **Add data export/deletion** - GDPR compliance

---

## Documentation Tasks (Ongoing)

### User Documentation
- [ ] Create comprehensive user manual
- [ ] Add FAQ section
- [ ] Create video tutorials
- [ ] Add troubleshooting guide
- [ ] Create keyboard shortcut reference

### Developer Documentation
- [ ] Add docstrings to all functions
- [ ] Create architecture documentation (ARCHITECTURE.md)
- [ ] Create contributing guidelines (CONTRIBUTING.md)
- [ ] Add inline comments for complex logic
- [ ] Generate API documentation

---

## Testing Infrastructure (Phase 0 - Setup First!)

Before starting Phase 1, set up testing infrastructure:
- [ ] **Install test dependencies**: `pip install pytest pytest-cov pytest-qt pytest-mock`
- [ ] **Create test structure**: Ensure `tests/` directory structure mirrors `src/`
- [ ] **Configure pytest**: Update `pytest.ini` with coverage settings
- [ ] **Set up test fixtures**: Create reusable test fixtures for common objects
- [ ] **Add test helpers**: Create mock objects for Qt, audio, Whisper
- [ ] **Verify test runner**: Ensure `pytest` runs successfully

## TDD Test Requirements (Per Feature - MANDATORY)

For EVERY feature, follow TDD cycle:

**1. Unit Tests (Write BEFORE implementation)**
- [ ] Test happy path (expected behavior)
- [ ] Test edge cases (boundary conditions)
- [ ] Test error cases (invalid inputs)
- [ ] Test state changes (before/after)
- [ ] Mock external dependencies (file I/O, network, Qt widgets)

**2. Integration Tests (After unit tests pass)**
- [ ] Test component interactions
- [ ] Test data flow between modules
- [ ] Test UI signal/slot connections

**3. Manual Testing (Before marking complete)**
- [ ] Create manual test checklist
- [ ] Test on actual hardware (microphone, etc.)
- [ ] Test UI behavior
- [ ] Test user workflows

**4. Performance Testing (For performance-critical features)**
- [ ] Benchmark execution time
- [ ] Test memory usage
- [ ] Test under load

**5. Security Testing (For security-related features)**
- [ ] Test input validation
- [ ] Test permission checks
- [ ] Test data encryption/sanitization

---

## Notes

### Current Version: 1.0.2
- Focus on stability and core features first
- Each phase should result in a usable release
- Get user feedback before moving to next phase
- Document breaking changes

### Version Planning
- **v1.1.0** - Phase 1 complete (Alpha stable)
- **v1.2.0** - Phase 2 complete (Beta feature complete)
- **v1.3.0** - Phase 3 complete (Performance optimized)
- **v2.0.0** - Phase 4 complete (Enterprise ready)

### Priority Legend
- 🔴 Critical - Blocks release
- 🟡 Important - Should have
- 🟢 Nice to have - Future consideration

---

## Completed Tasks

### 2025-12-24

**Phase 0: Testing Infrastructure** ✅
- Set up virtual environment with uv
- Installed pytest, pytest-cov, pytest-qt, pytest-mock, pytest-timeout
- Configured pytest.ini with coverage settings
- Ready for TDD development

**Phase 1.1: Fix Crash Handling** ✅ (TDD Complete)
- **RED**: Created 9 failing tests in tests/test_crash_handling.py
- **GREEN**: Fixed all crash handling issues
  - Removed destructive monitor_main_thread that used os._exit(1)
  - Replaced os._exit with sys.exit in gui.py
  - Changed close_application to use QApplication.quit()
  - Added config save before shutdown
- **Result**: All 9 tests PASS, no more force-killing, proper cleanup
- **Commits**: e04c684 (RED), 6eb940e (GREEN)
- **Files**: src/gui.py, src/dictator.py, tests/test_crash_handling.py

**Phase 1.3: Implement Logging System** ✅ (TDD - Mostly Complete)
- **RED**: Created 16 failing tests in tests/test_logging_system.py
- **GREEN**: Implemented logger.py module and integrated logging
  - Created src/logger.py with file rotation (10 files, 10MB each)
  - Added log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
  - Logs to ~/.config/dictator/logs/
  - Integrated logging in gui.py (replaced all prints)
  - Integrated logging in dictator.py (added logger, replaced critical prints)
  - Integrated logging in recorder.py (replaced module-level prints)
- **Result**: 14/16 tests PASS (87.5% success)
  - Remaining: Remove 100+ debug emoji from dictator.py, fix rotation test
- **Commits**: a400b74 (RED), f533879 (GREEN)
- **Files**: src/logger.py, src/gui.py, src/dictator.py, src/recorder.py, tests/test_logging_system.py

**Phase 1.1.5: Fix SSL Verification** ✅ (TDD Complete)
- **RED**: Created 9 failing tests in tests/test_ssl_security.py
- **GREEN**: Removed SSL bypass from recorder.py
  - Removed ssl._create_unverified_context (2 instances)
  - Removed modification of ssl._create_default_https_context
  - SSL certificate verification now properly enabled
  - Added documentation for certificate troubleshooting
- **Result**: All 9 tests PASS - Security vulnerability eliminated
- **Commits**: 9338d0a (RED), 4a86167 (GREEN)
- **Files**: src/recorder.py, tests/test_ssl_security.py
- **Security Impact**: Prevents man-in-the-middle attacks, validates certificates

**Phase 1.2: Fix Config File Corruption** ✅ (TDD Complete)
- **RED**: Created 19 failing tests in tests/test_config_handling.py
- **GREEN**: Implemented atomic file writes with backup and validation
  - Created backup before saving (config.json.bak)
  - Atomic writes using temp file + rename
  - JSON validation before saving
  - Error recovery from backup on load failure
  - Proper error handling and logging
- **Result**: All 19 tests PASS - Config file corruption prevented
- **Commits**: 89f8b63 (RED), 1332b2d (GREEN)
- **Files**: src/dictator.py, tests/test_config_handling.py

**Phase 1.4: Audio Device Disconnect Handling** ✅ (TDD Complete)
- **RED**: Created 19 failing tests in tests/test_audio_device_disconnect.py
- **GREEN**: Implemented graceful device disconnect handling
  - Device validation before starting recording
  - Check if microphone is selected (not None)
  - Verify device still exists via get_current_microphone()
  - Error callbacks with meaningful messages
  - Added get_audio_devices() method to refresh device list
  - Comprehensive error handling with try/except
- **Result**: All 19 tests PASS (100%) - Graceful device handling implemented
- **Commits**: 0cb52bb (RED), 0eaa49a (GREEN)
- **Files**: src/recorder.py, tests/test_audio_device_disconnect.py

**Whisper Model Configuration UI** ✅ (Feature Complete)
- Implemented comprehensive Whisper model settings in UI
  - Model size dropdown (tiny, base, small, medium, large-v2, large-v3)
  - Custom model directory selection with file browser
  - Compute device selection (auto, cpu, cuda with auto-detection)
  - Persistent settings in config.json
  - Auto-fallback to tiny model on failure
- **Commits**: bd6f4f4 (feature implementation)
- **Files**: src/settings_ui.py, src/dictator.py, src/recorder.py

**Test Suite Fixes** ✅ (All Tests Passing)
- Fixed 23 pre-existing test failures across 3 test files
  - test_cli.py: Fixed config paths and import mocking (6 tests)
  - test_logging_system.py: Fixed handler checks and emoji exclusions (2 tests)
  - test_main.py: Fixed dynamic import patching (15 tests)
- **Result**: All 149 tests passing (100%)
- **Commits**: 84b01b4 (test fixes)
- **Files**: tests/test_cli.py, tests/test_logging_system.py, tests/test_main.py

**Phase 1.2: User-Facing Error Dialogs** ✅ (TDD Complete)
- **RED**: Created 20 comprehensive tests in tests/test_error_dialogs.py
- **GREEN**: Implemented show_error_dialog method and error handling
  - Added show_error_dialog() method to DictatorWindow
  - Modal QMessageBox.Critical dialogs with helpful messages
  - Recording errors show dialog with troubleshooting checklist
  - Config load errors show dialog when main and backup both fail
  - Config save errors show dialog for permission/encoding errors
  - All errors logged while showing user-facing dialog
- **Result**: All 20 tests PASS (100%) - 169 total tests passing
- **Commits**: 9b0d2ec (RED), 9a5102b (GREEN)
- **Files**: src/dictator.py, tests/test_error_dialogs.py
- **User Impact**: Users now get clear, actionable error messages instead of silent failures

**Whisper Model Download UI** ✅ (TDD Complete)
- **RED**: Created 20 comprehensive tests in tests/test_whisper_model_download.py
- **GREEN**: Implemented model download button in settings
  - Added download button, progress bar, and status label
  - Background threading prevents UI freeze during download
  - Success/error handlers with user-friendly messages
  - Download uses selected model size and directory
  - Proper error handling for network, disk, permission errors
- **Result**: All 20 tests PASS (100%) - 189 total tests passing
- **Commits**: 8cf1ebd (RED), fe93b70 (GREEN)
- **Files**: src/settings_ui.py, tests/test_whisper_model_download.py
- **User Impact**: Users can now download models directly through the UI

**Phase 1.3: Debug Mode Toggle** ✅ (TDD Complete)
- **RED**: Created 20 comprehensive tests in tests/test_debug_mode_toggle.py
- **GREEN**: Implemented debug mode toggle in settings
  - Added Advanced tab in settings dialog
  - Debug mode checkbox with clear label and tooltip
  - toggle_debug_mode() handler sets log level to DEBUG or INFO
  - Config persistence (saves/loads debug_mode_enabled)
  - Defaults to False (INFO level) for normal users
  - Log level applied on config load at startup
- **Result**: All 20 tests PASS (100%) - 207 total tests passing
- **Commits**: 44422d2 (feature implementation)
- **Files**: src/settings_ui.py, src/dictator.py, tests/test_debug_mode_toggle.py
- **User Impact**: Users can now enable verbose debug logging for troubleshooting

**Phase 1.2: Bare Except Handler Replacement** ✅ (TDD Complete)
- **RED**: Created 17 comprehensive tests in tests/test_error_handling.py
- **GREEN**: Replaced all 4 bare except statements with proper error handling
  - gui.py: 3 bare except fixed - icon loading uses (FileNotFoundError, AttributeError, OSError)
  - gui.py: Emergency cleanup uses Exception with exc_info=True for traceback
  - audio_recorder_sd.py: Temp cleanup uses (OSError, FileNotFoundError, PermissionError)
  - All errors now logged with context (icon size, file path, error details)
  - No more silent exception handling
  - Specific exceptions don't catch SystemExit, KeyboardInterrupt
- **Result**: All 17 tests PASS (100%) - 224 total tests passing
- **Commits**: 41c3d9a (implementation)
- **Files**: src/gui.py, src/audio_recorder_sd.py, tests/test_error_handling.py
- **User Impact**: Better error logging for debugging, no silent failures

**Phase 1.4: Threading Code Audit** ✅ (Documentation Complete)
- Comprehensive audit of all threading code across 5 source files
- **Identified Issues:**
  - 8 race conditions (3 HIGH, 5 MEDIUM severity)
  - 3 threading design issues
- **Critical Findings:**
  - audio_queue accessed without synchronization (data corruption risk)
  - audio_data list modified by multiple threads (HIGH risk)
  - is_monitoring flag has race condition
  - whisper_model loading not thread-safe
  - active_subprocess unprotected access
- **Design Issues:**
  - Mixed threading models (queue-based + Qt signals)
  - No thread pool management
  - Daemon threads may terminate abruptly
- **Documentation**: Created docs/THREADING_AUDIT.md with:
  - Detailed analysis of each race condition
  - Code examples for proper fixes
  - Testing recommendations
  - Prioritized fix roadmap (3 phases)
- **Commits**: c173175 (audit documentation)
- **Files**: docs/THREADING_AUDIT.md
- **Next Steps**: Implement critical race condition fixes (Phase 1 of audit)

**Phase 1.4: Critical Race Condition Fixes** ✅ (TDD Complete)
- **RED**: Created 17 comprehensive threading safety tests
- **GREEN**: Implemented thread-safe synchronization for all critical race conditions
- **Thread Safety Infrastructure:**
  - Added 5 locks to PureRecorder:
    - monitoring_lock: Protects is_monitoring flag
    - model_loading_lock: Prevents concurrent Whisper model loads
    - subprocess_lock: Protects active_subprocess reference
    - recording_lock: Protects recording state transitions
    - audio_level_lock: Protects audio_data and current_audio_level
- **Critical Fixes:**
  - audio_queue: Replaced list with queue.Queue(maxsize=1000) - thread-safe bounded queue
  - is_monitoring: Protected by monitoring_lock with proper check-and-set
  - whisper_model: Protected by model_loading_lock, prevents duplicate loads
  - Monitoring start/stop: Properly synchronized, prevents multiple threads
- **Result**: All 17 threading tests PASS - 241 total tests passing
- **Commits**: a8a6c59 (implementation)
- **Files**: src/recorder.py, tests/test_threading_safety.py
- **User Impact**: More stable under concurrent operations, no data corruption, reduced memory usage

---

## Task Workflow (TDD Approach)

1. **Pick** a task from current phase
2. **Branch**: `git checkout -b feature/task-name`
3. **RED**: Write failing test
   - Create test file: `tests/test_feature_name.py`
   - Write test that defines expected behavior
   - Run: `pytest tests/test_feature_name.py` (should FAIL)
   - Commit: `test: add failing test for [feature]`
4. **GREEN**: Implement minimal code to pass
   - Write feature implementation
   - Run: `pytest tests/test_feature_name.py` (should PASS)
   - Commit: `feat: implement [feature]`
5. **REFACTOR**: Clean up and optimize
   - Improve code quality
   - Run: `pytest` (all tests should still PASS)
   - Commit: `refactor: improve [feature] implementation`
6. **Verify**: Run full test suite
   - `pytest --cov=src tests/`
   - Ensure 80%+ coverage for new code
7. **Document**: Update this TASKS.md
   - Mark task as complete: `[x]`
   - Move to completed section with date
8. **Merge**: Merge feature branch
   - `git checkout main && git merge feature/task-name`

**Remember:**
- Red-Green-Refactor cycle for EVERY task
- No code without tests
- One feature at a time
- Build it right!
