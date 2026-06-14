import requests

try:
    r = requests.get('http://127.0.0.1:8000/api/stream-query', params={'q': 'what is the name of the person in this PVC card'}, stream=True, timeout=20)
    print('status', r.status_code)
    count = 0
    for line in r.iter_lines(decode_unicode=True):
        if line:
            print('LINE:', line)
            count += 1
        if count >= 20:
            break
    r.close()
except Exception as e:
    print('request_error', repr(e))
