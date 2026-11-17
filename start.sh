#!/data/data/com.termux/files/usr/bin/bash

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE_DIR"

# Detect IP address
LAN_IP=$(python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(('8.8.8.8', 80))
    print(s.getsockname()[0])
except Exception:
    print('127.0.0.1')
finally:
    s.close()
")

echo "=========================================================="
echo "    🎡 Wonderla Photo Retrieval Web Server               "
echo "=========================================================="
echo " Starting server..."
echo " Open in your phone or computer browser:"
echo "   👉 Local:   http://localhost:8080"
echo "   👉 Network: http://${LAN_IP}:8080"
echo "=========================================================="
echo " Press Ctrl+C to stop the server at any time."
echo "=========================================================="

python3 server.py
