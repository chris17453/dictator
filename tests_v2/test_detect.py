"""Session detection, including the trap that produced G-00."""
from dictatord.platform.detect import SessionType, detect


def test_xdg_session_type_wins():
    assert detect({"XDG_SESSION_TYPE": "wayland"}).type is SessionType.WAYLAND
    assert detect({"XDG_SESSION_TYPE": "x11"}).type is SessionType.X11


def test_xwayland_trap_display_is_set_on_wayland():
    """Under XWayland both are set; 'if DISPLAY: use_x11()' picks the broken path."""
    session = detect({
        "XDG_SESSION_TYPE": "wayland",
        "DISPLAY": ":0",
        "WAYLAND_DISPLAY": "wayland-0",
    })
    assert session.type is SessionType.WAYLAND
    assert session.is_wayland and not session.is_x11


def test_wayland_socket_used_when_session_type_absent(tmp_path):
    (tmp_path / "wayland-0").write_text("")
    session = detect({
        "WAYLAND_DISPLAY": "wayland-0",
        "XDG_RUNTIME_DIR": str(tmp_path),
        "DISPLAY": ":0",
    })
    assert session.type is SessionType.WAYLAND


def test_missing_wayland_socket_does_not_claim_wayland(tmp_path):
    session = detect({"WAYLAND_DISPLAY": "wayland-9", "XDG_RUNTIME_DIR": str(tmp_path)})
    assert session.type is SessionType.HEADLESS


def test_headless_when_nothing_is_present():
    session = detect({})
    assert session.type is SessionType.HEADLESS
    assert session.is_headless


def test_unreachable_display_is_not_x11():
    assert detect({"DISPLAY": ":99"}).type is SessionType.HEADLESS


def test_evidence_is_always_recorded():
    for env in ({}, {"XDG_SESSION_TYPE": "wayland"}, {"DISPLAY": ":99"}):
        assert detect(env).evidence
