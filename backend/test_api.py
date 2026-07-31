import httpx
import json

url = "http://127.0.0.1:8000/api/chat"
headers = {"Content-Type": "application/json"}
data = {
    "message": "show all active users",
    "history": []
}

print(f"Sending POST to {url}...")
try:
    response = httpx.post(url, json=data, timeout=30.0)
    print("Status Code:", response.status_code)
    print("Response JSON:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print("Request failed:", e)
