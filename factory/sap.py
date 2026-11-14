"""Talk to an SAP system through its ADT REST interface.

Credentials come from an env file with A4H_USER, A4H_PASSWORD and A4H_CLIENT (default ~/.config/evolve/a4h.env, or
SAP_ENV). The base URL is SAP_URL, by default a local SSH tunnel. One Sap object keeps one set of cookies, so it uses
one security session on the server instead of one per request.
"""
import base64
import http.cookiejar
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

DEFAULT_ENV = "~/.config/evolve/a4h.env"
DEFAULT_URL = "http://127.0.0.1:15000"
PACKAGE = "$TMP"


class SapError(Exception):
    pass


def load_env(path):
    values = {}
    with open(os.path.expanduser(path)) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


class Sap:
    def __init__(self, env=None, url=None):
        values = load_env(env or os.environ.get("SAP_ENV", DEFAULT_ENV))
        self.user = values["A4H_USER"]
        self.client = values["A4H_CLIENT"]
        token = base64.b64encode(f"{self.user}:{values['A4H_PASSWORD']}".encode()).decode()
        self.auth = "Basic " + token
        self.url = (url or os.environ.get("SAP_URL", DEFAULT_URL)).rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = None

    # -- plumbing ---------------------------------------------------------------------------------------------------

    def request(self, method, path, body=None, content_type=None, accept="*/*", stateful=False, retry=True):
        url = self.url + path + ("&" if "?" in path else "?") + "sap-client=" + self.client
        headers = {"Authorization": self.auth, "Accept": accept, "X-CSRF-Token": self.csrf or "Fetch"}
        if content_type:
            headers["Content-Type"] = content_type
        if stateful:
            headers["X-sap-adt-sessiontype"] = "stateful"
        data = body.encode("utf-8") if isinstance(body, str) else body
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=300) as resp:
                self.csrf = resp.headers.get("x-csrf-token", self.csrf)
                return resp.status, resp.headers, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            if e.code == 403 and retry and "csrf" in (e.headers.get("x-csrf-token", "") + text).lower():
                self.csrf = None
                self.fetch_csrf()
                return self.request(method, path, body, content_type, accept, stateful, retry=False)
            if e.code == 400 and retry and not stateful and "Session Timed Out or Not Found" in text:
                # The server dropped this session (after a short dump, for one): start a new one.
                self.jar.clear()
                self.csrf = None
                self.fetch_csrf()
                return self.request(method, path, body, content_type, accept, stateful, retry=False)
            raise SapError(f"{method} {path}: HTTP {e.code}: {short(text)}") from None

    def fetch_csrf(self):
        self.request("GET", "/sap/bc/adt/discovery", accept="application/atomsvc+xml")

    def post(self, path, body="", **kw):
        if not self.csrf:
            self.fetch_csrf()
        return self.request("POST", path, body, **kw)

    # -- reading ----------------------------------------------------------------------------------------------------

    def sql(self, query, rows=5000):
        """Run an Open SQL SELECT through the data preview and return a list of dicts (values as strings)."""
        _, _, text = self.post(f"/sap/bc/adt/datapreview/freestyle?rowNumber={rows}", query,
                               content_type="text/plain", accept="application/xml, application/vnd.sap.adt.datapreview.table.v1+xml")
        root = ET.fromstring(text)
        columns = []
        for col in root.iter():
            if local(col.tag) != "columns":
                continue
            name, values = None, []
            for child in col:
                if local(child.tag) == "metadata":
                    name = attr(child, "name")
                elif local(child.tag) == "dataSet":
                    values = [(d.text or "") for d in child]
            columns.append((name, values))
        count = max((len(v) for _, v in columns), default=0)
        return [{name: values[i].rstrip() for name, values in columns} for i in range(count)]

    def source(self, uri):
        _, _, text = self.request("GET", uri, accept="text/plain")
        return text

    def program_source(self, name):
        return self.source(f"/sap/bc/adt/programs/programs/{q(name)}/source/main")

    def include_source(self, name):
        return self.source(f"/sap/bc/adt/programs/includes/{q(name)}/source/main")

    # -- writing and running ABAP -----------------------------------------------------------------------------------

    def write_program(self, name, source, description="Proof Port helper"):
        """Create the report if needed, replace its source and activate it. Local objects only ($TMP)."""
        uri = f"/sap/bc/adt/programs/programs/{q(name)}"
        if not self.exists(uri):
            body = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<program:abapProgram xmlns:program="http://www.sap.com/adt/programs/programs" '
                'xmlns:adtcore="http://www.sap.com/adt/core" '
                f'adtcore:description="{description}" adtcore:name="{name.upper()}" adtcore:type="PROG/P" '
                f'adtcore:responsible="{self.user}">'
                f'<adtcore:packageRef adtcore:name="{PACKAGE}"/></program:abapProgram>'
            )
            self.post("/sap/bc/adt/programs/programs", body,
                      content_type="application/vnd.sap.adt.programs.programs.v2+xml")
        _, _, text = self.post(f"{uri}?_action=LOCK&accessMode=MODIFY", stateful=True,
                               accept="application/vnd.sap.as+xml;charset=UTF-8;dataname=com.sap.adt.lock.result")
        handle = urllib.parse.quote(re.search(r"<LOCK_HANDLE>(.*?)</LOCK_HANDLE>", text).group(1), safe="")
        try:
            self.request("PUT", f"{uri}/source/main?lockHandle={handle}", source,
                         content_type="text/plain; charset=utf-8", stateful=True)
        finally:
            try:
                self.post(f"{uri}?_action=UNLOCK&lockHandle={handle}", stateful=True)
            except SapError as e:
                print(f"warning: unlock of {name} failed: {e}")
        self.activate(uri, name)

    def activate(self, uri, name):
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<adtcore:objectReferences xmlns:adtcore="http://www.sap.com/adt/core">'
            f'<adtcore:objectReference adtcore:uri="{uri}" adtcore:name="{name.upper()}"/>'
            '</adtcore:objectReferences>'
        )
        _, _, text = self.post("/sap/bc/adt/activation?method=activate&preauditRequested=true", body,
                               content_type="application/xml")
        errors = re.findall(r'<msg[^>]*type="E"[^>]*>.*?<txt>(.*?)</txt>', text, re.S)
        if errors:
            raise SapError(f"activating {name}: " + " | ".join(errors))

    def exists(self, uri):
        try:
            self.request("GET", uri, accept="application/vnd.sap.adt.programs.programs.v2+xml, application/xml")
            return True
        except SapError as e:
            if "HTTP 404" in str(e):
                return False
            raise

    def run_program(self, name):
        """Run a report without a selection screen and return its list output as text."""
        _, _, text = self.post(f"/sap/bc/adt/programs/programrun/{q(name)}", accept="text/plain")
        return text

    def run_abap(self, source, name="ZPP_RUN"):
        self.write_program(name, source)
        return self.run_program(name)


def local(tag):
    return tag.rsplit("}", 1)[-1]


def attr(el, name):
    for key, value in el.attrib.items():
        if local(key) == name:
            return value
    return None


def q(name):
    return urllib.parse.quote(name.lower(), safe="")


def short(text, n=400):
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:n]
