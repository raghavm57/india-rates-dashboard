def save_ndsom(reference_date):

    print("\nStarting NDS-OM browser fetch...")

    try:
        data = fetch_ndsom_data()
    except Exception as e:
        print(f"NDS-OM fetch failed: {e}")
        return

    gsecs = data.get("gsecs", [])
    tbills = data.get("tbills", [])

    print(f"NDS-OM G-Secs received: {len(gsecs)}")
    print(f"NDS-OM T-Bills received: {len(tbills)}")

    # ============================================================
    # G-SECS
    # ============================================================

    gsec_saved = 0

    for row in gsecs:

        tenor = row.get("tenor")
        security = row.get("security_description")
        maturity = row.get("maturity_date")
        lty = row.get("lty")
        ltp = row.get("ltp")

        if not tenor:
            continue

        if tenor not in ["2Y", "5Y", "10Y"]:
            continue

        if not security:
            continue

        if lty is None:
            continue

        print(
            f"NDS-OM G-Sec {tenor}: "
            f"{security} | {maturity} | LTY {lty}"
        )

        save_observation(
            observation_date=reference_date,
            source="NDS-OM",
            series="GSEC",
            tenor=tenor,
            value=lty,
            unit="percent",
            publication_time=None,
            source_url="https://www.ccilindia.com/market-watch",
            status="success",
            security_description=security,
            maturity_date=maturity,
            ltp=ltp,
        )

        gsec_saved += 1

    # ============================================================
    # T-BILLS
    # ============================================================

    tbill_saved = 0

    for row in tbills:

        tenor = row.get("tenor")
        security = row.get("security_description")
        maturity = row.get("maturity_date")
        lty = row.get("lty")
        ltp = row.get("ltp")

        if not tenor:
            continue

        if tenor not in ["91D", "182D", "364D"]:
            continue

        if not security:
            continue

        if lty is None:
            continue

        print(
            f"NDS-OM T-Bill {tenor}: "
            f"{security} | {maturity} | LTY {lty}"
        )

        save_observation(
            observation_date=reference_date,
            source="NDS-OM",
            series="TBILL",
            tenor=tenor,
            value=lty,
            unit="percent",
            publication_time=None,
            source_url="https://www.ccilindia.com/market-watch",
            status="success",
            security_description=security,
            maturity_date=maturity,
            ltp=ltp,
        )

        tbill_saved += 1

    print(f"NDS-OM G-Secs saved: {gsec_saved}")
    print(f"NDS-OM T-Bills saved: {tbill_saved}")
