from flask import Flask, request, render_template, jsonify, redirect, url_for
import requests
import json
import os
import threading
from queue import Queue
import time

app = Flask(__name__)
DATA_FILE = "generated_keys.json"

GEN_URL = "https://digitalauth.vercel.app/api/genkey"
CHECK_URL = "https://digitalauth.vercel.app/api/checkkey"
HEADERS = {
    "Content-Type": "application/json",
    "x-api-key": "LUNARSOL25"
}

EXPIRATION_OPTIONS = {
    "1d": 1,
    "7d": 7,
    "1m": 30,
    "6m": 180,
    "12m": 365,
    "inf": "inf"
}

def load_keys():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return []

def save_keys(keys):
    with open(DATA_FILE, "w") as f:
        json.dump(keys, f, indent=2)

generated_keys = load_keys()

@app.route('/')
def home():
    return redirect(url_for('generate'))

def post_with_retries(url, json_data, headers, retries=3, delay=2):
    for attempt in range(retries):
        try:
            res = requests.post(url, json=json_data, headers=headers, timeout=10)
            if res.status_code == 200:
                return res
            else:
                print(f"Attempt {attempt+1}: API returned status {res.status_code}")
                time.sleep(delay)
        except Exception as e:
            print(f"Attempt {attempt+1} Exception: {e}")
            time.sleep(delay)
    return None
@app.route('/generate', methods=['GET', 'POST'])
def generate():
    message = ""
    new_keys = []

    if request.method == 'POST':
        try:
            count = int(request.form['amount'])
            exp_key = request.form['expiration']
            expiration = EXPIRATION_OPTIONS.get(exp_key)

            if expiration is None:
                message = "❌ Invalid expiration selected."
                return render_template(
                    'base.html',
                    active_tab="generate",
                    message=message,
                    expiration_options=EXPIRATION_OPTIONS,
                    keys=[],
                    check_result=None,
                    check_error=None
                )

            task_queue = Queue()
            result_lock = threading.Lock()
            new_keys_shared = []

            for _ in range(count):
                task_queue.put(1)

            def worker():
                while not task_queue.empty():
                    try:
                        task_queue.get_nowait()
                    except:
                        return
                    body = {"expiration": expiration}
                    print(f"Sending payload: {body}")
                    res = post_with_retries(GEN_URL, body, HEADERS)
                    if res is None:
                        task_queue.task_done()
                        continue
                    print(f"Response code: {res.status_code}, content: {res.text}")

                    try:
                        data = res.json()
                    except json.JSONDecodeError:
                        task_queue.task_done()
                        continue

                    if data.get("success") and "key" in data:
                        key_info = data["key"]
                        with result_lock:
                            new_keys_shared.append(key_info)
                    task_queue.task_done()

            threads_count = 1  # test single-threaded first
            threads = []
            for _ in range(threads_count):
                t = threading.Thread(target=worker)
                t.start()
                threads.append(t)

            for t in threads:
                t.join()

            if new_keys_shared:
                generated_keys.extend(new_keys_shared)
                save_keys(generated_keys)
                message = f"✅ Generated {len(new_keys_shared)} key(s) successfully."
                new_keys = new_keys_shared
            else:
                message = "❌ Failed to generate any keys."

        except Exception as e:
            message = f"❌ Error: {e}"

    return render_template(
        'base.html',
        active_tab="generate",
        message=message,
        expiration_options=EXPIRATION_OPTIONS,
        keys=new_keys,
        check_result=None,
        check_error=None
    )


@app.route('/generated')
def generated():
    return render_template('base.html', 
                           active_tab="generated", 
                           keys=generated_keys,
                           message=None,
                           expiration_options=EXPIRATION_OPTIONS,
                           check_result=None,
                           check_error=None)

@app.route('/check', methods=['GET', 'POST'])
def check():
    result = None
    error = None
    if request.method == 'POST':
        key = request.form['key']
        try:
            res = requests.get(f"{CHECK_URL}?key={key}", timeout=10)
            data = res.json()
            if data.get("success"):
                result = data["details"]
            else:
                error = data.get("message", "Invalid key.")
        except Exception as e:
            error = str(e)
    return render_template('base.html', 
                           active_tab="check", 
                           keys=[],
                           message=None,
                           expiration_options=EXPIRATION_OPTIONS,
                           check_result=result,
                           check_error=error)

@app.route('/check/<license_key>')
def check_key(license_key):
    try:
        res = requests.get(f"{CHECK_URL}?key={license_key}", timeout=10)
        data = res.json()
        if data.get("success"):
            result = data["details"]
        else:
            result = None
    except:
        result = None
    return render_template('base.html', 
                           active_tab="check", 
                           keys=[],
                           message=None,
                           expiration_options=EXPIRATION_OPTIONS,
                           check_result=result,
                           check_error=None)

if __name__ == '__main__':
    app.run(debug=True)
