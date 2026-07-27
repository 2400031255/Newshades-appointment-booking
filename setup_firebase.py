#!/usr/bin/env python3
"""
setup_firebase.py
-----------------
Run this once to convert your downloaded Firebase service account JSON
into the single-line format needed in .env

Usage:
    python setup_firebase.py path/to/serviceAccountKey.json
"""
import sys, json, os, re

if len(sys.argv) < 2:
    print("Usage: python setup_firebase.py path/to/serviceAccountKey.json")
    sys.exit(1)

json_path = sys.argv[1]
if not os.path.exists(json_path):
    print(f"File not found: {json_path}")
    sys.exit(1)

with open(json_path, 'r') as f:
    cred = json.load(f)

# Validate it looks like a service account
if cred.get('type') != 'service_account':
    print("ERROR: This doesn't look like a Firebase service account JSON.")
    sys.exit(1)

# Convert to single-line JSON string
single_line = json.dumps(cred)

env_path = os.path.join(os.path.dirname(__file__), '.env')

# Read existing .env
with open(env_path, 'r') as f:
    content = f.read()

# Replace or insert FIREBASE_CREDENTIALS line
if 'FIREBASE_CREDENTIALS=' in content:
    content = re.sub(r'FIREBASE_CREDENTIALS=.*', f'FIREBASE_CREDENTIALS={single_line}', content)
else:
    content += f'\nFIREBASE_CREDENTIALS={single_line}\n'

with open(env_path, 'w') as f:
    f.write(content)

print(f"✅ Done! FIREBASE_CREDENTIALS written to .env")
print(f"   Project: {cred.get('project_id')}")
print(f"   Account: {cred.get('client_email')}")
print(f"\nNow run your app: python app.py")
