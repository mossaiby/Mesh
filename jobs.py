import asyncio
import os
import sys
import time
from typing import Dict, Any, List, Optional, Tuple
from theme import console


class JobEntry:
    def __init__(self, job_id: int, command: str, process: asyncio.subprocess.Process):
        self.job_id = job_id
        self.command = command
        self.process = process
        self.pid = process.pid
        self.start_time = time.time()
        self.status = "running"
        self.output_log: List[str] = []
        self._stdout_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None

    def start_logging_tasks(self):
        self._stdout_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())

    async def _read_stdout(self):
        try:
            while self.process.stdout and not self.process.stdout.at_eof():
                line = await self.process.stdout.readline()
                if not line:
                    break
                line_str = line.decode("utf-8", errors="replace").strip()
                if line_str:
                    self.output_log.append(f"[stdout] {line_str}")
                    if len(self.output_log) > 200:
                        self.output_log.pop(0)
        except Exception:
            pass
        finally:
            if self.process.returncode is not None:
                self.status = "completed" if self.process.returncode == 0 else f"failed (code {self.process.returncode})"

    async def _read_stderr(self):
        try:
            while self.process.stderr and not self.process.stderr.at_eof():
                line = await self.process.stderr.readline()
                if not line:
                    break
                line_str = line.decode("utf-8", errors="replace").strip()
                if line_str:
                    self.output_log.append(f"[stderr] {line_str}")
                    if len(self.output_log) > 200:
                        self.output_log.pop(0)
        except Exception:
            pass

    async def stop(self) -> bool:
        if self.process.returncode is None:
            try:
                if sys.platform == "win32":
                    import subprocess
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                else:
                    self.process.terminate()
                self.status = "stopped"
                return True
            except Exception:
                try:
                    self.process.kill()
                    self.status = "stopped"
                    return True
                except Exception:
                    return False
        return False


class JobManager:
    """Manages spawning, logging, querying, and terminating background subprocesses."""
    def __init__(self):
        self.jobs: Dict[int, JobEntry] = {}
        self._next_id = 1

    async def start_job(self, command: str, shell_prefix: Optional[str] = None) -> Dict[str, Any]:
        full_cmd = f"{shell_prefix} {command}" if shell_prefix else command

        try:
            proc = await asyncio.create_subprocess_shell(
                full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            job_id = self._next_id
            self._next_id += 1

            entry = JobEntry(job_id=job_id, command=full_cmd, process=proc)
            entry.start_logging_tasks()
            self.jobs[job_id] = entry

            console.print(f"[success]🚀 Background Job #{job_id} Started (PID: {proc.pid}):[/success] {full_cmd}")

            return {
                "status": "started",
                "job_id": job_id,
                "pid": proc.pid,
                "command": full_cmd,
                "message": f"Job #{job_id} running in background. Use /jobs to check status or logs."
            }
        except Exception as e:
            return {"status": "error", "error": f"Failed to start background job: {str(e)}"}

    def get_job_info(self, job_id: int) -> Optional[Dict[str, Any]]:
        entry = self.jobs.get(job_id)
        if not entry:
            return None

        # Check process status
        if entry.process.returncode is not None and entry.status == "running":
            entry.status = "completed" if entry.process.returncode == 0 else f"failed (code {entry.process.returncode})"

        runtime = int(time.time() - entry.start_time)
        return {
            "job_id": entry.job_id,
            "pid": entry.pid,
            "command": entry.command,
            "status": entry.status,
            "runtime_seconds": runtime,
            "recent_logs": entry.output_log[-10:]
        }

    async def stop_job(self, job_id: int) -> Tuple[bool, str]:
        entry = self.jobs.get(job_id)
        if not entry:
            return False, f"Job #{job_id} not found."

        success = await entry.stop()
        if success:
            return True, f"Stopped background Job #{job_id} (PID: {entry.pid})."
        return False, f"Could not stop Job #{job_id}."

    def list_jobs(self) -> List[Dict[str, Any]]:
        result = []
        for j_id, entry in self.jobs.items():
            if entry.process.returncode is not None and entry.status == "running":
                entry.status = "completed" if entry.process.returncode == 0 else f"failed (code {entry.process.returncode})"
            runtime = int(time.time() - entry.start_time)
            result.append({
                "job_id": j_id,
                "pid": entry.pid,
                "command": entry.command,
                "status": entry.status,
                "runtime": f"{runtime}s"
            })
        return result

    async def stop_all(self):
        for entry in self.jobs.values():
            await entry.stop()


# Global job manager instance
job_manager = JobManager()