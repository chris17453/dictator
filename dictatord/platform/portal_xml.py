"""Pinned introspection XML for the portal interfaces we depend on.

We deliberately do not introspect the live portal object. Two reasons:

* Correctness. xdg-desktop-portal advertises interfaces whose members are not
  valid D-Bus member names (``org.freedesktop.portal.PowerProfileMonitor`` has
  a ``power-saver-enabled`` property), which strict clients refuse to parse.
  Introspecting the whole object fails on a detail we never use.
* Contract. Declaring exactly the methods and signatures we call means a portal
  that changes shape produces a clear error here, rather than an attribute
  error somewhere deep in a backend.
"""
from __future__ import annotations

GLOBAL_SHORTCUTS = """
<node>
  <interface name="org.freedesktop.portal.GlobalShortcuts">
    <method name="CreateSession">
      <arg type="a{sv}" name="options" direction="in"/>
      <arg type="o" name="handle" direction="out"/>
    </method>
    <method name="BindShortcuts">
      <arg type="o" name="session_handle" direction="in"/>
      <arg type="a(sa{sv})" name="shortcuts" direction="in"/>
      <arg type="s" name="parent_window" direction="in"/>
      <arg type="a{sv}" name="options" direction="in"/>
      <arg type="o" name="request_handle" direction="out"/>
    </method>
    <method name="ListShortcuts">
      <arg type="o" name="session_handle" direction="in"/>
      <arg type="a{sv}" name="options" direction="in"/>
      <arg type="o" name="request_handle" direction="out"/>
    </method>
    <signal name="Activated">
      <arg type="o" name="session_handle"/>
      <arg type="s" name="shortcut_id"/>
      <arg type="t" name="timestamp"/>
      <arg type="a{sv}" name="options"/>
    </signal>
    <signal name="Deactivated">
      <arg type="o" name="session_handle"/>
      <arg type="s" name="shortcut_id"/>
      <arg type="t" name="timestamp"/>
      <arg type="a{sv}" name="options"/>
    </signal>
    <signal name="ShortcutsChanged">
      <arg type="o" name="session_handle"/>
      <arg type="a(sa{sv})" name="shortcuts"/>
    </signal>
    <property name="version" type="u" access="read"/>
  </interface>
</node>
"""

REMOTE_DESKTOP = """
<node>
  <interface name="org.freedesktop.portal.RemoteDesktop">
    <method name="CreateSession">
      <arg type="a{sv}" name="options" direction="in"/>
      <arg type="o" name="handle" direction="out"/>
    </method>
    <method name="SelectDevices">
      <arg type="o" name="session_handle" direction="in"/>
      <arg type="a{sv}" name="options" direction="in"/>
      <arg type="o" name="handle" direction="out"/>
    </method>
    <method name="Start">
      <arg type="o" name="session_handle" direction="in"/>
      <arg type="s" name="parent_window" direction="in"/>
      <arg type="a{sv}" name="options" direction="in"/>
      <arg type="o" name="handle" direction="out"/>
    </method>
    <method name="NotifyKeyboardKeycode">
      <arg type="o" name="session_handle" direction="in"/>
      <arg type="a{sv}" name="options" direction="in"/>
      <arg type="i" name="keycode" direction="in"/>
      <arg type="u" name="state" direction="in"/>
    </method>
    <method name="NotifyKeyboardKeysym">
      <arg type="o" name="session_handle" direction="in"/>
      <arg type="a{sv}" name="options" direction="in"/>
      <arg type="i" name="keysym" direction="in"/>
      <arg type="u" name="state" direction="in"/>
    </method>
    <property name="version" type="u" access="read"/>
    <property name="AvailableDeviceTypes" type="u" access="read"/>
  </interface>
</node>
"""

CLIPBOARD = """
<node>
  <interface name="org.freedesktop.portal.Clipboard">
    <method name="RequestClipboard">
      <arg type="o" name="session_handle" direction="in"/>
      <arg type="a{sv}" name="options" direction="in"/>
    </method>
    <method name="SetSelection">
      <arg type="o" name="session_handle" direction="in"/>
      <arg type="a{sv}" name="options" direction="in"/>
    </method>
    <method name="SelectionWrite">
      <arg type="o" name="session_handle" direction="in"/>
      <arg type="u" name="serial" direction="in"/>
      <arg type="h" name="fd" direction="out"/>
    </method>
    <method name="SelectionWriteDone">
      <arg type="o" name="session_handle" direction="in"/>
      <arg type="u" name="serial" direction="in"/>
      <arg type="b" name="success" direction="in"/>
    </method>
    <method name="SelectionRead">
      <arg type="o" name="session_handle" direction="in"/>
      <arg type="s" name="mime_type" direction="in"/>
      <arg type="h" name="fd" direction="out"/>
    </method>
    <signal name="SelectionOwnerChanged">
      <arg type="o" name="session_handle"/>
      <arg type="a{sv}" name="options"/>
    </signal>
    <signal name="SelectionTransfer">
      <arg type="o" name="session_handle"/>
      <arg type="s" name="mime_type"/>
      <arg type="u" name="serial"/>
    </signal>
    <property name="version" type="u" access="read"/>
  </interface>
</node>
"""

REQUEST = """
<node>
  <interface name="org.freedesktop.portal.Request">
    <method name="Close"/>
    <signal name="Response">
      <arg type="u" name="response"/>
      <arg type="a{sv}" name="results"/>
    </signal>
  </interface>
</node>
"""

SESSION = """
<node>
  <interface name="org.freedesktop.portal.Session">
    <method name="Close"/>
    <signal name="Closed">
      <arg type="a{sv}" name="details"/>
    </signal>
  </interface>
</node>
"""

BY_NAME = {
    "GlobalShortcuts": GLOBAL_SHORTCUTS,
    "RemoteDesktop": REMOTE_DESKTOP,
    "Clipboard": CLIPBOARD,
}
