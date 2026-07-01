import truststore
import requests
from uuid import uuid4

truststore.inject_into_ssl()
rq_uid = str(uuid4())

url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"

payload={
  'scope': 'GIGACHAT_API_PERS'
}
headers = {
  'Content-Type': 'application/x-www-form-urlencoded',
  'Accept': 'application/json',
  'RqUID': str(rq_uid),
  'Authorization': 'Basic MDE5ZjFkMjUtMjM4OC03NWY1LTljMTAtNzJmOGQ1ZWE5Y2Y0OmYxN2E0ZGZiLTI1ZDktNDc2YS05MGRmLTNlMDdiZGZhNmE4NQ=='
}

response = requests.request("POST", url, headers=headers, data=payload, timeout=30)

print(response.status_code)
print(response.text)

