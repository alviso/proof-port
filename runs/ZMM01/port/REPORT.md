# ZMM01 ported to RAP

Transaction ZMM01 (article maintenance, screens 0100 and 0200 with three tabbed subscreens 0210, 0220, 0230) is now
a RAP business object on the same two tables, behind an OData V4 UI service with a Fiori Elements list report and
object page.

**Grader result: 117 of 117 of my own cases behave the same; tables restored; no drift.** The cases are in
`my_cases.json`, written from the extract and from what the oracle answered when I asked it; the grader's own
report is in `grade_my_cases.json`.

```
python3 factory/grade.py ZMM01 runs/ZMM01/port/my_cases.json
117 of 117 cases behave the same; tables restored: True; drift: 0
```

---

## 1. What I built

All on SAP, all active, the binding published.

| Object | Kind | What it is |
|---|---|---|
| `ZPP_MM_R_ARTICLE` | DDLS | Root view entity over `ZRET_T_ARTICLE`, composition of the variants |
| `ZPP_MM_R_VARIANT` | DDLS | View entity over `ZRET_T_ART_VAR`, association to parent |
| `ZPP_MM_P_SAVE` | DDLS | Abstract entity: the parameter of the Save action |
| `ZPP_MM_R_ARTICLE` | BDEF | Behaviour definition, `managed`, `strict ( 2 )` |
| `ZPP_MM_BP_ARTICLE` | CLAS | Behaviour pool (global class and its local implementation) |
| `ZPP_MM_X_ARTICLE` | DDLX | UI annotations of the article: header, facets, line items, field groups |
| `ZPP_MM_X_VARIANT` | DDLX | UI annotations of the variant table |
| `ZPP_MM_UI_ARTICLE` | SRVD | Service definition, exposing `RetailArticle` and `RetailArticleVariant` |
| `ZPP_MM_UI_ARTICLE_O4` | SRVB | OData V4 UI service binding, published |

Service root: `/sap/opu/odata4/sap/zpp_mm_ui_article_o4/srvd/sap/zpp_mm_ui_article/0001/`

The source of each one is in `src/`, byte for byte what is active (SAP stores the files with CRLF line endings;
apart from that they are identical, which I checked by downloading each one back with `rap.py get` and diffing).

The three tabs became three sections of one object page: Basic data (identification), Price (a field group) and
Variants (the child table). Nothing is hidden behind a tab any more, which matters for one old behaviour described
in §4.

### Two fields in the service that are not in the tables

`RetailArticle.SaveTab` and `RetailArticleVariant.ScreenRow` are CDS casts with no counterpart in the database (the
behaviour definition activates with a warning saying exactly that, which is the intention). They carry old-screen
state that the new object genuinely needs in order to behave the same:

* **`SaveTab`** — which tab was open when Save was pressed. The old program runs the open subscreen's PAI module
  before `FORM check_all`, so the open tab decides *which message comes back first* and *which default value gets
  filled in*. Without it I could not reproduce either (§4 has the detail). Both metadata extensions hide it.
* **`ScreenRow`** — the row a variant sat on in the old table control. The old messages name the row
  ("`Variante ligne 3 : ...`"), and after a deletion the rows shift up, so the number has to travel with the line.
  When it is absent (a person adding a row in the app), the validation falls back to the line's position.

### Why Save is an action and not a deep insert

Pressing Save on the old screen checks and writes the article and all its variant rows **in one go**: one
`PERFORM check_all`, one `MODIFY`, one `COMMIT WORK`. In OData that is one request, and the natural shape is a deep
insert — a POST to `RetailArticle` with the variants nested.

That does not work on this system. Any create whose body carries a nested collection (even an empty one) is refused
before it reaches any of my code:

```
Virus scan profile /IWBEP/V4/ODATA_UPLOAD is not active (refer to SAP note 3027559)
```

The V4 runtime treats a deep-insert payload as an upload and wants a virus scan profile that is not active here.
Activating it would mean changing an object outside the `ZPP_MM_` namespace, which the rules of this task forbid, so
I did not. A flat create (no nested collection) works, and so do action calls.

So Save is a static action, `pressSave`, which takes one screenful — the article's fields plus the six lines of the
variant table — and does one `MODIFY ENTITIES ... CREATE ... CREATE BY \_variant`. This is the same shape a
draft-enabled Fiori app has, where Save is the framework's own activation action rather than a deep insert.

**The action carries no rule.** It copies its parameters into the entities and hands back whatever the framework
says. Every check and every derived value is in the determination and the validation, which a person creating or
editing an article through the object page goes through just the same.

Six rows is not an arbitrary cap: the old table control shows six lines and can never show more, which I confirmed
against the old screen (a seventh row does not exist on the dynpro, so nothing can be typed into it).

---

## 2. Every rule of the old program, and where it lives now

### Checks and derived values — in the RAP object

| Old code | Message or effect | Where now |
|---|---|---|
| `MODULE check_0210` | `Renseignez le nom de l'article` | validation `checkArticle` |
| `MODULE check_0210` | `Choisissez un type d'article` | validation `checkArticle` |
| `MODULE check_0210` | base unit defaults to `ST` when the Basic data tab is the open one | determination `prepareSave` |
| `MODULE check_0220` | `Le prix doit être supérieur à zéro` | validation `checkArticle` |
| `MODULE check_0220` | currency defaults to `EUR` when the Price tab is the open one | determination `prepareSave` |
| `FORM check_all` | the same three, then the variant rows in order | validation `checkArticle`, in the old order |
| `FORM check_all` | `Variante ligne {n} : identifiant manquant` | validation `checkArticle` |
| `FORM check_all` | `Variante ligne {n} : l'EAN doit avoir 13 chiffres` | validation `checkArticle` |
| `FORM check_all` | a row with neither an identifier nor an EAN is passed over | action `pressSave` does not send it on; the validation skips it too |
| `FORM save_article` | a variant with no currency takes the header's | determination `prepareSave` |
| `FORM save_article` | the header EAN is the EAN of the first variant that has one, else none | determination `prepareSave` |
| `FORM save_article` | `created_by` / `created_on` on creation, `changed_by` / `changed_on` always | determination `prepareSave` |
| `FORM save_article` | `MODIFY zret_t_article`, variants into `zret_t_art_var` | the managed save, through the behaviour definition's `persistent table` and `mapping` |
| `FORM save_article` | only rows with an identifier become variants | action `pressSave` and the validation |
| `FORM load_article` | a new article starts with base unit `ST`, currency `EUR`, active flag set | the driver: these are the screen's initial values, not a rule the service enforces |

The validation reports **exactly one** message, because the old screen stops at its first `MESSAGE ... TYPE 'E'`.
Its order is the old one: the open subscreen's own check first, then `check_all`'s order of name, type, price, and
then the variant rows one at a time.

There is no log table. `summary.json` lists two tables and the program writes both; nothing else is touched.

### Screen behaviour — in the driver

The driver is the old screen's keyboard and its memory, and nothing else. It holds no business rule. What it does:

* **which field is which property, and which tab it is on.** A step that types a field belonging to a tab that is
  not open is typing into a field that is not on the screen; batch input stops there and nothing is saved.
* **what the characters a user types mean.** This is the dynpro's own input conversion and its data element's
  domain check, both of which run *before* any of the program's code — the same place a Fiori field's own
  validation sits, which is why these are reported with `client.ui` and nowhere else:

  | Typed | What the old screen does |
  |---|---|
  | nothing in the article field | `Formatting error in the field ZRET_S_ART-ARTICLE_ID; see next message` and `Make an entry in mandatory field "Article"` |
  | more characters than the field holds | batch input stops, no error message, nothing saved |
  | `!` | empties the field |
  | `1.234,56` | 1234.56 — this user's notation |
  | `1.234` | 1234 |
  | `1234,5` | 1234.50 |
  | ` 5` | 5 — a numeric field is right aligned |
  | `,` | nothing, so zero |
  | `10.` or `.` or `1.23.456` or `1,234` | `Input must be in the format __.___.___.___,__` |
  | `5-` or `-5` | `Specify positive values only` — the price domain has no sign |
  | `abc` or `+5` or `1,2,3` | `Enter a numeric value` |
  | `999.999.999.999` | `Entry too long (enter in the format __.___.___.___,__)` — the field is DEC 13,2 |
  | an article type outside `HARD`, `SOFT`, `ACCE`, `CONS` | `Enter a valid value` |
  | `x` in the active flag | `Enter a valid value` — it is a check box whose data element has fixed values |
  | `x` in a variant's mark | kept as typed, and Delete does not see it as a tick — that column has no data element, so no fixed values |
  | lower case anywhere else | upper cased |
  | a base unit | left as typed: that one field allows lower case, and the service's own CUNIT conversion handles it |

* **what each function code does to that memory**: which tab is open, how many lines the variant table has, and
  when Save sends the lot to the service.

Two things in that table deserve a note.

**The article type list box offers a value the field will not accept.** `MODULE init_listbox` fills the drop-down
with `HARD`, `SOFT` and `FOOD`, but the domain's fixed values are `HARD`, `SOFT`, `ACCE` and `CONS`. Choosing
*Food* from the list is rejected with `Enter a valid value`, and `ACCE` and `CONS` are accepted although the list
never offers them. I reproduce the field's behaviour, which is what the old screen actually does. In the new app
the fixed values come from the domain, so the value help and the field agree — the old screen's inconsistency is
gone, and in that one respect the new app is not identical to the old one. Cases p016, p017 and p018 pin this down.

**The base unit goes through a conversion exit on both sides.** The old screen field carries `CUNIT`, so it takes
the unit in the log-on language's spelling. In English the internal code `ST` is spelled `PC`: typing `ST` is
rejected with `Unit ST is not created in language EN.` and typing `PC` stores `ST`. My CDS view leaves the field
typed as a unit of measure, so the service does the same conversion and gives the same message, word for word
(cases p086 to p089). The one consequence for the driver is that a new article's pre-filled base unit has to be
held as `PC`, which is what the old screen *displays* for the internal `ST` it put there.

---

## 3. What a step sequence means for the new app

A case is one run of the old transaction by batch input. These are the readings I settled on, each one checked
against the old screen rather than guessed:

1. **A step's `screen` has to be the screen the program is showing.** If it is not, batch input finds no data for
   the screen it is on, says so with an information message and stops; nothing is saved. The driver stops too.
2. **One save per case.** `FORM save_article` ends with `COMMIT WORK`, and a `COMMIT WORK` in a batch input session
   closes the transaction. Every step after a successful save is thrown away — no second article, no second save
   (cases p060, p061). The driver stops after Save for the same reason.
3. **A failed save ends the case as well**, because an error message aborts batch input. So a case cannot fix a
   mistake and save again (case p071).
4. **Enter, a blank code, `/00` and any unknown code on screen 0200 do nothing** beyond transporting what was
   typed. The field checks all begin with `CHECK ok_code = 'SAVE'` (cases p049, p108).
5. **Back, Exit and Cancel on screen 0200 do nothing at all.** This surprised me. The program has
   `MODULE exit_0200 AT EXIT-COMMAND`, which would offer a popup and return to the first screen — but these three
   codes are not exit commands in this screen's status, so that module never runs, and `MODULE user_command_0200`
   has no branch for them either. The second screen simply stays where it is with everything still typed in it, and
   a later Save still works (cases p105, p106, p107). I confirmed this directly: pressing Back and then carrying on
   saving on screen 0200 saves the article.
6. **Back, Exit and Cancel on screen 0100 end the program**, with nothing written (case p045).
7. **Save on screen 0100, and unknown codes there, do nothing**; the screen stays where it is (cases p072, p109).
8. **Switching tabs transports the open subscreen's fields first, then switches.** So a value typed on the Price
   tab survives a move to another tab (case p077).
9. **Add and Delete only act while the Variants tab is open**, because they are that subscreen's buttons and only
   the open subscreen's code runs (cases p093, p094).
10. **The variant table starts with five lines and shows six.** A sixth line can only be typed into after Add has
    appended one, and a seventh never exists — typing into a line that is not there stops the case without a word
    (cases p029, p030, p031). Delete removes the ticked lines and the rest shift up, so the row numbers in later
    messages are the new ones (case p032).
11. **The screen remembers across steps.** The driver keeps the article, every field of all three tabs, every line
    of the variant table and which tab is open, and sends the lot when Save is pressed.

---

## 4. What I could not reproduce

**1. Two variants with the same identifier make the old program dump.** `FORM save_article` builds its variant
table and runs `INSERT zret_t_art_var FROM TABLE lt_var`, which raises `SAPSQL_ARRAY_INSERT_DUPREC` when two rows
share a key. This is not a graded difference, because the oracle cannot record it either — the report that replays
the case dies with the dump and takes the whole batch with it, which is how I found it. My service refuses the
duplicate key with the framework's own message and writes nothing. A case like this in the sealed set would break
the oracle, not just the comparison.

**2. `Erreur à la sauvegarde des variantes` (text `e05`) cannot happen.** The code sets `sy-subrc = 0` by hand just
before the insert and then tests `sy-subrc` after it; a failing insert dumps (see above) rather than returning 4.
So the `ROLLBACK WORK` branch is dead and the message is unreachable. My service has no equivalent.

**3. `Renseignez un identifiant d'article` (text `e01`) cannot happen either.** The article field is a required
field of screen 0100, so the dynpro's own check fires first and the program never sees an empty article id. What
comes back is the dynpro's pair of messages instead (case p002). The new object still has the rule, as
`field ( mandatory : create )` on the key.

**4. Saving over an article that already exists is not graded, and my version differs.** A case can save only once
and both tables start empty, so every save the grader ever sees is a creation. I implemented creation faithfully.
On a change the old program would:

* overwrite the whole header row from the screen structure, which **clears `COLOR` and `ART_SIZE`** — two columns
  of `ZRET_T_ARTICLE` that no screen can fill, so the old program silently wipes anything already in them;
* **delete every variant of the article and insert the screen's rows again**;
* overwrite each variant's currency with the header's, because the screen never sends one.

My business object updates the row and maintains variants individually, which is what a Fiori object page does: it
leaves `COLOR` and `ART_SIZE` alone, and it does not wipe variants that are not on the screen. It does re-derive the
header EAN on every save, as the old program does. I judged the old wholesale overwrite to be data loss rather than
a rule worth carrying over, and since no graded case can reach it, nothing here tests the choice. **If the grader's
baseline ever had rows in it, these cases would diverge.**

**5. The unsaved-changes popup is dead code.** `POPUP_TO_CONFIRM` in `MODULE exit_0200` never runs, for the reason in
§3 item 5. I reproduce what the screen observably does, not the popup.

**6. Success messages.** `Article X existe : passage en modification` and
`Article X sauvegardé (N variante(s))` are `TYPE 'S'` messages. The oracle does not capture them at all (they are
displayed on a screen that batch input never reaches) and the grader compares only error messages, so they are
invisible to the comparison. My service does not emit them. A person using the new app gets the framework's own
"object created" toast instead of the old sentence with its variant count.

**7. Titles and the tab strip.** `SET TITLEBAR 'T_MAIN'` builds `Modifier article X` or `Créer article`, and the
tab strip shows three tabs. The new object page has a header and three sections. Neither is compared.

**8. I could not start the local app host.** `factory/app.py` is not among the commands this sandbox lets me run, so
I could not open the Fiori app in a browser and look at it. What I did verify: both metadata extensions activate
against the views (which checks every annotation and every element name), the service binding activates and
publishes as an OData V4 **UI** service, and the service answers the list read with `$filter` and `$expand` that
the driver performs on every case. The app's own Save, if a person pressed it on an object page with variant rows,
would hit the same virus scan refusal described in §1 — the action exists precisely because of it, and a person
would need either the profile activated or a button wired to `pressSave`.

**9. A leftover file.** `src/ZPP_MM_ARTICLE.bdef` is not an object. A behaviour definition takes its root entity's
name, so I renamed the file to `ZPP_MM_R_ARTICLE.bdef` early on and deleted the object of the wrong name from the
system; this sandbox refused every attempt to delete the file, so I emptied it and left a note inside. Nothing
called `ZPP_MM_ARTICLE` exists on SAP.

---

## 5. What comparing messages and rows cannot show

The grader compares the set of error messages and every row of both tables. That is a strong test, and here is what
it still cannot see.

**Only the first problem is ever compared.** The old screen stops at its first error and batch input aborts, so a
screenful with three problems yields one message. My validation also yields one, in the old order — but the second
and third are never exercised. If my ordering were wrong *after* the first message, no case would say so. The
places this matters are the ones I had to reason about rather than observe: the order of the variant checks within
one row (identifier before EAN) and across rows (by row number). I did test both directions across rows
(p095, p096), but not every combination.

**The tab-dependent behaviour is a real difference the comparison only partly reaches.** In the old screen the open
tab changes two things. The message order: saving from the Price tab with an empty name *and* a price of zero
reports the price, while saving from either other tab reports the name (p005, p006, p007). And the default values:
clearing the base unit and saving from the Price tab leaves it **empty** in the database, because only the Basic
data tab fills it in (p019, p020, p022); the same goes for the currency, and for the variant currency that copies
it (p021). I carried this across with `SaveTab`, and the cases pass. But in the new app there are no tabs — a
person filling in one object page can never produce the "cleared base unit stays cleared" row that the old screen
produces. The port is faithful to the old screen when driven from a screen sequence, and better behaved when driven
by a person; the comparison cannot distinguish those two readings.

**Row order is not compared.** The grader normalises each table's rows into a sorted set, so the order in which
variants were inserted is invisible. The old program inserts them in screen-row order and so does mine, but nothing
checks it.

**`COLOR` and `ART_SIZE` are compared but unreachable.** No screen writes them, so they are blank in every graded
row. §4 item 4 is the behaviour they would expose, and nothing tests it.

**Nothing about concurrency or authorization.** The old program takes no lock at all — there is no lock object in
the extract — so two users could save the same article over each other. Mine is `lock master` and takes RAP's lock.
The old program checks no authority; my behaviour definition is `authorization master ( global )` and allows
everything. Both are departures, neither is comparable, and the second one would need real thought before this went
anywhere near a real system.

**Anything a person sees.** Field order, field labels, which fields are even on the screen, the drop-down's
contents, the cursor landing on the field that is wrong after an error (the old `MESSAGE ... TYPE 'E'` inside a
`CHAIN` does that), input help, the tab a message sends you to (`check_all` sets `ts_main-activetab` before each
message so the user lands on the right tab — my service reports the message without that). None of it is compared,
and the list box inconsistency in §2 is a bug a person would notice on the first day and no amount of row
comparison ever will.

**Two things that are the same only because both runs are alike.** The administrative columns `CREATED_BY` and
`CHANGED_BY` match because the oracle and my service run as the same SAP user; `CREATED_ON` and `CHANGED_ON` match
because both use the server date, and a run spanning midnight would split them. The unit conversion matches because
both sides run in English; in another log-on language the same typed text means a different unit, on both sides,
but a comparison across two languages is untested.

**Cost and shape.** Nothing compares how many database calls, how long, or how many round trips. The old screen is
one dialog step per key press; the new app is one HTTP request per press, and Save is one request carrying
everything.
