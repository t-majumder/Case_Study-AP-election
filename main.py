import threading
import time
import uvicorn

from mcp_server import app as mcp_app
from mcp_client import ElectionAgent
from config import MCP_HOST, MCP_PORT
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="langchain")

def start_server():
    uvicorn.run(mcp_app, host=MCP_HOST, port=MCP_PORT, log_level="error")

if __name__ == "__main__":
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    time.sleep(2)

    agent = ElectionAgent()
    while True:
        try:
            query = input("User: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExit!")
            break

        if not query:
            continue
        if query.lower() in ("exit", "quit", "q"):
            print("Exit!")
            break

        print("Agent: ", end="", flush=True)
        response = agent.chat(query)
        print(response)
        print()