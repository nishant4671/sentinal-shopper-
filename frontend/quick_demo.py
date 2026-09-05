import requests, json
BASE = "http://localhost:8002"

print("\n" + "="*60)
print(" SENTINEL SHOPPER - LIVE DEMO")
print("="*60)

# 1. Success
print("\n[1] BUYING MOUSE (₹2,500 - Should PASS)")
r = requests.post(f"{BASE}/create_order", json={"product_id": "p1"})
print(f"Status: {r.status_code} | Response: {json.dumps(r.json(), indent=2)}")

# 2. Failure
print("\n[2] BUYING LAPTOP (₹12,500 - Should BLOCK)")
r = requests.post(f"{BASE}/create_order", json={"product_id": "p2"})
data = r.json()
print(f"Status: {r.status_code} | Response: {json.dumps(data, indent=2)}")
txn_id = data.get("txn_id")

# 3. Approval (if blocked)
if txn_id:
    print(f"\n[3] APPROVING TRANSACTION {txn_id} (Step-Up Token)")
    r = requests.post(f"{BASE}/approve/{txn_id}")
    print(f"Status: {r.status_code} | Response: {json.dumps(r.json(), indent=2)}")
else:
    print("\n[3] No transaction to approve.")

print("\n" + "="*60)
print(" DEMO COMPLETE. CHECK AUDIT TRAIL AT /audit")
print("="*60)