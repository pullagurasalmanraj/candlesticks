"""Run the read-only comparison without starting Flask, OAuth, or live feeds."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from psycopg2 import Error as DatabaseError
from routes.strategy_comparison import run_entry_geometry_comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    parser.add_argument("--holdout-from-date")
    parser.add_argument("--cost-model-file", type=Path, help="Optional JSON cost-model object; same fields as the API")
    parser.add_argument("--output", type=Path, help="Optional compact JSON artifact, never a database table")
    options = parser.parse_args()
    data = {key: value for key, value in vars(options).items()
            if key in ("from_date", "to_date", "holdout_from_date") and value is not None}
    try:
        if options.cost_model_file:
            data["cost_model"] = json.loads(options.cost_model_file.read_text(encoding="utf-8-sig"))
        result = run_entry_geometry_comparison(data)
    except DatabaseError:
        result = {"status": "DATABASE_UNAVAILABLE", "rows_written": 0}
    except (ValueError, OSError) as exc:
        result = {"status": "INVALID_REQUEST", "error": str(exc), "rows_written": 0}
    serialized = json.dumps(result, separators=(",", ":"), allow_nan=False)
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(serialized, encoding="utf-8")
        print(json.dumps({"status": result["status"], "output": str(options.output), "rows_written": 0}))
    else:
        print(serialized)
    return 0 if result["status"] == "SUCCESS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
