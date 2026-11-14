"""Serve the port's Fiori Elements app locally: a list report and object page over the new OData V4 service.

UI5 comes from the SAP system itself, and every /sap/ request is passed through to SAP with the factory's user, so
the browser needs no SAP logon. The service and its main entity set come from runs/<TCODE>/port/service.json.

    python3 factory/app.py ZCRED [port]          -> http://127.0.0.1:8100/
"""
import http.server
import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
import sap  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PASS_HEADERS = ("content-type", "accept", "x-csrf-token", "if-match", "if-none-match", "prefer", "odata-version",
                "odata-maxversion", "sap-contextid-accept", "sap-cancel-on-close", "x-requested-with")
BACK_HEADERS = ("content-type", "x-csrf-token", "sap-messages", "etag", "odata-version", "location",
                "sap-contextid", "preference-applied")

INDEX = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<script id="sap-ui-bootstrap" src="/sap/public/bc/ui5_ui5/resources/sap-ui-core.js"
  data-sap-ui-theme="sap_horizon" data-sap-ui-async="true" data-sap-ui-compatVersion="edge"
  data-sap-ui-resourceroots='{{"proofport": "./"}}' data-sap-ui-oninit="module:sap/ui/core/ComponentSupport"
  data-sap-ui-language="EN"></script></head>
<body class="sapUiBody sapUiSizeCompact"><div data-sap-ui-component data-name="proofport" data-id="app"
 data-settings='{{"id": "proofport"}}' style="height:100%"></div></body></html>"""

COMPONENT = """sap.ui.define(["sap/fe/core/AppComponent"], function (AppComponent) {
  "use strict";
  return AppComponent.extend("proofport.Component", { metadata: { manifest: "json" } });
});"""


def manifest(title, root, entity):
    return {
        "_version": "1.60.0",
        "sap.app": {"id": "proofport", "type": "application", "title": title, "applicationVersion": {"version": "1.0.0"},
                    "dataSources": {"mainService": {"uri": root, "type": "OData",
                                                    "settings": {"odataVersion": "4.0"}}}},
        "sap.ui": {"technology": "UI5", "deviceTypes": {"desktop": True, "tablet": True, "phone": True}},
        "sap.ui5": {
            "dependencies": {"minUI5Version": "1.120.0", "libs": {"sap.m": {}, "sap.ui.core": {}, "sap.fe.templates": {}}},
            "models": {"": {"dataSource": "mainService", "preload": True,
                            "settings": {"operationMode": "Server", "autoExpandSelect": True, "earlyRequests": True}}},
            "routing": {
                "routes": [{"pattern": ":?query:", "name": "List", "target": "List"},
                           {"pattern": entity + "({key}):?query:", "name": "Object", "target": "Object"}],
                "targets": {
                    "List": {"type": "Component", "id": "List", "name": "sap.fe.templates.ListReport",
                             "options": {"settings": {"contextPath": "/" + entity, "variantManagement": "None",
                                                      "initialLoad": "Enabled",
                                                      "navigation": {entity: {"detail": {"route": "Object"}}}}}},
                    "Object": {"type": "Component", "id": "Object", "name": "sap.fe.templates.ObjectPage",
                               "options": {"settings": {"contextPath": "/" + entity, "editableHeaderContent": False}}},
                },
            },
        },
        "sap.fe": {"app": {"title": title}},
    }


def make_handler(tcode, s, service):
    title = f"{tcode}, the new app"

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def proxy(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            path = self.path + ("&" if "?" in self.path else "?") + "sap-client=" + s.client
            headers = {"Authorization": s.auth}
            for h in PASS_HEADERS:
                if self.headers.get(h):
                    headers[h] = self.headers[h]
            req = urllib.request.Request(s.url + path, data=body, method=self.command, headers=headers)
            try:
                resp = s.opener.open(req, timeout=120)
                code, rh, data = resp.status, resp.headers, resp.read()
            except urllib.error.HTTPError as e:
                code, rh, data = e.code, e.headers, e.read()
            self.send_response(code)
            for h in BACK_HEADERS:
                if rh.get(h):
                    self.send_header(h, rh[h])
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def route(self):
            p = self.path.split("?")[0]
            if p.startswith("/sap/"):
                return self.proxy()
            if p in ("/", "/index.html"):
                return self.send(200, INDEX.format(title=title), "text/html; charset=utf-8")
            if p == "/Component.js":
                return self.send(200, COMPONENT, "application/javascript")
            if p == "/manifest.json":
                return self.send(200, json.dumps(manifest(title, service["root"], service["entity"])),
                                 "application/json")
            return self.send(404, "not found", "text/plain")

        do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = do_HEAD = route

    return Handler


def main_entity(s, root):
    _, _, text = s.request("GET", root + "$metadata", accept="application/xml")
    sets = re.findall(r'<EntitySet Name="([^"]+)"', text)
    return sets[0] if sets else None


def main(tcode, port=8100):
    s = sap.Sap()
    with open(os.path.join(ROOT, "runs", tcode, "port", "service.json")) as f:
        service = json.load(f)
    service.setdefault("entity", main_entity(s, service["root"]))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), make_handler(tcode, s, service))
    print(f"{tcode} new app on http://127.0.0.1:{port}/ (entity set {service['entity']})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main(sys.argv[1].upper(), int(sys.argv[2]) if len(sys.argv) > 2 else 8100)
