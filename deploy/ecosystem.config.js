module.exports = {
  apps: [
    {
      name: "ricevision",
      script: "server.py",
      args: "--port 11111",
      interpreter: "./venv/bin/python3.11",
      instances: 1,
      autorestart: true,
      restart_delay: 1000,
      kill_timeout: 3000,
      watch: false,
      max_memory_restart: "500M",
      env: {
        PYTHONUNBUFFERED: "1",
        PORT: "11111",
        FBARX_SIM: "0",
        FBARX_PORT: "socket://127.0.0.1:5020"
      }
    },
    {
      name: "fbarx-slave-sim",
      script: "modbus_slave_sim.py",
      args: "--port 5020",
      interpreter: "./venv/bin/python3.11",
      instances: 1,
      autorestart: true,
      restart_delay: 1000,
      kill_timeout: 3000,
      watch: false,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    }
  ]
};

