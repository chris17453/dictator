# Direct device access

`dictator setup --no-portal` grants the daemon direct access to the kernel's
input devices. Nothing then prompts, and hold-to-talk works everywhere. This
page is what you should read before running it.

## What it grants

| Device | Capability |
|---|---|
| `/dev/input/event*` | reading raw key events — **a keylogging capability** |
| `/dev/uinput` | writing synthetic key events — **an input-injection capability** |

Access is granted to your user, not to dictator. Any process running as you
gains both. There is no way to give it to one program and not another; the
kernel's granularity is the device.

This is the same power any X11 client holds by default, and exactly what
`ydotool`, `dotool` and similar tools require. It is a reasonable trade on a
machine you control and a poor one on a shared host.

## What it changes

```bash
dictator setup --no-portal
dictator setup --revoke-device-access   # undo
```

It writes `/etc/udev/rules.d/70-dictator.rules`, adds you to the `input` group,
and grants an ACL to the devices that already exist.

The rule grants an explicit ACL rather than relying on the group alone. Two
alternatives were considered and rejected:

- `TAG+="uaccess"` grants only to a session attached to a **seat**. A remote
  session has none, so it grants nothing — on the machine this was developed
  against, it handed access to `gdm` instead.
- Group membership alone only reaches processes started after a fresh login, so
  a keyboard plugged in today would not work until you logged out and back in.

The rule names the user who ran setup. That is the honest cost of a file that
lives in `/etc`.

## What it does not do

It does not grab your keyboard. Devices are **monitored**, not grabbed:

- grabbing takes the key away from the application underneath, and
- grabbing takes *every* key on that device, so a crashed daemon would leave
  the keyboard dead.

The cost of monitoring is that the chord also reaches whatever has focus, so
pick one nothing else is bound to. `dictator keys conflicts` checks.

It also does not run anything as root. The daemon stays unprivileged; only the
one-time setup uses `sudo`.

## The requirement

The backends need the `evdev` Python package, which is a C extension and
therefore an optional extra — requiring it would fail the install on any machine
without a compiler and Python headers.

```bash
sudo dnf install python3-evdev        # or apt / pacman / zypper
# or, to build it:
pip install 'the-dictator[no-portal]'
```

`dictator setup --no-portal` checks for it first and refuses rather than
granting device access that nothing would use.

## If you would rather not

Everything works through the desktop portal instead. It asks once for the
shortcut and once for typing, remembers your answer, and never asks again.
`dictator grant` re-opens a question you declined.

The trade runs the other way there: the portal's consent is a real security
property, and `dictator doctor` reports which trust model is active so the
answer is never implicit.
