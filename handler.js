const net = require('net');
const os = require('os');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const isWin = process.platform === "win32";
const SOCKET_PATH = isWin ? null : '/tmp/ki_shell.sock';
const SOCKET_PORT = 8777;
const SOCKET_HOST = '127.0.0.1';

function findPython() {
  const base = __dirname;
  // Erst nach venv-Python suchen:
  const venvPy = process.platform === "win32"
    ? path.join(base, ".venv", "Scripts", "python.exe")
    : path.join(base, ".venv", "bin", "python");
  if (fs.existsSync(venvPy)) return venvPy;
  // Fallback:
  return process.platform === "win32" ? "python" : "python3";
}

function findGuiBinary() {
  const base = __dirname;
  const venvPython = findPython();
  if (process.platform === "win32") {
    const exePath = path.join(base, 'ki_shell_gui.exe');
    if (fs.existsSync(exePath)) return { cmd: exePath, args: [] };
    const pyPath = path.join(base, 'ki_shell_gui.py');
    if (fs.existsSync(pyPath)) return { cmd: venvPython, args: [pyPath] };
    return null;
  } else {
    const binPath = path.join(base, 'ki_shell_gui');
    if (fs.existsSync(binPath) && fs.statSync(binPath).mode & 0o111) return { cmd: binPath, args: [] };
    const pyPath = path.join(base, 'ki_shell_gui.py');
    if (fs.existsSync(pyPath)) return { cmd: venvPython, args: [pyPath] };
    return null;
  }
}

function startGuiIfNeeded(cb) {
  if (isWin) {
    // Für TCP prüfen wir, ob Port offen ist (simple Connect mit kurzem Timeout)
    const test = net.createConnection({ host: SOCKET_HOST, port: SOCKET_PORT }, () => {
      test.end();
      cb();
    });
    test.on('error', () => {
      // Backend starten
      const gui = findGuiBinary();
      if (!gui) throw new Error("KI-Shell-GUI Backend nicht gefunden!");
      console.log("Starte das KI-Shell-GUI Backend...");
      spawn(gui.cmd, gui.args, { detached: true, stdio: 'ignore' }).unref();
      setTimeout(cb, 2000);
    });
    test.setTimeout(1000, () => test.destroy());
  } else {
    if (fs.existsSync(SOCKET_PATH)) return cb();
    // Backend starten
    const gui = findGuiBinary();
    if (!gui) throw new Error("KI-Shell-GUI Backend nicht gefunden!");
    console.log("Starte das KI-Shell-GUI Backend...");
    spawn(gui.cmd, gui.args, { detached: true, stdio: 'ignore' }).unref();
    setTimeout(cb, 2000);
  }
}

function sendSkillRequest(session, command) {
  return new Promise((resolve, reject) => {
    startGuiIfNeeded(() => {
      let client, data = "";
      if (isWin) {
        client = net.createConnection({ host: SOCKET_HOST, port: SOCKET_PORT }, () => {
          client.write(JSON.stringify({ session, command, type: "request" }) + "\n");
        });
      } else {
        client = net.createConnection(SOCKET_PATH, () => {
          client.write(JSON.stringify({ session, command, type: "request" }) + "\n");
        });
      }
      client.on('data', chunk => { data += chunk.toString(); });
      client.on('end', () => {
        try {
          const response = JSON.parse(data);
          resolve(response);
        } catch (e) {
          reject(e);
        }
      });
      client.on('error', reject);
    });
  });
}

module.exports.runtime = {
  handler: async function(args) {
    if (!args.sessionId || !args.command) {
      return "❌ sessionId und command erforderlich!";
    }
    try {
      const result = await sendSkillRequest(args.sessionId, args.command);
      if (result.status === "approved") {
        return `[Terminal Output]\n${result.output}`;
      } else if (result.status === "rejected") {
        return "❌ Der Befehl wurde vom Nutzer abgelehnt.";
      } else {
        return "⚠️ Unerwartete Antwort vom Shell-GUI.";
      }
    } catch (e) {
      return "❌ Fehler bei Kommunikation mit dem lokalen KI-Shell-GUI: " + (e.message || e);
    }
  }
};
