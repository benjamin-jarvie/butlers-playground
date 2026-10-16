"""The lab's guard: Layer 1 is exactly three frozen files, and no more.

Run: python3 tests/test_integrity.py

`pure` asserts that no file transforms a secret, and A-22's version of
this suite proved the absence. This repository is the one that keeps
them, so the claim is a different shape and a harder one: THREE files
transform secret material, each is pinned by hash, and nothing else in
the shipped tree computes on a key.

That split is the whole structure below. Checks 1 to 3 are the frozen-
module discipline the README promises: SHIM_HASH pins exactly those
three, the wordlist matches the canonical BIP39 hash, and the tamper
refusal fires. Checks 4 to 7 are `pure`'s own, applied to everything
else, so a fourth transforming file fails here on the day it appears.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASS = FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"ok   {name}  {detail}")
    else:
        FAIL += 1
        print(f"FAIL {name}  {detail}")


#: Layer 1, by name. Everything else in the shipped tree is held to
#: `pure`'s rules, and this set is the only exemption any check below
#: grants. It is written once, here.
LAYER1 = ("shim/bip39_shim.py", "coresigner/codex32.py",
          "coresigner/seedqr.py")

# 1. The three transforming modules exist and SHIM_HASH pins exactly them.
import hashlib
import shutil
import tempfile

for present in LAYER1 + ("shim/english.txt", "SHIM_HASH"):
    check(f"present: {present}", (ROOT / present).exists())

pins = {}
for line in (ROOT / "SHIM_HASH").read_text().splitlines():
    if line.strip():
        h, _, path = line.strip().partition("  ")
        pins[path] = h
check("SHIM_HASH pins exactly the three frozen Layer 1 modules",
      set(pins) == set(LAYER1),
      f"pins {sorted(pins)}" if set(pins) != set(LAYER1) else "")
for path, pinned in pins.items():
    if not (ROOT / path).exists():
        check(f"{path} exists to be hashed", False, "pinned but absent")
        continue
    actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    check(f"{path} matches its pinned hash", actual == pinned,
          "" if actual == pinned else
          f"CHANGED without re-pinning: pinned {pinned[:12]}.. "
          f"actual {actual[:12]}..")

# 2. The wordlist is the canonical BIP39 one, byte for byte.
CANON = "2f5eed53a4727b4bf8880d8f3f199efc90e58503646d9ff8eff3a2ed3b24dbda"
_wl = hashlib.sha256((ROOT / "shim" / "english.txt").read_bytes()).hexdigest()
check("english.txt matches the canonical BIP39 wordlist hash", _wl == CANON,
      "" if _wl == CANON else f"got {_wl[:12]}..")

# 3. The tamper refusal fires. A pinned hash proves the file we ship; this
#    proves the shim refuses a wordlist that is not the one it expects, so
#    a swapped english.txt cannot silently derive a different key.
_tmp = Path(tempfile.mkdtemp(prefix="shim-tamper-"))
try:
    shutil.copy(ROOT / "shim" / "bip39_shim.py", _tmp / "bip39_shim.py")
    _words = (ROOT / "shim" / "english.txt").read_text().splitlines()
    _words[0] = "tampered"
    (_tmp / "english.txt").write_text("\n".join(_words) + "\n")
    sys.path.insert(0, str(_tmp))
    import importlib
    _tampered = importlib.import_module("bip39_shim")
    try:
        _tampered.load_wordlist()
        check("tampered wordlist refused", False, "it was ACCEPTED")
    except ValueError:
        check("tampered wordlist refused", True, "ValueError")
    finally:
        sys.path.remove(str(_tmp))
        sys.modules.pop("bip39_shim", None)
finally:
    shutil.rmtree(_tmp, ignore_errors=True)

# 4. No shipped module OUTSIDE LAYER 1 imports a cryptographic
#    primitive. The three that do are hashing and GF(32) table math
#    with no curve library anywhere, which is checked separately.
# Everything a shipped module may import from outside the standard library.
# This is the signer's whole third-party surface, and the README section
# "What runs on the signer" lists the same names with their purpose. A new
# import fails here until both are updated on purpose (Ben, 2026-09-05: no
# unneeded dependencies left on the pinned signer).
import sys as _sys
_STDLIB = set(_sys.stdlib_module_names)
_OURS = {"signer", "screens", "filechannel", "qrchannel", "hal", "splash",
         "qrsource", "main", "codex32", "seedqr", "bip39_shim"}

ALLOWED_THIRD_PARTY = {
    "PIL",         # Pillow: every screen is a PIL image     (apt python3-pil)
    "qrcode",      # renders the outbound QR frames           (pip, pinned)
    "pyzbar",      # decodes what the camera sees, via libzbar0 (pip, pinned)
    "picamera2",   # the camera                              (apt)
    "spidev",      # the SPI bus the panel hangs off         (apt)
    "RPi",         # RPi.GPIO: the buttons                   (apt)
    "ur2",         # vendored: UR fountain codec, hw/vendor/ur2
    "st7789",      # vendored: the panel driver, hw/vendor/st7789.py
}

# `random` is here for the same reason as `secrets`: the README's first
# security claim is "no `os.urandom`, no `random`, no `secrets`, enforced
# by a test", and audit A8 (2026-09-06) found the test enforced one of the
# three. A device RNG is the one thing PLAN A-19 forbids outright, so the
# claim is now true rather than nearly true.
# Split in two, because Layer 1 needs one half and may never have the
# other. HASHING is what BIP39 and BIP93 are made of. A CURVE LIBRARY, or
# any source of entropy, is what no file in this repository may import:
# Core generates every key, and the splits derive their randomness from
# the seed itself (HMAC, domain-separated), so there is no device RNG to
# trust or to audit.
HASHING = {"hashlib", "hmac"}
BANNED_IMPORTS = HASHING | {"secrets", "random", "ecdsa", "coincurve",
                            "bip32", "cryptography", "nacl"}
# Every shipped .py, wherever it lives. The first version of this scanned
# coresigner/*.py only, so a reintroduced Layer 1 in a new top-level directory
# would have passed. Found by the A-22 spec review, 2026-09-04.
SHIPPED = sorted(p for p in ROOT.rglob("*.py")
                 if not any(part in {"tests", "hw", ".git", "m0", "tools",
                                     "image", "docs"} or part.startswith(".")
                            for part in p.relative_to(ROOT).parts))
check("shipped modules found", len(SHIPPED) >= 7, f"{len(SHIPPED)} files")

for src in SHIPPED:
    found = set()
    for node in ast.walk(ast.parse(src.read_text())):
        if isinstance(node, ast.Import):
            found |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    third_party = {n for n in found if n not in _STDLIB and n not in _OURS}
    stray = third_party - ALLOWED_THIRD_PARTY
    check(f"{src.name}: imports only the listed third-party packages",
          not stray, f"unlisted: {sorted(stray)}" if stray else "")
    rel = str(src.relative_to(ROOT))
    banned = BANNED_IMPORTS - HASHING if rel in LAYER1 else BANNED_IMPORTS
    bad = found & banned
    check(f"no banned import: {rel}", not bad,
          f"found {sorted(bad)}" if bad else "")

# 5. No key derivation is DEFINED outside Layer 1. On `pure` this check
#    matched the vocabulary as text, which is right where no file may even
#    name it. Here main.py has to call the shim by name, so text matching
#    would fail on a correct line and teach everyone to edit the test. It
#    is the DEFINITION that is forbidden: a name bound to a function body,
#    not a name called.
DERIVATION = ("pbkdf2", "mnemonic_to_", "seed_to_xprv", "load_wordlist",
              "derive_", "polymod", "ms32_", "bech32")
for src in SHIPPED:
    rel = str(src.relative_to(ROOT))
    if rel in LAYER1:
        continue
    defined = []
    for node in ast.walk(ast.parse(src.read_text())):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            low = node.name.lower()
            defined += [t for t in DERIVATION if t in low]
    check(f"defines no derivation: {rel}", not defined,
          f"found {defined}" if defined else "")

# 6. And nothing anywhere reads entropy or names the BIP32 seed constant.
#    urandom is an attribute on an allowed stdlib module, so no import
#    scan can see it; it has to be read out of the text. "Bitcoin seed" is
#    BIP32's HMAC key, and the shim is the one file entitled to it.
for src in SHIPPED:
    rel = str(src.relative_to(ROOT))
    body = src.read_text()
    hits = [t for t in ("urandom",) if t in body]
    if rel != "shim/bip39_shim.py" and "Bitcoin seed" in body:
        hits.append("Bitcoin seed")
    check(f"no entropy, no seed constant: {rel}", not hits,
          f"found {hits}" if hits else "")

# 7. signer.py may CALL the shim and may not BE one. The words path is
#    one import and one call; everything it then hands Core goes through
#    importdescriptors like every other path.
sig = (ROOT / "coresigner" / "signer.py").read_text()
check("signer imports the shim rather than implementing it",
      "from bip39_shim import mnemonic_to_xprv" in sig
      and "def mnemonic_to_xprv" not in sig
      and "importdescriptors" in sig and "open_session_xprv" in sig,
      "one import, one call, Core does the rest")

print("\n" + "=" * 62)
print(f"PASS {PASS}   FAIL {FAIL}")
print("Layer 1 is three pinned files, and nothing else computes on a key.")
sys.exit(1 if FAIL else 0)
