#!/usr/bin/env python3
"""Keep active Herdr agents above inactive agents, then sort by recency."""

import json
import os
import socket
import sys


STATUS_RANK = {"blocked": "3", "working": "2", "done": "1", "idle": "1", "unknown": "0"}


def call(socket_path: str, method: str, params: dict) -> dict:
    request = {"id": method, "method": method, "params": params}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(5)
        client.connect(socket_path)
        client.sendall((json.dumps(request) + "\n").encode())
        with client.makefile("r", encoding="utf-8") as reader:
            response = reader.readline()
    if not response:
        raise RuntimeError(f"Herdr closed the socket during {method}")
    result = json.loads(response)
    if "error" in result or "result" not in result:
        raise RuntimeError(f"Herdr rejected {method}: {result}")
    return result["result"]


def main() -> None:
    socket_path = os.environ["HERDR_SOCKET_PATH"]
    plugin_id = os.environ["HERDR_PLUGIN_ID"]

    agents = call(socket_path, "agent.list", {})["agents"]
    for agent in agents:
        call(
            socket_path,
            "pane.report_metadata",
            {
                "pane_id": agent["pane_id"],
                "source": f"plugin:{plugin_id}",
                "seq": agent["state_change_seq"],
                "tokens": {"activity_rank": STATUS_RANK[agent["agent_status"]]},
            },
        )
    view = call(
        socket_path,
        "agent.view.set",
        {
            "source": f"plugin:{plugin_id}",
            "label": "Ativos e recentes",
            "sort": [
                {"field": {"token": "activity_rank"}, "order": "desc"},
                {"field": "state_change_seq", "order": "desc"},
            ],
        },
    )

    if view.get("active") is not True:
        raise RuntimeError(f"Herdr did not activate the Agent view: {view}")
    print(f"{len(agents)} agentes ordenados por atividade e recência.")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, OSError, ValueError, RuntimeError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
