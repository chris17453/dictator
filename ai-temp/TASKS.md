# DICTATOR - Development Task List

**Goal:** Complete Alpha/Beta features, then build towards enterprise dictation app
**Last Updated:** 2025-12-24

---

## Phase 1: Critical Fixes & Stability (ALPHA)

### 1.1 Critical Bug Fixes
- [ ] **Fix crash handling** - Remove force-kill monitor thread (gui.py:96-115)
- [ ] **Fix resource cleanup** - Replace `os._exit(0)` with proper shutdown (dictator.py:1383)
- [ ] **Fix config file corruption** - Add validation and backup before save
- [ ] **Fix audio device disconnect handling** - Graceful handling when mic unplugged
- [ ] **Fix SSL verification** - Remove SSL bypass for Whisper downloads (recorder.py:83)

### 1.2 Error Handling
- [ ] Replace all bare `except: pass` with proper error handling
- [ ] Add user-facing error dialogs for failures
- [ ] Implement config load/save error reporting
- [ ] Add error recovery for failed transcriptions
- [ ] Handle microphone permission errors gracefully

### 1.3 Logging System
- [ ] Replace print() statements with Python logging module
- [ ] Add log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- [ ] Write logs to file in `~/.config/dictator/logs/`
- [ ] Add log rotation (keep last 10 files)
- [ ] Add debug mode toggle in settings
- [ ] Remove all debug emoji (🔥, 🚨) from production code

### 1.4 Thread Safety
- [ ] Audit all threading code for race conditions
- [ ] Replace queue-based UI updates with proper Qt signals/slots
- [ ] Remove monitor thread or make it non-destructive
- [ ] Add proper thread pool management
- [ ] Ensure all UI updates happen on main thread

---

## Phase 2: Core Features & UX (BETA)

### 2.1 Recording & Input
- [ ] **Add push-to-talk mode** - Hold key to record, release to stop
- [ ] **Add pause/resume** - Pause during recording without stopping
- [ ] **Add recording timeout settings** - User configurable max recording time
- [ ] **Add silence detection settings** - Configurable VAD sensitivity
- [ ] **Add audio quality indicator** - Show when audio is too quiet/loud
- [ ] **Add recording preview** - Play audio before transcription

### 2.2 Transcription Features
- [ ] **Show transcription progress** - Progress bar during Whisper processing
- [ ] **Add confidence scores** - Display confidence for transcription
- [ ] **Add model selection in UI** - Choose tiny/base/small/medium models
- [ ] **Add language selection** - Support multiple languages
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
- [ ] **Add loading indicator** - Show when Whisper model is loading
- [ ] **Add tooltips** - Help text on all buttons/controls
- [ ] **Add keyboard shortcuts** - Document and expand shortcuts
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

## Testing Tasks (Per Feature)

For each feature implemented:
- [ ] Write unit tests
- [ ] Write integration tests
- [ ] Manual testing checklist
- [ ] Performance testing
- [ ] Security testing

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

_None yet - let's get started!_

---

## Task Workflow

1. Pick a task from current phase
2. Create feature branch: `git checkout -b feature/task-name`
3. Implement feature
4. Test thoroughly
5. Commit with descriptive message
6. Mark task as complete in this file
7. Move to completed section
8. Continue!

Remember: One feature at a time, one commit per feature. Build it right!
