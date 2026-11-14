"""A small OData V4 client for the new service, handed to the port's driver by the grader.

The driver never sees credentials: it gets a Client and calls get, post, patch and delete with paths relative to the
service root. Every call returns a Response with the status, the JSON body and the messages the service sent (error
body and details, and the sap-messages header), each as {"type": "E"|"W"|"S"|"I", "text": ...}.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import sap  # noqa: E402

SEVERITY = {1: "S", 2: "I", 3: "W", 4: "E"}


class Response:
    def __init__(self, status, body, messages):
        self.status, self.body, self.messages = status, body, messages

    @property
    def ok(self):
        return 200 <= self.status < 300

    def __repr__(self):
        return f"Response({self.status}, messages={self.messages})"


class Client:
    def __init__(self, service_root, s=None):
        self.s = s or sap.Sap()
        self.root = service_root.rstrip("/") + "/"
        self.csrf = None

    def _messages(self, headers, body):
        out = []
        err = body.get("error") if isinstance(body, dict) else None
        if err:
            details = err.get("details") or []
            if not details:
                out.append({"type": "E", "text": err.get("message", "")})
            for d in details:
                out.append({"type": SEVERITY.get(d.get("@Common.numericSeverity"), "E"), "text": d.get("message", "")})
            if details and err.get("message") and err["message"] not in [d.get("message") for d in details]:
                out.insert(0, {"type": "E", "text": err["message"]})
        raw = headers.get("sap-messages") if headers else None
        if raw:
            try:
                for m in json.loads(raw):
                    out.append({"type": SEVERITY.get(m.get("numericSeverity"), "I"), "text": m.get("message", "")})
            except ValueError:
                pass
        return out

    def call(self, method, path, data=None, headers=None):
        if method != "GET" and not self.csrf:
            self._fetch_csrf()
        url = self.root + path.lstrip("/")
        hdrs = {"Accept": "application/json", "Authorization": self.s.auth}
        if self.csrf:
            hdrs["X-CSRF-Token"] = self.csrf
        body = None
        if data is not None:
            body = json.dumps(data).encode()
            hdrs["Content-Type"] = "application/json"
        hdrs.update(headers or {})
        import urllib.request
        import urllib.error
        req = urllib.request.Request(url + ("&" if "?" in url else "?") + "sap-client=" + self.s.client,
                                     data=body, method=method, headers=hdrs)
        try:
            with self.s.opener.open(req, timeout=120) as resp:
                status, h, text = resp.status, resp.headers, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            status, h, text = e.code, e.headers, e.read().decode("utf-8", "replace")
            if status == 403 and "csrf" in (e.headers.get("x-csrf-token", "") or "").lower():
                self.csrf = None
                self._fetch_csrf()
                return self.call(method, path, data, headers)
        try:
            parsed = json.loads(text) if text.strip() else {}
        except ValueError:
            parsed = {"raw": text[:2000]}
        return Response(status, parsed, self._messages(h, parsed))

    def _fetch_csrf(self):
        import urllib.request
        req = urllib.request.Request(self.root + "?sap-client=" + self.s.client,
                                     headers={"X-CSRF-Token": "Fetch", "Authorization": self.s.auth,
                                              "Accept": "application/json"})
        with self.s.opener.open(req, timeout=60) as resp:
            self.csrf = resp.headers.get("x-csrf-token")

    def ui(self, type_, text):
        """Record a message the app's UI shows before calling the service (input format only, never a rule)."""
        self.ui_messages = getattr(self, "ui_messages", []) + [{"type": type_, "text": text, "from": "ui"}]
        return Response(0, {}, [{"type": type_, "text": text}])

    def get(self, path, **kw):
        return self.call("GET", path, **kw)

    def post(self, path, data=None, **kw):
        return self.call("POST", path, data if data is not None else {}, **kw)

    def patch(self, path, data, **kw):
        return self.call("PATCH", path, data, **kw)

    def delete(self, path, **kw):
        return self.call("DELETE", path, **kw)
