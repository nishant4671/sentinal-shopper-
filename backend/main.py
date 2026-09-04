import os
import sys
import time
import uuid
import hashlib
import asyncio
import jwt
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import razorpay

from rich.console import Console
from rich.table import Table
from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

# -- Logging Setup --
console = Console()

# -- Fallback for sentinel.py --
JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret_123")
MAX_AMOUNT = 5000

try:
    import sentinel
    console.print("[green]Successfully imported sentinel.py[/green]")
except Exception as e:
    console.print(f"[yellow]Failed to import sentinel.py due to: {e}. Using fallback MockSentinel.[/yellow]")
    class MockSentinel:
        @staticmethod
        def verify(token: str, amount: int) -> tuple[bool, str]:
            limit = MAX_AMOUNT
            if token:
                try:
                    # 2 AM Failure Story FIX: Use integer time.time() explicitly.
                    decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
                    if decoded.get("exp", 0) < int(time.time()):
                        return False, "Token expired"
                    limit = decoded.get("max_amount", MAX_AMOUNT)
                except Exception as exc:
                    return False, f"JWT Error: {exc}"
            
            if amount <= limit:
                return True, "Budget approved"
            return False, "Budget exceeded"
    sentinel = MockSentinel()

# -- FastAPI App Setup --
app = FastAPI(title="Sentinel Shopper")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Globals & State --
PRODUCT_CATALOG = [
    {"id": "p1", "name": "Wireless Mouse", "price": 2500},
    {"id": "p2", "name": "Gaming Laptop", "price": 12500}
]

approval_queue = {}
audit_log = []

class AgentState(TypedDict):
    messages: List[str]
    product_id: str
    amount: int
    status: str
    txn_id: str
    token: str

class OrderRequest(BaseModel):
    product_id: str

# -- Audit Trail --
def add_audit_log(event: str, data: dict, txn_id: str):
    global audit_log
    prev_hash = audit_log[-1]["hash"] if audit_log else "GENESIS"
    content = event + str(data) + prev_hash
    cur_hash = hashlib.sha256(content.encode()).hexdigest()
    entry = {
        "event": event,
        "data": data,
        "txn_id": txn_id,
        "prev_hash": prev_hash,
        "hash": cur_hash,
        "timestamp": int(time.time())
    }
    audit_log.append(entry)
    console.print(f"[dim]Audit Log Appended: {event} (Hash: {cur_hash[:8]}...)[/dim]")

# -- Razorpay Logic --
async def create_razorpay_order(amount: int) -> str:
    mode = os.getenv("PAYMENT_MODE", "MOCK")
    if mode == "MOCK":
        console.print("[yellow]PAYMENT_MODE is MOCK, returning mock order.[/yellow]")
        return "mock_order_123"
        
    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    
    if not key_id or not key_secret:
        console.print("[red]Missing Razorpay keys. Falling back to mock order.[/red]")
        return "mock_order_123"
        
    client = razorpay.Client(auth=(key_id, key_secret))
    delays = [1, 2, 4]
    
    for attempt, delay in enumerate(delays, 1):
        try:
            order = client.order.create({
                "amount": amount * 100,
                "currency": "INR",
                "payment_capture": "1"
            })
            return order["id"]
        except Exception as e:
            console.print(f"[red]Razorpay API error on attempt {attempt}: {e}[/red]")
            await asyncio.sleep(delay)
            
    raise Exception("Razorpay SDK failed after 3 retries (exponential backoff)")

# -- LangGraph Nodes --
def init_node(state: AgentState):
    txn_id = state.get("txn_id") or str(uuid.uuid4())
    console.print(f"\n[bold blue]Init Node[/bold blue] | Txn: {txn_id}")
    add_audit_log("INIT", {"product_id": state.get("product_id")}, txn_id)
    return {"txn_id": txn_id}

def plan_node(state: AgentState):
    console.print(f"[bold cyan]Plan Node[/bold cyan] | Agent deciding...")
    requested_id = state.get("product_id", "")
    
    # Check if the product_id is valid, otherwise fallback gracefully to "p1"
    valid_ids = [p["id"] for p in PRODUCT_CATALOG]
    if requested_id not in valid_ids:
        console.print(f"  [yellow]Warning: Product '{requested_id}' not found. Falling back to 'p1'[/yellow]")
        requested_id = "p1"
        
    product = next(p for p in PRODUCT_CATALOG if p["id"] == requested_id)
    amount = product["price"]
    
    console.print(f"  [cyan]LLM Output (structured):[/cyan] {{\"product_id\": \"{product['id']}\"}} | Cost: {amount}")
    add_audit_log("PLAN", {"selected_product": product["id"], "amount": amount}, state.get("txn_id", ""))
    return {"product_id": product["id"], "amount": amount}

def sentinel_check_node(state: AgentState):
    console.print(f"[bold magenta]Sentinel_Check Node[/bold magenta] | Hard Crypto Boundary")
    amount = state["amount"]
    token = state.get("token", "")
    
    passed, reason = sentinel.verify(token, amount)
    status = "APPROVED" if passed else "BLOCKED"
    
    console.print(f"  [magenta]Budget Check Result: {passed} | Reason: {reason} | Status: {status}[/magenta]")
    add_audit_log("SENTINEL_CHECK", {"amount": amount, "status": status, "reason": reason}, state.get("txn_id", ""))
    
    return {"status": status}

async def execute_node(state: AgentState):
    console.print(f"[bold green]Execute Node[/bold green] | Processing payment...")
    try:
        order_id = await create_razorpay_order(state["amount"])
        console.print(f"  [green]Order created successfully: {order_id}[/green]")
        add_audit_log("EXECUTE_SUCCESS", {"order_id": order_id}, state.get("txn_id", ""))
        return {"status": "COMPLETED", "messages": [f"Order ID: {order_id}"]}
    except Exception as e:
        console.print(f"  [red]Execution failed: {e}[/red]")
        add_audit_log("EXECUTE_FAILED", {"error": str(e)}, state.get("txn_id", ""))
        return {"status": "FAILED", "messages": [str(e)]}

def block_node(state: AgentState):
    console.print(f"[bold red]Block Node[/bold red] | Routing to HITL queue")
    txn_id = state["txn_id"]
    approval_queue[txn_id] = {
        "product": state["product_id"],
        "amount": state["amount"],
        "original_token": state.get("token"),
        "status": "PENDING",
        "attempts": 0
    }
    console.print(f"  [red]Transaction {txn_id} stored in approval_queue (PENDING)[/red]")
    add_audit_log("BLOCKED_HITL", {"queue_status": "PENDING"}, txn_id)
    return {"status": "BLOCKED"}

def should_continue(state: AgentState):
    if state.get("status") == "APPROVED":
        return "Execute"
    return "Block"

# -- Build Graph --
workflow = StateGraph(AgentState)
workflow.add_node("Init", init_node)
workflow.add_node("Plan", plan_node)
workflow.add_node("Sentinel_Check", sentinel_check_node)
workflow.add_node("Execute", execute_node)
workflow.add_node("Block", block_node)

workflow.set_entry_point("Init")
workflow.add_edge("Init", "Plan")
workflow.add_edge("Plan", "Sentinel_Check")
workflow.add_conditional_edges("Sentinel_Check", should_continue, {"Execute": "Execute", "Block": "Block"})
workflow.add_edge("Execute", END)
workflow.add_edge("Block", END)

agent_app = workflow.compile()

# -- Endpoints --
@app.post("/create_order")
async def create_order_endpoint(req: OrderRequest):
    result = await agent_app.ainvoke({
        "messages": [],
        "product_id": req.product_id,
        "amount": 0,
        "status": "",
        "txn_id": "",
        "token": ""
    })
    
    if result["status"] == "BLOCKED":
        return {"status": "BLOCKED", "txn_id": result["txn_id"], "reason": "Budget exceeded", "message": "Transaction blocked. Requires HITL approval."}
        
    return {"status": result["status"], "txn_id": result["txn_id"], "messages": result.get("messages", [])}

@app.post("/approve/{txn_id}")
async def approve_txn_endpoint(txn_id: str):
    console.print(f"\n[bold yellow]HITL Approval Requested for {txn_id}[/bold yellow]")
    if txn_id not in approval_queue:
        raise HTTPException(status_code=404, detail="Transaction not found in queue")
        
    txn = approval_queue[txn_id]
    if txn["status"] == "COMPLETED":
        raise HTTPException(status_code=409, detail="Transaction already completed")
        
    # Generate new step-up JWT
    current_time = int(time.time())
    new_token = jwt.encode({
        "max_amount": 15000, 
        "txn_id": txn_id, 
        "exp": current_time + 3600
    }, JWT_SECRET, algorithm="HS256")
    
    console.print(f"  [yellow]Generated Step-Up JWT with 15000 limit[/yellow]")
    add_audit_log("HITL_APPROVED", {"new_limit": 15000}, txn_id)
    
    # Auto-retry by running the exact same transaction state again
    result = await agent_app.ainvoke({
        "messages": [],
        "product_id": txn["product"],
        "amount": txn["amount"],
        "status": "",
        "txn_id": txn_id,
        "token": new_token
    })
    
    if result["status"] == "COMPLETED":
        txn["status"] = "COMPLETED"
        return {"status": "success", "order_id": result.get("messages", [""])[0]}
    else:
        txn["attempts"] += 1
        return {"status": "failed", "attempts": txn["attempts"]}

@app.post("/reset")
async def reset_state():
    global approval_queue, audit_log
    approval_queue.clear()
    audit_log.clear()
    console.print("[bold red]State reset completely (Queue & Audit Log)[/bold red]")
    return {"status": "reset_complete"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/audit")
async def get_audit_log():
    return {"audit_log": audit_log}

@app.get("/queue")
async def get_queue():
    return {"queue": approval_queue}
