#!/usr/bin/env python3
"""
Standalone version of the Bifrost config patch described in
docs/deployment-vigil.md.

Applies the two changes required for a remote Ollama instance on a private
IP to work behind Bifrost's anti-SSRF filter and model allow-list:

  1. providers.ollama.keys[0].models = ["*"]
  2. providers.ollama.network_config.allow_private_network = True

Usage:
  python3 bifrost-patch.py [path to bifrost/config.json]
  (defaults to /opt/vigil/docker/bifrost/config.json)

After running this script, recreate the Bifrost container:
  docker compose up -d --force-recreate bifrost
"""

import json
import sys

DEFAULT_PATH = "/opt/vigil/docker/bifrost/config.json"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH

    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)

    ollama_key = cfg["providers"]["ollama"]["keys"][0]
    ollama_key["models"] = ["*"]

    network_config = cfg["providers"]["ollama"].setdefault("network_config", {})
    network_config["allow_private_network"] = True

    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    print(f"Patched {path}: models=['*'], allow_private_network=True")


if __name__ == "__main__":
    main()
