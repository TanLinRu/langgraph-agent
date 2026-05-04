"""测试 ACP stdio 客户端"""
import sys
sys.path.insert(0, "D:\\project\\ai\\langgraph-agent\\src")

from agent.acp_stdio_client import ACPStdioClient

client = ACPStdioClient(timeout=60)

print("=== Testing initialize ===")
result = client.initialize()
print(f"Initialize result: {result}")

if result:
    print(f"\nProtocol version: {client._protocol_version}")
    
    print("\n=== Testing create_session ===")
    session_id = client.create_session()
    print(f"Session ID: {session_id}")
    
    if session_id:
        print("\n=== Testing send_prompt ===")
        response = client.send_prompt("Say hello in one word")
        print(f"Response: {response[:500] if response else 'empty'}")

client.close()
print("\n=== Done ===")