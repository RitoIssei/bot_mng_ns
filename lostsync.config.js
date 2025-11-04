module.exports = {
  apps: [
    {
      name: "sync_lost",
      script: "venv\\Scripts\\pythonw.exe",
      args: "sync_data_lost.py",
      interpreter: "none", // vì script là file Python đã được chỉ rõ interpreter
      exec_mode: "fork",
      autorestart: true,
      watch: false,
    },
  ],
};
