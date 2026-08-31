"""Launches the Claude desktop app, trying a native binary then flatpak."""
import shutil
import subprocess

CANDIDATES = [
    ["claude-desktop"],
    ["flatpak", "run", "com.anthropic.ClaudeDesktop"],
]


def launch_claude():
    attempts = []
    for command in CANDIDATES:
        if shutil.which(command[0]) is None:
            attempts.append({"command": " ".join(command), "error": "command not found"})
            continue
        try:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True, {"launched": " ".join(command), "attempts": attempts}
        except OSError as exc:
            attempts.append({"command": " ".join(command), "error": str(exc)})
    return False, {
        "error": "Could not start Claude Desktop - it does not appear to be installed.",
        "attempts": attempts,
    }
