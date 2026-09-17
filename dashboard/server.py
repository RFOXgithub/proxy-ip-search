"""Small integration server for the three independent proxy finders."""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import mimetypes
import os
import sys
import threading
import time
import uuid
from dataclasses import fields
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "static"

METHODS = {
    "impulse": {
        "name": "DataImpulse", "description": "Sticky port range scanner",
        "folder": "impulse", "protocol": "HTTP",
        "fields": ["proxy_username", "proxy_password", "proxy_host", "proxy_mode",
                   "country", "city", "asn", "start_port", "end_port",
                   "target_prefix", "max_workers", "request_timeout",
                   "execution_duration", "batch_delay"],
    },
    "oxy": {
        "name": "Oxylabs", "description": "Sequential session rotation",
        "folder": "oxy", "protocol": "HTTP",
        "fields": ["proxy_username", "proxy_password", "proxy_host", "proxy_port",
                   "proxy_mode", "country", "city", "asn", "session_prefix",
                   "session_minutes", "start_session", "target_prefix", "max_workers",
                   "request_timeout", "execution_duration", "batch_delay"],
    },
    "royale": {
        "name": "IPRoyal", "description": "Random sticky SOCKS sessions",
        "folder": "royale", "protocol": "SOCKS5",
        "fields": ["proxy_username", "proxy_password", "proxy_host", "proxy_port",
                   "proxy_scheme", "country", "city", "session_prefix",
                   "session_minutes", "target_prefix", "max_workers",
                   "request_timeout", "execution_duration", "batch_delay"],
    },
}


def load_package(key: str):
    package_dir = ROOT / METHODS[key]["folder"] / "proxy_finder"
    name = f"dashboard_method_{key}"
    spec = importlib.util.spec_from_file_location(
        name, package_dir / "__init__.py", submodule_search_locations=[str(package_dir)]
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Tidak dapat memuat metode {key}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


MODULES = {key: load_package(key) for key in METHODS}
JOBS: dict[str, dict[str, Any]] = {}
LOCK = threading.RLock()
OPTIONAL_FILTERS = {"asn", "city", "country"}
UNAVAILABLE = "Data tidak tersedia"


def env_config(key: str) -> dict[str, str]:
    """Merge local provider .env values with deployment environment values.

    Provider-prefixed process variables avoid collisions when all three finders
    run in one backend. Process variables intentionally win over local files.
    """
    raw = dotenv_values(ROOT / METHODS[key]["folder"] / ".env")
    values = {str(k).lower(): str(v) for k, v in raw.items() if v is not None}
    prefix = f"{key.upper()}_"
    for name, value in os.environ.items():
        if name.startswith(prefix):
            values[name[len(prefix):].lower()] = value
    return values


def config_for(key: str, supplied: dict[str, Any]):
    cls = MODULES[key].Settings
    env = env_config(key)
    secret_map = {"proxy_username": "proxy_username", "proxy_password": "proxy_password"}
    values: dict[str, Any] = {}
    for field in fields(cls):
        env_name = field.name.upper()
        value = supplied.get(field.name)
        if value in (None, "") and not (
            field.name in OPTIONAL_FILTERS and field.name in supplied
        ):
            value = env.get(env_name.lower())
        if field.name in OPTIONAL_FILTERS and value is not None:
            value = str(value).strip()
            if not value:
                value = None if field.name == "asn" else ""
        if value is None:
            if field.name == "asn" and field.name in supplied:
                values[field.name] = None
            continue
        default = getattr(cls, field.name, None)
        if field.name == "asn" and value == "":
            value = None
        elif isinstance(default, int) or field.name in {"asn", "start_port", "end_port", "proxy_port",
                                                        "max_workers", "session_minutes", "start_session"}:
            value = int(value)
        elif isinstance(default, float) or field.name in {"request_timeout", "execution_duration", "batch_delay"}:
            value = float(value)
        elif field.name not in secret_map:
            value = str(value).strip().lower() if field.name in {"country", "city", "proxy_mode", "proxy_scheme"} else str(value).strip()
        values[field.name] = value
    return cls(**values)


def public_methods() -> list[dict[str, Any]]:
    result = []
    for key, meta in METHODS.items():
        cls = MODULES[key].Settings
        env = env_config(key)
        defaults = {}
        for field in fields(cls):
            if field.name in {"proxy_username", "proxy_password", "ip_info_url"}:
                continue
            env_value = env.get(field.name)
            defaults[field.name] = env_value if env_value is not None else getattr(cls, field.name, "")
        result.append({"id": key, **{k: v for k, v in meta.items() if k != "folder"},
                       "configured": bool(env.get("proxy_username") and env.get("proxy_password")),
                       "defaults": defaults})
    return result


def available(value: Any) -> Any:
    return value if value not in (None, "", "N/A") else UNAVAILABLE


def normalize_result(key: str, item: Any, started: float) -> dict[str, Any]:
    data = item._asdict() if hasattr(item, "_asdict") else dict(item)
    complete = all(data.get(name) not in (None, "", "N/A")
                   for name in ("asn", "city", "country"))
    return {
        "ip": data.get("ip", ""), "port": data.get("port") or "—",
        "protocol": METHODS[key]["protocol"],
        "status": "Data lengkap" if complete else "Data sebagian tersedia",
        "status_code": "complete" if complete else "partial",
        "source": METHODS[key]["name"], "latency": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "asn": available(data.get("asn") or data.get("isp")),
        "city": available(data.get("city")),
        "country": available(data.get("country")),
        "isp": available(data.get("isp")),
        "session": data.get("session", "—"),
    }


def unmatched_result(key: str, settings: Any) -> dict[str, Any]:
    return {
        "ip": settings.target_prefix, "port": "—",
        "protocol": METHODS[key]["protocol"],
        "status": "IP tidak ditemukan / tidak cocok", "status_code": "not_found",
        "source": METHODS[key]["name"], "latency": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "asn": UNAVAILABLE, "city": UNAVAILABLE, "country": UNAVAILABLE,
        "isp": UNAVAILABLE, "session": "—",
    }


def similarity(ip: str, target_prefix: str) -> int:
    target = target_prefix.rstrip(".").split(".")
    candidate = ip.split(".")
    matching = 0
    for expected, actual in zip(target, candidate):
        if expected != actual:
            break
        matching += 1
    return round(matching / len(target) * 100) if target else 0


def observed_result(key: str, item: dict[str, Any], settings: Any,
                    started: float) -> dict[str, Any]:
    row = normalize_result(key, item, started)
    row["similarity"] = similarity(row["ip"], settings.target_prefix)
    if not item.get("matched"):
        row["status_code"] = "not_match"
        row["status"] = f"Tidak cocok · kemiripan {row['similarity']}%"
    return row


def run_job(job_id: str, key: str, settings: Any) -> None:
    with LOCK:
        job = JOBS[job_id]
        job["status"] = "running"
        job["message"] = "Pencarian sedang berjalan"
    try:
        def observe(item: dict[str, Any]) -> None:
            row = observed_result(key, item, settings, job["started_at"])
            with LOCK:
                current = job["results"]
                for index, existing in enumerate(current):
                    if existing["ip"] == row["ip"]:
                        current[index] = row
                        break
                else:
                    current.append(row)

        results = MODULES[key].find_matching_ip(settings, job["stop"], observe)
        normalized = [normalize_result(key, item, job["started_at"]) for item in (results or [])]
        with LOCK:
            streamed = list(job["results"])
        by_ip = {row["ip"]: row for row in streamed}
        for row in normalized:
            by_ip.setdefault(row["ip"], row)
        normalized = list(by_ip.values())
        if not normalized and not job["cancel_requested"]:
            normalized = [unmatched_result(key, settings)]
        with LOCK:
            job["results"] = normalized
            if job["cancel_requested"]:
                job["status"], job["message"] = "cancelled", "Pencarian dibatalkan"
            else:
                job["status"] = "completed"
                matched = bool(results)
                job["message"] = "IP cocok ditemukan" if matched else "Selesai, IP tidak ditemukan / tidak cocok"
    except Exception as exc:
        with LOCK:
            job["status"] = "failed"
            job["message"] = f"{type(exc).__name__}: {exc}"
    finally:
        with LOCK:
            job["finished_at"] = time.time()


def job_public(job: dict[str, Any]) -> dict[str, Any]:
    duration = job["duration"]
    elapsed = (job.get("finished_at") or time.time()) - job["started_at"]
    progress = min(100, round(elapsed / duration * 100)) if duration else 0
    return {k: v for k, v in job.items() if k not in {"stop", "thread"}} | {
        "elapsed": round(elapsed, 1), "progress": progress,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "ProxyDashboard/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[dashboard] {self.address_string()} {fmt % args}")

    def send_json(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 100_000:
            raise ValueError("Payload terlalu besar")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self.send_json({"status": "ok"}); return
        if path == "/api/methods":
            self.send_json(public_methods()); return
        if path == "/api/jobs":
            with LOCK: data = [job_public(job) for job in JOBS.values()]
            self.send_json(data); return
        if path.startswith("/api/jobs/"):
            job_id = path.rsplit("/", 1)[-1]
            with LOCK: job = JOBS.get(job_id)
            self.send_json(job_public(job) if job else {"error": "Job tidak ditemukan"}, 200 if job else 404); return
        relative = "index.html" if path == "/" else path.lstrip("/")
        target = (STATIC / relative).resolve()
        if STATIC.resolve() not in target.parents or not target.is_file():
            self.send_error(404); return
        payload = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers(); self.wfile.write(payload)

    def do_POST(self) -> None:
        try:
            if self.path.startswith("/api/methods/") and self.path.endswith("/run"):
                key = self.path.split("/")[3]
                if key not in METHODS: self.send_json({"error": "Metode tidak dikenal"}, 404); return
                payload = self.body(); settings = config_for(key, payload.get("config", {}))
                job_id = uuid.uuid4().hex
                job = {"id": job_id, "method": key, "method_name": METHODS[key]["name"],
                       "status": "queued", "message": "Menyiapkan pencarian", "results": [],
                       "started_at": time.time(), "finished_at": None,
                       "duration": float(settings.execution_duration), "cancel_requested": False,
                       "stop": threading.Event()}
                thread = threading.Thread(target=run_job, args=(job_id, key, settings), daemon=True)
                job["thread"] = thread
                with LOCK: JOBS[job_id] = job
                thread.start(); self.send_json(job_public(job), 202); return
            if self.path.startswith("/api/jobs/") and self.path.endswith("/cancel"):
                job_id = self.path.split("/")[3]
                with LOCK: job = JOBS.get(job_id)
                if not job: self.send_json({"error": "Job tidak ditemukan"}, 404); return
                if job["status"] in {"queued", "running"}:
                    job["cancel_requested"] = True; job["stop"].set(); job["message"] = "Membatalkan request aktif…"
                self.send_json(job_public(job)); return
            self.send_json({"error": "Endpoint tidak ditemukan"}, 404)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            self.send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8765"))
    print(f"Proxy IP Finder Dashboard: http://{host}:{port}")
    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
