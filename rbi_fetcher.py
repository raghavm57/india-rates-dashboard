import re
from datetime import datetime
from zoneinfo import ZoneInfo
from io import StringIO

import pandas as pd
import requests
from bs4 import BeautifulSoup


RBI_PRESS_RELEASES = (
    "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def _number(value):
    """Convert RBI formatted numbers such as 1,47,625.00 to float."""
    if value is None:
        return None

    text = str(value).replace(",", "").replace("₹", "").strip()

    if text in ("", "-", "–", "—", "nan", "NaN"):
        return None

    try:
        return float(text)
    except Exception:
        return None


def _get_release_links():
    """Get recent RBI press-release links."""
    response = requests.get(
        RBI_PRESS_RELEASES,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    results = []

    for link in soup.find_all("a"):
        title = " ".join(link.get_text(" ", strip=True).split())

        if "Money Market Operations as on" in title:
            href = link.get("href")

            if not href:
                continue

            if href.startswith("/"):
                href = "https://www.rbi.org.in" + href
            elif not href.startswith("http"):
                href = "https://www.rbi.org.in/" + href.lstrip("/")

            results.append((title, href))
           
            print("MMO FOUND:")
            print("TITLE:", title)
            print("URL:", href)

    return results


def _parse_mmo_release(url):
    """Parse one RBI Money Market Operations release."""

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    tables = pd.read_html(StringIO(response.text))

    observations = []

    # ---------------------------------------------------------
    # Search every table for the RBI operations rows
    # ---------------------------------------------------------

    for table in tables:

        for _, row in table.iterrows():

            values = [str(x).strip() for x in row.tolist()]
            text = " | ".join(values)

            lower = text.lower()

            metric = None

            if "net liquidity injected (outstanding including today's operations)" in lower:
                metric = "NET_LIQUIDITY_OUTSTANDING"

            elif "net liquidity injected from today's operations" in lower:
                metric = "NET_LIQUIDITY_TODAY"

            elif re.search(r"\bVRRR\b", text, re.IGNORECASE):
                metric = "VRRR"

            elif "reverse repo operation" in lower:
                metric = "REVERSE_REPO"

            elif re.search(r"\brepo operation\b", lower):
                metric = "REPO"

            elif re.search(r"\bMSF\b", text):
                metric = "MSF"

            elif re.search(r"\bSDF\b", text):
                metric = "SDF"

            elif re.search(r"\bSLF\b", text):
                metric = "SLF"

            if metric is None:
                continue

            numbers = []

            for value in values:
                number = _number(value)

                if number is not None:
                    numbers.append(number)

            if not numbers:
                continue

            # RBI rows generally have Amount as the last useful number.
            amount = numbers[0]

            observations.append(
                {
                    "metric": metric,
                    "value": amount,
                }
            )

    # Remove duplicate metrics while preserving first occurrence.
    final = {}

    for item in observations:
        if item["metric"] not in final:
            final[item["metric"]] = item["value"]

    return final


def fetch_rbi_mmo():
    """
    Fetch latest RBI Money Market Operations release.

    Returns:
        {
            "publication_title": ...,
            "source_url": ...,
            "data": {...}
        }
    """

    links = _get_release_links()

    if not links:
        raise RuntimeError(
            "No RBI Money Market Operations release found."
        )

    # RBI listing is normally newest first.
    title, url = links[0]

    print(f"RBI MMO release found: {title}")
    print(f"RBI MMO URL: {url}")

    data = _parse_mmo_release(url)

    if not data:
        raise RuntimeError(
            "RBI MMO release found but no liquidity data could be parsed."
        )

    return {
        "publication_title": title,
        "source_url": url,
        "data": data,
    }


if __name__ == "__main__":

    result = fetch_rbi_mmo()

    print("\nRBI MMO DATA")
    print("==============================")

    for key, value in result["data"].items():
        print(f"{key}: {value}")
