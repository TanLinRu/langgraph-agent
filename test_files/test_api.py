"""Quick API test script"""
from fastapi.testclient import TestClient
from server import app

client = TestClient(app)

print("=== Test /api/agents ===")
resp = client.get("/api/agents")
data = resp.json()
print(f"Status: {resp.status_code}")
print(f"Agents count: {data['count']}")

print("\n=== Test /api/agent-graphs ===")
resp = client.get("/api/agent-graphs")
data = resp.json()
print(f"Status: {resp.status_code}")
print(f"Graphs count: {data['count']}")

print("\n=== Test create graph ===")
resp = client.post("/api/agent-graphs", json={
    "name": "Test Agent Graph",
    "description": "Test graph for API",
    "nodes": [
        {"id": "n1", "type": "agent", "agent_id": "builtin-code_review", "data": {"label": "Code Review"}}
    ],
    "edges": []
})
data = resp.json()
print(f"Status: {resp.status_code}")
graph_id = data["graph"]["id"]
print(f"Created graph: {graph_id}")

print("\n=== Test execution plan ===")
resp = client.post("/api/execution/plan", json={
    "graph_id": graph_id,
    "input_text": "Review this Python code"
})
data = resp.json()
print(f"Status: {resp.status_code}")
print(f"Total LLM calls: {data['total_llm_calls']}")
print(f"Estimated cost: ${data['estimated_cost_usd']}")
print(f"Steps count: {len(data['steps'])}")
print(f"Suggestions: {len(data.get('optimization_suggestions', []))}")

print("\n=== All tests passed ===")