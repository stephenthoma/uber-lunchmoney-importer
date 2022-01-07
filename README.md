# uber-lunchmoney-importer
A tool to import Uber transaction metadata into [Lunch Money](https://lunchmoney.app/)

This tool attempts to match Lunch Money transactions with a Payee of 'Uber*' to Uber and Uber Eats transactions. 
Transaction metadata is added to the Lunch Money notes field.
Uber rides have the trip destination added, and Uber Eats orders have the restaurant name and order items added.

## Matching methodology
The tool matches Lunch Money transactions to Uber transactions by referencing cost and date.
Exact matches are not required -- a transaction is considered a match if the cost is within $0.05 and date is within 2 days.

If multiple potential matches are found, the transaction with the closest cost, then date will be used.

## Usage
To use this tool you must [request a copy of your Uber data](https://myprivacy.uber.com/privacy/exploreyourdata/download). 
You will also need to put a Lunch Money API token into the file `.lunch_money_token`

Run the tool via `python uber.py <PATH_TO_DATA>.zip`

## Limitations
The Uber data download does not currently include tip data. Transactions that include tips will not be matched :sob:
