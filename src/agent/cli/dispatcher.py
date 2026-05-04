"""
Coding CLI 调度器

支持两种执行模式：
- run: 同步执行，等待完成后返回结果
- stream: 流式执行，实时返回输出（SSE）
- serve: 启动持久服务
"""
import subprocess
import json
import os
import time
import signal
import logging
import threading
from typing import Optional, Generator

logger = logging.getLogger(__name__)

_active_serve_processes = {}


def dispatch_run(
    cli_name,
    cli_path,
    task,
    working_dir=".",
    auto_approve=True,
    model=None,
    timeout=600,
):
    start_time = time.time()
    cmd = _build_cmd(cli_name, cli_path, task, working_dir, auto_approve, model)

    logger.info("[CLI Dispatch] run mode: %s", " ".join(cmd))

    # timeout=0 means no timeout
    effective_timeout = None if timeout == 0 else timeout

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=effective_timeout,
            cwd=os.path.abspath(working_dir),
        )

        duration = time.time() - start_time
        parsed_output = _parse_output(result.stdout, cli_name)

        return {
            "status": "success" if result.returncode == 0 else "error",
            "output": parsed_output or result.stdout,
            "stdout": result.stdout[-5000:] if result.stdout else "",
            "stderr": result.stderr[-2000:] if result.stderr else "",
            "exit_code": result.returncode,
            "duration_sec": round(duration, 2),
            "mode": "run",
        }

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return {
            "status": "timeout",
            "output": "Task timed out after %ds" % timeout,
            "exit_code": -1,
            "duration_sec": round(duration, 2),
            "mode": "run",
        }
    except Exception as e:
        duration = time.time() - start_time
        return {
            "status": "error",
            "output": "Execution failed: %s" % str(e),
            "exit_code": -1,
            "duration_sec": round(duration, 2),
            "mode": "run",
        }


def dispatch_run_stream(
    cli_name,
    cli_path,
    task,
    working_dir=".",
    auto_approve=True,
    model=None,
    timeout=600,
):
    """
    Generator that yields SSE-compatible events as subprocess output arrives.
    Each yield is a dict with type, data, and optional metadata.
    """
    cmd = _build_cmd(cli_name, cli_path, task, working_dir, auto_approve, model)

    logger.info("[CLI Dispatch] stream mode: %s", " ".join(cmd))
    start_time = time.time()

    yield {"type": "start", "data": {"cmd": cmd, "timeout": timeout}}

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=os.path.abspath(working_dir),
        )

        full_stdout = []
        full_stderr = []
        output_buffer = []

        def _read_stderr(proc, lines):
            if proc.stderr:
                for line in iter(proc.stderr.readline, ""):
                    if line:
                        lines.append(line)

        stderr_thread = threading.Thread(
            target=_read_stderr, args=(process, full_stderr), daemon=True
        )
        stderr_thread.start()

        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                if line:
                    full_stdout.append(line)
                    output_buffer.append(line)
                    yield {"type": "stdout", "data": line.rstrip()}

        process.stdout.close()
        stderr_thread.join(timeout=2)
        effective_timeout = None if timeout == 0 else timeout
        exit_code = process.wait(timeout=effective_timeout)

        duration = time.time() - start_time
        parsed_output = _parse_output("".join(full_stdout), cli_name)

        yield {
            "type": "complete",
            "data": {
                "status": "success" if exit_code == 0 else "error",
                "output": parsed_output or "".join(full_stdout),
                "stderr": "".join(full_stderr)[-2000:],
                "exit_code": exit_code,
                "duration_sec": round(duration, 2),
                "mode": "stream",
            },
        }

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        process.kill()
        timeout_msg = "no limit" if timeout == 0 else "%ds" % timeout
        yield {
            "type": "error",
            "data": {
                "status": "timeout",
                "output": "Task timed out after %s" % timeout_msg,
                "duration_sec": round(duration, 2),
            },
        }
    except Exception as e:
        duration = time.time() - start_time
        yield {
            "type": "error",
            "data": {
                "status": "error",
                "output": "Execution failed: %s" % str(e),
                "duration_sec": round(duration, 2),
            },
        }


def _build_cmd(cli_name, cli_path, task, working_dir, auto_approve, model):
    cmd = [cli_path, "run"]

    if cli_name == "opencode":
        cmd.extend(["--format", "json"])
        if auto_approve:
            cmd.append("--dangerously-skip-permissions")
        if model:
            cmd.extend(["-m", model])
    elif cli_name == "claude":
        cmd.append("--dangerously-skip-permissions")
        if model:
            cmd.extend(["-m", model])

    cmd.extend(["--dir", os.path.abspath(working_dir)])
    cmd.append("--")
    cmd.append(task)
    return cmd


def start_serve(cli_name, cli_path, working_dir=".", port=0, session_id=None):
    cmd = [cli_path, "serve", "--hostname", "127.0.0.1"]
    if port:
        cmd.extend(["--port", str(port)])

    env = os.environ.copy()
    if session_id:
        env["CLI_SESSION_ID"] = session_id

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=os.path.abspath(working_dir),
            env=env,
        )

        serve_id = "%s-%d" % (cli_name, process.pid)
        _active_serve_processes[serve_id] = {
            "process": process,
            "cli_name": cli_name,
            "pid": process.pid,
            "working_dir": working_dir,
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        time.sleep(3)
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr else ""
            return {
                "status": "error",
                "output": "Service failed to start: %s" % stderr,
            }

        return {
            "status": "success",
            "serve_id": serve_id,
            "pid": process.pid,
            "cli_name": cli_name,
            "working_dir": working_dir,
        }

    except Exception as e:
        return {
            "status": "error",
            "output": "Failed to start: %s" % str(e),
        }


def stop_serve(serve_id):
    if serve_id not in _active_serve_processes:
        return {"status": "error", "output": "Service not found"}

    proc_info = _active_serve_processes[serve_id]
    process = proc_info["process"]

    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_C_EVENT)
        else:
            process.terminate()
        process.wait(timeout=5)
    except Exception:
        process.kill()

    del _active_serve_processes[serve_id]
    return {"status": "success", "output": "Service stopped"}


def get_active_serves():
    result = []
    for serve_id, info in _active_serve_processes.items():
        process = info["process"]
        result.append({
            "serve_id": serve_id,
            "cli_name": info["cli_name"],
            "pid": info["pid"],
            "working_dir": info["working_dir"],
            "started_at": info["started_at"],
            "running": process.poll() is None,
        })
    return result


def _parse_output(stdout, cli_name):
    if not stdout:
        return None

    lines = stdout.strip().split("\n")
    last_text = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if cli_name == "opencode":
                if event.get("type") == "text" and event.get("text"):
                    last_text += event["text"]
                elif event.get("type") == "result" and event.get("text"):
                    last_text = event["text"]
        except json.JSONDecodeError:
            last_text += line + "\n"

    return last_text.strip() if last_text.strip() else None


__all__ = [
    "dispatch_run",
    "dispatch_run_stream",
    "start_serve",
    "stop_serve",
    "get_active_serves",
    "_active_serve_processes",
]
