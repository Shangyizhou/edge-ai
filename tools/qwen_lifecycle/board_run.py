"""Isolated local llama-server lifecycle; never invokes device handlers.

Run on target: python -m tools.qwen_lifecycle.board_run REQUEST OUTPUT.
Request adds server.binary and server.argv, without model/host/port.
"""

from .server_lifecycle import execute as execute_server
from .server_lifecycle import launcher_handoff  # noqa: F401
from .server_lifecycle import main as launcher_main


def execute(request, output):
    return execute_server(request, output, ("ldd", ["ldd"]))


def main():
    launcher_main(execute, __doc__)


if __name__ == "__main__":
    main()
