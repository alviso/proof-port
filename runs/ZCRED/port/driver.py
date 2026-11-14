"""Do with the new service what the old ZCRED screens did with the typed steps.

The old transaction is two screens. Screen 0100 takes a customer number and any key looks it up; screen 0200
shows what was loaded, takes a new credit limit and a reason, and saves on the function code SAVE. The new app is
a Fiori Elements list report over the same customers with two actions: ChooseCustomer (the number typed on screen
0100) and ChangeCreditLimit (the new limit and the reason, pressed with SAVE on screen 0200).

This module only translates: which field is which property, what a function code means, and what the typed text is
worth. Every check is in the RAP behavior pool. The one thing decided here is what the app's own input fields do
before anything is called:

  * a field holds at most as many characters as the old screen's field did; more and the step cannot be typed;
  * the new limit is a number field in the SAP user's notation (1.234,56) and the app refuses what is not one,
    with the same two messages the old screen showed (recorded with client.ui, never a rule);
  * '!' in the first position clears a field, as it does on any SAP screen;
  * the new limit is read-only when the service says so (CreditLimitFc = 1, which the service derives from the
    customer's priority), so the app offers no field to type in.

A step sequence stops being processed when the old screen would have stopped: an error message (batch input gives
up), a saved change (the old transaction ends), a system command that leaves the transaction, or a step naming a
screen that is not the one in front of the user.
"""

import urllib.parse
from decimal import Decimal

SERVICE_NAMESPACE = "com.sap.gateway.srvd.zpp_cr_ui_credit.v0001"
ENTITY_SET = "Customer"

# the input fields of the old screens and how many characters each one holds
SCREEN_FIELDS = {
    "0100": {"GV_KUNNR": 10},
    "0200": {"GV_NEW_LIMIT": 17, "GV_REASON": 60},
}

# what the dynpro says about text it cannot read as a number
MSG_FORMAT = "Formatting error in the field GV_NEW_LIMIT; see next message"
ERR_SIGN = "Specify positive values only"
ERR_NUMERIC = "Enter a numeric value"
ERR_PATTERN = "Input must be in the format _.___.___.___.__~,__"
ERR_TOO_LONG = "Entry too long (enter in the format _.___.___.___.__~,__)"

# a system command typed into the command field leaves the transaction
MSG_TERMINATED = "The transaction was terminated by the user"
LEAVE_WITH_MESSAGE = ("/N", "/I")


def absolute(client):
    """service.json names the service by its path; point the client at it on its own system."""
    if "://" not in client.root:
        client.root = client.s.url.rstrip("/") + "/" + client.root.lstrip("/")


def namespace(client):
    """The namespace the bound actions live in; the service metadata of the binding names it."""
    return SERVICE_NAMESPACE


def parse_amount(text):
    """What the old screen's DEC field makes of typed text, in this user's notation (1.234,56).

    Returns (value, None) or (None, message).
    """
    if text[:1] == "!":                                   # '!' clears the field
        return Decimal("0.00"), None
    body = text.strip(" ")
    if body == "":
        return Decimal("0.00"), None
    if "-" in body:                                       # the field has no sign
        return None, ERR_SIGN
    if not any(c.isdigit() for c in body):                # nothing to read as a number
        return (Decimal("0.00"), None) if body == "," else (None, ERR_PATTERN)
    if "+" in body:
        return None, ERR_NUMERIC
    whole, separator, fraction = body.partition(",")
    if separator and fraction and not fraction.isdigit():  # junk behind the decimal separator
        return None, ERR_NUMERIC
    if len(fraction) > 2:
        return None, ERR_PATTERN
    groups = whole.split(".")
    if len(groups) > 1:
        if any(len(g) != 3 or not g.isdigit() for g in groups[1:]):
            return None, ERR_PATTERN
        if groups[0] and (len(groups[0]) > 3 or not groups[0].isdigit()):
            return None, ERR_PATTERN
    elif groups[0] and not groups[0].isdigit():
        return None, ERR_PATTERN
    digits = "".join(groups)
    if len(digits.lstrip("0")) > 13:                      # more than the field can show
        return None, ERR_TOO_LONG
    return Decimal((digits or "0") + "." + (fraction + "00")[:2]), None


def function_code(step):
    """The function code of a step, as the screen would see it."""
    code = str(step.get("ok", "/00")).strip().upper()
    if code.startswith("="):
        code = code[1:].strip()
    return code or "/00"


def errors(response):
    return [m for m in response.messages if m.get("type") in ("E", "A", "X")]


class Session:
    """One run of the transaction: which screen the user is on and what the fields hold."""

    def __init__(self, client):
        absolute(client)
        self.client = client
        self.screen = "0100"
        self.over = False
        self.customer = None
        self.limit = Decimal("0.00")
        self.reason = ""
        self.locked = False
        self.typed = {}

    # -- the steps ---------------------------------------------------------------------------------------------

    def step(self, step):
        if self.over or step.get("screen") != self.screen:
            return False
        fields = SCREEN_FIELDS[self.screen]
        for name, text in (step.get("fields") or {}).items():
            text = "" if text is None else str(text)
            if name not in fields or len(text) > fields[name]:
                return False                               # the app has no such field, or it is too short
            if self.screen == "0200" and name == "GV_NEW_LIMIT" and self.locked:
                return False                               # the service says the limit cannot be typed
            self.typed[name] = text
        code = function_code(step)
        if code.startswith("/") and code != "/00":
            if code.startswith(LEAVE_WITH_MESSAGE):
                self.client.ui("A", MSG_TERMINATED)
            return False                                   # a system command leaves the transaction
        if self.screen == "0100":
            return self.open_customer()
        return self.screen_0200(code)

    # -- screen 0100 -------------------------------------------------------------------------------------------

    def open_customer(self):
        number = self.typed.get("GV_KUNNR", "").upper().rstrip(" ")
        chosen = self.client.post("%s/%s.ChooseCustomer" % (ENTITY_SET, namespace(self.client)),
                                  {"Customer": number})
        if errors(chosen):
            self.over = True
            return False
        shown = self.client.get("%s(%s)?$select=CreditLimit,CreditLimitFc"
                                % (ENTITY_SET, key(number)))
        if errors(shown):
            self.over = True
            return False
        self.customer = number
        self.limit = Decimal(str(shown.body.get("CreditLimit", "0")))
        self.locked = str(shown.body.get("CreditLimitFc", "7")) == "1"
        self.reason = ""                                   # MODULE user_command_0100 clears the reason
        self.typed = {}
        self.screen = "0200"
        return True

    # -- screen 0200 -------------------------------------------------------------------------------------------

    def screen_0200(self, code):
        if "GV_NEW_LIMIT" in self.typed:
            value, message = parse_amount(self.typed.pop("GV_NEW_LIMIT"))
            if message:
                self.client.ui("E", MSG_FORMAT)
                self.client.ui("E", message)
                self.over = True
                return False
            self.limit = value
        if "GV_REASON" in self.typed:
            text = self.typed.pop("GV_REASON")
            self.reason = "" if text[:1] == "!" else text
        if code != "SAVE":
            return True                                    # nothing happens; the fields keep what they hold
        self.client.post("%s(%s)/%s.ChangeCreditLimit" % (ENTITY_SET, key(self.customer),
                                                          namespace(self.client)),
                         {"NewLimit": float(self.limit), "Reason": self.reason})
        self.over = True                                   # saved: the old transaction ends here
        return False


def key(customer):
    return "'" + urllib.parse.quote(customer.replace("'", "''"), safe="") + "'"


def run(client, steps):
    session = Session(client)
    for step in steps:
        if not session.step(step):
            return
