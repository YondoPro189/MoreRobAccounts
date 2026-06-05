"""Notificaciones de escritorio Windows."""

from __future__ import annotations

import subprocess
import sys


def show_notification(title: str, message: str) -> None:
    if sys.platform != "win32":
        return

    title_esc = title.replace("'", "''").replace('"', '`"')
    msg_esc = message.replace("'", "''").replace('"', '`"')

    ps = f"""
$title = '{title_esc}'
$msg = '{msg_esc}'
try {{
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
    $template = @"
<toast>
  <visual>
    <binding template="ToastText02">
      <text id="1">$title</text>
      <text id="2">$msg</text>
    </binding>
  </visual>
</toast>
"@
    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml($template)
    $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('MoreRobAccounts').Show($toast)
}} catch {{
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($msg, $title) | Out-Null
}}
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
