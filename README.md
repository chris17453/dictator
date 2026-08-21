# dictator

Speech to text, without a window.

Press two keys, talk, and the text lands in whatever field has focus — and on
your clipboard. Tap the chord to toggle; hold it to dictate only while held.
There is no UI in normal operation and nothing to keep on screen.

Runs as a headless user service on **both X11 and Wayland**.

```
Super+D            tap to start, tap to stop
Super+D (held)     dictate while held, delivers on release
Super+Escape       discard what you are saying
```

## Install

```bash
pip install the-dictator                 # or: make setup, from a checkout
dictator setup --install                 # systemd unit + desktop entry
dictator setup --no-portal               # optional: no prompts, ever
dictator doctor
```

The prompt-free backends need `evdev`, which is a C extension and therefore an
optional extra rather than a hard dependency — a compiler is not something an
install should require. Your distribution almost certainly packages it:

```bash
sudo dnf install python3-evdev     # or apt / pacman / zypper
# or, to build it:  pip install 'the-dictator[no-portal]'
```

Without it, everything still works through the desktop portal; `dictator setup
--no-portal` says so rather than silently granting device access that nothing
would use.

`--no-portal` is the recommended path on a machine you control. It grants the
daemon direct access to the kernel's input devices, so **nothing ever prompts**
and hold-to-talk works. Without it the daemon falls back to the desktop portal,
which asks for permission twice — once for the shortcut, once for typing.

What `--no-portal` grants, stated plainly:

| Device | Capability |
|---|---|
| `/dev/input/event*` | reading raw key events — a keylogging capability |
| `/dev/uinput` | writing synthetic key events — an input-injection capability |

Any process running as you gains both. That is the same power any X11 client
holds by default, and exactly what `ydotool` and similar tools require. Revoke
with `dictator setup --revoke-device-access`.

If you would rather not grant it, everything still works through the portal —
the daemon asks once, remembers your answer, and never asks again. Use
`dictator grant` to re-open a permission you declined.

### Why the systemd unit is not optional on GNOME

GNOME refuses global-shortcut requests from applications it cannot identify,
and xdg-desktop-portal derives that identity from the systemd unit a process
runs under:

```
gnome-control-c: Discarded shortcut bind request from application
                 with an invalid app_id ><.
```

A daemon started from a shell has no unit, so no identity, so no shortcut.
`dictator setup --install` is what gives it one.

## Using it

| Command | What it does |
|---|---|
| `dictator toggle` | Start dictating, or stop and deliver |
| `dictator push` | Dictate for as long as the command runs |
| `dictator cancel` | Discard the utterance in progress |
| `dictator again [id]` | Deliver a stored transcript again |
| `dictator status` | What the daemon is doing right now |
| `dictator doctor` | Check every dependency and say what to fix |
| `dictator stats` | Counters and measured latency percentiles |
| `dictator health` | One-line verdict for monitoring; exits non-zero when degraded |
| `dictator watch` | Live transcription as you speak |
| `dictator meter` | Live input levels in the terminal |

Everything goes through the daemon's D-Bus API, so `dictator toggle` works even
where global shortcuts do not — bind it to a key yourself if you prefer.

## Configuration

```bash
dictator config list              # every setting, and where it came from
dictator config set model.name small
dictator config sample            # a fully commented reference file
dictator config edit              # open it in $EDITOR
```

Settings are layered: built-in defaults, then `/etc/dictator/config.toml`, then
`~/.config/dictator/config.toml`, then `DICTATOR_*` environment variables, then
command-line overrides. Changes apply to the running daemon immediately.

### Shortcuts

```bash
dictator keys list
dictator keys set dictate "Super+d"
dictator keys check "Ctrl+Alt+Space"    # validate without binding
dictator keys conflicts                 # what the desktop has already taken
```

### Models

`auto` picks `large-v3-turbo` on a GPU and `base` on a CPU.

```bash
dictator models list
dictator models set large-v3-turbo
dictator models download small
```

Weights are checked against a recorded SHA-256 before they load. The first time
a model is seen its digest is recorded and enforced from then on — trust on
first use, which is weaker than a shipped pin, and is described that way rather
than dressed up.

### Microphone

```bash
dictator devices              # list, with the active one marked
dictator devices set yeti     # matches on name or description
dictator devices cycle        # bindable to a shortcut
```

**Remote sessions.** A session with no local seat reaches no local sound card,
so a microphone has to be redirected by the remote-desktop protocol. GNOME
Remote Desktop implements RDP audio input, but the *client* must ask for it —
FreeRDP `/microphone`, Remmina's *Redirect microphone*, or in Windows `mstsc`
under Remote audio → *Record from this computer*. It has no camera redirection
at all.

You can also present a microphone to the remote session yourself, without any
client support, using a virtual source:

```bash
pactl load-module module-null-sink sink_name=mic_bridge
pactl load-module module-remap-source master=mic_bridge.monitor source_name=bridged_mic
# then stream your local microphone into mic_bridge over SSH, ffmpeg, etc.
dictator devices set bridged_mic
```

Often the better answer is to run dictator on the machine the microphone is
plugged into: its synthetic keystrokes reach the remote session through the
client anyway, with no audio crossing the wire. `dictator doctor` detects this
situation and says so rather than reporting a microphone that cannot hear.

Devices are addressed by stable name, never by a positional index, and the
daemon reacts to a device disappearing rather than discovering it at the next
attempt.

### Memory

Every utterance is stored in SQLite with a full-text index.

```bash
dictator history
dictator search "quarterly forecast"
dictator again 42
```

Audio is **not** retained by default. Retention is bounded
(`memory.retain_days`), and `memory.redact_patterns` matches text that is
delivered but never stored.

### Lexicon

Words the recogniser should expect, and rewrites it should always apply.

```bash
dictator lexicon add ctranslate2 Kubernetes
dictator lexicon fix cubernetes Kubernetes
```

Learning from your corrections is opt-in (`lexicon.learn`) and requires a
correction to be seen repeatedly before it is trusted.

## How it works

One long-lived user service holds everything that must be warm, stateful, or
consented: the resident model, the open audio stream, and the platform
sessions. Every client — the CLI, and any future UI — is an ordinary subscriber
to its D-Bus contract on `com.watkinslabs.Dictator1`.

```
GlobalShortcuts / XGrabKey ──▶ dictatord ──▶ RemoteDesktop / XTEST ──▶ focused field
                                  │
                                  ├─ ring buffer (300 ms pre-roll) + VAD
                                  ├─ streaming ASR on CUDA
                                  └─ SQLite memory + lexicon
```

Capture runs continuously, so the 300 ms *before* the chord registered is
already in hand — which is why the first word is not clipped.

### Platform support

| Environment | Shortcuts | Injection | App detection | Tier |
|---|---|---|---|---|
| Any desktop, device access granted | evdev | uinput | chord-bound | 1 |
| GNOME · Wayland | portal | portal | chord-bound | 1 |
| Any WM · X11 | XGrabKey | XTEST | automatic | 1 |
| KDE · Wayland | portal | portal | chord-bound | 2 |
| Sway / Hyprland | portal | wtype | chord-bound | 2 |
| Headless / CI | none | clipboard | n/a | 3 |

The evdev/uinput pair is preferred whenever it is available, because it never
prompts and still reports key release, so hold-to-talk works. The portal's
guarantee is consent, not capability — it is the fallback, not the ideal.

The display server is detected once, in strict order, keying on
`XDG_SESSION_TYPE` first — because under XWayland `DISPLAY` is set on a Wayland
session, and `if DISPLAY: use_x11()` picks the broken path on every modern
desktop.

**One asymmetry, stated plainly.** X11 exposes the focused window's class, so
paste profiles (a terminal needs `Ctrl+Shift+V`) are automatic. Wayland exposes
no such thing through any standard interface. There, bind a second chord:

```bash
dictator keys set dictate_terminal "Super+Shift+d"
```

**One security note, also plainly.** X11 places no restriction on grabbing keys
or injecting input — any client can do both to any other, silently. Wayland's
portal consent is not friction; it is the security property. X11 is supported
because people run it, not because it is equivalent. `dictator doctor` reports
which trust model is active.

## Operating it

`dictator health` is built for monitoring: it exits `0` when healthy or still
starting, `1` when degraded, and `2` when the daemon is down. "Starting" is
deliberately not a failure — a daemon waiting for you to approve a consent
prompt is not broken, and restarting it would only re-ask the question.

`dictator stats` reports what has actually been measured against the latency
budgets, so the acceptance targets are checkable rather than claimed. Fewer
than five samples reports `unknown` rather than a green tick.

```bash
dictator stats --prometheus     # scrapeable text exposition
dictator stats --json
```

The service runs confined: `ProtectSystem=strict`, `ProtectHome=read-only`,
`NoNewPrivileges`, a system-call filter, and a device allow-list narrow enough
to leave only the sound card and the GPU reachable. `systemd-analyze --user
security` scores it 4.6 ("OK"). `TimeoutStopSec=30` gives an utterance already
being transcribed time to finish, because those words are the one thing a
restart cannot recover.

## Development

```bash
make dev
make test          # 155 tests, no display server required
make daemon        # run in the foreground with debug logging
make logs          # follow the service log
```

The test suite targets the D-Bus contract, not internals, and runs entirely
headless — which is the point of the null backends.

## Requirements

- Python 3.10+
- PipeWire or PulseAudio
- `wl-clipboard` on Wayland
- A GPU is optional; `nvidia-cudnn-cu12` is needed for CUDA decoding

## License

MIT
