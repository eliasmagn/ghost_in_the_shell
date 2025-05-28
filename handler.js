const net = require('net');
const fs = require('fs');
const path = require('path');

const SOCKET_PATH = '/tmp/ki_shell.sock';

function startGuiIfNeeded(cb) {
  const base = __dirname;
  const pyPath = path.join(base, 'ki_shell_gui.py');
  if (!fs.existsSync(SOCKET_PATH)) {
    const { spawn } = require('child_process');
    spawn('python3', [pyPath], { detached: true, stdio: 'ignore' }).unref();
    setTimeout(cb, 1500);
  } else {
    cb();
  }
}

function sendSuggestion(session, command) {
  return new Promise((resolve, reject) => {
    startGuiIfNeeded(() => {
      const client = net.createConnection(SOCKET_PATH, () => {
        client.write(JSON.stringify({ session, command, type: "suggestion" }));
        client.end();
        resolve("Command was sent as suggestion to the terminal.");
      });
      client.on('error', (e) => {
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
    let sessionId = args.sessionId || randomSessionId();
    let command = args.command;
    if (!command) {
      await new Promise((res) => startGuiIfNeeded(res));
      return "GhostShell Terminal GUI started. You can now suggest KI commands or type directly.";
    }
    try {
      const msg = await sendSuggestion(sessionId, command);
      return msg + `\n(Suggestion: "${command}")`;
    } catch (e) {
      return "Error communicating with GhostShell GUI: " + (e.message || e);
    }
  }
};
