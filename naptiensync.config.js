module.exports = {
  apps: [
    {
      name: "sync_naptien",
      script: "venv\\Scripts\\pythonw.exe",
      args: "sync_naptien_hold.py",
      interpreter: "none", // vì script là file Python đã được chỉ rõ interpreter
      exec_mode: "fork",
      autorestart: true,
      watch: false,
    },
  ],
};
