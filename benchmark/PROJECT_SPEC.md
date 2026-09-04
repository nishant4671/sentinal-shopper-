---
# 🎯 Razorpay Hackathon 2026 - Track 01: Agentic Commerce
**Project Name:** Sentinel Shopper (or whatever you want to name it later)

## Core Problem We Are Solving
AI agents cannot be trusted with money using prompt-based guardrails alone. 
They hallucinate budgets, product IDs, and timestamps. 
We solve this by moving authorization from the LLM layer to a deterministic cryptographic boundary (the Sentinel).

## Non-Negotiable Features (Must have in final demo)
1. **LangGraph Agent with exactly 4 nodes:**
   - Init (start)
   - Plan (LLM picks product from catalog)
   - Sentinel_Check (hard crypto/budget verification)
   - Execute (if pass) OR Block (if fail -> HITL queue)

2. **Sentinel Hard Limit:** MAX_AMOUNT = 5000 (INR)

3. **Two Demo Scenarios:**
   - Success: ₹2,500 (Wireless Mouse) -> Approved -> Razorpay Order Created.
   - Failure: ₹12,500 (Gaming Laptop) -> Blocked -> HITL Approval Queue.

4. **Human-in-the-Loop (HITL):**
   - In-memory queue holding blocked transactions.
   - An "/approve/{txn_id}" endpoint that issues a new JWT token with increased limit and retries.

5. **Audit Trail:** Immutable log (each entry has a hash of the previous).

6. **2 AM Failure Story:** Timezone-naive vs timezone-aware datetime in JWT `exp` claim causing silent verification failure. Fixed by using shared `time.time()` integers.

## Architecture Strategy (How we built it)
- Extracted `ui/` (frontend) and `grantex_auth.py` (sentinel) from `agentic-org`.
- Built a fresh FastAPI + LangGraph backend from scratch (200 lines max).
- Everything else from the original repo was discarded to avoid bloat.
---
