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

function debugOut(ctx, msg) {
  if (ctx && typeof ctx.introspect === "function") ctx.introspect(`[GhostShell DEBUG] ${msg}`);
  console.log(`[GhostShell DEBUG] ${msg}`);
}

function startGuiIfNeeded(ctx, cb) {
  if (isWin) {
    const test = net.createConnection({ host: SOCKET_HOST, port: SOCKET_PORT }, () => {
      test.end();
      debugOut(ctx, "KI-Shell-GUI ist bereits gestartet (TCP-Verbindung ok)");
      cb();
    });
    test.on('error', (err) => {
      debugOut(ctx, "KI-Shell-GUI nicht erreichbar, wird jetzt gestartet...");
      const gui = findGuiBinary();
      if (!gui) {
        debugOut(ctx, "KI-Shell-GUI Backend nicht gefunden!");
        throw new Error(
          "KI-Shell-GUI Backend nicht gefunden!\n" +
          "Bitte stelle sicher, dass ki_shell_gui.py im Skill-Verzeichnis liegt\n" +
          "und vorher mit 'pip install -r requirements.txt' (im venv!) installiert wurde."
        );
      }
      debugOut(ctx, `Starte Backend mit: ${gui.cmd} ${gui.args.join(" ")}`);
      spawn(gui.cmd, gui.args, { detached: true, stdio: 'ignore' }).unref();
      setTimeout(() => {
        debugOut(ctx, "2 Sekunden gewartet, GUI sollte jetzt bereit sein.");
        cb();
      }, 2000);
    });
    test.setTimeout(1000, () => test.destroy());
  } else {
    if (fs.existsSync(SOCKET_PATH)) {
      debugOut(ctx, "KI-Shell-GUI ist bereits gestartet (Unix-Socket gefunden)");
      return cb();
    }
    debugOut(ctx, "KI-Shell-GUI nicht erreichbar, wird jetzt gestartet...");
    const gui = findGuiBinary();
    if (!gui) {
      debugOut(ctx, "KI-Shell-GUI Backend nicht gefunden!");
      throw new Error(
        "KI-Shell-GUI Backend nicht gefunden!\n" +
        "Bitte stelle sicher, dass ki_shell_gui.py im Skill-Verzeichnis liegt\n" +
        "und vorher mit 'pip install -r requirements.txt' (im venv!) installiert wurde."
      );
    }
    debugOut(ctx, `Starte Backend mit: ${gui.cmd} ${gui.args.join(" ")}`);
    spawn(gui.cmd, gui.args, { detached: true, stdio: 'ignore' }).unref();
    setTimeout(() => {
      debugOut(ctx, "2 Sekunden gewartet, GUI sollte jetzt bereit sein.");
      cb();
    }, 2000);
  }
}

function sendSkillRequest(ctx, session, command) {
  debugOut(ctx, `sendSkillRequest für session=${session}, command=${command}`);
  return new Promise((resolve, reject) => {
    startGuiIfNeeded(ctx, () => {
      let client, data = "";
      debugOut(ctx, "Verbinde mit GUI-Socket...");
      if (isWin) {
        client = net.createConnection({ host: SOCKET_HOST, port: SOCKET_PORT }, () => {
          debugOut(ctx, "Verbindung (TCP) hergestellt, sende Anfrage.");
          client.write(JSON.stringify({ session, command, type: "request" }) + "\n");
        });
      } else {
        client = net.createConnection(SOCKET_PATH, () => {
          debugOut(ctx, "Verbindung (Unix-Socket) hergestellt, sende Anfrage.");
          client.write(JSON.stringify({ session, command, type: "request" }) + "\n");
        });
      }
      client.on('data', chunk => { data += chunk.toString(); });
      client.on('end', () => {
        debugOut(ctx, `Antwort erhalten: ${data}`);
        try {
          const response = JSON.parse(data);
          resolve(response);
        } catch (e) {
          debugOut(ctx, `Fehler beim Parsen der Antwort: ${e}`);
          reject(e);
        }
      });
      client.on('error', (err) => {
        debugOut(ctx, `Fehler beim Socket: ${err.message}`);
        reject(err);
      });
    });
  });
}

function randomSessionId() {
  return "sess_" + Math.random().toString(36).slice(2, 12);
}

module.exports.runtime = {
  handler: async function(args) {
    const ctx = this;
    debugOut(ctx, `Handler aufgerufen mit: ${JSON.stringify(args)}`);

    // GUI immer starten, auch ohne command!
    return await new Promise((resolve) => {
      startGuiIfNeeded(ctx, () => {
        if (!args.command) {
          debugOut(ctx, "GUI wurde (ggf. erneut) gestartet, kein Kommando empfangen.");
          resolve(
            "GhostShell Terminal GUI wurde gestartet.\n" +
            "Du kannst jetzt Befehle senden oder die Session im Fenster konfigurieren."
          );
        } else {
          let sessionId = args.sessionId || randomSessionId();
          let command = args.command;
          sendSkillRequest(ctx, sessionId, command)
            .then(result => {
              debugOut(ctx, `Antwort vom GUI: ${JSON.stringify(result)}`);
              if (result.status === "approved") {
                resolve(`[Terminal Output]\n${result.output}`);
              } else if (result.status === "rejected") {
                resolve("Der Befehl wurde vom Nutzer abgelehnt.");
              } else {
                resolve("Unerwartete Antwort vom Shell-GUI.");
              }
            })
            .catch(e => {
              debugOut(ctx, "Fehler bei Kommunikation mit GUI: " + (e.message || e));
              resolve("Fehler bei Kommunikation mit dem lokalen KI-Shell-GUI: " + (e.message || e));
            });
        }
      });
    });
  }
};
