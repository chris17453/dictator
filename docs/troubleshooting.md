# Troubleshooting

Start here, always:

```bash
dictator doctor
```

It checks every dependency and gives each failure a remedy that is a command
you can run. It exists because v1's worst property was failing silently and
then misdiagnosing itself — telling users to join the `input` group when the
real problem was that an X11 library cannot see Wayland input at all.

```bash
dictator doctor --verbose     # every backend that was probed, not just the winner
dictator status               # what the daemon is doing now
dictator health               # one line, and an exit code for monitoring
dictator stats                # counters and measured latency
journalctl --user -u app-com.watkinslabs.Dictator.service -f
```

---

## The chord does nothing

**Check what is bound and whether anything else claims it.**

```bash
dictator keys list
dictator keys conflicts
```

`Super+Space` is the input-method switcher on GNOME, which is why the default
is `Super+D`. A chord the desktop already owns will usually lose.

**Check a shortcut backend is actually active.**

```bash
dictator status | grep shortcuts
```

`portal - not active` means the binding was never granted. `none` means no
backend was available at all, and dictation only works through
`dictator toggle`.

### GNOME refused the binding

```
gnome-control-c: Discarded shortcut bind request from application
                 with an invalid app_id ><
```

GNOME will not bind shortcuts for an application it cannot identify, and
xdg-desktop-portal derives that identity from the systemd unit the process runs
under. Started from a shell there is no unit, so no identity.

```bash
dictator setup --install     # writes the unit and the desktop entry
```

This is why the systemd unit is mandatory on GNOME rather than a convenience.

### You dismissed the prompt

A declined or unanswered permission is remembered and never re-asked — otherwise
every restart becomes another dialog to dismiss.

```bash
dictator grant          # re-open the question
dictator restart        # trigger the prompt again
```

### You would rather never be asked

```bash
dictator setup --no-portal
```

Grants direct access to the kernel's input devices, so nothing prompts and
hold-to-talk works. Read [device-access.md](device-access.md) first: it is a
real trade, not a formality.

---

## Text is copied but never typed

```bash
dictator status | grep injection
```

`not active` means the typing permission was declined or never granted. The
transcript still reaches your clipboard, so nothing is lost.

```bash
dictator grant injection && dictator restart
```

**Pasting into a terminal does nothing.** Terminals need `Ctrl+Shift+V`; the
default profile sends `Ctrl+V`, which is a control character there. On X11 the
right profile is chosen automatically. On Wayland the focused application cannot
be identified, so bind a second chord and use it for terminals:

```bash
dictator keys set dictate_terminal "Super+Shift+d"
```

**Some applications must never receive synthetic input:**

```bash
dictator config set delivery.clipboard_only_apps keepassxc,bitwarden
```

---

## No microphone

```bash
dictator devices
```

### "this is a remote session with no microphone redirected"

A session with no local seat reaches no local sound card. Either redirect one
from your client, or run dictator where the microphone is.

| Client | Setting |
|---|---|
| FreeRDP | `/microphone` |
| Remmina | RDP profile → Advanced → *Redirect microphone* |
| Windows `mstsc` | Local Resources → Remote audio → *Record from this computer* |

GNOME Remote Desktop implements RDP audio input, so this works once the client
asks for it. It implements no camera redirection at all.

You can also build a virtual source yourself, which needs no client support:

```bash
pactl load-module module-null-sink sink_name=mic_bridge
pactl load-module module-remap-source master=mic_bridge.monitor source_name=bridged_mic
dictator devices set bridged_mic
```

Then stream your local microphone into `mic_bridge`. The `remap-source` step
matters: a bare `.monitor` is a loopback of *output*, and dictator filters those
out because a monitor is never what anyone means by a microphone.

Often the better answer is to run dictator on the machine holding the
microphone — its keystrokes reach the remote session through the client anyway,
with no audio crossing the wire.

### "Invalid sample rate"

Fixed: capture asks for 16 kHz, falls back through the device's own rate, and
resamples. If you still see it, the device rejected every rate tried — report
it with `dictator doctor --verbose`.

### The device disappears mid-sentence

```bash
dictator config set audio.on_device_lost fallback   # the default
```

`fallback` switches to the system default and tells you. `fail` stops instead.

---

## Recognition is poor

**Check which model is actually loaded.** `auto` means `large-v3-turbo` on a
GPU and `base` on a CPU — and `base` is noticeably weaker.

```bash
dictator models current
dictator models set large-v3-turbo
```

**Check the input level.** Too quiet and the VAD never opens; clipping is worse
than quiet.

```bash
dictator meter
```

**Teach it your vocabulary.** Proper nouns and jargon are where Whisper fails
most predictably.

```bash
dictator lexicon add ctranslate2 Kubernetes Watkins
dictator lexicon fix cubernetes Kubernetes
```

**Force the language** if detection keeps guessing wrong:

```bash
dictator config set model.language en
```

**Sentences are being cut short** — the VAD is closing too early:

```bash
dictator config set vad.silence_ms 1200
```

---

## It is slow

```bash
dictator stats
```

Reports measured percentiles against the budgets. Fewer than five samples shows
`unknown` rather than a pass.

- **Decode is slow** — check `model_device` is `cuda`, not `cpu`. CUDA falls
  back silently to the CPU when cuDNN is incomplete; the log says so, and
  `pip install 'the-dictator[cuda]'` fixes it.
- **First use of every session is slow** — the model is not resident:
  `dictator config set model.keep_resident true`.
- **Partials lag** — raise `streaming.interval_ms`, or set
  `streaming.enabled false`. Finals are unaffected.

---

## The daemon will not start

```bash
systemctl --user status app-com.watkinslabs.Dictator.service
journalctl --user -u app-com.watkinslabs.Dictator.service -n 50
```

**`status=226/NAMESPACE`** — the unit confines itself with
`ProtectSystem=strict`, and a directory it is allowed to write does not exist.
`dictator setup --install` creates them.

**`another process already owns com.watkinslabs.Dictator1`** — one is already
running. `dictator status`, or `dictator quit` first.

**Configuration is rejected** — the error names the setting and the fix:

```bash
dictator config list --changed
dictator config reset <setting>
```

Settings that v1 had and v2 does not are reported and ignored, never fatal.

---

## Starting over

```bash
dictator setup --uninstall              # unit and desktop entry
dictator setup --revoke-device-access   # udev rule and group
rm -rf ~/.local/share/dictator ~/.local/state/dictator ~/.config/dictator
```

The first two leave your configuration and transcripts alone. The third is what
removes them.
