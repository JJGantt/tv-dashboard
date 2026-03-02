"""
Coding session manager — wraps 3 Claude CLI processes for the TV coding mode.
Each session maintains a Claude conversation via --resume.
"""

import json
import logging
import os
import subprocess

logger = logging.getLogger(__name__)

CLAUDE_CMD = "claude"
MAC_CLAUDE_CMD = "/usr/local/bin/claude"
MAC_USER = "jaredgantt@Jareds-MacBook-Air.local"
MAC_PROJECTS_DIR = "/Users/jaredgantt/.claude/projects"


def _is_mac_reachable():
    """Check if the Mac is reachable via SSH."""
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=2", "-o", "BatchMode=yes",
             MAC_USER, "true"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _shell_quote(s: str) -> str:
    """Quote a string for shell use."""
    if not s:
        return "''"
    import re
    if re.match(r'^[a-zA-Z0-9._/=-]+$', s):
        return s
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _decode_project_path(dirname: str) -> str:
    """Decode Claude's project directory name back to a path.
    e.g. '-Users-jaredgantt-workspace' -> '/Users/jaredgantt/workspace'
    """
    if dirname.startswith("-"):
        return "/" + dirname[1:].replace("-", "/")
    return dirname


def _project_label(project_path: str) -> str:
    """Extract a short label from a project path.
    e.g. '/Users/jaredgantt/workspace' -> 'workspace'
    """
    parts = project_path.rstrip("/").split("/")
    # Skip common prefixes
    skip = {"Users", "jaredgantt", "home", "Projects"}
    meaningful = [p for p in parts if p and p not in skip]
    return meaningful[-1] if meaningful else project_path


class CodingSessionManager:
    def __init__(self):
        self.sessions = [None, None, None]  # session IDs per terminal
        self.labels = ["Terminal 1", "Terminal 2", "Terminal 3"]

    def send_message(self, terminal: int, text: str):
        """Run claude -p with --resume, yield NDJSON lines as they stream."""
        if not 0 <= terminal <= 2:
            yield json.dumps({"type": "error", "message": "Invalid terminal"}) + "\n"
            return

        cmd = [CLAUDE_CMD, "-p", text, "--output-format", "stream-json", "--verbose"]
        if self.sessions[terminal]:
            cmd += ["--resume", self.sessions[terminal]]

        run_cmd = cmd
        logger.info(f"Terminal {terminal}: running locally on Pi")

        try:
            process = subprocess.Popen(
                run_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
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

                # Capture session ID from init
                if etype == "system" and event.get("subtype") == "init":
                    sid = event.get("session_id")
                    if sid:
                        self.sessions[terminal] = sid
                        logger.info(f"Terminal {terminal}: session {sid}")

                # Assistant message — extract text content
                elif etype == "assistant":
                    msg = event.get("message", {})
                    content = msg.get("content", [])
                    for block in content:
                        if block.get("type") == "text":
                            text_content = block.get("text", "")
                            if text_content:
                                yield json.dumps({"type": "delta", "text": text_content}) + "\n"
                        elif block.get("type") == "tool_use":
                            tool_name = block.get("name", "tool")
                            yield json.dumps({"type": "tool", "name": tool_name}) + "\n"

                # Result — contains session_id too
                elif etype == "result":
                    sid = event.get("session_id")
                    if sid:
                        self.sessions[terminal] = sid

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
        """Return session info for each terminal."""
        return [
            {
                "active": self.sessions[i] is not None,
                "session_id": self.sessions[i],
                "label": self.labels[i],
            }
            for i in range(3)
        ]

    def clear(self, terminal: int):
        """Clear a session (start fresh next time)."""
        if 0 <= terminal <= 2:
            self.sessions[terminal] = None
            self.labels[terminal] = f"Terminal {terminal + 1}"
            logger.info(f"Terminal {terminal}: session cleared")

    def attach(self, terminal: int, session_id: str, project_path: str = "", label: str = None):
        """Attach an existing Mac session to a terminal.

        Copies the session JSONL from the Mac to the Pi so --resume can find it.
        """
        if not 0 <= terminal <= 2:
            return False

        # Copy JSONL from Mac to Pi's project dir for the server's cwd
        if _is_mac_reachable() and project_path:
            mac_dir_name = project_path.replace("/", "-").lstrip("-")
            mac_jsonl = f"{MAC_PROJECTS_DIR}/-{mac_dir_name}/{session_id}.jsonl"

            pi_project_dir = os.path.expanduser("~/.claude/projects/-home-jaredgantt-tv-dashboard")
            os.makedirs(pi_project_dir, exist_ok=True)
            pi_jsonl = f"{pi_project_dir}/{session_id}.jsonl"

            try:
                subprocess.run(
                    ["scp", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
                     f"{MAC_USER}:{mac_jsonl}", pi_jsonl],
                    capture_output=True, timeout=30,
                )
                logger.info(f"Terminal {terminal}: copied session {session_id} from Mac")
            except Exception as e:
                logger.error(f"Terminal {terminal}: failed to copy session: {e}")

        self.sessions[terminal] = session_id
        if label:
            self.labels[terminal] = label
        logger.info(f"Terminal {terminal}: attached session {session_id} ({label})")
        return True

    def scan_mac_sessions(self) -> list[dict]:
        """SSH to Mac and scan for existing Claude Code sessions."""
        if not _is_mac_reachable():
            return []

        # Run a Python one-liner on the Mac to scan sessions
        scan_script = r"""
import json, os, sys
from pathlib import Path

projects_dir = Path(os.path.expanduser("~/.claude/projects"))
if not projects_dir.exists():
    print("[]")
    sys.exit(0)

sessions = []
for project_dir in sorted(projects_dir.iterdir()):
    if not project_dir.is_dir():
        continue
    dirname = project_dir.name
    # Decode project path
    if dirname.startswith("-"):
        project_path = "/" + dirname[1:].replace("-", "/")
    else:
        project_path = dirname

    for jsonl in sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = jsonl.stat()
        session_id = jsonl.stem
        size_mb = stat.st_size / (1024 * 1024)

        # Read first user message for summary
        summary = ""
        msg_count = 0
        try:
            with open(jsonl) as f:
                for line in f:
                    obj = json.loads(line)
                    t = obj.get("type")
                    if t == "user":
                        msg_count += 1
                        if not summary:
                            content = obj.get("message", {}).get("content", "")
                            if isinstance(content, str):
                                summary = content[:200]
                            elif isinstance(content, list):
                                texts = [b.get("text", "") for b in content if b.get("type") == "text"]
                                summary = " ".join(texts)[:200]
                    elif t == "assistant":
                        msg_count += 1
        except Exception:
            pass

        sessions.append({
            "session_id": session_id,
            "project_path": project_path,
            "modified": stat.st_mtime,
            "size_mb": round(size_mb, 1),
            "msg_count": msg_count,
            "summary": summary,
        })

# Sort by most recently modified
sessions.sort(key=lambda s: s["modified"], reverse=True)
print(json.dumps(sessions[:30]))
"""
        try:
            result = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
                 MAC_USER, "python3", "-c", _shell_quote(scan_script)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout.strip())
            else:
                logger.error(f"scan_mac_sessions failed: {result.stderr}")
                return []
        except Exception as e:
            logger.error(f"scan_mac_sessions error: {e}")
            return []

    def get_session_history(self, session_id: str) -> list[dict]:
        """SSH to Mac and extract conversation messages from a session JSONL."""
        if not _is_mac_reachable():
            return []

        history_script = r"""
import json, os, sys, glob
from pathlib import Path

session_id = sys.argv[1]
projects_dir = Path(os.path.expanduser("~/.claude/projects"))
# Find the JSONL file
matches = list(projects_dir.rglob(f"{session_id}.jsonl"))
if not matches:
    print("[]")
    sys.exit(0)

jsonl_path = matches[0]
messages = []
try:
    with open(jsonl_path) as f:
        for line in f:
            obj = json.loads(line)
            t = obj.get("type")
            if t == "user":
                content = obj.get("message", {}).get("content", "")
                if isinstance(content, list):
                    texts = [b.get("text", "") for b in content if b.get("type") == "text"]
                    content = " ".join(texts)
                if content.strip():
                    messages.append({"role": "user", "content": content.strip()})
            elif t == "assistant":
                content_blocks = obj.get("message", {}).get("content", [])
                texts = []
                for block in (content_blocks if isinstance(content_blocks, list) else []):
                    if block.get("type") == "text" and block.get("text", "").strip():
                        texts.append(block["text"])
                if texts:
                    messages.append({"role": "assistant", "content": "\n\n".join(texts)})
except Exception:
    pass

print(json.dumps(messages[-50:]))
"""
        try:
            result = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
                 MAC_USER, "python3", "-c", _shell_quote(history_script), session_id],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout.strip())
            else:
                logger.error(f"get_session_history failed: {result.stderr}")
                return []
        except Exception as e:
            logger.error(f"get_session_history error: {e}")
            return []
