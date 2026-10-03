S2_REF = "627401221499"  # City Mobiles


def test_paytm_records(client):
    txns = client.get("/mock/paytm/transactions").json()["transactions"]
    assert any(t["id"] == "txn_s2_citymobiles" for t in txns)


def test_evidence_endpoints(client):
    assert client.get(f"/mock/npci/status?upi_ref={S2_REF}").json()["status"] == "FAILED"
    ledger = client.get(f"/mock/bank/ledger?upi_ref={S2_REF}").json()
    assert ledger["state"] == "DEBITED" and ledger["amount_paise"] == 149900
    assert client.get(f"/mock/merchant/credit?upi_ref={S2_REF}").json()["credited"] is False
    assert client.get("/mock/npci/status?upi_ref=nope").json()["available"] is False


def test_clock_skip(client):
    before = client.get("/mock/clock").json()["offset_seconds"]
    r = client.post("/mock/clock", json={"advance_days": 2})
    assert r.json()["offset_seconds"] == before + 2 * 86400
    assert client.post("/mock/clock", json={"advance_days": -1}).status_code == 400
    assert client.post("/mock/clock", json={"reset": True}).json()["offset_seconds"] == 0


def test_inject_reversal(client):
    r = client.post("/mock/inject", json={"txn_id": "txn_s2_citymobiles", "ledger": {"state": "REVERSED"}})
    assert r.status_code == 200
    assert r.json()["ledger"]["state"] == "REVERSED" and r.json()["ledger"]["reversed_at"]
    assert client.get(f"/mock/bank/ledger?upi_ref={S2_REF}").json()["state"] == "REVERSED"


def test_inject_requires_reference(client):
    assert client.post("/mock/inject", json={"ledger": {"state": "DEBITED"}}).status_code == 422


def test_udir_dispute(client):
    r = client.post("/mock/npci/udir/dispute", json={"upi_ref": S2_REF, "kind": "DEBIT_NO_CREDIT", "amount_paise": 149900})
    assert r.json()["ref"].startswith("UDIR")
    assert client.get("/mock/npci/udir/disputes").json()["disputes"][0]["upi_ref"] == S2_REF
