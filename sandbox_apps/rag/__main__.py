from sandbox_apps._common.http_server import run_cli
from sandbox_apps.rag import build_app

if __name__ == "__main__":
    run_cli("rag", build_app)
