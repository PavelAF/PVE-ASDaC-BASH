#!/usr/bin/env python3
"""
Скрипт автопроверки стендов PVE. Независимый инструмент: конфиг .conf, pvesh API,
выполнение проверок через Guest Agent и serial console. Запуск: python3 autocheck_standalone.py [config]
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ANSI
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]|\x1b\[\?[0-9;]*[A-Za-z]|\x08.')
AC_SEP_RE = re.compile(r'===AC_SEP_(\d+)===')

SCRIPT_DIR = Path(__file__).resolve().parent
AUTOCHECK_DIR = SCRIPT_DIR / 'autocheck'

# Colors (disable if NO_COLOR or not TTY)
def _use_color():
    if os.environ.get('NO_COLOR'):
        return False
    return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()

def _c(name: str) -> str:
    if not _use_color():
        return ''
    colors = {
        'ok': '\033[32m',
        'info': '\033[36m',
        'warn': '\033[33m',
        'value': '\033[1;34m',
        'null': '\033[0m',
    }
    return colors.get(name, '')


# ─── Config parser (.conf bash-like) ───────────────────────────────────────
def _parse_conf_value(line: str, rest: str, lines_iter) -> str:
    """Parse value: '...' or '...\n...' (multiline)."""
    if rest.startswith("'") and "'" in rest[1:]:
        end = rest.index("'", 1)
        return rest[1:end].replace("\\'", "'")
    if rest.startswith('"') and '"' in rest[1:]:
        end = rest.index('"', 1)
        return rest[1:end].replace('\\"', '"').replace('\\n', '\n')
    if rest.startswith("'") or rest.startswith("'"):
        q = rest[0]
        buf = [rest[1:]] if len(rest) > 1 else []
        for li in lines_iter:
            if q in li:
                idx = li.index(q)
                buf.append(li[:idx].replace("\\'", "'") if q == "'" else li[:idx].replace('\\"', '"'))
                break
            buf.append(li.replace("\\'", "'") if q == "'" else li.replace('\\"', '"'))
        return '\n'.join(buf)
    return rest.strip()


def load_conf(path: str) -> dict:
    """Load .conf file (bash-style key='value'). Returns dict of all keys (lowercased for compat)."""
    path = path.strip()
    if path.startswith(('http://', 'https://')):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            try:
                with urllib.request.urlopen(path, timeout=30) as r:
                    f.write(r.read().decode('utf-8', errors='replace'))
                f.flush()
                real_path = f.name
            except Exception as e:
                raise SystemExit(f"Не удалось скачать конфиг: {e}")
        try:
            return _load_conf_file(real_path)
        finally:
            os.unlink(real_path)

    return _load_conf_file(path)


def _load_conf_file(filepath: str) -> dict:
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    out = {}
    lines = content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            i += 1
            continue
        m = re.match(r"^([a-zA-Z0-9_]+)\s*=\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2).strip()
        if rest.startswith("'") and rest.count("'") == 1:
            val_parts = [rest[1:]]
            i += 1
            while i < len(lines):
                li = lines[i]
                if "'" in li:
                    end = li.index("'")
                    val_parts.append(li[:end].replace("\\'", "'"))
                    i += 1
                    break
                val_parts.append(li.replace("\\'", "'"))
                i += 1
            out[key] = '\n'.join(val_parts)
            continue
        if rest.startswith('"') and rest.count('"') == 1:
            val_parts = [rest[1:]]
            i += 1
            while i < len(lines):
                li = lines[i]
                if '"' in li:
                    end = li.index('"')
                    val_parts.append(li[:end].replace('\\"', '"'))
                    i += 1
                    break
                val_parts.append(li.replace('\\"', '"'))
                i += 1
            out[key] = '\n'.join(val_parts)
            continue
        if rest.startswith("'"):
            end = rest.index("'", 1) if "'" in rest[1:] else -1
            if end != -1:
                out[key] = rest[1:end].replace("\\'", "'")
            else:
                out[key] = rest[1:].replace("\\'", "'")
        elif rest.startswith('"'):
            end = rest.index('"', 1) if '"' in rest[1:] else -1
            if end != -1:
                out[key] = rest[1:end].replace('\\"', '"').replace('\\n', '\n')
            else:
                out[key] = rest[1:].replace('\\"', '"').replace('\\n', '\n')
        else:
            out[key] = rest.rstrip('\r')
        i += 1

    return out


def parse_autocheck_vms(raw: str) -> dict[str, str]:
    """Parse autocheck_vms multiline into { vm_name: exec_type }."""
    result = {}
    for line in raw.split('\n'):
        line = line.strip()
        if '=' not in line:
            continue
        left, _, right = line.partition('=')
        vm_name = left.strip().rstrip()
        exec_type = right.strip().rstrip()
        if vm_name and exec_type:
            result[vm_name] = exec_type
    return result


def get_conf_checks(conf: dict) -> list[tuple[int, str, str, str, str]]:
    """Returns list of (check_id, name, vms_str, cmd_agent, cmd_serial)."""
    checks = []
    n = 1
    while True:
        name_key = f'check_{n}_name'
        if name_key not in conf:
            break
        name = conf.get(name_key, f'Проверка {n}')
        vms = conf.get(f'check_{n}_vms', '')
        cmd_agent = conf.get(f'check_{n}_cmd_exec_agent', '')
        cmd_serial = conf.get(f'check_{n}_cmd_exec_serial', '')
        checks.append((n, name, vms, cmd_agent, cmd_serial))
        n += 1
    return checks


# ─── PVE API (pvesh) ───────────────────────────────────────────────────────
def pvesh_get(path: str) -> dict | list:
    r = subprocess.run(
        ['pvesh', 'get', path, '--output-format', 'json'],
        capture_output=True,
        timeout=30,
    )
    if r.returncode != 0:
        raise SystemExit(f"pvesh get {path}: {r.stderr.decode('utf-8', errors='replace')}")
    return json.loads(r.stdout.decode('utf-8', errors='replace'))


def discover_pools() -> tuple[dict[str, list[str]], dict[str, str]]:
    """Returns (pools: group_id -> [pool_name, ...], print_info: group_id -> "GroupId : comment")."""
    acl = pvesh_get('/access/acl')
    groups_res = pvesh_get('/access/groups')
    groups_list = groups_res.get('data', groups_res) if isinstance(groups_res, dict) else groups_res
    groups_by_id = {}
    if isinstance(groups_list, list):
        for g in groups_list:
            if isinstance(g, dict):
                gid = g.get('groupid') or g.get('group')
                if gid:
                    groups_by_id[gid] = g.get('comment', '')
    elif isinstance(groups_list, dict):
        for k, v in groups_list.items():
            groups_by_id[k] = v.get('comment', '') if isinstance(v, dict) else str(v)

    data = acl.get('data', acl) if isinstance(acl, dict) else acl
    if not isinstance(data, list):
        data = []
    pools: dict[str, list[str]] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if entry.get('type') != 'group':
            continue
        path_val = entry.get('path', '')
        if not path_val.startswith('/pool/'):
            continue
        if entry.get('roleid') != 'NoAccess' or entry.get('propagate', 1) != 0:
            continue
        pool_name = path_val[len('/pool/'):].strip()
        if not pool_name:
            continue
        ugid = entry.get('ugid') or entry.get('groupid') or ''
        if ugid:
            if ugid not in pools:
                pools[ugid] = []
            if pool_name not in pools[ugid]:
                pools[ugid].append(pool_name)

    for gid in list(pools.keys()):
        pools[gid] = sorted(set(pools[gid]))

    print_info = {}
    for gid in pools:
        print_info[gid] = f"{gid} : {groups_by_id.get(gid, '')}"
    return pools, print_info


def get_pool_members(pool_name: str) -> list[dict]:
    """Returns list of member dicts with vmid, name, node, type, status."""
    raw = pvesh_get(f'/pools/{pool_name}')
    members = []
    if isinstance(raw, dict) and 'members' in raw:
        members = raw.get('members', [])
    elif isinstance(raw, list):
        members = raw
    out = []
    for m in members:
        if not isinstance(m, dict):
            continue
        typ = m.get('type', '')
        if not typ and 'id' in m:
            id_val = m.get('id', '')
            if '/' in str(id_val):
                typ = str(id_val).split('/')[0]
        if typ != 'qemu':
            continue
        vmid = m.get('vmid')
        if vmid is None and 'id' in m:
            id_val = m.get('id', '')
            if '/' in str(id_val):
                try:
                    vmid = int(str(id_val).split('/')[1])
                except ValueError:
                    continue
        if vmid is None:
            continue
        name = m.get('name', '') or m.get('id', str(vmid))
        if isinstance(name, str) and '/' in name:
            name = name.split('/')[-1]
        node = m.get('node', '')
        status = m.get('status', 'unknown')
        out.append({'vmid': vmid, 'name': name, 'node': node, 'type': typ, 'status': status})
    return out


def get_vm_status(node: str, vmid: int) -> str:
    try:
        d = pvesh_get(f'/nodes/{node}/qemu/{vmid}/status/current')
        if isinstance(d, dict):
            return d.get('status', '')
    except Exception:
        pass
    return ''


# ─── Executor (serial + agent) ──────────────────────────────────────────────
def strip_ansi(s: str) -> str:
    s = ANSI_RE.sub('', s)
    return s.replace('\x1b', '')


async def drain_buf(reader, timeout: float = 0.3):
    buf = b''
    end = asyncio.get_event_loop().time() + timeout
    while True:
        left = end - asyncio.get_event_loop().time()
        if left <= 0:
            break
        try:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=min(0.1, left))
            if not chunk:
                break
            buf += chunk
        except (asyncio.TimeoutError, ConnectionError, OSError):
            break
    return buf


async def read_until(reader, pattern, timeout: float):
    buf = b''
    pat = re.compile(pattern if isinstance(pattern, str) else pattern.decode())
    end = asyncio.get_event_loop().time() + timeout
    while True:
        left = end - asyncio.get_event_loop().time()
        if left <= 0:
            break
        try:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=min(0.5, left))
            if not chunk:
                break
            buf += chunk
            text = buf.replace(b'\r', b'').decode('utf-8', errors='replace')
            stripped = strip_ansi(text)
            if pat.search(stripped):
                return stripped, True
        except asyncio.TimeoutError:
            continue
        except (ConnectionError, OSError):
            break
    text = buf.replace(b'\r', b'').decode('utf-8', errors='replace')
    return strip_ansi(text), False


async def check_serial_vm(task: dict, verbose: bool = False) -> tuple[str, dict | None, str | None]:
    name = task['name']
    sock = task['socket']
    cmds = task['commands']
    prompt = task.get('prompt', r'[A-Za-z0-9._-]+[#>]')
    tout = int(task.get('timeout', 5))
    login = task.get('login', '')
    passwd = task.get('password', '')
    enable = task.get('enable', False)
    enable_password = task.get('enable_password', '')
    setup_cmds = task.get('setup_cmds', [])
    auth_prompt = prompt if '[#>]' in prompt or '>' in prompt else prompt.rstrip('#') + '[#>]'

    if not os.path.exists(sock):
        return name, None, f"Серийный порт не найден ({sock})"
    try:
        reader, writer = await asyncio.open_unix_connection(sock)
    except (ConnectionError, OSError) as e:
        return name, None, f"Не удалось подключиться: {e}"

    if verbose:
        print(f"[serial] {name}: подключен к {sock}", file=sys.stderr, flush=True)
    results = {}
    try:
        writer.write(b'q\r\n')
        await writer.drain()
        await asyncio.sleep(0.3)
        writer.write(b'\x03')
        await writer.drain()
        await asyncio.sleep(0.2)
        await drain_buf(reader, 0.5)

        auth_pat = f'([Ll]ogin:|[Uu]sername:|[Pp]assword:|{auth_prompt})'
        writer.write(b'\r\n')
        await writer.drain()
        buf, ok = await read_until(reader, auth_pat, tout)
        if not ok:
            return name, None, f"Консоль не отвечает (таймаут {tout}с)"

        if re.search(r'[Ll]ogin:|[Uu]sername:', buf):
            if not login:
                return name, None, "Требуется логин, но не задан"
            if verbose:
                print(f"[serial] {name}: авторизация...", file=sys.stderr, flush=True)
            writer.write(f'{login}\r\n'.encode())
            await writer.drain()
            _, ok = await read_until(reader, r'[Pp]assword:', tout)
            if not ok:
                return name, None, "Не дождались запроса пароля"
            writer.write(f'{passwd}\r\n'.encode())
            await writer.drain()
            _, ok = await read_until(reader, auth_prompt, tout)
            if not ok:
                return name, None, "Авторизация не удалась"
        elif re.search(r'[Pp]assword:', buf):
            if verbose:
                print(f"[serial] {name}: ввод пароля...", file=sys.stderr, flush=True)
            writer.write(f'{passwd}\r\n'.encode())
            await writer.drain()
            _, ok = await read_until(reader, auth_prompt, tout)
            if not ok:
                return name, None, "Авторизация не удалась"
        else:
            if verbose:
                print(f"[serial] {name}: уже авторизован", file=sys.stderr, flush=True)
        await drain_buf(reader, 0.3)

        if enable:
            if verbose:
                print(f"[serial] {name}: enable...", file=sys.stderr, flush=True)
            writer.write(b'enable\r\n')
            await writer.drain()
            buf, ok = await read_until(reader, f'([Pp]assword:|{auth_prompt})', tout)
            if ok and re.search(r'[Pp]assword:', buf):
                writer.write(f'{enable_password}\r\n'.encode())
                await writer.drain()
                _, ok = await read_until(reader, auth_prompt, tout)
                if not ok:
                    return name, None, "enable: неверный пароль"
            elif not ok:
                return name, None, "enable: нет ответа"
            await drain_buf(reader, 0.3)

        for setup_cmd in setup_cmds:
            if verbose:
                print(f"[serial] {name}: setup: {setup_cmd}", file=sys.stderr, flush=True)
            writer.write(f'{setup_cmd}\r\n'.encode())
            await writer.drain()
            await read_until(reader, prompt, tout)
            await drain_buf(reader, 0.3)

        for cn, cmd in cmds:
            await drain_buf(reader, 0.3)
            if verbose:
                print(f"[serial] {name}: проверка {cn}: {cmd[:80]}", file=sys.stderr, flush=True)
            writer.write(f'{cmd}\r\n'.encode())
            await writer.drain()
            output, _ = await read_until(reader, prompt, tout)
            lines = [
                l for l in output.split('\n')
                if l.strip() and l.strip() != cmd.strip() and not re.search(prompt, strip_ansi(l))
            ]
            results[str(cn)] = '\n'.join(lines)

        if verbose:
            print(f"[serial] {name}: готово ({len(cmds)} проверок)", file=sys.stderr, flush=True)
    except Exception as e:
        return name, None, f"Ошибка: {e}"
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
    return name, results, None


def _decode_agent_output(s: str) -> str:
    if not s or not isinstance(s, str):
        return s or ''
    s = s.strip()
    if not s:
        return ''
    if not re.match(r'^[A-Za-z0-9+/=\s]+$', s):
        return s
    try:
        b = base64.b64decode(s)
    except Exception:
        return s
    for enc in ('utf-8', 'cp1251', 'latin-1'):
        try:
            return b.decode(enc)
        except (UnicodeDecodeError, LookupError):
            pass
    return b.decode('utf-8', errors='replace')


def _agent_vm_sync(task: dict, verbose: bool) -> tuple[str, dict | None, str | None]:
    name = task['name']
    node = task['node']
    vmid = task['vmid']
    script_b64 = task['script_b64']
    timeout_sec = int(task.get('timeout_sec', 60))
    check_ids = task.get('check_ids', [])

    script_path = f'/tmp/ac_check_{vmid}.sh'
    run_path = f'{script_path}.run'
    run_cmd = f"base64 -d '{script_path}' > '{run_path}' && bash '{run_path}'; rm -f '{script_path}' '{run_path}'"

    if verbose:
        print(f"[agent] {name}: ping VMID={vmid}...", file=sys.stderr, flush=True)
    for attempt in range(1, 11):
        r = subprocess.run(
            ['pvesh', 'create', f'/nodes/{node}/qemu/{vmid}/agent/ping', '--output-format', 'json'],
            capture_output=True,
            timeout=10,
        )
        if r.returncode == 0:
            if verbose:
                print(f"[agent] {name}: ping OK (попытка {attempt})", file=sys.stderr, flush=True)
            break
        if verbose:
            err = (r.stderr or r.stdout or b'')[:200].decode('utf-8', errors='replace')
            print(f"[agent] {name}: ping попытка {attempt}/10: returncode={r.returncode} err={err!r}", file=sys.stderr, flush=True)
        if attempt == 10:
            return name, None, "Guest Agent недоступен (не ответил на ping за 30с)"
        time.sleep(3)

    if verbose:
        print(f"[agent] {name}: file-write {script_path} size={len(script_b64)}", file=sys.stderr, flush=True)
    for attempt in range(1, 4):
        r = subprocess.run(
            ['pvesh', 'create', f'/nodes/{node}/qemu/{vmid}/agent/file-write', '--file', script_path, '--content', script_b64],
            capture_output=True,
            timeout=30,
        )
        if r.returncode == 0:
            if verbose:
                print(f"[agent] {name}: file-write OK", file=sys.stderr, flush=True)
            break
        if verbose:
            err = (r.stderr or r.stdout or b'')[:200].decode('utf-8', errors='replace')
            print(f"[agent] {name}: file-write попытка {attempt}/3: {r.returncode} {err!r}", file=sys.stderr, flush=True)
        if attempt == 3:
            return name, None, "Не удалось записать скрипт проверки на ВМ"
        time.sleep(2)

    if verbose:
        print(f"[agent] {name}: exec (timeout {timeout_sec}s)...", file=sys.stderr, flush=True)
    pid = None
    for attempt in range(1, 6):
        r = subprocess.run(
            ['pvesh', 'create', f'/nodes/{node}/qemu/{vmid}/agent/exec', '--command', 'bash', '--command', '-c', '--command', run_cmd, '--output-format', 'json'],
            capture_output=True,
            timeout=15,
        )
        out_raw = (r.stdout or b'') + b'\n' + (r.stderr or b'')
        out = out_raw.decode('utf-8', errors='replace')
        if r.returncode != 0:
            if verbose:
                print(f"[agent] {name}: exec попытка {attempt}/5: returncode={r.returncode}", file=sys.stderr, flush=True)
            time.sleep(2 * attempt)
            continue
        try:
            j = json.loads((r.stdout or b'').decode('utf-8', errors='replace'))
            pid = str(j.get('pid', ''))
        except Exception:
            pid = None
        if not pid or not pid.isdigit():
            pid_m = re.search(r'"pid"\s*:\s*(\d+)', out)
            if not pid_m:
                pid_m = re.search(r'pid\s*[\|\u2502]\s*(\d+)', out)
            if pid_m:
                pid = pid_m.group(1)
        if pid and pid.isdigit():
            if verbose:
                print(f"[agent] {name}: exec PID={pid}", file=sys.stderr, flush=True)
            break
        if verbose:
            print(f"[agent] {name}: exec ответ без pid: {out[:300]!r}", file=sys.stderr, flush=True)
        time.sleep(2 * attempt)
    else:
        return name, None, "[Ошибка] Guest Agent недоступен"

    for poll_num in range(timeout_sec):
        r = subprocess.run(
            ['pvesh', 'get', f'/nodes/{node}/qemu/{vmid}/agent/exec-status', '--pid', pid, '--output-format', 'json'],
            capture_output=True,
            timeout=10,
        )
        out_str = (r.stdout or b'') + b'\n' + (r.stderr or b'')
        out_str = out_str.decode('utf-8', errors='replace')
        if r.returncode != 0:
            time.sleep(1)
            continue
        try:
            data = json.loads((r.stdout or b'').decode('utf-8', errors='replace'))
        except Exception:
            try:
                data = json.loads(out_str)
            except Exception:
                time.sleep(1)
                continue
        if data.get('exited') not in (1, True):
            time.sleep(1)
            continue
        if verbose:
            print(f"[agent] {name}: exec завершён за {poll_num}с", file=sys.stderr, flush=True)
        out_data = data.get('out-data') or ''
        err_data = data.get('err-data') or ''
        if isinstance(out_data, str):
            out_data = _decode_agent_output(out_data)
        if isinstance(err_data, str):
            err_data = _decode_agent_output(err_data)
        raw = out_data or ''
        if err_data:
            raw = (raw + '\n' + err_data) if raw else err_data
        results = {}
        cur_id = None
        cur_lines = []
        for line in (raw.split('\n') if isinstance(raw, str) else []):
            m = AC_SEP_RE.match(line.strip())
            if m:
                if cur_id is not None:
                    results[str(cur_id)] = '\n'.join(cur_lines).strip()
                cur_id = int(m.group(1))
                cur_lines = []
            elif cur_id is not None:
                cur_lines.append(line)
        if cur_id is not None:
            results[str(cur_id)] = '\n'.join(cur_lines).strip()
        for cid in check_ids:
            if str(cid) not in results:
                results[str(cid)] = ''
        if verbose:
            print(f"[agent] {name}: готово ({len(results)} проверок)", file=sys.stderr, flush=True)
        return name, results, None

    return name, None, f"Таймаут выполнения команды ({timeout_sec}с)"


async def check_agent_vm(task: dict, semaphore: asyncio.Semaphore, verbose: bool) -> tuple[str, dict | None, str | None]:
    async with semaphore:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: _agent_vm_sync(task, verbose))


async def run_tasks(tasks: list[dict], verbose: bool) -> str:
    """Run all tasks, return combined stdout (===AC_VM/AC_CHK/AC_ERR protocol)."""
    agent_semaphore = asyncio.Semaphore(5)
    out_lines = []

    async def run_one(t):
        if t.get('type') == 'agent':
            return await check_agent_vm(t, agent_semaphore, verbose)
        return await check_serial_vm(t, verbose)

    done = await asyncio.gather(*[run_one(t) for t in tasks], return_exceptions=True)
    for item in done:
        if isinstance(item, Exception):
            out_lines.append('===AC_VM:???===')
            out_lines.append('===AC_ERR===')
            out_lines.append(str(item))
            continue
        name, data, error = item
        out_lines.append(f'===AC_VM:{name}===')
        if error:
            out_lines.append('===AC_ERR===')
            out_lines.append(error)
        elif data:
            for cn in sorted(data.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
                out_lines.append(f'===AC_CHK:{cn}===')
                if data[cn]:
                    out_lines.append(data[cn])
    return '\n'.join(out_lines)


# ─── Numrange (1,2-5,8) ─────────────────────────────────────────────────────
def parse_numrange(s: str) -> list[int]:
    if not s or not s.strip():
        return []
    result = []
    for part in s.replace(' ', '').split(','):
        if '-' in part:
            a, b = part.split('-', 1)
            try:
                lo, hi = int(a.strip()), int(b.strip())
                result.extend(range(lo, hi + 1))
            except ValueError:
                pass
        elif '..' in part:
            a, b = part.split('..', 1)
            try:
                lo, hi = int(a.strip()), int(b.strip())
                result.extend(range(lo, hi + 1))
            except ValueError:
                pass
        else:
            try:
                result.append(int(part.strip()))
            except ValueError:
                pass
    return sorted(set(result))


# ─── Main flow ─────────────────────────────────────────────────────────────
def select_config_file(config_arg: str | None, autocheck_dir: Path) -> str | None:
    if config_arg:
        if config_arg.startswith(('http://', 'https://')):
            print(f"[Info] Скачивание конфигурации: {config_arg}", flush=True)
        return config_arg
    if not autocheck_dir.is_dir():
        print(f"Папка autocheck/ не найдена: {autocheck_dir}", file=sys.stderr)
        return None
    conf_files = sorted(autocheck_dir.glob('*.conf'))
    if not conf_files:
        print(f"Файлы автопроверки не найдены в {autocheck_dir}", file=sys.stderr)
        return None
    print("\nДоступные конфигурации автопроверки:")
    for i, f in enumerate(conf_files, 1):
        try:
            c = load_conf(str(f))
            name = c.get('autocheck_name', f.name)
        except Exception:
            name = f.name
        print(f"  {i}. {name}")
    try:
        sel = input("Выберите конфигурацию (номер): ").strip()
        idx = int(sel)
        if 1 <= idx <= len(conf_files):
            return str(conf_files[idx - 1])
    except (ValueError, EOFError):
        pass
    return None


def run_stand(
    pool_name: str,
    conf: dict,
    vm_exec: dict[str, str],
    checks: list,
    pools_members: dict[str, list[dict]],
    verbose: bool,
    mode: str,
) -> list[str]:
    """Run checks for one stand (pool_name). Returns list of report lines."""
    filebuf: list[str] = []
    members = pools_members.get(pool_name, [])
    map_id = {}
    map_node = {}
    map_status = {}
    for m in members:
        if m.get('type') != 'qemu':
            continue
        name = m.get('name') or m.get('id') or ''
        vmid = m.get('vmid') or m.get('id')
        if vmid is None:
            continue
        node = m.get('node', '')
        map_id[name] = str(vmid)
        map_node[name] = node
        map_status[name] = m.get('status', 'unknown')

    batch_script = {}
    batch_checks = {}
    serial_cmds = {}
    serial_checks = {}

    for cn, cname, vms_str, cmd_agent, cmd_serial in checks:
        if not vms_str.strip():
            continue
        for vm in vms_str.split():
            if vm_exec.get(vm) != 'exec_agent':
                continue
            if vm not in map_id:
                continue
            if vm not in batch_script:
                batch_script[vm] = []
                batch_checks[vm] = []
            batch_script[vm].append(f"echo '===AC_SEP_{cn}==='; {{ {cmd_agent}; }} 2>&1; ")
            batch_checks[vm].append(cn)
    for cn, cname, vms_str, cmd_agent, cmd_serial in checks:
        if not vms_str.strip():
            continue
        for vm in vms_str.split():
            if vm_exec.get(vm) != 'exec_serial':
                continue
            if vm not in map_id:
                continue
            if vm not in serial_cmds:
                serial_cmds[vm] = []
                serial_checks[vm] = []
            serial_cmds[vm].append((cn, cmd_serial))
            serial_checks[vm].append(cn)

    results = {}

    def fill_not_running(vm: str, status: str, check_ids: list):
        for cid in check_ids:
            results[(vm, cid)] = f"[Ошибка] ВМ не запущена ({status})"

    tasks_payload = []
    prompt = conf.get('exec_serial_prompt', '[A-Za-z0-9._-]+[#>]')
    timeout_s = int(conf.get('exec_serial_timeout', 5) or 5)

    for vm in serial_cmds:
        vmid = map_id[vm]
        node = map_node[vm]
        status = get_vm_status(node, int(vmid))
        if status != 'running':
            if mode == 'tty':
                print(f"  ▸ [{pool_name}] {_c('ok')}{vm}{_c('null')} (VMID {vmid}, serial)")
                print(f"    {_c('warn')}ВМ не запущена ({status}), пропуск{_c('null')}")
            fill_not_running(vm, status, serial_checks[vm])
            continue
        map_status[vm] = 'running'
        chk_count = len(serial_cmds[vm])
        if mode == 'tty':
            print(f"  ▸ [{pool_name}] {_c('ok')}{vm}{_c('null')} (VMID {vmid}, serial, {chk_count} проверок)")

        san = vm.replace('-', '_')
        login = conf.get(f'{san}_serial_login') or conf.get('exec_serial_login') or ''
        password = conf.get(f'{san}_serial_password') or conf.get('exec_serial_password') or ''
        enable = conf.get(f'{san}_serial_enable') or conf.get('exec_serial_enable')
        if isinstance(enable, str):
            enable = enable.strip().lower() in ('true', '1', 'yes', 'да')
        enable_password = conf.get(f'{san}_serial_enable_password') or conf.get('exec_serial_enable_password') or ''
        setup = conf.get(f'{san}_serial_setup') or conf.get('exec_serial_setup') or ''
        setup_cmds = [x.strip() for x in setup.split(';') if x.strip()] if setup else []

        tasks_payload.append({
            'type': 'serial',
            'name': vm,
            'socket': f'/var/run/qemu-server/{vmid}.serial0',
            'commands': serial_cmds[vm],
            'prompt': prompt,
            'timeout': timeout_s,
            'login': login,
            'password': password,
            'enable': bool(enable),
            'enable_password': enable_password,
            'setup_cmds': setup_cmds,
        })

    for vm in batch_script:
        vmid = map_id[vm]
        node = map_node[vm]
        status = get_vm_status(node, int(vmid))
        if status != 'running':
            if mode == 'tty':
                print(f"  ▸ [{pool_name}] {_c('ok')}{vm}{_c('null')} (VMID {vmid})")
                print(f"    {_c('warn')}ВМ не запущена ({status}), пропуск{_c('null')}")
            fill_not_running(vm, status, batch_checks[vm])
            continue
        map_status[vm] = 'running'
        chk_count = len(batch_checks[vm])
        if mode == 'tty':
            print(f"  ▸ [{pool_name}] {_c('ok')}{vm}{_c('null')} (VMID {vmid}, {chk_count} проверок)")

        script_body = '#!/bin/bash\n' + ''.join(batch_script[vm])
        script_b64 = base64.b64encode(script_body.encode()).decode()
        timeout_sec = chk_count * 5 + 30
        tasks_payload.append({
            'type': 'agent',
            'name': vm,
            'node': node,
            'vmid': vmid,
            'script_b64': script_b64,
            'timeout_sec': timeout_sec,
            'check_ids': batch_checks[vm],
        })

    if not tasks_payload:
        if mode == 'tty':
            print("    Нет запущенных ВМ для проверки")
        return

    helper_out = asyncio.run(run_tasks(tasks_payload, verbose))

    cur_vm = ''
    cur_cn = ''
    cur_out = []
    for line in helper_out.split('\n'):
        if re.match(r'^===AC_VM:(.+)===$', line):
            m = re.match(r'^===AC_VM:(.+)===$', line)
            if m:
                if cur_vm and cur_cn is not None:
                    results[(cur_vm, cur_cn)] = '\n'.join(cur_out)
                cur_vm = m.group(1)
                cur_cn = None
                cur_out = []
        elif re.match(r'^===AC_CHK:([0-9]+)===$', line):
            m = re.match(r'^===AC_CHK:([0-9]+)===$', line)
            if m:
                if cur_vm and cur_cn is not None:
                    results[(cur_vm, cur_cn)] = '\n'.join(cur_out)
                cur_cn = int(m.group(1))
                cur_out = []
        elif line == '===AC_ERR===':
            if cur_vm and cur_cn is not None:
                results[(cur_vm, cur_cn)] = '\n'.join(cur_out)
            cur_cn = 'error'
            cur_out = []
        else:
            cur_out.append(line)
    if cur_vm and cur_cn is not None:
        results[(cur_vm, cur_cn)] = '\n'.join(cur_out)

    for vm in serial_checks:
        if (vm, 'error') in results:
            err = results.pop((vm, 'error'), '')
            for cid in serial_checks[vm]:
                if (vm, cid) not in results:
                    results[(vm, cid)] = f"[Ошибка] {err}"
    for vm in batch_checks:
        if (vm, 'error') in results:
            err = results.pop((vm, 'error'), '')
            for cid in batch_checks[vm]:
                if (vm, cid) not in results:
                    results[(vm, cid)] = f"[Ошибка] {err}"

    if mode == 'tty':
        print(f"    {_c('ok')}✓{_c('null')} проверки завершены")

    autocheck_name = conf.get('autocheck_name', pool_name)
    sep = f"{_c('value')}══════════════════════════════════════{_c('null')}"
    filebuf.append(sep)
    filebuf.append(f" Автопроверка: {_c('ok')}{autocheck_name}{_c('null')}")
    filebuf.append(f" Стенд: {_c('value')}{pool_name}{_c('null')}")
    filebuf.append(sep)
    filebuf.append('')

    if mode == 'tty':
        print()
        print(sep)
        print(f" Автопроверка: {_c('ok')}{autocheck_name}{_c('null')}")
        print(f" Стенд: {_c('value')}{pool_name}{_c('null')}")
        print(sep)

    for cn, cname, vms_str, _ca, _cs in checks:
        if not vms_str.strip():
            continue
        if mode == 'tty':
            print()
            print(f"── Проверка {cn}: {cname} ──")
        filebuf.append(f"── Проверка {cn}: {cname} ──")
        filebuf.append('')

        for vm in vms_str.split():
            etype = vm_exec.get(vm, '')
            if not etype:
                if mode == 'tty':
                    print(f"  [{_c('ok')}{vm}{_c('warn')}] Тип подключения не указан в autocheck_vms{_c('null')}")
                continue
            vid = map_id.get(vm, '')
            if not vid:
                if mode == 'tty':
                    print(f"  [{_c('ok')}{vm}{_c('warn')}] ВМ не найдена в стенде {pool_name}{_c('null')}")
                continue
            vstat = map_status.get(vm, '')
            if vstat != 'running':
                if mode == 'tty':
                    print(f"  [{_c('ok')}{vm}{_c('warn')}] ВМ не запущена ({vstat}){_c('null')}")
                filebuf.append(f"  [{_c('ok')}{vm}{_c('null')}] ({etype}):")
                filebuf.append(f"[Ошибка] ВМ не запущена ({vstat})")
                filebuf.append('')
                continue
            cmd_var = f'check_{cn}_cmd_{etype}'
            cmd_val = conf.get(cmd_var, '')
            if not cmd_val:
                if mode == 'tty':
                    print(f"  [{vm}] Команда для {etype} не задана")
                continue
            out = results.get((vm, cn), '')
            if mode == 'tty':
                print()
                print(f"  [{_c('ok')}{vm}{_c('null')}] ({etype}):")
                if out:
                    for ln in out.split('\n'):
                        print(f"  {ln}")
                else:
                    print(f"  {_c('info')}(пустой вывод){_c('null')}")
            filebuf.append(f"  [{_c('ok')}{vm}{_c('null')}] ({etype}):")
            filebuf.append(out or '(пустой вывод)')
            filebuf.append('')

    return filebuf


def main():
    parser = argparse.ArgumentParser(description='Автопроверка стендов PVE')
    parser.add_argument('config', nargs='?', help='Файл или URL конфигурации .conf')
    parser.add_argument('-g', '--group', help='Группа (ID) стендов')
    parser.add_argument('-s', '--stands', help='Номера стендов (например 1,2-5,8)')
    parser.add_argument('-o', '--output', help='Файл для сохранения отчёта')
    parser.add_argument('-p', '--parallel', type=int, default=None, metavar='N', help='Проверять одновременно N стендов (по умолчанию 1)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Подробный вывод')
    parser.add_argument('--no-interact', action='store_true', help='Без интерактивных вопросов')
    args = parser.parse_args()

    autocheck_dir = AUTOCHECK_DIR
    config_path = args.config
    if not config_path and not args.no_interact:
        config_path = select_config_file(None, autocheck_dir)
    elif not config_path:
        config_path = None
    if not config_path:
        print("Конфигурация не указана.", file=sys.stderr)
        sys.exit(1)

    try:
        conf = load_conf(config_path)
    except FileNotFoundError:
        print(f"Файл конфигурации не найден: {config_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка загрузки конфига: {e}", file=sys.stderr)
        sys.exit(1)

    autocheck_name = conf.get('autocheck_name', Path(config_path).name)
    raw_vms = conf.get('autocheck_vms', '')
    vm_exec = parse_autocheck_vms(raw_vms)
    if not vm_exec:
        print("Не найдено ВМ в autocheck_vms конфигурации", file=sys.stderr)
        sys.exit(1)

    checks = get_conf_checks(conf)
    if not checks:
        print("В конфигурации не найдено проверок (check_N_name)", file=sys.stderr)
        sys.exit(1)

    try:
        pools, print_info = discover_pools()
    except Exception as e:
        print(f"Не удалось получить список пулов: {e}", file=sys.stderr)
        sys.exit(1)

    if not pools:
        print("Не найдено ни одной развёрнутой конфигурации.")
        return

    group_name = args.group
    if not group_name:
        if args.no_interact:
            group_name = next(iter(pools.keys()), None)
        else:
            print("\nСписок развернутых конфигураций:")
            items = list(pools.keys())
            for i, gid in enumerate(items, 1):
                print(f"  {i}. {print_info.get(gid, gid)}")
            try:
                sel = input("Выберите номер конфигурации: ").strip()
                idx = int(sel)
                if 1 <= idx <= len(items):
                    group_name = items[idx - 1]
            except (ValueError, EOFError):
                pass
            if not group_name:
                print("Конфигурация не выбрана.", file=sys.stderr)
                sys.exit(1)

    if group_name not in pools:
        print(f"Группа '{group_name}' не найдена.", file=sys.stderr)
        sys.exit(1)

    stand_list = pools[group_name]
    stand_count = len(stand_list)
    sel_stands = []
    if args.stands:
        indices = parse_numrange(args.stands)
        sel_stands = [i for i in indices if 1 <= i <= stand_count]
        if not sel_stands:
            sel_stands = list(range(1, stand_count + 1))
    elif args.no_interact:
        sel_stands = list(range(1, stand_count + 1))
    else:
        if stand_count > 1:
            print("\nВыберите стенды для проверки:")
            for i, p in enumerate(stand_list, 1):
                print(f"  {i}. {p}")
            print("\nДля выбора всех стендов нажмите Enter")
            inp = input("Введите номера стендов (прим 1,2-6): ").strip()
            if inp:
                indices = parse_numrange(inp)
                sel_stands = [i for i in indices if 1 <= i <= stand_count]
            else:
                sel_stands = list(range(1, stand_count + 1))
        else:
            sel_stands = [1]
        if not sel_stands:
            print("Стенды не выбраны.", file=sys.stderr)
            sys.exit(1)

    parallel = args.parallel
    if parallel is None and len(sel_stands) > 1 and not args.no_interact:
        try:
            inp = input(f"Проверять одновременно стендов (1-{len(sel_stands)}) [1]: ").strip()
            if inp:
                parallel = max(1, min(len(sel_stands), int(inp)))
            else:
                parallel = 1
        except (ValueError, EOFError):
            parallel = 1
    elif parallel is None:
        parallel = 1
    else:
        parallel = max(1, min(len(sel_stands), parallel))

    outfile = args.output
    if not outfile and not args.no_interact:
        try:
            inp = input("Сохранить результаты в файл? [y/N]: ").strip().lower()
            if inp and inp[0] in ('y', 'д', '1'):
                outfile = input(f"Путь к файлу [{os.getcwd()}/autocheck_report.txt]: ").strip()
                if not outfile:
                    outfile = f"{os.getcwd()}/autocheck_report.txt"
        except EOFError:
            pass

    pools_members = {}
    for p in stand_list:
        try:
            pools_members[p] = get_pool_members(p)
        except Exception:
            pools_members[p] = []

    all_filebuf: list[str] = []
    if parallel <= 1:
        for idx in sel_stands:
            if idx < 1 or idx > stand_count:
                continue
            pool_name = stand_list[idx - 1]
            lines = run_stand(
                pool_name=pool_name,
                conf=conf,
                vm_exec=vm_exec,
                checks=checks,
                pools_members=pools_members,
                verbose=args.verbose,
                mode='tty',
            )
            all_filebuf.extend(lines)
    else:
        def run_one(idx: int) -> tuple[int, list[str]]:
            if idx < 1 or idx > stand_count:
                return idx, []
            pool_name = stand_list[idx - 1]
            lines = run_stand(
                pool_name=pool_name,
                conf=conf,
                vm_exec=vm_exec,
                checks=checks,
                pools_members=pools_members,
                verbose=args.verbose,
                mode='quiet',
            )
            return idx, lines

        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {executor.submit(run_one, idx): idx for idx in sel_stands}
            results_by_idx: dict[int, list[str]] = {}
            for future in as_completed(futures):
                idx, lines = future.result()
                results_by_idx[idx] = lines
            for idx in sel_stands:
                if idx in results_by_idx:
                    lines = results_by_idx[idx]
                    for ln in lines:
                        print(ln)
                    all_filebuf.extend(lines)

    if outfile and all_filebuf:
        try:
            with open(outfile, 'w', encoding='utf-8') as f:
                f.write('\n'.join(all_filebuf))
            print()
            print(f"Результаты сохранены в {_c('value')}{outfile}{_c('null')}")
        except Exception as e:
            print(f"Не удалось записать в файл: {e}", file=sys.stderr)

    print()
    print(f"{_c('ok')}Автопроверка завершена.{_c('null')}")


if __name__ == '__main__':
    main()
