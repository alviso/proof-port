"""Create, change, activate and publish RAP objects through ADT. This is the port agent's tool.

    python3 factory/rap.py put KIND NAME FILE [--desc TEXT] [--part implementations]
    python3 factory/rap.py activate KIND:NAME [KIND:NAME ...]
    python3 factory/rap.py binding NAME SERVICE_DEFINITION [--desc TEXT]
    python3 factory/rap.py publish NAME
    python3 factory/rap.py get KIND NAME [--part implementations]
    python3 factory/rap.py delete KIND NAME
    python3 factory/rap.py sql "SELECT ..."

KIND is DDLS (CDS view), BDEF (behavior definition), CLAS (class; --part implementations is the local types
include of a behavior pool), DDLX (metadata extension), SRVD (service definition) or SRVB (service binding).
Objects are local ($TMP). Credentials come from SAP_ENV, the agent's own SAP user.
"""
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(__file__))
import sap  # noqa: E402

KINDS = {
    "DDLS": ("/sap/bc/adt/ddic/ddl/sources", "application/vnd.sap.adt.ddlSource+xml",
             'ddl:ddlSource xmlns:ddl="http://www.sap.com/adt/ddic/ddlsources"', "DDLS/DF"),
    "BDEF": ("/sap/bc/adt/bo/behaviordefinitions", "application/vnd.sap.adt.blues.v1+xml",
             'blue:blueSource xmlns:blue="http://www.sap.com/wbobj/blue"', "BDEF/BDO"),
    "CLAS": ("/sap/bc/adt/oo/classes", "application/vnd.sap.adt.oo.classes.v4+xml",
             'class:abapClass xmlns:class="http://www.sap.com/adt/oo/classes" class:final="true" '
             'class:visibility="public"', "CLAS/OC"),
    "DDLX": ("/sap/bc/adt/ddic/ddlx/sources", "application/vnd.sap.adt.ddic.ddlx.v1+xml",
             'ddlx:ddlxSource xmlns:ddlx="http://www.sap.com/adt/ddic/ddlxsources"', "DDLX/EX"),
    "SRVD": ("/sap/bc/adt/ddic/srvd/sources", "application/vnd.sap.adt.ddic.srvd.v1+xml",
             'srvd:srvdSource xmlns:srvd="http://www.sap.com/adt/ddic/srvdsources" srvd:srvdSourceType="S"',
             "SRVD/SRV"),
    "SRVB": ("/sap/bc/adt/businessservices/bindings", "application/vnd.sap.adt.businessservices.servicebinding.v2+xml",
             None, "SRVB/SVB"),
}


def q(name):
    return urllib.parse.quote(name.lower(), safe="")


def uri(kind, name):
    return f"{KINDS[kind][0]}/{q(name)}"


def source_uri(kind, name, part=None):
    if kind == "CLAS" and part:
        return f"{uri(kind, name)}/includes/{part}"
    return f"{uri(kind, name)}/source/main"


def exists(s, kind, name):
    try:
        s.request("GET", uri(kind, name), accept="*/*")
        return True
    except sap.SapError as e:
        if "HTTP 404" in str(e):
            return False
        raise


def create(s, kind, name, desc):
    collection, ctype, root, adt_type = KINDS[kind]
    tag = root.split()[0]
    body = (f'<?xml version="1.0" encoding="UTF-8"?><{root} xmlns:adtcore="http://www.sap.com/adt/core" '
            f'adtcore:description="{desc}" adtcore:name="{name.upper()}" adtcore:type="{adt_type}" '
            f'adtcore:masterLanguage="EN" adtcore:responsible="{s.user}">'
            f'<adtcore:packageRef adtcore:name="{sap.PACKAGE}"/></{tag}>')
    s.post(collection, body, content_type=ctype)


def lock(s, object_uri):
    _, _, text = s.post(f"{object_uri}?_action=LOCK&accessMode=MODIFY", stateful=True,
                        accept="application/vnd.sap.as+xml;charset=UTF-8;dataname=com.sap.adt.lock.result")
    return urllib.parse.quote(re.search(r"<LOCK_HANDLE>(.*?)</LOCK_HANDLE>", text).group(1), safe="")


def unlock(s, object_uri, handle):
    try:
        s.post(f"{object_uri}?_action=UNLOCK&lockHandle={handle}", stateful=True)
    except sap.SapError as e:
        print(f"warning: unlock failed: {e}")


def put(s, kind, name, text, desc=None, part=None):
    if not exists(s, kind, name):
        create(s, kind, name, desc or name)
    handle = lock(s, uri(kind, name))
    try:
        s.request("PUT", f"{source_uri(kind, name, part)}?lockHandle={handle}", text,
                  content_type="text/plain; charset=utf-8", stateful=True)
    finally:
        unlock(s, uri(kind, name), handle)


def get(s, kind, name, part=None):
    return s.source(source_uri(kind, name, part))


def activate(s, objects):
    refs = "".join(f'<adtcore:objectReference adtcore:uri="{uri(k, n)}" adtcore:name="{n.upper()}"/>'
                   for k, n in objects)
    body = ('<?xml version="1.0" encoding="UTF-8"?><adtcore:objectReferences '
            f'xmlns:adtcore="http://www.sap.com/adt/core">{refs}</adtcore:objectReferences>')
    _, _, text = s.post("/sap/bc/adt/activation?method=activate&preauditRequested=true", body,
                        content_type="application/xml")
    messages = []
    for m in re.finditer(r"<msg\b([^>]*)>(.*?)</msg>", text, re.S):
        attrs, inner = m.group(1), m.group(2)
        kind = re.search(r'type="(\w)"', attrs)
        where = re.search(r'href="([^"]*)"', attrs)
        txt = " ".join(re.findall(r"<txt>(.*?)</txt>", inner, re.S))
        messages.append(f"{kind.group(1) if kind else '?'} {urllib.parse.unquote(where.group(1)) if where else ''}: "
                        f"{txt}")
    return messages


def binding(s, name, srvd, desc=None):
    collection, ctype, _, _ = KINDS["SRVB"]
    body = (f'<?xml version="1.0" encoding="UTF-8"?><srvb:serviceBinding '
            f'xmlns:adtcore="http://www.sap.com/adt/core" xmlns:srvb="http://www.sap.com/adt/ddic/ServiceBindings" '
            f'srvb:releaseSupported="false" srvb:published="false" srvb:bindingCreated="true" '
            f'adtcore:description="{desc or name}" adtcore:name="{name.upper()}" adtcore:type="SRVB/SVB" '
            f'adtcore:masterLanguage="EN" adtcore:responsible="{s.user}">'
            f'<adtcore:packageRef adtcore:name="{sap.PACKAGE}"/>'
            f'<srvb:services srvb:name="{name.upper()}"><srvb:content srvb:version="0001">'
            f'<srvb:serviceDefinition adtcore:name="{srvd.upper()}"/></srvb:content></srvb:services>'
            f'<srvb:binding srvb:type="ODATA" srvb:version="V4" srvb:category="0">'
            f'<srvb:implementation adtcore:name=""/></srvb:binding></srvb:serviceBinding>')
    s.post(collection, body, content_type=ctype)


def publish(s, name):
    body = ('<?xml version="1.0" encoding="UTF-8"?><adtcore:objectReferences '
            'xmlns:adtcore="http://www.sap.com/adt/core">'
            f'<adtcore:objectReference adtcore:type="SRVB/SVB" adtcore:name="{name.upper()}"/>'
            '</adtcore:objectReferences>')
    _, _, text = s.post(f"/sap/bc/adt/businessservices/odatav4/publishjobs?servicename={name.upper()}"
                        "&serviceversion=0001", body, content_type="application/xml", accept="application/vnd.sap.as+xml")
    return sap.short(text, 600)


def delete(s, kind, name):
    handle = lock(s, uri(kind, name))
    s.request("DELETE", f"{uri(kind, name)}?lockHandle={handle}", stateful=True)


def main(argv):
    args, opts = [], {}
    it = iter(argv)
    for a in it:
        if a.startswith("--"):
            opts[a[2:]] = next(it)
        else:
            args.append(a)
    s = sap.Sap()
    cmd = args[0]
    prefix = os.environ.get("RAP_PREFIX", "ZPP_").upper()
    names = [a.split(":", 1)[-1] for a in args[1:3]] if cmd in ("put", "get", "delete", "binding") else \
        [a.split(":", 1)[-1] for a in args[1:]] if cmd in ("activate", "publish") else []
    if cmd in ("put", "get", "delete") and len(args) > 2:
        names = [args[2]]
    bad = [n for n in names if not n.upper().startswith(prefix)]
    if bad:
        print(f"refused: names must start with {prefix}: {bad}")
        return 2
    if cmd == "put":
        kind, name, path = args[1].upper(), args[2], args[3]
        with open(path) as f:
            put(s, kind, name, f.read(), opts.get("desc"), opts.get("part"))
        print(f"saved {kind} {name.upper()} (not active yet: run activate)")
    elif cmd == "get":
        print(get(s, args[1].upper(), args[2], opts.get("part")))
    elif cmd == "activate":
        objects = [tuple(a.split(":", 1)) for a in args[1:]]
        messages = activate(s, [(k.upper(), n) for k, n in objects])
        errors = [m for m in messages if m.startswith(("E", "A"))]
        print("\n".join(messages) if messages else "activated")
        return 1 if errors else 0
    elif cmd == "binding":
        binding(s, args[1], args[2], opts.get("desc"))
        print(f"created service binding {args[1].upper()} for {args[2].upper()}; activate it, then publish")
    elif cmd == "publish":
        print(publish(s, args[1]))
    elif cmd == "delete":
        delete(s, args[1].upper(), args[2])
        print("deleted")
    elif cmd == "sql":
        print(json.dumps(s.sql(args[1], rows=int(opts.get("rows", 500))), indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
