import datetime
import csv
import sys
from pathlib import Path
from zipfile import ZipFile
from pprint import pprint


import requests
from dateutil import parser

LM_HEADERS = {"Authorization": f"Bearer {Path('.lunch_money_token').read_text().strip()}"}
LM_URL = "https://dev.lunchmoney.app/v1"
LM_UBER_CATEGORY = "Ridesharing"
LM_EATS_CATEGORY = "Food Delivery"


def extract_zip(zip_path: Path) -> dict:
    """Read zip contents into memory, create a dict mapping file name to zip contents"""
    input_zip: ZipFile = ZipFile(file=zip_path)
    return {name: input_zip.read(name).decode("utf-8") for name in input_zip.namelist()}


def get_restaurant_map(zip: dict) -> dict:
    """Pull a mapping of restaurant id to restaurant name from the zip"""
    path = "Uber Data/Eats/eats_restaurant_names.csv"
    reader = csv.reader(zip[path].splitlines())
    return {r[1]: r[2] for r in reader}


def get_uber_transactions(zip: dict) -> list:
    path = "Uber Data/Rider/trips_data.csv"
    reader = csv.reader(zip[path].splitlines())
    next(reader)  # Skip header

    transactions = []
    for transaction in reader:
        product_type = transaction[1]
        if product_type != "UberEATS Marketplace":
            transactions.append(
                {
                    "product_type": transaction[1],
                    "date": parser.parse(transaction[3][0:-10]),
                    "dropoff_address": transaction[11],
                    "amount": float(transaction[13]),
                }
            )

    return transactions


def get_eats_transactions(zip: dict) -> list:
    restaurants = get_restaurant_map(zip)
    path = "Uber Data/Eats/eats_order_details.csv"
    reader = csv.reader(zip[path].splitlines())
    next(reader)  # Skip header

    transactions = {}
    for transaction in reader:
        transaction_id = transaction[2]
        # If an order has multiple items, each item will be a row
        if transaction_id in transactions:
            transactions[transaction_id]["items"].append(transaction[5])
        else:
            cost = transaction[9]
            if cost == "" or cost == "0.0":
                continue

            transactions[transaction_id] = {
                "restaurant_name": restaurants.get(transaction[1], "No name"),
                "id": transaction[2],
                "date": parser.parse(transaction[3][0:-10]),
                "items": [transaction[5]],
                "amount": float(cost),
            }

    return list(transactions.values())


def get_lunchmoney_categories() -> dict:
    categories = requests.get(f"{LM_URL}/categories", headers=LM_HEADERS).json()["categories"]
    return {c["name"]: c["id"] for c in categories}


def update_lunchmoney_transaction(transaction_id: int, updated_fields: dict):
    res = requests.put(
        f"{LM_URL}/transactions/{transaction_id}",
        headers=LM_HEADERS,
        json={"transaction": updated_fields},
    )
    print(res.request.body)


def get_lm_uber_transactions(start_date, end_date) -> list:
    """Get lunch money transactions within date range returning only transactions with uber payee"""
    payload = {"start_date": start_date, "end_date": end_date}

    res = requests.get(f"{LM_URL}/transactions", params=payload, headers=LM_HEADERS)
    transactions = res.json()["transactions"]

    return [t for t in transactions if "UBER" in t["payee"].upper()]


def is_matching_transaction(lm_txn: dict, uber_txn: dict) -> bool:
    if abs(float(lm_txn["amount"]) - uber_txn["amount"]) > 0.05:
        return False

    lm_date = parser.parse(lm_txn["date"])
    if abs(lm_date - uber_txn["date"]) > datetime.timedelta(days=2):
        return False

    return True


def get_matching_transactions(lm_txn: dict, uber_txns: list) -> list:
    """Search through all uber transactions to find ones that match lm_txn"""
    return [t for t in uber_txns if is_matching_transaction(lm_txn, t)]


def get_best_match(lm_txn, transactions: list) -> dict:
    """When multiple matches were found, return the one that is closest"""
    lm_date = parser.parse(lm_txn["date"])
    cost_diffs = [(t, abs(float(lm_txn["amount"]) - t["amount"])) for t in transactions]

    # prioritize choosing exact cost matches
    exact_matches = [d for d in cost_diffs if d[1] == 0.0]
    if len(exact_matches) == 1:
        return exact_matches[0][0]
    elif len(exact_matches) > 1:
        # with multiple exact matches, get the one with closest date
        date_diffs = [(d[0], abs(lm_date - d[0]["date"])) for d in exact_matches]
        return sorted(date_diffs, key=lambda d: d[1], reverse=True)[0][0]
    else:  # no exact matches, choose closest date
        date_diffs = [(t, abs(lm_date - t["date"])) for t in transactions]
        return sorted(date_diffs, key=lambda d: d[1], reverse=True)[0][0]


def lm_eats_note(eats_txn: dict) -> str:
    return f"{eats_txn['restaurant_name']}: {', '.join(eats_txn['items'])}"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Must pass path to uber data zip as only arg")
        exit(1)

    uber_zip = extract_zip(Path(sys.argv[1]))

    start_date = str(datetime.datetime.fromisoformat("2020-12-12"))
    end_date = str(datetime.datetime.now().date().isoformat())

    lm_txns = get_lm_uber_transactions(start_date, end_date)
    lm_categories = get_lunchmoney_categories()

    for lm_txn in lm_txns:
        uber_txns = get_matching_transactions(lm_txn, get_uber_transactions(uber_zip))
        if len(uber_txns) == 1:
            update_lunchmoney_transaction(
                lm_txn["id"],
                {
                    "notes": uber_txns[0]["dropoff_address"],
                },
            )
            continue

        eats_txns = get_matching_transactions(lm_txn, get_eats_transactions(uber_zip))
        if len(eats_txns) == 1:
            update_lunchmoney_transaction(lm_txn["id"], {"notes": lm_eats_note(eats_txns[0])})
        elif len(eats_txns) > 1:
            eats_txn = get_best_match(lm_txn, eats_txns)
            update_lunchmoney_transaction(lm_txn["id"], {"notes": lm_eats_note(eats_txn)})
