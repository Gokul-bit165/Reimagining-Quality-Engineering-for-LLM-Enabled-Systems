from sandbox_apps._common.http_server import run_cli
from sandbox_apps.multiagent import build_app

if __name__ == "__main__":
    run_cli("multiagent", build_app)
