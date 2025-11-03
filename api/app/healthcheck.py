import sys
import json
import time
import urllib.request
import urllib.error

def main() -> int:
    # Use IPv4 loopback explicitly to avoid ::1 resolution issues
    url = "http://127.0.0.1:8000/health"
    for _ in range(5):
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
                if data.get("ok") is True:
                    return 0
        except Exception:
            time.sleep(0.5)
    return 1

if __name__ == "__main__":
    sys.exit(main())
