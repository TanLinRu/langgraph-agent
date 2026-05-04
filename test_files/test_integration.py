"""Full integration test with execution"""
import os
os.environ['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY', '')

from fastapi.testclient import TestClient
from server import app

client = TestClient(app)

print("=== Full Integration Test ===\n")

# Create a more complex graph
print("1. Create test graph with 2 agents")
resp = client.post("/api/agent-graphs", json={
    "name": "Review and Debug Graph",
    "description": "Test graph with code review and debugging",
    "nodes": [
        {"id": "n1", "type": "agent", "agent_id": "builtin-code_review", "data": {"label": "Code Review"}},
        {"id": "n2", "type": "agent", "agent_id": "builtin-debugging", "data": {"label": "Debugging"}},
    ],
    "edges": [
        {"source": "n1", "target": "n2"}
    ]
})
data = resp.json()
graph_id = data["graph"]["id"]
print(f"   Created graph: {graph_id}")

# Generate plan
print("\n2. Generate execution plan")
resp = client.post("/api/execution/plan", json={
    "graph_id": graph_id,
    "input_text": "Review this function and fix any bugs: def add(a,b): return a - b"
})
plan = resp.json()
print(f"   Total LLM calls: {plan['total_llm_calls']}")
print(f"   Steps: {len(plan['steps'])}")
for s in plan['steps']:
    print(f"     - Step {s['step_id']}: {s['agent_name']}")

if plan.get('optimization_suggestions'):
    print("   Suggestions:")
    for sug in plan['optimization_suggestions']:
        print(f"     - [{sug['impact']}] {sug['description']}: {sug['detail']}")

# Execute
print("\n3. Execute (with approved=true)")
resp = client.post("/api/execution/run", json={
    "graph_id": graph_id,
    "input_text": "Review this function and fix any bugs: def add(a,b): return a - b",
    "approved": True
})
result = resp.json()
print(f"   Status: {result['status']}")
print(f"   Total LLM calls: {result.get('total_llm_calls', 0)}")
print(f"   Cost: ${result.get('total_cost_usd', 0):.4f}")
print(f"   Steps completed:")
for s in result.get('steps', []):
    print(f"     - Step {s['step_id']}: {s['agent_name']} -> {s['status']}")
    if s.get('result'):
        print(f"       Result: {s['result'][:100]}...")

if result.get('output'):
    print(f"\n   Output preview: {result['output'][:200]}...")

# Get report
print("\n4. Get execution report")
if result.get('execution_id'):
    resp = client.get(f"/api/execution/{result['execution_id']}/report")
    report = resp.json()
    print(f"   Summary:")
    print(f"     - Total calls: {report['summary']['total_llm_calls']}")
    print(f"     - Total cost: ${report['summary']['total_cost_usd']}")
    print(f"     - Duration: {report['summary']['total_duration_ms']}ms")
    
    if report.get('optimization_insights', {}).get('suggestions'):
        print(f"   Suggestions:")
        for s in report['optimization_insights']['suggestions']:
            print(f"     - [{s['priority']}] {s['description']}")
            print(f"       Action: {s['action']}")

print("\n=== Integration Test Complete ===")