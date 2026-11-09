"""Command-line entry point: `mm-sim <command>`.

Commands
  check-config [--scenario X]   validate config.yaml (+ scenario) and print it with its hash
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from mm_sim import __version__
from mm_sim.config import DEFAULT_CONFIG_PATH, Config, available_scenarios, load_config
from mm_sim.logging_setup import setup_logging
from mm_sim.runinfo import RunInfo, new_run_info


def _start(args: argparse.Namespace) -> tuple[Config, RunInfo]:
    cfg, chash = load_config(args.config, args.scenario)
    info = new_run_info(chash, cfg.scenario.name)
    log = setup_logging(cfg.logging, cfg.paths.logs, info.run_id)
    log.info("run start command=%s %s", args.command, json.dumps(info.as_dict()))
    return cfg, info


def cmd_check_config(args: argparse.Namespace) -> int:
    cfg, info = _start(args)
    print(yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False), end="")
    print("---")
    print(f"config OK   scenario={cfg.scenario.name}   horizon T={cfg.market.horizon:g}")
    print(f"config_hash {info.config_hash}")
    print(f"run_id      {info.run_id}")
    print(f"git_commit  {info.git_commit}{' (dirty)' if info.git_dirty else ''}")
    print(f"scenarios   {', '.join(available_scenarios(args.config))}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mm-sim", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"mm-sim {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
        p.add_argument("--scenario", default=None, help="name of a file in scenarios/")

    p_check = sub.add_parser("check-config", help="validate the config and print it")
    add_common(p_check)
    p_check.set_defaults(func=cmd_check_config)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code: int = args.func(args)
    except (ValidationError, ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return code


if __name__ == "__main__":
    sys.exit(main())
