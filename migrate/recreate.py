#!/usr/bin/env python3
"""Пересоздаёт контейнер на новом сервере по `docker inspect` со старого.

Использование: python3 recreate.py containers/<имя>.json [...]
Образ берётся migrate/<имя>:latest (снимок из backup.sh). Переменные
окружения передаются через --env-file, чтобы секреты не светились в `ps`.
"""
import json
import os
import subprocess
import sys

# Имена контейнеров на старом сервере → на новом
RENAMES = {
    "103c04531ada_remnawave-db": "remnawave-db",
    "7df4acdb2761_remnawave-redis": "remnawave-redis",
}
# Боты, у которых хост БД зашит в код по умолчанию
FORCE_ENV = {
    "remna-sales-bot": {"POSTGRES_HOST": "remnawave-db"},
}


def fix(value: str) -> str:
    for old, new in RENAMES.items():
        value = value.replace(old, new)
    return value


def build(spec: dict, env_dir: str) -> list[str]:
    name = spec["Name"].lstrip("/")
    cfg, host = spec["Config"], spec["HostConfig"]
    cmd = ["docker", "run", "-d", "--name", name]

    env = [fix(e) for e in cfg.get("Env") or []]
    keys = {e.split("=", 1)[0] for e in env}
    for k, v in FORCE_ENV.get(name, {}).items():
        if k in keys:
            env = [e for e in env if not e.startswith(k + "=")]
        env.append(f"{k}={v}")
    # Ручные правки (например, новый API-токен): containers/<имя>.override,
    # строки КЛЮЧ=значение заменяют одноимённые переменные
    override = os.path.join(os.path.dirname(env_dir), f"{name}.override")
    if os.path.exists(override):
        with open(override) as f:
            extra = [l.strip() for l in f if "=" in l and not l.startswith("#")]
        for e in extra:
            k = e.split("=", 1)[0]
            env = [x for x in env if not x.startswith(k + "=")]
            env.append(e)
    env_file = os.path.join(env_dir, f"{name}.env")
    with open(env_file, "w") as f:
        f.write("\n".join(env) + "\n")
    os.chmod(env_file, 0o600)
    cmd += ["--env-file", env_file]

    mode = host.get("NetworkMode") or "default"
    if mode not in ("default", "bridge"):
        cmd += ["--network", mode]

    rp = host.get("RestartPolicy") or {}
    if rp.get("Name") and rp["Name"] != "no":
        policy = rp["Name"]
        if policy == "on-failure" and rp.get("MaximumRetryCount"):
            policy += f":{rp['MaximumRetryCount']}"
        cmd += ["--restart", policy]

    for m in spec.get("Mounts") or []:
        src = m["Name"] if m["Type"] == "volume" else m["Source"]
        opt = "" if m.get("RW", True) else ":ro"
        cmd += ["-v", f"{src}:{m['Destination']}{opt}"]

    ports = []
    for port, binds in (host.get("PortBindings") or {}).items():
        for b in binds or []:
            ip = b.get("HostIp") or ""
            hp = b.get("HostPort") or ""
            if ip in ("0.0.0.0", "::"):
                ip = ""  # «все адреса» — docker сам повесит и IPv4, и IPv6
            elif ":" in ip:
                ip = f"[{ip}]"
            p = f"{ip + ':' if ip else ''}{hp}:{port}"
            if p not in ports:
                ports.append(p)
    for p in ports:
        cmd += ["-p", p]

    if host.get("Privileged"):
        cmd.append("--privileged")
    for cap in host.get("CapAdd") or []:
        cmd += ["--cap-add", cap]
    for d in host.get("Devices") or []:
        cmd += ["--device", f"{d['PathOnHost']}:{d['PathInContainer']}:{d['CgroupPermissions']}"]
    for k, v in (host.get("Sysctls") or {}).items():
        cmd += ["--sysctl", f"{k}={v}"]
    for h in host.get("ExtraHosts") or []:
        cmd += ["--add-host", h]

    cmd.append(f"migrate/{name}:latest")
    return cmd


def main() -> None:
    env_dir = os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), "env")
    os.makedirs(env_dir, mode=0o700, exist_ok=True)
    dry = os.getenv("DRY_RUN") == "1"
    for path in sys.argv[1:]:
        with open(path) as f:
            spec = json.load(f)[0]
        cmd = build(spec, env_dir)
        print("+", " ".join(cmd))
        if not dry:
            subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
