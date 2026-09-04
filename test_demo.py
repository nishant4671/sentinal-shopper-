import requests
import time
from rich.console import Console

console = Console()
BASE_URL = "http://127.0.0.1:8002"

def run_tests():
    passed = 0
    failed = 0
    txn_id_blocked = None

    def assert_true(condition, msg):
        if not condition:
            raise AssertionError(msg)

    try:
        # Test 1
        console.print("[cyan]Running Test 1: Health Check...[/cyan]")
        r = requests.get(f"{BASE_URL}/health")
        assert_true(r.status_code == 200, f"Status code {r.status_code}")
        assert_true(r.json()["status"] == "ok", "Status not ok")
        console.print("[green]PASS Test[/green]\n")
        passed += 1

        # Test 2
        console.print("[cyan]Running Test 2: Success Scenario (p1 - 2500)...[/cyan]")
        r = requests.post(f"{BASE_URL}/create_order", json={"product_id": "p1"})
        assert_true(r.status_code == 200, f"Status code {r.status_code}")
        data = r.json()
        assert_true(data["status"] in ["APPROVED", "COMPLETED"], f"Status was {data['status']}")
        assert_true("messages" in data and len(data["messages"]) > 0 and "Order ID" in data["messages"][0], "No order ID")
        assert_true("txn_id" in data, "No txn_id")
        console.print("[green]PASS Test[/green]\n")
        passed += 1

        # Test 3
        console.print("[cyan]Running Test 3: Failure Scenario (p2 - 12500)...[/cyan]")
        r = requests.post(f"{BASE_URL}/create_order", json={"product_id": "p2"})
        assert_true(r.status_code == 200, f"Status code {r.status_code}")
        data = r.json()
        assert_true(data["status"] == "BLOCKED", "Status not BLOCKED")
        assert_true("txn_id" in data, "No txn_id")
        assert_true(data.get("reason") == "Budget exceeded", "Reason not correct")
        txn_id_blocked = data["txn_id"]
        console.print("[green]PASS Test[/green]\n")
        passed += 1

        # Test 4
        console.print("[cyan]Running Test 4: HITL Approval...[/cyan]")
        r = requests.post(f"{BASE_URL}/approve/{txn_id_blocked}")
        assert_true(r.status_code == 200, f"Status code {r.status_code}")
        data = r.json()
        assert_true(data["status"] == "success", f"Status not success: {data}")
        assert_true("order_id" in data, "No order_id in approval")
        console.print("[green]PASS Test[/green]\n")
        passed += 1

        # Test 5
        console.print("[cyan]Running Test 5: Idempotency...[/cyan]")
        r = requests.post(f"{BASE_URL}/approve/{txn_id_blocked}")
        assert_true(r.status_code == 409, f"Status code {r.status_code} not 409")
        assert_true("already completed" in r.json()["detail"].lower(), "Incorrect 409 message")
        console.print("[green]PASS Test[/green]\n")
        passed += 1

        # Test 6
        console.print("[cyan]Running Test 6: Audit Trail Integrity...[/cyan]")
        r = requests.get(f"{BASE_URL}/audit")
        assert_true(r.status_code == 200, "Audit endpoint failed")
        audit_log = r.json().get("audit_log", [])
        assert_true(len(audit_log) >= 3, f"Expected >= 3 audit logs, got {len(audit_log)}")
        assert_true(audit_log[0]["prev_hash"] == "GENESIS", "First entry not GENESIS")
        for i in range(1, len(audit_log)):
            assert_true(audit_log[i]["prev_hash"] == audit_log[i-1]["hash"], f"Hash chain broken at index {i}")
        console.print("[green]PASS Test[/green]\n")
        passed += 1

        # Test 7
        console.print("[cyan]Running Test 7: Invalid Product Fallback...[/cyan]")
        r = requests.post(f"{BASE_URL}/create_order", json={"product_id": "p3"})
        assert_true(r.status_code == 200, "Fallback failed")
        assert_true(r.json()["status"] in ["APPROVED", "COMPLETED"], "Did not fallback to p1 successfully")
        console.print("[green]PASS Test[/green]\n")
        passed += 1

        # Test 8
        console.print("[cyan]Running Test 8: Reset Endpoint...[/cyan]")
        r = requests.post(f"{BASE_URL}/reset")
        assert_true(r.status_code == 200, "Reset failed")
        audit_r = requests.get(f"{BASE_URL}/audit")
        assert_true(len(audit_r.json()["audit_log"]) == 0, "Audit log not empty")
        queue_r = requests.get(f"{BASE_URL}/queue")
        assert_true(len(queue_r.json()["queue"]) == 0, "Queue not empty")
        console.print("[green]PASS Test[/green]\n")
        passed += 1

    except Exception as e:
        console.print(f"[red]X Test Failed: {e}[/red]")
        failed += 1

    console.print(f"\n[bold]Summary: {passed} Passed, {failed} Failed[/bold]")

if __name__ == "__main__":
    run_tests()
