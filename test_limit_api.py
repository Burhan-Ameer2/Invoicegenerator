import requests
import time
import os

BASE_URL = "http://127.0.0.1:7000"

def test_usage_limit():
    print("Checking usage stats...")
    response = requests.get(f"{BASE_URL}/api/usage")
    if response.status_code == 200:
        stats = response.json()
        print(f"Total calls: {stats['total_calls']}")
        print(f"Max trial invoices: {stats.get('max_trial_invoices', 'Not set')}")
        print(f"Invoices remaining: {stats.get('invoices_remaining', 'Unknown')}")
        print(f"Trial Expires At: {stats.get('trial_expires_at', 'Missing')}")
        print(f"Is limit reached: {stats.get('is_limit_reached', 'Unknown')}")
    else:
        print(f"Failed to get usage: {response.text}")

if __name__ == "__main__":
    test_usage_limit()
