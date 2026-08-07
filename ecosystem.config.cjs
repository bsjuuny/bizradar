const fs = require('fs');
const path = require('path');

function resolvePythonInterpreter() {
  if (process.env.BIZRADAR_PYTHON) return process.env.BIZRADAR_PYTHON;

  const venvPython =
    process.platform === 'win32'
      ? path.join(__dirname, '.venv', 'Scripts', 'python.exe')
      : path.join(__dirname, '.venv', 'bin', 'python');

  if (fs.existsSync(venvPython)) return venvPython;

  return process.platform === 'win32' ? 'python' : 'python3';
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
