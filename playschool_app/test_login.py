import requests
r = requests.post("http://127.0.0.1:5000/login", data={"email":"teacher@playschool.com","password":"teacher123"}, allow_redirects=False)
print(r.status_code, r.headers.get("Location"))
