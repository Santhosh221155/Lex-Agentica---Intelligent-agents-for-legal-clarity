import urllib.request
import urllib.parse

query = 'what is the name of the person in this PVC card'
url = 'http://127.0.0.1:8000/api/stream-query?' + urllib.parse.urlencode({'q': query})
req = urllib.request.Request(url)
with urllib.request.urlopen(req, timeout=30) as resp:
    print('status', resp.status)
    body = resp.read(2000)
    print(body.decode('utf-8', errors='replace'))
