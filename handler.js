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
  const venvPy = isWin
    ? path.join(base, ".venv", "Scripts", "python.exe")
    : path.join(base, ".venv", "bin", "python3");
  if (fs.existsSync(venvPy)) return venvPy;
  return isWin ? "python" : "python3";
}

function findGuiBinary() {
  const base = __dirname;
  const venvPython = findPython();
  if (isWin) {
    const exePath = path.join(base, 'ki_shell_gui.exe');
    if (fs.existsSync(exePath)) return { cmd: exePath, args: [] };
    const pyPath = path.join(base, 'ki_shell_gui.py');
    if (fs.existsSync(pyPath)) return { cmd: venvPython, args: [pyPath] };
    return null;
  } else {
    const binPath = path.join(base, 'ki_shell_gui');
    if (fs.existsSync(binPath) && (fs.statSync(binPath).mode & 0o111)) return { cmd: binPath, args: [] };
    const pyPath = path.join(base, 'ki_shell_gui.py');
    if (fs.existsSync(pyPath)) return { cmd: venvPython, args: [pyPath] };
    return null;
  }
}

function startGuiIfNeeded(cb) {
  if (isWin) {
    const test = net.createConnection({ host: SOCKET_HOST, port: SOCKET_PORT }, () => {
      test.end();
      cb();
    });
    test.on('error', () => {
      const gui = findGuiBinary();
      if (!gui) throw new Error(
        "KI-Shell-GUI Backend nicht gefunden!\n" +
        "Bitte stelle sicher, dass ki_shell_gui.py im Skill-Verzeichnis liegt\n" +
        "und vorher mit 'pip install -r requirements.txt' (im venv!) installiert wurde."
      );
      console.log("Starte das KI-Shell-GUI Backend...");
      spawn(gui.cmd, gui.args, { detached: true, stdio: 'ignore' }).unref();
      setTimeout(cb, 2000);
    });
    test.setTimeout(1000, () => test.destroy());
  } else {
    if (fs.existsSync(SOCKET_PATH)) return cb();
    const gui = findGuiBinary();
    if (!gui) throw new Error(
      "KI-Shell-GUI Backend nicht gefunden!\n" +
      "Bitte stelle sicher, dass ki_shell_gui.py im Skill-Verzeichnis liegt\n" +
      "und vorher mit 'pip install -r requirements.txt' (im venv!) installiert wurde."
    );
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

function randomSessionId() {
  return "sess_" + Math.random().toString(36).slice(2, 12);
}

module.exports.runtime = {
  handler: async function(args) {
    // IMMER das GUI starten, auch ohne command!
    return await new Promise((resolve) => {
      startGuiIfNeeded(() => {
        if (!args.command) {
          resolve(
            "GhostShell Terminal GUI wurde gestartet.\n" +
            "Du kannst jetzt Befehle senden oder die Session im Fenster konfigurieren."
          );
        } else {
          let sessionId = args.sessionId || randomSessionId();
          let command = args.command;
          sendSkillRequest(sessionId, command)
            .then(result => {
              if (result.status === "approved") {
                resolve(`[Terminal Output]\n${result.output}`);
              } else if (result.status === "rejected") {
                resolve("Der Befehl wurde vom Nutzer abgelehnt.");
              } else {
                resolve("Unerwartete Antwort vom Shell-GUI.");
              }
            })
            .catch(e => resolve("Fehler bei Kommunikation mit dem lokalen KI-Shell-GUI: " + (e.message || e)));
        }
      });
    });
  }
};
