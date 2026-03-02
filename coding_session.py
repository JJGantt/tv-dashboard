"""
Coding session manager — wraps 3 Claude CLI processes for the TV coding mode.
Each session maintains a Claude conversation via --resume.
"""

import json
import logging
import subprocess

logger = logging.getLogger(__name__)

# Try Mac first (more powerful), fall back to local Pi
MAC_SSH = "ssh -o ConnectTimeout=3 -o BatchMode=yes jaredgantt@10.0.0.14"
CLAUDE_CMD = "claude"


def _is_mac_reachable():
    """Check if the Mac is reachable via SSH."""
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=2", "-o", "BatchMode=yes",
             "jaredgantt@10.0.0.162", "true"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


class CodingSessionManager:
    def __init__(self):
        self.sessions = [None, None, None]  # session IDs per terminal

    def send_message(self, terminal: int, text: str):
        """Run claude -p with --resume, yield NDJSON lines as they stream."""
        if not 0 <= terminal <= 2:
            yield json.dumps({"type": "error", "message": "Invalid terminal"}) + "\n"
            return

        cmd = [CLAUDE_CMD, "-p", text, "--output-format", "stream-json"]
        if self.sessions[terminal]:
            cmd += ["--resume", self.sessions[terminal]]

        # Try Mac first, fall back to local
        use_mac = _is_mac_reachable()
        if use_mac:
            # Wrap command for SSH execution
            escaped = " ".join(_shell_quote(c) for c in cmd)
            run_cmd = [
                "ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
                "jaredgantt@10.0.0.162", escaped,
            ]
            logger.info(f"Terminal {terminal}: running on Mac via SSH")
        else:
            run_cmd = cmd
            logger.info(f"Terminal {terminal}: running locally on Pi")

        try:
            process = subprocess.Popen(
                run_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # line-buffered
            )

            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type", "")

                # Capture session ID from system message
                if etype == "system" and event.get("subtype") == "init":
                    sid = event.get("session_id")
                    if sid:
                        self.sessions[terminal] = sid
                        logger.info(f"Terminal {terminal}: session {sid}")

                # Forward text deltas
                elif etype == "assistant" and event.get("subtype") == "text":
                    text_content = event.get("text", "")
                    if text_content:
                        yield json.dumps({"type": "delta", "text": text_content}) + "\n"

                # Tool use events — forward as info
                elif etype == "tool_use":
                    tool_name = event.get("tool", event.get("name", ""))
                    yield json.dumps({"type": "tool", "name": tool_name}) + "\n"

                # Tool results
                elif etype == "tool_result":
                    pass  # Don't forward raw tool results to TV

                # Result message (final complete response)
                elif etype == "result":
                    # The result contains the final text; we already streamed deltas
                    pass

            process.wait()
            if process.returncode != 0:
                stderr = process.stderr.read() if process.stderr else ""
                logger.error(f"Terminal {terminal}: claude exited {process.returncode}: {stderr}")
                if stderr:
                    yield json.dumps({"type": "error", "message": stderr[:500]}) + "\n"

        except Exception as e:
            logger.error(f"Terminal {terminal}: error: {e}")
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

        yield json.dumps({"type": "done"}) + "\n"

    def get_sessions(self):
        """Return which sessions are active."""
        return [s is not None for s in self.sessions]

    def clear(self, terminal: int):
        """Clear a session (start fresh next time)."""
        if 0 <= terminal <= 2:
            self.sessions[terminal] = None
            logger.info(f"Terminal {terminal}: session cleared")


def _shell_quote(s: str) -> str:
    """Quote a string for shell use."""
    if not s:
        return "''"
    # If it's safe, return as-is
    import re
    if re.match(r'^[a-zA-Z0-9._/=-]+$', s):
        return s
    # Otherwise single-quote it, escaping any existing single quotes
    return "'" + s.replace("'", "'\"'\"'") + "'"
