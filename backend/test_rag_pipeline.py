import sys
import json
import os
import httpx
import asyncio

# Configurations (uses local port 8000 inside the container)
API_URL = "http://localhost:8000"
TOKEN = os.getenv("ATLAS_TEST_TOKEN", "")
WORKSPACE_ID = "255c0ca1-6bf4-4772-9dc6-2bf56c705d78"

# Test markdown content
MOCK_FILE_CONTENT = """# Paul Hartmann Developer Biography
Paul Hartmann is the chief architect of AtlasLM. He specializes in designing privacy-first localized RAG setups.
He invented the KLAW system, which stands for Knowledge-Linked Agentic Workspace, for handling high-volume text chunk indexing.
In his spare time, he researches mathematical optimizations for pgvector index traversal and cosine distance metrics.
"""

async def run_end_to_end_test():
    if not TOKEN:
        print("SKIP: set ATLAS_TEST_TOKEN through a secure test environment")
        return

    headers = {
        "Authorization": f"Bearer {TOKEN}"
    }
    
    print("=== STARTING PHASE 2 END-TO-END RAG PROGRAMMATIC TEST ===")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Ingest a mock markdown file into the workspace
        print("\n1. Uploading document source (atlassian_hartmann.md)...")
        files = {
            "file": ("atlassian_hartmann.md", MOCK_FILE_CONTENT.encode("utf-8"), "text/markdown")
        }
        data = {
            "provider": "openrouter" # Uses active OpenRouter key from env
        }
        res_upload = await client.post(
            f"{API_URL}/api/v1/workspaces/{WORKSPACE_ID}/documents",
            headers=headers,
            files=files,
            data=data
        )
        if res_upload.status_code != 201:
            print(f"FAILED to upload document: {res_upload.status_code} - {res_upload.text}")
            return
            
        doc_info = res_upload.json()
        print(f"SUCCESS: Ingested document '{doc_info['filename']}' under ID: {doc_info['id']}")
        
        # 2. Create a new chat session for this workspace
        print("\n2. Initializing new chat session...")
        res_session = await client.post(
            f"{API_URL}/api/v1/workspaces/{WORKSPACE_ID}/sessions",
            headers=headers,
            json={"title": "RAG Verification Session"}
        )
        if res_session.status_code != 200:
            print(f"FAILED to create session: {res_session.status_code} - {res_session.text}")
            return
            
        session_info = res_session.json()
        session_id = session_info["id"]
        print(f"SUCCESS: Created chat session under ID: {session_id}")
        
        # 3. Stream grounded answers with citations via SSE
        print("\n3. Triggering streaming chat request for query: 'What does KLAW stand for?'...")
        chat_payload = {
            "content": "What does KLAW stand for?"
        }
        
        async with client.stream(
            "POST",
            f"{API_URL}/api/v1/sessions/{session_id}/chat/stream?provider=openrouter",
            headers=headers,
            json=chat_payload
        ) as stream_res:
            if stream_res.status_code != 200:
                print(f"FAILED to trigger chat stream: {stream_res.status_code}")
                # Try to read body
                body = await stream_res.aread()
                print(body.decode())
                return
                
            print("\n=== SSE CHAT STREAM STARTED ===")
            async for line in stream_res.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                
                if line.startswith("event:"):
                    print(f"\n[SSE Event]: {line[6:].strip()}")
                elif line.startswith("data:"):
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        print("\n[SSE Event]: Stream finished [DONE]")
                        break
                    try:
                        payload = json.loads(data_str)
                        if payload.get("type") == "metadata":
                            print(f"[SSE Metadata - Grounded Citations]: {json.dumps(payload.get('sources'), indent=2)}")
                        elif payload.get("type") == "chunk":
                            sys.stdout.write(payload.get("content", ""))
                            sys.stdout.flush()
                    except Exception as e:
                        print(f"\nError parsing chunk: {e}")
            print("\n=== SSE CHAT STREAM COMPLETE ===")

if __name__ == "__main__":
    asyncio.run(run_end_to_end_test())
