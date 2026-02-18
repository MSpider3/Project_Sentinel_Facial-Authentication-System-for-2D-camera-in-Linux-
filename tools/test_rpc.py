#!/usr/bin/env python3
import json
import subprocess
import sys

def run_rpc(method, params=None):
    req = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": 1
    }
    
    # Run service as a subprocess
    process = subprocess.Popen(
        ['python3', 'sentinel_service.py'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    input_str = json.dumps(req) + "\n"
    stdout, stderr = process.communicate(input=input_str)
    
    if stderr:
        print(f"STDERR: {stderr}")
        
    try:
        response = json.loads(stdout)
        print(f"Response for {method}:")
        print(json.dumps(response, indent=2))
        return response
    except json.JSONDecodeError:
        print(f"Failed to decode: {stdout}")
        return None

if __name__ == "__main__":
    print("Testing get_config...")
    run_rpc("get_config")
    
    print("\nTesting initialize...")
    run_rpc("initialize")
