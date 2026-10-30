"""The setup wizard (memory/hub/building_kit_plan.md 5.1, build steps 2 and 3):
every first-run question in one guided dialog — account → cloud folder →
auto-update → keep syncing when logged out → what is this device for.

Steps are data: STEPS is a list of Step(name, applies, ask). `applies` reads
the live state (logged in? which channel? systemd there?), so a step that
does not fit this device is skipped, also on the way back. `ask` asks one
question through Terminal.choose (defaults preselected, 'b' goes back) and
applies the answer right away — every answer is an idempotent setting, so an
interrupted wizard leaves nothing half-done. Where it stopped is remembered
(PROGRESS) and the next `zentrale setup` on a not yet set-up device picks up
there; on a set-up device `zentrale setup` re-opens it from the start.

Only the front lives here: words in, texts out (zentrale_cli/texte.py). The
TUI has no setup of its own; a second front (TUI, phone) uses the same STEPS.
devkit/states.py plays "wizard step n" from this list.
"""

from dataclasses import dataclass
from typing import Callable

from zentrale_cli import aktualisieren, befehle
from zentrale_cli.ausgabe import BACK
from zentrale_cli.texte import t

import abgleich_apps        # noqa: E402
import account_ownership    # noqa: E402
import ai_config            # noqa: E402
import builtin_store_apps   # noqa: E402
import cloud_folder         # noqa: E402
import konto                # noqa: E402

NEXT, CANCEL = "next", "cancel"
PROGRESS = "setup_wizard_at"      # setting: name of the step to resume at ("" = none)
CLOUD_FOLDER_APP = "cloud_folder"


@dataclass(frozen=True)
class Step:
    name: str
    applies: Callable[[dict], bool]
    ask: Callable[[object, dict], str]      # (term, ctx) → NEXT | BACK | CANCEL


# ── When a step fits this device ──────────────────────────────────────

def _no_account(ctx):
    return not konto.angemeldet()


def _with_account(ctx):
    return konto.angemeldet()


def _self_updating(ctx):
    return aktualisieren.kanal(befehle.WURZEL) == "script"


def _linger_possible(ctx):
    return konto.angemeldet() and befehle.timer_modul().linger() is not None


# ── One question each ─────────────────────────────────────────────────

def _choose(term, ctx, question, options, default):
    ctx["asked"] = True
    return term.choose(question, options, default=default, back=ctx["can_back"])


def ask_account(term, ctx):
    way = _choose(term, ctx, t("setup_account_q"), t("setup_account_opts"), "login")
    if way == BACK:
        return BACK
    if way == "local":
        ctx["local"] = True
        return NEXT
    rc = befehle.account_create(term) if way == "create" else befehle.login(term)
    if rc != 0:
        ctx["rc"] = rc
        return CANCEL
    return NEXT


def ask_cloud_folder(term, ctx):
    now = (abgleich_apps.entscheidungen() or {}).get(CLOUD_FOLDER_APP)
    a = _choose(term, ctx, t("wiz_cloud_folder_q", pfad=cloud_folder.root()),
                t("wiz_cloud_folder_opts"), "no" if now is False else "yes")
    if a == BACK:
        return BACK
    befehle.choose_sync(term, {CLOUD_FOLDER_APP: a == "yes"}, show_plan=False)
    ctx.setdefault("answered", set()).add(CLOUD_FOLDER_APP)
    return NEXT


def owned_elsewhere(ctx) -> list:
    """Shop addresses the ACCOUNT owns that are not installed on this node
    (building kit step 10): what a second device offers. Not the cloud (it
    comes with the login) and nothing already answered in this run. Offline
    → [] (never blocks the wizard)."""
    if "owned" not in ctx:
        try:
            ctx["owned"] = sorted(account_ownership.owned())
        except account_ownership.OwnershipError:
            ctx["owned"] = []
    skip = {builtin_store_apps.address("cloud")}
    skip |= {builtin_store_apps.address(n) for n in ctx.get("answered", ())}
    skip |= {builtin_store_apps.address(n) for n in builtin_store_apps.installed_names()}
    return [a for a in ctx["owned"] if a not in skip]


def _owned_name(adr) -> str:
    ident = adr.rsplit("/", 1)[-1]
    return befehle.app_name(ident, {})[0]


def _offer_owned(term, ctx):
    """"What do you plan here?", part one: the apps the account already owns.
    Built-in ones are switched on here; downloaded ones come from the store
    (they need git and a choice of views). → NEXT | BACK."""
    offer = owned_elsewhere(ctx)
    if not offer:
        return NEXT
    term.sag(t("wiz_owned_found", liste=", ".join(_owned_name(a) for a in offer)))
    builtin = [a for a in offer if builtin_store_apps.by_address(a)]
    store = [a for a in offer if not builtin_store_apps.by_address(a)]
    if builtin:
        a = _choose(term, ctx, t("wiz_owned_q", liste=", ".join(_owned_name(x) for x in builtin)),
                    t("wiz_owned_opts"), "yes")
        if a == BACK:
            return BACK
        for adr in builtin:
            name = builtin_store_apps.by_address(adr)
            if a == "yes":
                builtin_store_apps.install(name)
            ctx.setdefault("answered", set()).add(name)
    if store:
        term.sag(t("wiz_owned_store", liste=", ".join(_owned_name(a) for a in store)), "blass")
    return NEXT


def ask_auto_update(term, ctx):
    a = _choose(term, ctx, t("wiz_auto_update_q"), t("wiz_auto_update_opts"),
                "on" if aktualisieren.auto_on() else "off")
    if a == BACK:
        return BACK
    aktualisieren.set_auto(a == "on")
    return NEXT


def ask_linger(term, ctx):
    tm = befehle.timer_modul()
    a = _choose(term, ctx, t("wiz_linger_q"), t("wiz_linger_opts"), "yes")
    if a == BACK:
        return BACK
    if a == "no":
        term.sag(t("wiz_linger_off"), "blass")
        return NEXT
    if tm.linger():
        term.sag(t("wiz_linger_on"), "gut")
        return NEXT
    on, error = tm.enable_linger()
    if on:
        term.sag(t("wiz_linger_on"), "gut")
    else:
        term.sag(t("wiz_linger_refused", text=error or "?", user=tm._user()), "warn")
    return NEXT


def ask_purpose(term, ctx):
    """Which apps are stationed here (memory/hub/standort_und_app.md): only
    apps that already have data, here or in the account."""
    import abgleich
    from zentrale_cli import assistent
    if _offer_owned(term, ctx) == BACK:
        return BACK
    table = abgleich_apps.tabelle()
    offer = [n for n in abgleich_apps.mit_daten(befehle.WURZEL, abgleich.cloud_pfade())
             if n != CLOUD_FOLDER_APP]
    if not offer:
        term.sag(t("setup_nothing_yet"))
        return NEXT
    term.sag(t("setup_apps_found", liste=", ".join(befehle.app_name(n, table)[0] for n in offer)))
    way = _choose(term, ctx, t("wiz_purpose_q"), t("setup_choose_opts"), "all")
    if way == BACK:
        return BACK
    if way in ("all", "none"):
        choice = {n: way == "all" for n in offer}
    else:
        choice = assistent.apps_ankreuzen(term, offer, table)
        if choice is None:
            term.sag(t("cancelled"))
            ctx["rc"] = 1
            return CANCEL
    on = [befehle.app_name(n, table)[0] for n in offer if choice[n]]
    term.sag(t("setup_choice_saved", liste=", ".join(on)) if on else t("setup_choice_none"))
    befehle.choose_sync(term, choice, show_plan=False)
    return NEXT


STEPS = (
    Step("account", lambda ctx: _no_account(ctx) and not ctx.get("local"), ask_account),
    Step("cloud_folder", _with_account, ask_cloud_folder),
    Step("auto_update", _self_updating, ask_auto_update),
    Step("linger", _linger_possible, ask_linger),
    Step("purpose", _with_account, ask_purpose),
)


# ── The engine ────────────────────────────────────────────────────────

def _progress_set(name):
    ai_config.set_override(PROGRESS, name, persist=True)


def start_index(first_start=False) -> int:
    """Resume where an unfinished first setup stopped; a set-up device starts over."""
    at = ai_config.setting(PROGRESS) or ""
    if befehle.eingerichtet() or not at:
        return 0
    names = [s.name for s in STEPS]
    return names.index(at) if at in names else 0


def run(term, steps=STEPS, start=0) -> int:
    """Walk the steps; 'b' goes back to the last step that asked something.
    → 0 when through, else the cancelling step's return code."""
    ctx = {"rc": 0}
    history = []                       # indexes of steps that asked a question
    i = start
    if start:
        term.sag(t("wiz_resume"), "blass")
    total = len(steps)
    while i < len(steps):
        step = steps[i]
        if not step.applies(ctx):
            i += 1
            continue
        ctx["asked"] = False
        ctx["can_back"] = bool(history)
        term.sag()
        term.sag(t("wiz_step", n=i + 1, total=total), "blass")
        r = step.ask(term, ctx)
        if r == CANCEL:
            return ctx["rc"] or 1
        if r == BACK:
            i = history.pop()
            ctx.pop("local", None)           # "stay local" is open again
            continue
        if ctx["asked"]:
            history.append(i)
        i += 1
        _progress_set(steps[i].name if i < len(steps) else "")
    return finish(term, ctx)


def _mark_owned(term):
    """Signup/login installs the Cloud app, and with an account installed
    means owned (/v1/besitz) — the cloud folder too, when it is on here."""
    adrs = [builtin_store_apps.address(n) for n in builtin_store_apps.installed_names()]
    try:
        account_ownership.mark(adrs)
    except account_ownership.OwnershipError as e:
        term.sag(t("wiz_owned_not_saved", text=str(e)), "warn")   # side matter, never blocks


def finish(term, ctx) -> int:
    """After the last step: a local device is done; with an account the cloud
    goes on, the device registers, syncs once and gets its timers."""
    if not konto.angemeldet():
        befehle.einrichtung_merken()
        term.sag()
        term.sag(t("setup_local_ok"), "gut")
        return 0
    from zentrale_cli import assistent
    befehle.choose_sync(term, {}, show_plan=False)   # {} = nothing decided yet: new apps ask themselves
    assistent.cloud_einschalten()
    _mark_owned(term)
    befehle.einrichtung_merken()
    try:
        befehle.geraet_melden()
    except konto.KontoFehler as e:
        term.sag(str(e), "warn")             # registering is a side matter — syncing comes first
    term.sag()
    if any((abgleich_apps.entscheidungen() or {}).values()):
        term.sag(t("setup_sync_now"), "blass")
        befehle.sync(term)
    # The timers (zentrale_cli/timer.py); without systemd --user one sentence.
    term.sag()
    befehle.timers_installieren(term, leise=True)
    befehle.vdirsyncer_hinweis(term)
    term.sag(t("setup_done"), "gut")
    return 0
