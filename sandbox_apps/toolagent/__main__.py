from sandbox_apps._common.http_server import run_cli
from sandbox_apps.toolagent import build_app

if __name__ == "__main__":
    run_cli("toolagent", build_app)
