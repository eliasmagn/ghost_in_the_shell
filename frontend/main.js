import { Terminal } from 'xterm';
import 'xterm/css/xterm.css';

const term = new Terminal({
  theme: { background: "#181c1f", foreground: "#e3e8ee", cursor: "#81f7c0" },
  fontFamily: "Fira Mono, Consolas, monospace",
  fontSize: 16
});
term.open(document.getElementById('terminal'));

// Connect to backend websocket
let ws = new WebSocket("ws://127.0.0.1:8765");
ws.onmessage = ev => term.write(ev.data);
term.onData(data => ws.send(data));

// KI Suggestion bar API for host window
window.setKICmd = function(cmd) {
  document.getElementById("ki-cmd").textContent = cmd;
  document.getElementById("ki-bar").classList.add("active");
  window._pendingKiCmd = cmd;
};
window.clearKICmd = function() {
  document.getElementById("ki-bar").classList.remove("active");
  window._pendingKiCmd = "";
};

document.getElementById("approve").onclick = function() {
  if (window._pendingKiCmd) term.write(window._pendingKiCmd + "\r");
  window.clearKICmd();
};
document.getElementById("reject").onclick = function() {
  window.clearKICmd();
};
