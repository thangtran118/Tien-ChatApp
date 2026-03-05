import requests

API_KEY = "AIzaSyDafBvycO9hL7baCVwzFEZrpf3pw8yypGM"

# ===== REGISTER =====
def firebase_register(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}"

    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }

    r = requests.post(url, json=payload)
    data = r.json()

    if "error" in data:
        raise Exception(data["error"]["message"])

    return data  # chứa idToken, localId, email


# ===== LOGIN =====
def firebase_login(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"

    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }

    r = requests.post(url, json=payload)
    data = r.json()

    if "error" in data:
        raise Exception(data["error"]["message"])

    return data
