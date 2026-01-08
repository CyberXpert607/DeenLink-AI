import requests

INNGEST_URL = "http://localhost:8288/e/agent_query"

def log_event(payload: dict):
    try:
        requests.post(INNGEST_URL, json=payload, timeout=2)
    except Exception:
        pass

#this is what we'll use for monitoring the agents reponse, though this is just a basic implemenatation