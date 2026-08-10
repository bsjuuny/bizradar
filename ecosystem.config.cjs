const fs = require('fs');
const path = require('path');

function resolvePythonInterpreter() {
  if (process.env.BIZRADAR_PYTHON) return process.env.BIZRADAR_PYTHON;

  // pythonw.exe (not python.exe) on Windows - the windowless build. python.exe is a
  // console-subsystem executable, and Windows 11's "default terminal" feature auto-opens
  // a visible Windows Terminal window to host its console even with pm2's
  // windowsHide:true, since that option doesn't reliably apply through pm2's
  // interpreter-based spawn path. pythonw.exe never allocates a console in the first
  // place, so there's nothing to auto-host - and pm2 still captures stdout/stderr into
  // its own logs via pipe redirection either way.
  const venvPython =
    process.platform === 'win32'
      ? path.join(__dirname, '.venv', 'Scripts', 'pythonw.exe')
      : path.join(__dirname, '.venv', 'bin', 'python');

  if (fs.existsSync(venvPython)) return venvPython;

  return process.platform === 'win32' ? 'pythonw' : 'python3';
}

module.exports = {
  apps: [
    {
      name: 'bizradar-worker',
      script: 'worker/scheduler/main.py',
      interpreter: resolvePythonInterpreter(),
      cwd: __dirname,
      autorestart: true,
      watch: false,
      windowsHide: true,
      env_file: '.env.worker',
    },
  ],
};
