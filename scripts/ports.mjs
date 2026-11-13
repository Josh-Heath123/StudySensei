// Port checks for `npm run dev`.
//
// We probe by *connecting* rather than by trying to bind: uvicorn sets SO_REUSEADDR, and on Windows that lets
// a second server bind a port that's already taken, so the old one keeps answering and the new one is never hit.
import { execFileSync } from "node:child_process";
import net from "node:net";

/** Resolve true if something accepts a TCP connection on host:port. */
function accepts(host, port) {
  return new Promise((resolve) => {
    const socket = net.connect({ host, port });
    const done = (result) => {
      socket.destroy();
      resolve(result);
    };
    socket.setTimeout(1000, () => done(false));
    socket.once("connect", () => done(true));
    socket.once("error", () => done(false));
  });
}

/** True if the port is answering on IPv4 or IPv6 loopback (Vite's "localhost" is often ::1). */
export async function inUse(port) {
  const results = await Promise.all([
    accepts("127.0.0.1", port),
    accepts("::1", port),
  ]);
  return results.some(Boolean);
}

/** Describe the processes listening on a port, one per line. Best effort: returns [] if the OS tools fail. */
export function listeners(port) {
  try {
    return process.platform === "win32"
      ? windowsListeners(port)
      : unixListeners(port);
  } catch {
    return [];
  }
}

function windowsListeners(port) {
  // A listening socket has remote port 0. Match on that as well as State: some sandboxes report listeners in
  // other states. Also list each owner's children: a uvicorn --reload parent can be invisible to Win32_Process
  // while its worker (the process that actually answers) still shows up with the parent's PID.
  const script = `
    $owners = @(Get-NetTCPConnection -LocalPort ${port} -ErrorAction SilentlyContinue |
      Where-Object { ($_.State -eq 'Listen' -or $_.RemotePort -eq 0) -and $_.OwningProcess -ne 0 } |
      Select-Object -ExpandProperty OwningProcess -Unique)
    $rows = foreach ($id in $owners) {
      $p = Get-CimInstance Win32_Process -Filter "ProcessId=$id"
      [pscustomobject]@{ pid = $id; role = 'listener'; cmd = if ($p) { $p.CommandLine } else { '(process details hidden)' } }
      Get-CimInstance Win32_Process -Filter "ParentProcessId=$id" |
        ForEach-Object { [pscustomobject]@{ pid = $_.ProcessId; role = 'child'; cmd = $_.CommandLine } }
    }
    ConvertTo-Json -Compress @($rows)`;
  const out = execFileSync(
    "powershell",
    ["-NoProfile", "-NonInteractive", "-Command", script],
    {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    },
  ).trim();
  if (!out) return [];
  const rows = [JSON.parse(out)].flat();
  return rows.map((r) => `PID ${r.pid} (${r.role}): ${r.cmd ?? "(unknown)"}`);
}

function unixListeners(port) {
  const out = execFileSync(
    "lsof",
    ["-nP", `-iTCP:${port}`, "-sTCP:LISTEN", "-Fpc"],
    {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    },
  );
  const lines = [];
  let pid;
  for (const line of out.split("\n")) {
    if (line.startsWith("p")) pid = line.slice(1);
    else if (line.startsWith("c"))
      lines.push(`PID ${pid} (listener): ${line.slice(1)}`);
  }
  return lines;
}

/**
 * Exit with a clear message if any of the ports is taken. `ports` maps a port to what we want to run on it.
 */
export async function requireFreePorts(ports) {
  const busy = [];
  for (const [port, name] of Object.entries(ports)) {
    if (await inUse(Number(port)))
      busy.push({ port, name, holders: listeners(port) });
  }
  if (busy.length === 0) return;

  const kill =
    process.platform === "win32"
      ? "PowerShell: Stop-Process -Force -Id <PID>"
      : "kill <PID>";
  console.error(
    "\nCan't start: these ports are already in use, probably by an old dev server.\n",
  );
  for (const { port, name, holders } of busy) {
    console.error(`  Port ${port} (needed for the ${name}) is held by:`);
    for (const h of holders.length
      ? holders
      : ["(couldn't identify the process)"]) {
      console.error(`    ${h}`);
    }
  }
  console.error(
    `\nStop those processes, children included (${kill}), then run npm run dev again.\n`,
  );
  process.exit(1);
}
