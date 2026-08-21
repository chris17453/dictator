# dictator

Speech to text, without a window.

Press two keys, talk, and the text lands in whatever field has focus — and on
your clipboard. **Tap** the chord to toggle; **hold** it to dictate only while
held. There is no UI in normal operation and nothing to keep on screen.

Runs as a headless user service on **X11 and Wayland**.

```
Super+D            tap to start, tap to stop
Super+D (held)     dictate while held, delivers on release
Super+Escape       discard what you are saying
```

## Install

```bash
pip install the-dictator
dictator setup --install      # systemd unit + desktop entry
dictator setup --no-portal    # optional: never be prompted (see below)
dictator doctor               # confirm it worked
```

From a checkout, `make setup` does the same.

### Two things worth knowing before you start

**The systemd unit is not optional on GNOME.** GNOME refuses to bind shortcuts
for an application it cannot identify, and xdg-desktop-portal derives that
identity from the systemd unit a process runs under:

```
gnome-control-c: Discarded shortcut bind request from application
                 with an invalid app_id ><
```

A daemon started from a shell has no unit, so no identity, so no shortcut.
`dictator setup --install` is what gives it one.

**`--no-portal` is a real trade.** It grants direct access to the kernel's input
devices, so nothing ever prompts and hold-to-talk works everywhere. It also
means any process running as you can read every keystroke and type into any
window — the same power any X11 client has, and what `ydotool` needs.
[device-access.md](docs/device-access.md) is the whole story. It needs the
`evdev` extra, which is a C extension:

```bash
sudo dnf install python3-evdev          # or apt / pacman / zypper
```

Skip it and everything still works through the desktop portal, which asks once
for the shortcut and once for typing, then never again.

## Using it

| Command | What it does |
|---|---|
| `dictator toggle` | Start dictating, or stop and deliver |
| `dictator start` / `dictator stop` | Explicit control, for scripts |
| `dictator push` | Dictate for as long as the command runs |
| `dictator cancel` | Discard the utterance in progress |
| `dictator again [id]` | Deliver a stored transcript again |
| `dictator status` | What the daemon is doing right now |
| `dictator doctor` | Check every dependency and say what to fix |
| `dictator watch` | Live transcription as you speak |
| `dictator meter` | Live input levels in the terminal |
| `dictator stats` | Counters and measured latency percentiles |
| `dictator health` | One line, and an exit code, for monitoring |

Everything goes through the daemon's D-Bus API, so `dictator toggle` works even
where global shortcuts do not — bind it to a key yourself if you prefer.

## Configuration

```bash
dictator config list                   # values, and where each came from
dictator config set model.name small
dictator config sample                 # a commented file to start from
dictator config edit                   # open yours in $EDITOR
```

Layered: built-in defaults, `/etc/dictator/config.toml`,
`~/.config/dictator/config.toml`, `DICTATOR_*` environment variables, then
command-line overrides. Changes reach a running daemon immediately.

Every setting is listed in [configuration.md](docs/configuration.md).

### Shortcuts

```bash
dictator keys list
dictator keys set dictate "Super+d"
dictator keys check "Ctrl+Alt+Space"    # validate without binding
dictator keys conflicts                 # what the desktop already claims
```

The default is `Super+D` because `Super+Space` is GNOME's input-method switcher
— `keys conflicts` is how that was found.

### Models

`auto` picks `large-v3-turbo` on a GPU and `base` on a CPU.

```bash
dictator models list
dictator models set large-v3-turbo
```

Weights are checked against a recorded SHA-256 before loading. The first time a
model is seen its digest is recorded and enforced from then on — trust on first
use, which is weaker than a shipped pin and is described that way rather than
dressed up.

For CUDA, `pip install 'the-dictator[cuda]'`. ctranslate2 links against cuDNN
but does not bundle all of it, and the missing symbol aborts the process
mid-decode rather than raising — so CUDA is verified in a subprocess before use,
and falls back to the CPU with a reason if it fails.

### Microphone

```bash
dictator devices              # list, with the active one marked
dictator devices set yeti     # matches on name or description
dictator devices cycle        # bindable to a shortcut
```

Devices are addressed by stable name, never by a positional index. Capture opens
at whatever rate the device offers and resamples to the 16 kHz Whisper wants,
because plenty of microphones refuse anything but 44.1 or 48 kHz.

**Remote sessions** reach no local sound card, so a microphone must be
redirected by the remote-desktop protocol — FreeRDP `/microphone`, Remmina's
*Redirect microphone*, mstsc's *Record from this computer*. GNOME Remote Desktop
implements RDP audio input but no camera redirection.
[troubleshooting.md](docs/troubleshooting.md) covers building a virtual source
if your client cannot help.

### Memory

Every utterance is stored in SQLite with a full-text index.

```bash
dictator history
dictator search "quarterly forecast"
dictator again 42
```

Audio is **not** retained by default. Retention is bounded by
`memory.retain_days`, and `memory.redact_patterns` matches text that is
delivered but never stored.

### Lexicon

Words the recogniser should expect, and rewrites it should always apply.

```bash
dictator lexicon add ctranslate2 Kubernetes
dictator lexicon fix cubernetes Kubernetes
```

Learning from your corrections is opt-in (`lexicon.learn`) and requires a
correction to be seen repeatedly before it is trusted, so one stray edit cannot
poison it.

## How it works

One long-lived user service holds everything that must be warm, stateful, or
consented: the resident model, the open audio stream, and the platform sessions.
Every client — the CLI, and any future UI — is an ordinary subscriber to its
D-Bus contract on `com.watkinslabs.Dictator1`.

```
shortcut backend ──▶ dictatord ──▶ injection backend ──▶ focused field
                         │
                         ├─ ring buffer (300 ms pre-roll) + VAD
                         ├─ streaming ASR on CUDA
                         └─ SQLite memory + lexicon
```

Capture runs continuously, so the 300 ms *before* the chord registered is
already in hand — which is why the first word is not clipped.

[architecture.md](docs/architecture.md) explains the rest, including why there
has to be a daemon at all.

### Platform support

| Environment | Shortcuts | Injection | App detection | Tier |
|---|---|---|---|---|
| Any desktop, device access granted | `evdev` | `uinput` | chord-bound | 1 |
| GNOME · Wayland | portal | portal | chord-bound | 1 |
| Any WM · X11 | `XGrabKey` | `XTEST` | automatic | 1 |
| KDE · Wayland | portal | portal | chord-bound | 2 |
| Sway / Hyprland | portal | `wtype` | chord-bound | 2 |
| Headless / CI | none | clipboard | n/a | 3 |

The `evdev`/`uinput` pair is preferred whenever available: it never prompts and
still reports key release, so hold-to-talk works. The portal's guarantee is
consent, not capability — it is the fallback, not the ideal.

The display server is detected once, keying on `XDG_SESSION_TYPE` first —
because under XWayland `DISPLAY` is set on a *Wayland* session, so
`if DISPLAY: use_x11()` picks the broken path on every modern desktop.

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

`dictator health` exits `0` when healthy or still starting, `1` when degraded,
`2` when the daemon is down. "Starting" is deliberately not a failure — a daemon
waiting for you to approve a consent prompt is not broken, and restarting it
would only re-ask the question.

`dictator stats` reports what has actually been measured against the latency
budgets, so the targets are checkable rather than claimed. Fewer than five
samples reports `unknown` rather than a green tick.

```bash
dictator stats --prometheus     # scrapeable text exposition
dictator stats --json
```

The service runs confined: `ProtectSystem=strict`, `ProtectHome=read-only`,
`NoNewPrivileges`, a system-call filter, and a device allow-list narrow enough
to leave only the sound card and the GPU reachable. `systemd-analyze --user
security` scores it 4.6 ("OK"). `TimeoutStopSec=30` lets an utterance already
being transcribed finish, because those words are the one thing a restart cannot
recover.

## Development

```bash
make dev
make test          # no display server required
make daemon        # run in the foreground with debug logging
make logs          # follow the service log
make docs          # regenerate the generated reference pages
```

`dictator daemon` runs the service in the foreground when you want its log in
front of you, and `dictator reload` re-reads configuration without a restart.

The test suite targets the D-Bus contract, not internals, and runs entirely
headless — which is the point of the null backends. See
[docs/](docs/README.md).

## Requirements

- Python 3.10+
- PipeWire or PulseAudio
- `wl-clipboard` on Wayland
- A GPU is optional; `the-dictator[cuda]` adds cuDNN for CUDA decoding
- `the-dictator[no-portal]` (or your distribution's `python3-evdev`) for the
  prompt-free backends

## License

MIT
