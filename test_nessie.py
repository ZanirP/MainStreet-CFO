"""Real-API smoke checks: read-only unless --create is explicitly supplied."""

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from backend.services.nessie_service import NessieService, NessieServiceError


def report(label, result):
    count = f" ({len(result)} items)" if isinstance(result, list) else ""
    print(f"PASS: {label} returned JSON{count}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--customer-id")
    parser.add_argument("--account-id")
    parser.add_argument("--create", choices=["customer", "account", "purchase", "deposit", "bill"])
    parser.add_argument("--payload", type=Path, help="JSON body file for one POST request")
    args = parser.parse_args()
    if args.create:
        if not args.payload:
            parser.error("--create requires --payload")
        if args.create == "account" and not args.customer_id:
            parser.error("Creating an account requires --customer-id")
        if args.create in ("purchase", "deposit", "bill") and not args.account_id:
            parser.error("Creating this resource requires --account-id")
    elif args.payload:
        parser.error("--payload requires --create")

    load_dotenv(Path(__file__).with_name(".env"))
    try:
        service = NessieService()
        if args.create:
            payload = json.loads(args.payload.read_text())
            if not isinstance(payload, dict):
                raise ValueError
            method = getattr(service, f"create_{args.create}")
            if args.create == "customer":
                result = method(payload)
            else:
                resource_id = args.customer_id if args.create == "account" else args.account_id
                result = method(resource_id, payload)
            report(f"create_{args.create}", result)
            return 0
        report("get_customers", service.get_customers())
        if args.customer_id:
            report("get_customer", service.get_customer(args.customer_id))
            report("get_customer_accounts", service.get_customer_accounts(args.customer_id))
        if args.account_id:
            for name in ("get_account", "get_purchases", "get_deposits", "get_bills"):
                report(name, getattr(service, name)(args.account_id))
    except NessieServiceError as exc:
        print(f"FAIL: {exc}")
        return 1
    except (ValueError, OSError):
        print("FAIL: check NESSIE_API_KEY and that the payload file contains a JSON object")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
