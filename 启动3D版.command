#!/bin/zsh

cd "$(dirname "$0")"
PORT=$(/usr/bin/python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')

/usr/bin/python3 -m http.server "$PORT" --bind 127.0.0.1 >/tmp/wasteland-fireline-3d.log 2>&1 &

for _ in {1..30}; do
  /usr/bin/curl -fsS "http://127.0.0.1:${PORT}/index.html" >/dev/null 2>&1 && break
  sleep 0.1
done

/usr/bin/open "http://127.0.0.1:${PORT}/"
