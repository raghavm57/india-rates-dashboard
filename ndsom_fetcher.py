
print("STARTING NDS-OM TEST")

import requests
import pandas as pd
from io import StringIO

URL = "https://www.ccilindia.com/market-watch"

headers = {
    "User-Agent": "Mozilla/5.0"
}

print("Requesting CCIL...")

response = requests.get(
    URL,
    headers=headers,
    timeout=30
)

print("HTTP STATUS:", response.status_code)
print("CONTENT TYPE:", response.headers.get("Content-Type"))
print("RESPONSE LENGTH:", len(response.text))

tables = pd.read_html(
    StringIO(response.text)
)

print("TABLES FOUND:", len(tables))

for i, table in enumerate(tables):

    print("\n====================")
    print("TABLE:", i)
    print("====================")

    print(table.head(5).to_string())

print("\nNDS-OM TEST FINISHED")
