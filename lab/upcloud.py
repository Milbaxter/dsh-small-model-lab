"""Read-only UpCloud diagnostics. No resource creation or billing changes."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import urllib.error
import urllib.request

PLAN = "GPU-SPOT-8xCPU-64GB-1xL40S"


def read_token(path):
    """Read a dotenv assignment as data, without executing a shell or displaying it."""
    if os.environ.get("UPCLOUD_TOKEN"):
        return os.environ["UPCLOUD_TOKEN"]
    for line in Path(path).expanduser().read_text().splitlines():
        parts = shlex.split(line, comments=True)
        if parts and parts[0] == "export":
            parts = parts[1:]
        if len(parts) == 1 and parts[0].startswith("UPCLOUD_TOKEN="):
            value = parts[0].split("=", 1)[1]
            if value:
                return value
    raise ValueError("No non-empty UPCLOUD_TOKEN assignment found")


def get(token, route):
    request = urllib.request.Request("https://api.upcloud.com/1.3" + route,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"UpCloud {route}: HTTP {exc.code}") from None


def quota_blockers(account, plan):
    """Minimum per-server checks; passing is not approval or spare-capacity proof."""
    limits = account.get("resource_limits", {})
    required = {"gpus": plan["gpu_amount"], "cores": plan["core_number"],
                "memory": plan["memory_amount"]}
    return [{"resource": key, "limit": limits.get(key), "required_for_new_server": amount}
            for key, amount in required.items()
            if not isinstance(limits.get(key), (float, int)) or limits[key] < amount]


def inspect(token):
    account = get(token, "/account")["account"]
    plans = get(token, "/plan")["plans"]["plan"]
    plan = next(p for p in plans if p["name"] == PLAN)
    servers = get(token, "/server")["servers"]["server"]
    breakdown = account.get("credits_breakdown", {})
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "plan": PLAN, "zone": "fi-hel2",
        "plan_resources": {k: plan[k] for k in ("gpu_amount", "core_number", "memory_amount")},
        "account_limits": {k: account.get("resource_limits", {}).get(k)
                           for k in ("gpus", "cores", "memory", "public_ipv4")},
        "minimum_quota_blockers": quota_blockers(account, plan),
        "existing_server_count": len(servers),
        "has_paid_balance": breakdown.get("account_credits", {}).get("paid_credits", 0) > 0,
        "promotion_expiry": [x.get("free_credits_expire") for x in
            breakdown.get("account_free_credits", {}).get("breakdown", [])],
        "note": "Read-only check. Existing resource usage, regional capacity and GPU billing eligibility still need confirmation.",
        "policy": "https://upcloud.com/docs/products/gpu-servers/availability/",
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", default="~/.config/upcloud-agent/credentials.env")
    args = parser.parse_args()
    report = inspect(read_token(args.credentials))
    print(json.dumps(report, indent=2))
    raise SystemExit(2 if report["minimum_quota_blockers"] else 0)


if __name__ == "__main__":
    main()
