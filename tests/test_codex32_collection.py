"""Codex32QR/v1-48 section 5.2: the rules a share collection obeys.

Ben Westgate opened CoreSigner issue #9 asking us not to invent a
codex32 QR
format, and then published one: `Codex32QR/v1-48`, in
FractalEncrypt/FractalEncrypt_seedsigner. Its section 5 is not about the
QR at all. It is about what a device does with the strings it reads, and
four of those rules are the ones a hand-written collection loop gets
wrong:

  5.2.1  every share carries the collection's own k and identifier;
  5.2.4  the same index with the same payload is a no-op;
  5.2.5  the same index with a DIFFERENT payload asks before replacing;
  7.2    a checksum failure is never corrected for the user.

Rule 5.2.1 is the one with teeth. Shares from two different sets
interpolate to a checksum-VALID string that opens a wallet nobody owns,
so a loop that does not compare headers loses coins quietly. This suite
drives the real loop with a scripted keypad and no bitcoind.

Run: python3 tests/test_codex32_collection.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "coresigner"))
sys.path.insert(0, str(ROOT / "shim"))
import codex32                      # noqa: E402
import main as coresigner_main      # noqa: E402
import screens                      # noqa: E402

fails = []


def ok(m):
    print("ok  ", m)


def bad(m):
    print("FAIL", m)
    fails.append(m)


class Recorder:
    """A display that remembers which screen function drew each frame."""

    width, height = 320, 240

    def __init__(self):
        self.shown = []

    def show(self, image, sensitive=False):
        self.shown.append(image)


class Script:
    def __init__(self, keys):
        self.keys = list(keys)
        self.i = 0

    def read(self):
        if self.i >= len(self.keys):
            raise AssertionError(
                f"the loop asked for press {self.i + 1} and the script has "
                f"{len(self.keys)}")
        key = self.keys[self.i]
        self.i += 1
        return key


# Name every screen by the function that drew it, so an assertion can say
# "the replace question was asked" rather than comparing pixels.
DREW = []


COLLECTION_SCREENS = ("codex32_shares", "text_entry", "codex32_error",
                      "codex32_replace", "codex32_verified", "busy")
EXPORT_SCREENS = ("codex32_unavailable", "codex32_export_menu",
                  "codex32_qr_warning", "codex32_qr")


def _name_screens(names=COLLECTION_SCREENS):
    for name in names:
        real = getattr(screens, name)

        def made(n=name, f=real):
            def draw(*a, **k):
                DREW.append(n)
                return f(*a, **k)
            return draw
        setattr(screens, name, made())


_name_screens()

# A share is typed on the device's own text grid since 2026-10-16, so the
# presses come from the helper that already replays that grid's rules
# rather than from a second model of them (TESTING.md rule 11).
sys.path.insert(0, str(ROOT / "tests"))
from e2e_keys import text_keys       # noqa: E402


def share_keys(share):
    """Presses that type one codex32 string and commit it.

    The 'ms1' prefix is prefilled by the entry loop, so only what follows
    is typed, and the walk down to DONE is the grid's own.
    """
    return list(text_keys("codex32", share.lower()[3:]))


def abort_keys():
    """Presses that leave the grid without typing. C is the MODE button
    on this device, not a way out, so the way out is the action bar:
    down off the grid, left to CANCEL, select."""
    from e2e_keys import commit_presses
    return list(commit_presses("codex32", 0, 0)[:-1]) + ["l", "a"]


class Harness:
    """One run of Session._seed_codex32_type with a scripted keypad."""

    def __init__(self, keys):
        self.opened = []
        self.sess = coresigner_main.Session(
            Recorder(), Script(keys), rpc=None)
        self.sess._codex32_open = lambda shares: (
            self.opened.append(list(shares)) or True)

    def run(self):
        DREW.clear()
        return self.sess._seed_codex32_type()


# Two 2-of-3 sets over different seeds. Both are typed by hand on the
# device, so both have to be real: the vectors come out of the frozen
# module itself rather than being pasted in.
SEED_A = bytes(range(16))
SEED_B = bytes(range(16, 32))
IDENT = "l0ve"
SET_A = [s.upper() for s in codex32.split(
    SEED_A, 2, 3, IDENT, codex32.derive_split_entropy(SEED_A, 2, 3))]
SET_B = [s.upper() for s in codex32.split(
    SEED_B, 2, 3, "cash", codex32.derive_split_entropy(SEED_B, 2, 3))]
SECRET_A = codex32.encode_secret(IDENT, SEED_A, threshold=0).upper()

for _s in SET_A + SET_B + [SECRET_A]:
    codex32.validate(_s)            # every vector below is a real string

# 1. The happy path: two shares of one set recover it.
h = Harness(share_keys(SET_A[0]) + ["a"] + share_keys(SET_A[1]) + ["a"])
if h.run() and len(h.opened) == 1 and len(h.opened[0]) == 2:
    ok("two shares of one set recover it")
else:
    bad(f"a 2-of-3 recovery did not open the key: {h.opened}")

# 2. The secret itself ends the flow at once, with no collection.
h = Harness(share_keys(SECRET_A))
if h.run() and h.opened == [[SECRET_A.lower()]]:
    ok("the secret itself opens the key with no shares collected")
else:
    bad(f"the secret did not open the key on its own: {h.opened}")

# 3. 5.2.4: the same index with the same payload is a no-op. The second
#    copy must not count toward the threshold, and must not be an error.
h = Harness(share_keys(SET_A[0]) + ["a"] + share_keys(SET_A[0])
            + share_keys(SET_A[1]) + ["a"])
if h.run() and len(h.opened) == 1 and len(h.opened[0]) == 2:
    if "codex32_error" in DREW:
        bad("a duplicate share was an ERROR; 5.2.4 says it is a no-op")
    else:
        ok("the same share twice is idempotent, and not an error")
else:
    bad(f"a repeated share broke the collection: {h.opened}")

# 4. 5.2.1: a share from another set is refused, and the refusal names
#    the header the collection expects. This is the one that loses coins.
h = Harness(share_keys(SET_A[0]) + ["a"] + share_keys(SET_B[0]) + ["c"])
h.run()
if "codex32_error" in DREW and not h.opened:
    ok("a share from another set is refused, not interpolated")
else:
    bad(f"a foreign share was accepted into the collection: {h.opened}")

# 5. 5.2.5: the same index with a different payload ASKS first, and
#    keeping the first is the default. SET_B's A share has SET_A's index
#    and a different body, so the question is reachable only after the
#    header check is satisfied; the header carries k and the identifier,
#    so a same-header clash needs a set that shares both.
SET_A2 = [s.upper() for s in codex32.split(
    SEED_B, 2, 3, IDENT, codex32.derive_split_entropy(SEED_B, 2, 3))]
same_index = next(s for s in SET_A2 if s[8] == SET_A[0][8])
if same_index.lower() == SET_A[0].lower():
    bad("the clash vector is the same string; 5.2.5 cannot be tested")
else:
    h = Harness(share_keys(SET_A[0]) + ["a"] + share_keys(same_index)
                + ["a"] + abort_keys())
    h.run()
    if "codex32_replace" in DREW:
        ok("the same index with a different payload asks before replacing")
    else:
        bad("a clashing share was taken or dropped without asking")

# 6. 7.2: a checksum failure is never corrected. One flipped character
#    must produce the error screen and no open key.
flipped = SET_A[0][:-1] + ("8" if SET_A[0][-1] != "8" else "7")
h = Harness(share_keys(flipped) + ["c"])
h.run()
if "codex32_error" in DREW and not h.opened:
    ok("a bad checksum is reported and never corrected")
else:
    bad(f"a corrupt share was accepted: {h.opened}")

# 7. The profile's ceiling is five shares, and it is the profile's number
#    rather than ours.
if coresigner_main.Session.MAX_SHARES == 5:
    ok("the collection holds the profile's five shares")
else:
    bad(f"MAX_SHARES is {coresigner_main.Session.MAX_SHARES}, not the "
        "profile's 5")

# ---- section 6: what an export may offer ------------------------------
#
# 6.1 gates export on a recoverable secret, 6.2 is the candidate set with
# the secret's SOURCE carried, and 6.3 fixes the order: the secret first,
# then the indices sorted. The warning in front of the code is ours and
# his both: a share QR and a secret QR do not carry the same consequence.
_name_screens(EXPORT_SCREENS)   # by the name that drew them


class ExportHarness:
    def __init__(self, keys, held):
        self.sess = coresigner_main.Session(
            Recorder(), Script(keys), rpc=None)
        self.sess.codex32 = held

    def run(self):
        DREW.clear()
        self.sess._tool_export_codex32()


# 6.1: nothing held, so nothing offered, and it says why.
h = ExportHarness(["a"], None)
h.run()
if DREW == ["codex32_unavailable"]:
    ok("6.1: with no secret held, export offers nothing and says why")
else:
    bad(f"6.1: an ungated export drew {DREW}")

# A 2-of-3 recovery leaves the candidate set behind, derived.
rec = Harness(share_keys(SET_A[0]) + ["a"] + share_keys(SET_A[1]) + ["a"])
rec.sess._codex32_open = coresigner_main.Session._codex32_open.__get__(
    rec.sess)
try:
    rec.run()
except Exception as exc:               # no bitcoind here; Core's step only
    if "rpc" not in str(exc).lower() and not isinstance(exc, AttributeError):
        raise
held = rec.sess.codex32
if held and held["derived"] and set(held["shares"]) == {
        SET_A[0][8].lower(), SET_A[1][8].lower()}:
    ok("6.2: a recovery keeps the derived secret and the entered shares")
else:
    bad(f"6.2: the candidate set after a recovery is {held}")

# 6.3: the order, and the source on the secret's row.
rows = screens.codex32_export_rows({"c", "a"}, derived=True)
if [r[0] for r in rows] == ["Secret S", "Share A", "Share C"]:
    ok("6.3: the secret comes first, then the indices sorted")
else:
    bad(f"6.3: the export order is {[r[0] for r in rows]}")
if rows[0][1] == "derived" and screens.codex32_export_rows(
        {"a"}, derived=False)[0][1] == "entered":
    ok("6.2: the secret's row says whether it was derived or entered")
else:
    bad("6.2: the secret's source is not on its row")

# The warning defaults to BACK, and BACK shows no code.
full = {"secret": SECRET_A.lower(), "derived": False, "shares": {}}
h = ExportHarness(["a", "a", "c"], full)   # pick, take default, leave
h.run()
if "codex32_qr" not in DREW and "codex32_qr_warning" in DREW:
    ok("the warning defaults to BACK, so one press shows no code")
else:
    bad(f"a QR appeared on the default press: {DREW}")

# And SHOW IT reaches it.
h = ExportHarness(["a", "r", "a", "a", "c"], full)  # pick, move,
#                   confirm, dismiss the code, leave the menu
h.run()
if "codex32_qr" in DREW:
    ok("SHOW IT draws the code, after the warning")
else:
    bad(f"SHOW IT never reached the code: {DREW}")


print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
