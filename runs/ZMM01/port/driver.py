"""Do with the new OData V4 service what a case's screen steps did on the old ZMM01 screen.

This file holds no business rule. It is the old screen's keyboard and memory:

  * which typed field is which service property, and which tab it sits on,
  * what the characters a user types mean (upper case, `!`, 1.234,56, field width,
    the fixed values a list box offers) -- the dynpro converts input and checks the
    data element's domain before any ABAP of the program runs, exactly as a Fiori
    field does before it calls anything, so those messages are reported with
    client.ui and nothing else here decides them,
  * what each function code does to that memory: which tab is open, which rows the
    table control has, and when Save sends it all to the service.

Every check of the program itself -- a missing name, a type, a price at or below
zero, a variant without an identifier, an EAN that is not thirteen digits -- lives
in the RAP behaviour pool and reaches us only as a message from the service.

A case is one run of the old transaction by batch input, and one press of Save ends
it: the program commits, and a COMMIT WORK in a batch input session closes the
transaction, so every later step is dropped. Steps are dropped the same way when the
old screen would have stopped for want of the field a step types.
"""

from urllib.parse import quote

# Entity set of the article, and the composition that carries its variants.
ARTICLES = "RetailArticle"
VARIANTS = "_Variant"

# Pressing Save sends the whole screenful in one request, so the service checks and
# writes it in one go, the way the old program did between PERFORM check_all and
# COMMIT WORK. The V4 runtime on this system refuses a create whose body carries a
# nested collection (its upload virus scan profile is not active), so Save is this
# action rather than a deep insert -- the same shape a draft app's activation has.
PRESS_SAVE = "%s/com.sap.gateway.srvd.zpp_mm_ui_article.v0001.pressSave" % ARTICLES

# How the dynpro treats a field. TEXT is a plain character field: upper cased,
# trailing blanks dropped. NUMBER is the price template __.___.___.___,__. CHECK
# is a check box, which takes the tick or nothing and is not upper cased, so a
# small x is not a tick. A tuple is a field whose data element has fixed values,
# which the dynpro checks before any of the program's own code runs.
# MARK is a check box too, but its column has no data element and so no fixed
# values: it keeps whatever single character was typed, and only a capital X
# counts as a tick when Delete looks at it.
TEXT = "text"
NUMBER = "number"
CHECK = "check"
CHECK_FREE = "check_free"
ARTICLE_TYPES = ("HARD", "SOFT", "ACCE", "CONS")

# The price is DEC 13,2, so eleven digits before the comma and no more.
PRICE_INTEGER_DIGITS = 11

# Screen 0210, the Basic data tab: typed name -> (property, dynpro width, kind)
TAB1_FIELDS = {
    "ZRET_S_ART-ARTICLE_NAME": ("ArticleName", 60, TEXT),
    "ZRET_S_ART-ARTICLE_TYPE": ("ArticleType", 4, ARTICLE_TYPES),
    "ZRET_S_ART-BASE_UOM": ("BaseUom", 3, TEXT),
    "ZRET_S_ART-ACTIVE_FLAG": ("ActiveFlag", 1, CHECK),
}

# Screen 0220, the Price tab
TAB2_FIELDS = {
    "ZRET_S_ART-PRICE": ("Price", 17, NUMBER),
    "ZRET_S_ART-CURRENCY": ("Currency", 5, TEXT),
    "ZRET_S_ART-GENERIC_ARTICLE_ID": ("GenericArticleId", 10, TEXT),
}

# Screen 0230, the Variants tab: one column of the table control
VARIANT_FIELDS = {
    "MARK": ("mark", 1, CHECK_FREE),
    "VARIANT_ID": ("VariantId", 4, TEXT),
    "COLOR": ("Color", 20, TEXT),
    "SIZE_CODE": ("SizeCode", 6, TEXT),
    "EAN": ("Ean", 18, TEXT),
    "PRICE": ("Price", 17, NUMBER),
}

TAB_OF_FIELD = {}
for _name in TAB1_FIELDS:
    TAB_OF_FIELD[_name] = "TAB1"
for _name in TAB2_FIELDS:
    TAB_OF_FIELD[_name] = "TAB2"

# The table control starts with five lines and the screen has room for six, so a
# sixth line can only be typed into after Add has appended one, and a seventh
# never exists.
TABLE_CONTROL_MIN_LINES = 5
TABLE_CONTROL_VISIBLE_LINES = 6

GO_CODES = ("GO", "ENTER", "/00", "")
LEAVE_CODES = ("BACK", "EXIT", "CANC")

# The old program pre-fills a new article's base unit with the internal code ST,
# and the screen field's CUNIT conversion exit shows it in the log-on language --
# PC in English. What the screen shows is what a user sends back, so that is what
# this buffer holds; the service converts it to ST again, as the old screen did.
DEFAULT_BASE_UOM_AS_SHOWN = "PC"


class Stop(Exception):
    """The old screen would go no further in this case, so neither do we."""


def blank_row():
    return {"mark": "", "VariantId": "", "Color": "", "SizeCode": "", "Ean": "", "Price": ""}


class Screen:
    """The old transaction's memory between two key presses."""

    def __init__(self, client):
        self.client = client
        self.screen = "0100"
        self.article_id = ""
        self.header = {}
        self.rows = []
        self.tab = "TAB1"

    # -- what the keyboard does to a field -------------------------------------

    def typed(self, raw, width, kind, dynpro_field):
        """One field as the dynpro takes it, or Stop if it would not take it."""
        if raw == "!":
            # A lone exclamation mark empties the field.
            return ""
        if len(raw) > width:
            # Batch input says the value is longer than the field and gives up on
            # the case. It is not an error message, and nothing is saved.
            raise Stop()
        if kind == NUMBER:
            # A numeric field is right aligned, so blanks on either side are no part
            # of what was typed.
            return self.number(raw.strip(), dynpro_field)
        if kind in (CHECK, CHECK_FREE):
            # A check box is not upper cased. The active flag's data element has
            # fixed values, so only the tick and nothing pass; the variant mark has
            # none, so anything a finger lands on is kept as it was typed.
            value = raw.rstrip()
            if kind == CHECK and value not in ("", "X"):
                self.format_error(dynpro_field, "Enter a valid value")
            return value
        value = raw.upper().rstrip()
        if kind != TEXT and value != "" and value not in kind:
            self.format_error(dynpro_field, "Enter a valid value")
        return value

    def number(self, value, dynpro_field):
        """A price as this user types it: 1.234,56. Returns a decimal string."""
        if not value:
            return ""
        if "-" in value:
            # The domain carries no sign, so the dynpro refuses a negative number
            # however it is written, SAP's trailing minus included.
            self.format_error(dynpro_field, "Specify positive values only")
        if any(c not in "0123456789.," for c in value) or value.count(",") > 1:
            self.format_error(dynpro_field, "Enter a numeric value")
        parts = value.split(",")
        whole, fraction = parts[0], (parts[1] if len(parts) == 2 else "")
        if "." in fraction or len(fraction) > 2:
            self.template_error(dynpro_field)
        groups = whole.split(".")
        if len(groups) > 1:
            # Thousands separators have to group the digits in threes.
            if not 1 <= len(groups[0]) <= 3 or any(len(g) != 3 for g in groups[1:]):
                self.template_error(dynpro_field)
        digits = "".join(groups)
        if len(digits.lstrip("0")) > PRICE_INTEGER_DIGITS:
            self.format_error(dynpro_field, "Entry too long (enter in the format __.___.___.___,__)")
        return "%s.%s" % (digits or "0", (fraction + "00")[:2])

    def template_error(self, dynpro_field):
        self.format_error(dynpro_field, "Input must be in the format __.___.___.___,__")

    def format_error(self, dynpro_field, detail):
        """What the dynpro puts on the status line, then it stops the case."""
        self.client.ui("E", "Formatting error in the field %s; see next message" % dynpro_field)
        self.client.ui("E", detail)
        raise Stop()

    # -- the two screens -------------------------------------------------------

    def step(self, step):
        want = str(step.get("screen", "")).zfill(4)
        if want != self.screen:
            # Batch input found no data for the screen the program put up.
            raise Stop()
        fields = step.get("fields") or {}
        code = (step.get("ok") or "").upper()
        if self.screen == "0100":
            self.step_0100(fields, code)
        else:
            self.step_0200(fields, code)

    def step_0100(self, fields, code):
        for name, raw in fields.items():
            if name.upper() != "ZRET_S_ART-ARTICLE_ID":
                raise Stop()
            self.article_id = self.typed(raw, 20, TEXT, "ZRET_S_ART-ARTICLE_ID")
        if code in LEAVE_CODES:
            # The program leaves. Nothing is written.
            raise Stop()
        if code not in GO_CODES:
            return
        if not self.article_id:
            # The article is a required field of the dynpro, so the screen never
            # reaches the program with it empty.
            self.client.ui("E", "Formatting error in the field ZRET_S_ART-ARTICLE_ID; see next message")
            self.client.ui("E", 'Make an entry in mandatory field "Article"')
            raise Stop()
        self.load()
        self.screen = "0200"
        self.tab = "TAB1"

    def load(self):
        """Open the article, the way the list report does. An article that is not
        there is a new one, and the old program pre-fills three of its fields."""
        where = quote("ArticleId eq '%s'" % self.article_id.replace("'", "''"), safe="")
        found = self.client.get("%s?$filter=%s&$expand=%s" % (ARTICLES, where, VARIANTS))
        rows = (found.body or {}).get("value") or []
        if rows:
            got = rows[0]
            self.header = {
                "ArticleName": got.get("ArticleName") or "",
                "ArticleType": got.get("ArticleType") or "",
                "BaseUom": got.get("BaseUom") or "",
                "ActiveFlag": "X" if got.get("ActiveFlag") else "",
                "Price": str(got.get("Price") or "0"),
                "Currency": got.get("Currency") or "",
                "GenericArticleId": got.get("GenericArticleId") or "",
            }
            self.rows = []
            for variant in got.get(VARIANTS) or []:
                row = blank_row()
                row["VariantId"] = variant.get("VariantId") or ""
                row["Color"] = variant.get("Color") or ""
                row["SizeCode"] = variant.get("SizeCode") or ""
                row["Ean"] = variant.get("Ean") or ""
                row["Price"] = str(variant.get("Price") or "")
                self.rows.append(row)
        else:
            self.header = {
                "ArticleName": "",
                "ArticleType": "",
                "BaseUom": DEFAULT_BASE_UOM_AS_SHOWN,
                "ActiveFlag": "X",
                "Price": "",
                "Currency": "EUR",
                "GenericArticleId": "",
            }
            self.rows = []
        self.pad()

    def pad(self):
        while len(self.rows) < TABLE_CONTROL_MIN_LINES:
            self.rows.append(blank_row())

    def step_0200(self, fields, code):
        # Back, Exit and Cancel do nothing at all here. The program has a module
        # that would ask whether to throw unsaved data away and return to the first
        # screen, but these three codes are not exit commands in this screen's
        # status, so that module never runs and no other code claims them: the
        # second screen simply stays where it is, with everything still typed in it.
        self.put_fields(fields)
        if code in ("TAB1", "TAB2", "TAB3"):
            self.tab = code
        elif code == "ADD" and self.tab == "TAB3":
            # Add and Delete are buttons of the variants subscreen, and only the
            # open subscreen's code runs. Pressed from another tab they do nothing.
            self.rows.append(blank_row())
        elif code == "DEL" and self.tab == "TAB3":
            self.rows = [r for r in self.rows if r["mark"] != "X"]
        elif code == "SAVE":
            self.save()
            raise Stop()
        self.pad()

    def put_fields(self, fields):
        for name, raw in fields.items():
            name = name.upper()
            if name.startswith("ZRET_S_ART_VAR-"):
                self.put_variant_field(name, raw)
                continue
            if TAB_OF_FIELD.get(name) != self.tab:
                # The field belongs to a tab that is not open, so it is not on the
                # screen at all and batch input stops.
                raise Stop()
            prop, width, domain = (TAB1_FIELDS.get(name) or TAB2_FIELDS.get(name))
            self.header[prop] = self.typed(raw, width, domain, name)

    def put_variant_field(self, name, raw):
        if self.tab != "TAB3":
            raise Stop()
        column, _, rest = name[len("ZRET_S_ART_VAR-"):].partition("(")
        row_number = int(rest.rstrip(")")) if rest else 1
        if column not in VARIANT_FIELDS:
            raise Stop()
        if row_number > TABLE_CONTROL_VISIBLE_LINES or row_number > len(self.rows):
            # Past the last line the table control shows, or on a line it shows but
            # has no entry for: either way the field cannot be typed into.
            raise Stop()
        prop, width, domain = VARIANT_FIELDS[column]
        dynpro_field = "ZRET_S_ART_VAR-%s" % column
        self.rows[row_number - 1][prop] = self.typed(raw, width, domain, dynpro_field)

    # -- Save ------------------------------------------------------------------

    def save(self):
        """One press of Save: the article and every line of the variant table go to
        the service together, and the service decides what they mean."""
        payload = {
            "ArticleId": self.article_id,
            "ArticleName": self.header.get("ArticleName", ""),
            "ArticleType": self.header.get("ArticleType", ""),
            "BaseUom": self.header.get("BaseUom", ""),
            "ActiveFlag": self.header.get("ActiveFlag", ""),
            "Price": float(self.header.get("Price") or 0),
            "Currency": self.header.get("Currency", ""),
            "GenericArticleId": self.header.get("GenericArticleId", ""),
            "SaveTab": self.tab,
        }
        # Every line the table control shows, filled or not, under the number it
        # sits on. Which of them is a variant is the service's call, not ours.
        for number in range(1, TABLE_CONTROL_VISIBLE_LINES + 1):
            row = self.rows[number - 1] if number <= len(self.rows) else blank_row()
            payload["Row%dVariantId" % number] = row["VariantId"]
            payload["Row%dColor" % number] = row["Color"]
            payload["Row%dSizeCode" % number] = row["SizeCode"]
            payload["Row%dEan" % number] = row["Ean"]
            payload["Row%dPrice" % number] = float(row["Price"] or 0)
        self.client.post(PRESS_SAVE, payload)


def run(client, steps):
    screen = Screen(client)
    try:
        for step in steps:
            screen.step(step)
    except Stop:
        return
