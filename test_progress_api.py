import requests
import time
import os

BASE_URL = "http://127.0.0.1:7000"
FILE_PATH = r"c:\Users\spTech\Desktop\Invoicegenerator\sample invoices\CHG-1.pdf"

def test_upload_and_progress():
    print(f"Uploading {FILE_PATH}...")
    with open(FILE_PATH, 'rb') as f:
        files = {'files[]': ('sample_invoice_1.pdf', f, 'application/pdf')}
        response = requests.post(f"{BASE_URL}/upload", files=files)
    
    if response.status_code != 200:
        print(f"Upload failed: {response.text}")
        return

    data = response.json()
    session_id = data['session_id']
    total_invoices = data['total_invoices']
    print(f"Upload successful. Session ID: {session_id}, Total invoices: {total_invoices}")

    print("Polling progress...")
    completed = False
    while not completed:
        progress_response = requests.get(f"{BASE_URL}/api/progress/{session_id}")
        if progress_response.status_code == 200:
            status = progress_response.json()
            if 'percentage' in status:
                print(f"Progress: {status['percentage']}% - {status['message']}")
            else:
                print(f"DEBUG: Status response missing percentage: {status}")
            
            if status.get('completed'):
                completed = True
                if 'error' in status:
                    print(f"Processing failed with error: {status['error']}")
                else:
                    print("Processing completed successfully!")
        else:
            print(f"Failed to get progress: {progress_response.text}")
            break
        time.sleep(2)

    if completed:
        print("Fetching results...")
        results_response = requests.get(f"{BASE_URL}/get_invoices/{session_id}")
        if results_response.status_code == 200:
            results = results_response.json()
            print(f"Found {len(results['invoices'])} processed invoices.")
        else:
            print(f"Failed to fetch results: {results_response.text}")

if __name__ == "__main__":
    test_upload_and_progress()
