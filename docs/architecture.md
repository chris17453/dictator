# Architecture

## Why there is a daemon

Three requirements force a long-lived process, independently of each other.

The **model must be resident**. Loading `large-v3-turbo` takes about two
seconds; doing that when someone presses a key makes the product feel broken.

The **portal sessions must be long-lived**. Permission to type into other
windows is granted per session. A process that starts on each keystroke would
ask every time.

The **audio device must stay open**. The first syllable of an utterance happens
before the user's finger leaves the key. A stream opened on demand has already
missed it.

So `dictatord` runs continuously and everything else subscribes to it.

```
PLATFORM      GlobalShortcuts │ RemoteDesktop │ evdev │ uinput │ XGrabKey │ XTEST │ PipeWire
                      ▲               ▲          ▲       ▲         ▲         ▲        ▲
┌─────────────────────┴───────────────┴──────────┴───────┴─────────┴─────────┴────────┴────┐
│ dictatord — systemd user service, no display dependency                                  │
│                                                                                          │
│   Session FSM  ──▶  Ring buffer + VAD  ──▶  Streaming ASR  ──▶  Delivery                  │
│   idle/listening/   300 ms pre-roll        CUDA, resident      clipboard + paste          │
│   transcribing/                                                                          │
│   delivering                                                                             │
│                                                                                          │
│   Memory (SQLite/FTS5) │ Lexicon │ Config │ Metrics │ Consent ledger                      │
└──────────────────────────────────────────┬───────────────────────────────────────────────┘
                                           │
CONTROL PLANE   D-Bus com.watkinslabs.Dictator1
                Toggle · PushBegin/End · Cancel · SetDevice · SetModel · Search · GetState
                    ⟶ StateChanged · Partial · Final · Level · Delivered · Fault
                                           │
CLIENTS         dictator CLI │ doctor │ meter │ watch │ (any future UI)
```

Every client is optional. Deleting all of them leaves dictation working.

## The platform layer

The v1 failure this rebuild exists to fix was a single unguarded `pynput` call —
an X11 client on a Wayland session, where it can neither observe keys nor inject
text. Nothing in the codebase read `XDG_SESSION_TYPE`.

Two narrow interfaces now stand between the daemon and any display server:

```python
class ShortcutBackend:     # bind(chords) → on_press / on_release
class InjectionBackend:    # set_clipboard · send_chord · type_text · focused_app_id
```

Everything above them — the state machine, the ASR pipeline, memory, the CLI —
imports neither. Backends are the only place a platform name appears.

### Selection

Probed once at startup, best first, and recorded so `GetState` and `doctor` can
report which path is live rather than guessing.

| Backend | Shortcuts | Injection | Prompts | Release events | Focused app |
|---|---|---|---|---|---|
| `evdev` / `uinput` | ✓ | ✓ | never | ✓ | ✗ |
| `portal` | ✓ | ✓ | once | ✓ | ✗ |
| `x11` / `xtest` | ✓ | ✓ | never | ✓ | ✓ |
| `none` | — | clipboard only | never | ✗ | ✗ |

`evdev`/`uinput` outrank the portal when available. The portal's guarantee is
*consent*, not capability — it is the fallback, not the ideal. See
[device-access.md](device-access.md) for what granting that costs.

### Session detection

Strict order, because the obvious check is wrong everywhere:

1. `XDG_SESSION_TYPE` when it says `wayland` or `x11`
2. `WAYLAND_DISPLAY`, with a connectable socket
3. `DISPLAY`, with a reachable server
4. otherwise headless

Under XWayland **both** `DISPLAY` and `WAYLAND_DISPLAY` are set, so
`if DISPLAY: use_x11()` selects the broken backend on every modern desktop.
That is exactly the bug v1 shipped.

## The utterance pipeline

```
chord press ─▶ take 300 ms of pre-roll from the ring buffer
               │
capture ───────┼─▶ resample to 16 kHz ─▶ accumulate ─▶ VAD segments
(continuous)   │                              │
               │                              ├─▶ every 400 ms: partial decode ─▶ Partial
               │                              │   (greedy, display only)
chord release ─┘                              │
                                              └─▶ final decode ─▶ Final
                                                        │
                                                        ├─▶ lexicon substitutions
                                                        ├─▶ store (redacted)
                                                        └─▶ deliver
```

**Pre-roll** is why the first word survives. Capture never stops, so audio from
before the chord registered is already in hand.

**Resampling** exists because Whisper wants 16 kHz and many microphones offer
only 44.1 or 48 kHz, refusing anything else outright. The resampler carries a
tail between blocks; converting each block independently clicks at every seam,
and a click reads as a speech onset to the VAD.

**Partials** are speculative re-decodes of a growing buffer, so they can revise
what they already said. Each carries `stable_chars` — how much has survived a
re-decode — so a client can render settled text differently from the tail.
Delivery never uses them.

## Delivery

Clipboard first, paste second, type last.

Per-character injection is slow, order-sensitive, and mangles anything outside
the active keyboard layout, so it is the fallback rather than the mechanism.
The clipboard *is* the delivery path, which is why the transcript is always
there even when injection fails.

| Profile | For | Chord |
|---|---|---|
| `standard` | GTK, Qt, Electron | `Ctrl+V` |
| `terminal` | VTE, Kitty, Alacritty, Foot | `Ctrl+Shift+V` |
| `clipboard-only` | anything you designate | none |

Choosing a profile needs the focused application's identity, which X11 exposes
and Wayland does not. On Wayland the configured default is used, and you state
intent by which chord you press — bind `dictate_terminal` for the terminal
profile.

## Tap or hold

One chord, two behaviours, decided by how long you held it:

- released within `hold_threshold_ms` (250 ms) — a **tap**. Recording continues;
  the next tap stops it.
- held longer — a **hold**. Recording stops on release.

You never choose a mode; the distinction is in your fingers. Recording starts on
press either way, so the first word is captured in both.

Where a backend cannot report release, a press means toggle outright — with hold
semantics no release would ever arrive and the session could not be stopped.

## Failure

Every failure is a `Fault` with a machine-readable code and a remedy that is a
command you can run. A fault the daemon cannot phrase as a remedy is a defect in
the daemon, not a puzzle for the user.

Nothing that can be degraded is fatal. No microphone, a declined shortcut, a
refused typing permission, a missing model — each reduces what works and says
so. The daemon publishes its D-Bus service *before* asking for any consent, so
`dictator status` and `dictator doctor` stay reachable while a dialog is open.

## Testing

The suite targets the D-Bus contract rather than internals, and runs entirely
headless — Tier 3 in the support matrix is what CI exercises on every commit,
which is what the null backends are for.

The X11 backend is automatable under `Xvfb`. The portal path is not: it is a
user-consented service on a live session bus. It is covered by a mock portal for
the contract and a manual matrix for the real thing. Saying which technique
covers what is the difference between a test suite and reassurance.
