# Documentation

| | |
|---|---|
| [architecture.md](architecture.md) | How it works, and why it is shaped this way |
| [configuration.md](configuration.md) | Every setting — *generated from the schema* |
| [dbus-api.md](dbus-api.md) | The service contract — *generated from the interface* |
| [faults.md](faults.md) | Fault codes — *generated* |
| [device-access.md](device-access.md) | What `--no-portal` grants, and what it costs |
| [troubleshooting.md](troubleshooting.md) | Symptoms, causes, and commands that fix them |
| [../v2.md](../v2.md) | The assessment of v1 this rebuild implements |

## Generated pages

`configuration.md`, `dbus-api.md` and `faults.md` are produced from the code
that defines them, because a hand-written settings table disagrees with the
product within a release or two.

```bash
make docs
```

CI checks the committed copies match. If a build fails saying the docs are
stale, run that and commit the result.

## Where to start

Installing → the [README](../README.md).
Something is broken → [troubleshooting.md](troubleshooting.md), or
`dictator doctor`, which usually says it more precisely.
Changing a setting → [configuration.md](configuration.md).
Writing a client → [dbus-api.md](dbus-api.md).
Understanding a decision → [architecture.md](architecture.md), and
[v2.md](../v2.md) for the reasoning that produced it.
