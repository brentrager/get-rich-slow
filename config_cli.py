"""CLI to view and update scanner config stored in SQLite.

Usage:
    python config_cli.py                     # show all config
    python config_cli.py set KEY VALUE       # set a config value
    python config_cli.py set min_yes_price 88
    python config_cli.py set max_bet_cents 2000
    python config_cli.py set max_positions 20
    python config_cli.py set min_volume 50
    python config_cli.py set stretch_price_min 85
    python config_cli.py set lead:basketball/nba 8
    python config_cli.py set lead:hockey/nhl 2
    python config_cli.py set final_seconds:soccer/eng.1 4800
    python config_cli.py delete KEY          # remove override (revert to default)
"""

import sys

from dotenv import load_dotenv

load_dotenv()

from db import ConfigEntry, get_all_config, get_session, init_db, set_config


def show_config():
    cfg = get_all_config()

    # Group into categories
    trading = {}
    leads = {}
    finals = {}
    other = {}

    for k, v in sorted(cfg.items()):
        if k.startswith("lead:"):
            leads[k.removeprefix("lead:")] = v
        elif k.startswith("final_seconds:"):
            finals[k.removeprefix("final_seconds:")] = v
        elif k in (
            "min_yes_price", "max_bet_cents", "max_positions",
            "min_volume", "stretch_price_min",
        ):
            trading[k] = v
        else:
            other[k] = v

    print("\n=== Trading Parameters ===")
    for k, v in sorted(trading.items()):
        print(f"  {k:25s} = {v}")

    print("\n=== Min Score Lead by Sport ===")
    for sport, lead in sorted(leads.items()):
        print(f"  {sport:40s} = {lead}")

    print("\n=== Final Minutes (seconds) by Sport ===")
    for sport, secs in sorted(finals.items()):
        s = int(secs)
        if s >= 60:
            desc = f"{s}s ({s // 60}m)"
        else:
            desc = f"{s}s"
        print(f"  {sport:40s} = {desc}")

    if other:
        print("\n=== Other ===")
        for k, v in sorted(other.items()):
            print(f"  {k:25s} = {v}")

    print()


def set_value(key: str, value: str):
    set_config(key, value)
    print(f"Set {key} = {value}")


def delete_key(key: str):
    session = get_session()
    entry = session.query(ConfigEntry).filter_by(key=key).first()
    if entry:
        session.delete(entry)
        session.commit()
        print(f"Deleted {key} (will use default)")
    else:
        print(f"{key} not in DB (already using default)")
    session.close()


if __name__ == "__main__":
    init_db()

    if len(sys.argv) == 1:
        show_config()
    elif sys.argv[1] == "set" and len(sys.argv) == 4:
        set_value(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "delete" and len(sys.argv) == 3:
        delete_key(sys.argv[2])
    else:
        print(__doc__)
