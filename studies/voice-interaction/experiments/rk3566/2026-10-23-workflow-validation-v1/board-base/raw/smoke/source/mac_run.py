"""Mac llama-server lifecycle and complete-context preflight.

Run on target: python -m tools.qwen_lifecycle.mac_run REQUEST OUTPUT.
Request adds server.binary and server.argv, without model/host/port.
"""

from .server_lifecycle import execute as execute_server
from .server_lifecycle import launcher_handoff  # noqa: F401
from .server_lifecycle import main as launcher_main


def execute(request, output):
    return execute_server(request, output, ("otool", ["otool", "-L"]))


def main():
    launcher_main(execute, __doc__)


if __name__ == "__main__":
    main()
