const net = require('net');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawn } = require('child_process');

const isWin = process.platform === "win32";
const BASE = __dirname;
const SOCKET_PATH = isWin ? null : '/tmp/ki_shell.sock';
const SOCKET_PORT = 8777;
const SOCKET_HOST = '127.0.0.1';

function findPython() {
  // Bevorzugt venv
  const venvPy = isWin
    ? path.join(BASE, ".venv", "Scripts", "python.exe")
    : path.join(BASE, ".venv", "bin", "python3");
  if (fs.existsSync(venvPy)) return venvPy;
  return isWin ? "python" : "python3";
}

function findGuiBinary() {
  const venvPython = findPython();
  if (isWin) {
    const exePath = path.join(BASE, 'ki_shell_gui.exe');
    if (fs.existsSync(exePath)) return { cmd: exePath, args: [] };
    const pyPath = path.join(BASE, 'ki_shell_gui.py');
    if (fs.existsSync(pyPath)) return { cmd: venvPython, args: [pyPath] };
    return null;
  } else {
    const binPath = path.join(BASE, 'ki_shell_gui');
    if (fs.existsSync(binPath) && (fs.statSync(binPath).mode & 0o111)) return { cmd: binPath, args: [] };
    const pyPath = path.join(BASE, 'ki_shell_gui.py');
    if (fs.existsSync(pyPath)) return { cmd: venvPython, args: [pyPath] };
    return null;
  }
}

// Prüft wirklich, ob der Socket erreichbar ist!
function isGuiRunning(introspect, cb) {
  if (isWin) {
    // TCP check
    const client = net.createConnection({ host: SOCKET_HOST, port: SOCKET_PORT });
    let done = false;
    client.on('connect', () => {
      done = true;
      client.destroy();
      if (introspect) introspect("[GhostShell DEBUG] GUI ist ERREICHBAR (TCP)");
      cb(true);
    });
    client.on('error', () => {
      if (!done && introspect) introspect("[GhostShell DEBUG] GUI ist NICHT erreichbar (TCP)");
      cb(false);
    });
    client.setTimeout(900, () => {
      if (!done && introspect) introspect("[GhostShell DEBUG] Timeout beim Verbinden zum GUI (TCP)");
      client.destroy(); cb(false);
    });
  } else {
    // UNIX socket
    if (!fs.existsSync(SOCKET_PATH)) {
      if (introspect) introspect("[GhostShell DEBUG] Socket existiert NICHT");
      cb(false); return;
    }
    const client = net.createConnection(SOCKET_PATH);
    let done = false;
    client.on('connect', () => {
      done = true;
      client.destroy();
      if (introspect) introspect("[GhostShell DEBUG] GUI ist ERREICHBAR (Socket)");
      cb(true);
    });
    client.on('error', () => {
      if (!done && introspect) introspect("[GhostShell DEBUG] GUI ist NICHT erreichbar (Socket)");
      cb(false);
    });
    client.setTimeout(900, () => {
      if (!done && introspect) introspect("[GhostShell DEBUG] Timeout beim Verbinden zum GUI (Socket)");
      client.destroy(); cb(false);
    });
  }
}

// Startet das GUI wirklich (im richtigen ENV!) und wartet ggf. darauf
function startGuiIfNeeded(introspect, cb) {
  isGuiRunning(introspect, (running) => {
    if (running) {
      if (introspect) introspect("[GhostShell DEBUG] GUI läuft bereits (erreichbar).");
      cb();
      return;
    }
    const gui = findGuiBinary();
    if (!gui) {
      if (introspect) introspect("[GhostShell DEBUG] KI-Shell-GUI Backend NICHT gefunden!");
      throw new Error(
        "KI-Shell-GUI Backend nicht gefunden!\n" +
        "Bitte stelle sicher, dass ki_shell_gui.py im Skill-Verzeichnis liegt\n" +
        "und vorher mit 'pip install -r requirements.txt' (im venv!) installiert wurde."
      );
    }
    if (introspect) introspect(`[GhostShell DEBUG] Starte KI-Shell-GUI Backend: ${gui.cmd} ${gui.args.join(" ")}`);
    spawn(gui.cmd, gui.args, { detached: true, stdio: 'ignore' }).unref();
    // Warten, bis Socket da UND erreichbar ist:
    let tries = 0;
    function retry() {
      isGuiRunning(introspect, (now) => {
        if (now) {
          if (introspect) introspect("[GhostShell DEBUG] GUI erfolgreich gestartet und erreichbar.");
          cb();
        } else if (tries++ < 9) {
          setTimeout(retry, 700);
        } else {
          if (introspect) introspect("[GhostShell DEBUG] GUI konnte NICHT gestartet werden (Timeout)!");
          cb(new Error("GUI konnte nicht gestartet werden!"));
        }
      });
    }
    setTimeout(retry, 1300);
  });
}

function sendSuggestion(session, command, introspect) {
  return new Promise((resolve, reject) => {
    startGuiIfNeeded(introspect, (err) => {
      if (err) return reject(err);
      // Jetzt ist der Socket wirklich da!
      let client;
      let payload = JSON.stringify({ session, command, type: "suggestion" });
      if (isWin) {
        client = net.createConnection({ host: SOCKET_HOST, port: SOCKET_PORT }, () => {
          if (introspect) introspect(`[GhostShell DEBUG] Sende KI-Vorschlag (TCP): ${payload}`);
          client.write(payload);
          client.end();
          resolve("Command sent as suggestion to the terminal (TCP).");
        });
      } else {
        client = net.createConnection(SOCKET_PATH, () => {
          if (introspect) introspect(`[GhostShell DEBUG] Sende KI-Vorschlag (Socket): ${payload}`);
          client.write(payload);
          client.end();
          resolve("Command sent as suggestion to the terminal (Socket).");
        });
      }
      client.on('error', (e) => {
        if (introspect) introspect(`[GhostShell DEBUG] Socket Error: ${e}`);
        reject(e);
      });
    });
  });
}

function randomSessionId() {
  return "sess_" + Math.random().toString(36).slice(2, 12);
}

module.exports.runtime = {
  handler: async function(args) {
    const introspect = typeof this.introspect === "function" ? this.introspect.bind(this) : () => {};
    introspect("[GhostShell DEBUG] Handler aufgerufen mit: " + JSON.stringify(args));
    let sessionId = args.sessionId || randomSessionId();
    let command = args.command;
    if (!command) {
      return await new Promise((resolve) => {
        startGuiIfNeeded(introspect, (err) => {
          if (err) resolve("GhostShell Terminal GUI NICHT gestartet! Fehler: " + err.message);
          else resolve("GhostShell Terminal GUI wurde definitiv gestartet. Du kannst jetzt Befehle senden oder das Fenster nutzen.");
        });
      });
    }
    try {
      const msg = await sendSuggestion(sessionId, command, introspect);
      introspect(`[GhostShell DEBUG] KI-Vorschlag wurde gesendet: "${command}"`);
      return msg + `\n(Vorschlag: "${command}")`;
    } catch (e) {
      introspect("[GhostShell DEBUG] Fehler bei Kommunikation mit GUI: " + (e.message || e));
      return "Error communicating with GhostShell GUI: " + (e.message || e);
    }
  }
};
