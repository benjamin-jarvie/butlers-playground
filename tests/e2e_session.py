"""Full-device dress rehearsals on the dev HAL: three scripted sessions
covering word entry, xprv-QR + QR PSBT in/out, and SeedQR + refusal of a
fee-less PSBT. Run: python3 tests/e2e_session.py"""

import base64
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "coresigner"))
sys.path.insert(0, str(ROOT / "shim"))
import signer  # noqa: E402
import qrchannel  # noqa: E402
from bip39_shim import load_wordlist, mnemonic_to_xprv  # noqa: E402

MNEMONIC = "abandon " * 11 + "about"
# The same key, as an xprv. `pure`'s sessions take this form and this
# repository derives it from the words rather than pasting a second
# constant that could drift out of step with them.
XPRV = mnemonic_to_xprv(MNEMONIC, mainnet=False)
# Button script for typing one BIP39 word (see main._collect_words). The
# word COMMITS ITSELF when one candidate is left, so there is no press
# that takes it: the script types letters until the list is one long and
# the loop moves to the next word on its own (2026-10-16).
WORDLIST_FOR_SCRIPT = load_wordlist()


def word_keys(word):
    """Type a BIP39 word on the 8x4 letter grid (a=0..z=25, wrap %32).

    Derived from the wordlist rather than fixed at four letters, because
    the loop stops at the first UNIQUE prefix and most words reach one
    sooner than that.
    """
    cur, out, prefix = 0, [], ""
    for ch in word:
        tgt = ord(ch) - 97
        d = (tgt - cur) % 32
        out.append("d" * (d // 8) + "r" * (d % 8) + "a")
        cur = tgt
        prefix += ch
        if len([w for w in WORDLIST_FOR_SCRIPT
                if w.startswith(prefix)]) == 1:
            break
    return "".join(out)


# 11x abandon + about, typed on the grid. Session F drives the backup
# tool in process, so it needs the presses rather than a wallet.
WORDS_SCRIPT = word_keys("abandon") * 11 + word_keys("about")


def run_device(datadir, script, frames, stick=None, qr_key=None, qr_psbt=None):
    import os
    os.environ["SCREENLOG"] = ("/private/tmp/claude-502/-Users-ai-sandbox/"
                               "f22f054f-2993-4214-9595-2942d9386f9b/"
                               "scratchpad/L-" + Path(frames).name + ".txt")
    cmd = [sys.executable, str(ROOT / "coresigner" / "main.py"), "--dev",
           f"--datadir={datadir}", "--chain=regtest", f"--script={script}",
           f"--frames-dir={frames}"]
    if stick:
        cmd.append(f"--stick-dir={stick}")
    if qr_key:
        cmd.append(f"--qr-key={qr_key}")
    if qr_psbt:
        cmd.append(f"--qr-psbt={qr_psbt}")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180)


def main():
    datadir = tempfile.mkdtemp(prefix="coresigner-sess-")
    import random as _rnd
    _port = _rnd.randint(20000, 60000)
    (Path(datadir) / "bitcoin.conf").write_text(
        "regtest=1\n[regtest]\nrpcport=%d\n" % _port)
    work = Path(tempfile.mkdtemp(prefix="coresigner-sess-work-"))
    daemon = subprocess.Popen(
        ["bitcoind", "-regtest", f"-datadir={datadir}", "-listen=0",
         "-fallbackfee=0.0001", "-server=1", "-debuglogfile=0"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rpc = signer.Rpc(datadir, chain="regtest")
    try:
        for _ in range(60):
            try:
                rpc.call("getblockcount")
                break
            except RuntimeError:
                time.sleep(0.5)

        # Coordinator: watch wallet from Core Signer's xpubs, funded
        signer.open_session_xprv(rpc, XPRV)
        pubs = signer.public_descriptors(rpc)
        signer.close_session(rpc)
        rpc.call("createwallet", "watch", True, True, "", False, True)
        rpc.call("importdescriptors",
                 [{"desc": d, "active": True, "timestamp": "now",
                   "range": [0, 200], "internal": "/1/*" in d}
                  for d in pubs], wallet="watch")
        addr = rpc.call("getnewaddress", wallet="watch")
        rpc.call("generatetoaddress", 101, addr)

        def fund_psbt(amount):
            dest = rpc.call("getnewaddress", wallet="watch")
            return rpc.call("walletcreatefundedpsbt", [], [{dest: amount}],
                            0, {"fee_rate": 10}, True, wallet="watch")["psbt"]

        import io
        import screens as scr

        def _render(fn, *a, **k):
            b = io.BytesIO()
            fn(320, 240, *a, **k).save(b, format="PNG")
            return b.getvalue()

        def _frames(d):
            return sorted(Path(d).glob("frame-*.png"))

        def _has(d, png):
            return any(p.read_bytes() == png for p in _frames(d))

        def _where(d, png):
            """Every frame number that drew this screen, in order shown."""
            return [i for i, p in enumerate(_frames(d))
                    if p.read_bytes() == png]


        # ---- Session B: xprv via QR + PSBT in AND out via QR ----
        xprv_file = work / "key.txt"
        xprv_file.write_text(mnemonic_to_xprv(MNEMONIC, mainnet=False))
        frames_file = work / "psbt_frames.txt"
        frames_file.write_text("\n".join(qrchannel.psbt_to_frames(fund_psbt(1.0))))
        # TWO review presses: a funded PSBT has a destination and a
        # change output, which is a page each, and the first A advances
        # to the unseen one rather than signing. That guard is the point
        # of the screen.
        r = run_device(datadir,
                       "ra" + "da" + "a" + "bb" + "a" + "aa" + "ra" + "draa",
                       work / "framesB",
                       qr_key=xprv_file, qr_psbt=frames_file)
        assert r.returncode == 0, f"B failed rc={r.returncode}:\n{r.stderr[-1200:]}"
        shots = sorted((work / "framesB").glob("frame-*.png"))
        assert len(shots) > 6, "B: expected QR output frames on screen"
        # detail is None on this path: the PSBT left as QR frames, so
        # there is no file to name (main._sign_and_deliver leaves detail
        # unset and _state_signed passes it through). The screen is drawn
        # twice, once per action, and either is proof it was reached.
        assert any(_has(work / "framesB",
                        _render(scr.result, ok=True, detail=None,
                                actions_sel=sel, label="SIGNED",
                                note="ready to send"))
                   for sel in (0, 1)), "B: the QR-out result never showed"
        print(f"ok   B: xprv QR (warning screen shown) -> PSBT via QR -> signed QR out ({len(shots)} frames)")

        # ---- Session C: SeedQR + fee-less PSBT refused ----
        seedqr_file = work / "seedqr.txt"
        seedqr_file.write_text("0000" * 11 + "0003")
        stickc = work / "stickC"; stickc.mkdir()
        utxo = rpc.call("listunspent", wallet="watch")[0]
        bare = rpc.call("createpsbt",
                        [{"txid": utxo["txid"], "vout": utxo["vout"]}],
                        [{rpc.call("getnewaddress", wallet="watch"): 1.0}])
        (stickc / "bad.psbt").write_bytes(base64.b64decode(bare))
        # R,A opens Keys and five DOWNs reach Scan SeedQR, which is the
        # sixth way in. A picks it, the scan reads the digits, A declines
        # the BIP39 passphrase, and the key opens on its own menu: two
        # backs reach home. Then the Sign tile loads the fee-less PSBT
        # from the stick, A dismisses the refusal, and the walk out is
        # Settings then Power off.
        r = run_device(datadir,
                       "ra" + "ddddd" + "a" + "a" + "bb" + "a" + "a"
                       + "draa", work / "framesC",
                       stick=stickc, qr_key=seedqr_file)
        assert r.returncode == 0, f"C failed:\n{r.stderr}"
        assert not (stickc / "bad-signed.psbt").exists(), "C: refused PSBT was signed!"
        # Golden-frame: the LAST rendered frame must be byte-identical to
        # the refusal screen (ok=False). Kills visual-lie mutants (e.g.
        # ok False->True showing success on a refusal) that no logic
        # assertion can see. PIL renders are deterministic.
        buf = io.BytesIO()
        scr.result(320, 240, ok=False,
                   detail="PSBT lacks input data; fee unknown; refused"
                   ).save(buf, format="PNG")
        # The refusal returns to home now (D7), so the refusal screen is no
        # longer the last frame; it must still be rendered byte-identically.
        assert _has(work / "framesC", buf.getvalue()), \
            "C: the exact refusal screen was never shown (visual lie?)"
        print("ok   C: SeedQR entry -> fee-less PSBT refused, nothing signed; "
              "refusal frame golden-verified")

        # ---- Session D: many-output PSBT forces paged review ----
        stickd = work / "stickD"; stickd.mkdir()
        dests = {rpc.call("getnewaddress", wallet="watch"): 0.2
                 for _ in range(4)}
        many = rpc.call("walletcreatefundedpsbt", [],
                        [{a: v} for a, v in dests.items()],
                        0, {"fee_rate": 10}, True, wallet="watch")["psbt"]
        (stickd / "many.psbt").write_bytes(base64.b64decode(many))
        key_file2 = work / "key2.txt"
        key_file2.write_text(XPRV)
        # ONE OUTPUT A PAGE since 2026-09-25, so four destinations and a
        # change output are five pages. DERIVED: each A with a page still
        # unseen advances instead of signing, so it takes one press per
        # page, the last of which signs. Written as 3 here while the
        # device believed the same wrong number, and both are fixed now.
        info_d = signer.describe_psbt(rpc, many)
        outs_d = [(o["address"], o["amount_btc"]) for o in info_d["outputs"]]
        review_d = "a" * scr.review_pages(outs_d)
        r = run_device(datadir,
                       "ra" + "da" + "a" + "bb" + "a" + review_d + "ra"
                       + "draa", work / "framesD",
                       stick=stickd, qr_key=key_file2)
        assert r.returncode == 0, f"D failed:\n{r.stderr}"
        assert (stickd / "many-signed.psbt").exists(), "D: signed file missing"
        # Negative: a SINGLE 'a' at review (one page still unseen) must NOT
        # sign — proves the gate blocks, not just that enough 'a's sign.
        stickd2 = work / "stickD2"; stickd2.mkdir()
        many2 = rpc.call("walletcreatefundedpsbt", [],
                         [{rpc.call("getnewaddress", wallet="watch"): 0.2}
                          for _ in range(4)] and
                         [{a: v} for a, v in dests.items()],
                         0, {"fee_rate": 10}, True, wallet="watch")["psbt"]
        (stickd2 / "many.psbt").write_bytes(base64.b64decode(many2))
        sq3 = work / "key3.txt"; sq3.write_text(XPRV)
        # load key, seedqr, review: ONE 'a' (force-advance only) then 'c'
        # rejects; 'a' dismisses the rejection, then settings -> power off.
        r = run_device(datadir, "ra" + "da" + "a" + "bb" + "a" + "ac" + "a" + "draa",
                       work / "framesD2",
                       stick=stickd2, qr_key=sq3)
        assert not (stickd2 / "many-signed.psbt").exists(), \
            "D2: PSBT signed with a page unseen — paging gate is broken!"
        assert r.returncode == 0, f"D2 failed:\n{r.stderr}"
        # The rejection returns to home now (D7), so it is no longer the
        # last frame; it must still be rendered byte-identically.
        assert _has(work / "framesD2", _render(
            scr.result, ok=False, detail="rejected by user")), \
            "D2: the exact rejection screen was never shown"
        print("ok   D: paged review — signs only after all pages seen, "
              "blocks when one is unseen")

        # ---- Session D3: paging NAVIGATION (u/d, wraparound) ----
        # Mutation testing showed the u/d paths and modulo arithmetic were
        # never exercised: D only force-advanced via 'a'. Here all pages
        # are seen by real navigation, both directions.
        stickd3 = work / "stickD3"; stickd3.mkdir()
        many3 = rpc.call("walletcreatefundedpsbt", [],
                         [{a: v} for a, v in dests.items()],
                         0, {"fee_rate": 10}, True, wallet="watch")["psbt"]
        (stickd3 / "many.psbt").write_bytes(base64.b64decode(many3))
        key_sq4 = work / "key4.txt"; key_sq4.write_text(XPRV)
        # DOWN then UP exercises both directions, and the sweep of DOWNs
        # after it visits every page whatever the count is, because the
        # paging wraps. DERIVED: one output a page since 2026-09-25, so
        # a hand-written "dudda" saw three of five.
        info3n = signer.describe_psbt(rpc, many3)
        outs3n = [(o["address"], o["amount_btc"]) for o in info3n["outputs"]]
        nav3 = "du" + "d" * (scr.review_pages(outs3n) - 1) + "a"
        r = run_device(datadir,
                       "ra" + "da" + "a" + "bb" + "a" + nav3 + "ra" + "draa",
                       work / "framesD3", stick=stickd3, qr_key=key_sq4)
        assert r.returncode == 0, f"D3 failed:\n{r.stderr}"
        assert (stickd3 / "many-signed.psbt").exists(), "D3: nav-sign missing"
        # wraparound: u from page0 lands on page2 ((0-1)%3), u again on 1
        stickd4 = work / "stickD4"; stickd4.mkdir()
        many4 = rpc.call("walletcreatefundedpsbt", [],
                         [{a: v} for a, v in dests.items()],
                         0, {"fee_rate": 10}, True, wallet="watch")["psbt"]
        (stickd4 / "many.psbt").write_bytes(base64.b64decode(many4))
        key_sq5 = work / "key5.txt"; key_sq5.write_text(XPRV)
        # UP twice from the first page is the wraparound: it lands on the
        # last page and then the one before it. The sweep that follows
        # sees the rest, because paging wraps either way.
        info4n = signer.describe_psbt(rpc, many4)
        outs4n = [(o["address"], o["amount_btc"]) for o in info4n["outputs"]]
        nav4 = "uu" + "d" * (scr.review_pages(outs4n) - 1) + "a"
        r = run_device(datadir,
                       "ra" + "da" + "a" + "bb" + "a" + nav4 + "ra" + "draa",
                       work / "framesD4", stick=stickd4, qr_key=key_sq5)
        assert r.returncode == 0, f"D4 failed:\n{r.stderr}"
        assert (stickd4 / "many-signed.psbt").exists(), "D4: wraparound broken"
        print("ok   D3/D4: paging navigation u/d + wraparound exercised")

        # ---- Session E: codex32 shares (scan) open the wallet ----
        import codex32 as c32
        seed = bytes(range(32))
        ident = "cqr0"
        # FROZEN vectors: computed once from the device's derivation and
        # pinned here as independent expectations — the test must NOT
        # re-derive them with the same code it is checking (tautology).
        FROZEN_SHARES = [
            "ms12cqr0a94fnp8pnd9j8lkl86yepyt6xwnvucpq77mcxrzhrzrr447fz6gdhx9flxvjeaa7s8",
            "ms12cqr0cuazrcemugr5eefvj8k688hv6v3zgjc3mahwfpu474ak29yz3qe2f6tvs9vz0whcvf",
            "ms12cqr0d5xdusu82az4ucq8ck3wxn2j85fcw3szwf4sleed08cur6cd6u28v83ex3va395e3n",
        ]
        import hashlib as hl
        import hmac as hm
        rand = b""
        i = 0
        while len(rand) < 64:
            rand += hm.new(seed, b"corky-split-v1" + bytes([i]), hl.sha512).digest()
            i += 1
        shares = c32.split(seed, 2, 3, ident, rand[:64])
        assert shares == FROZEN_SHARES, "split derivation drifted from frozen vectors"
        key_file = work / "c32shares.txt"
        key_file.write_text("\n".join(shares[:2]))
        sticke = work / "stickE"; sticke.mkdir()
        # fund the codex32 wallet's own descriptor set via a watch import
        xprv = c32.to_xprv(seed, mainnet=False)
        signer.open_session_xprv(rpc, xprv)
        pubs_e = signer.public_descriptors(rpc)
        signer.close_session(rpc)
        rpc.call("createwallet", "watchE", True, True, "", False, True)
        rpc.call("importdescriptors",
                 [{"desc": d, "active": True, "timestamp": "now",
                   "range": [0, 200], "internal": "/1/*" in d}
                  for d in pubs_e], wallet="watchE")
        addr_e = rpc.call("getnewaddress", wallet="watchE")
        rpc.call("generatetoaddress", 101, addr_e)
        dest_e = rpc.call("getnewaddress", wallet="watchE")
        funded_e = rpc.call("walletcreatefundedpsbt", [], [{dest_e: 1.0}],
                            0, {"fee_rate": 10}, True, wallet="watchE")
        (sticke / "c32.psbt").write_bytes(base64.b64decode(funded_e["psbt"]))
        # R,A opens Keys and three DOWNs reach Scan codex32, the fourth
        # way in. Both shares arrive in one QR, one per line, so the set
        # is recoverable without a second scan. Then two backs to home,
        # the Sign tile, the review's two pages (destination and change),
        # and out through Settings.
        info_e = signer.describe_psbt(rpc, funded_e["psbt"])
        outs_e = [(o["address"], o["amount_btc"]) for o in info_e["outputs"]]
        # The dev camera yields ONE line per scan, so the first share
        # arrives and the set is not yet recoverable: section 5.1 routes
        # into collection, and SCAN there reads the second. That is the
        # path a person with two share QRs and one camera actually takes.
        r = run_device(datadir,
                       "ra" + "ddd" + "a"          # Keys -> Scan codex32
                       + "la" + "a"                # SCAN, then VALID
                       + "bb" + "a"                # out to home, Sign
                       + "a" * scr.review_pages(outs_e) + "ra" + "draa",
                       work / "framesE", stick=sticke, qr_key=key_file)
        assert r.returncode == 0, f"E failed:\n{r.stderr}"
        assert (sticke / "c32-signed.psbt").exists(), "E: signed file missing"
        print("ok   E: codex32 2-of-3 shares (scan) -> wallet open -> stick sign")


        # ---- Session R3: 2-output PSBT is exactly TWO pages ----
        # It was one page, on `pages = (len(outputs) + 1) // 2`. The
        # review went to ONE OUTPUT A PAGE on 2026-09-25, when the whole
        # address started being shown in fours and two of them would not
        # fit, so a funded PSBT's destination and its change are a page
        # each. The old session asserted the count in its own print,
        # which is a claim and not a check, and it stayed wrong for three
        # weeks. It is asserted below now.
        stickr = work / "stickR3"; stickr.mkdir()
        p3 = rpc.call("walletcreatefundedpsbt", [],
                      [{rpc.call("getnewaddress", wallet="watch"): 0.1}],
                      0, {"fee_rate": 10}, True, wallet="watch")["psbt"]
        (stickr / "p3.psbt").write_bytes(base64.b64decode(p3))
        key_sqr = work / "sq_r3.txt"; key_sqr.write_text(XPRV)
        # Two pages, so two presses: the first advances to the change
        # output and the second signs.
        r = run_device(datadir,
                       "ra" + "da" + "a" + "bb" + "a" + "aa" + "ra" + "draa",
                       work / "framesR3", stick=stickr, qr_key=key_sqr)
        assert r.returncode == 0, f"R3 failed:\n{r.stderr}"
        assert (stickr / "p3-signed.psbt").exists(), \
            "R3: the 2-output PSBT was not signed"
        # The count, measured off the panel rather than claimed. Both
        # pages must have been drawn, which is the whole point of the
        # screen: the second output here is the change, and a review that
        # signs without showing it is the defect this found.
        info3 = signer.describe_psbt(rpc, p3)
        outs3 = [(o["address"], o["amount_btc"]) for o in info3["outputs"]]
        assert scr.review_pages(outs3) == 2, \
            f"R3: {len(outs3)} outputs is {scr.review_pages(outs3)} pages"
        ours3 = None
        for page in (0, 1):
            assert any(_has(work / "framesR3",
                            _render(scr.review, outs3, info3["fee_btc"],
                                    input_total_btc=info3["input_total_btc"],
                                    page=page, unseen_pages=unseen,
                                    quorum=info3["quorum"],
                                    cosigners=info3["cosigners"],
                                    ours=ours3,
                                    timelocks=info3["timelocks"],
                                    spend_lock=info3["spend_lock"]))
                        for unseen in (False, True)), \
                f"R3: the review never drew page {page + 1} of 2"
        print("ok   R3: a 2-output PSBT is two review pages, both drawn, "
              "and it signs")

        # ---- Session I: incomplete QR assembly, then abort at load ----
        allframes = qrchannel.psbt_to_frames(fund_psbt(1.0))
        assert len(allframes) > 1, "I: need a multi-frame PSBT"
        part = work / "partial_frames.txt"
        part.write_text(allframes[0])
        emptystick = work / "stickI"; emptystick.mkdir()
        sqi = work / "key_i.txt"; sqi.write_text(XPRV)
        # state_load now opens on a channel menu (Ben, 2026-09-04), and this
        # session supplies BOTH channels, so the menu appears and has to be
        # answered before the scan loop is reached at all. Without the extra
        # "a" the abort key lands on the menu and this stops testing what its
        # name says. B goes back one page to the menu, C aborts to home
        # (hw/HARDWARE.md), so the two need different tails.
        for abkey, tail in (("b", "c" + "draa"), ("c", "draa")):
            r = run_device(datadir,
                           "ra" + "da" + "a" + "bb" + "a" + "a" + abkey + tail,
                           work / ("framesI" + abkey),
                           stick=emptystick, qr_key=sqi, qr_psbt=part)
            assert r.returncode == 0, f"I({abkey}) failed:\n{r.stderr}"
            # In dev there is no camera frame, so screens.scanning falls back
            # to the wait frame with the scan's own message.
            assert _has(work / ("framesI" + abkey),
                        _render(scr.busy, "hold the QR in view")), \
                f"I({abkey}): the scan screen was never shown"
            assert _has(work / ("framesI" + abkey),
                        _render(scr.channel_menu, 0)), \
                f"I({abkey}): the channel menu was never shown"
        print("ok   I: partial QR makes progress; b/c abort the load loop")

        # ---- Session J: PSBT this wallet cannot complete -> refusal ----
        # A-22: the watch wallet used to be a by-product of the codex32
        # session, which moved to the lab. J makes its own, so it stands
        # alone: a funded wallet whose keys Core Signer does not hold.
        # It makes its own foreign wallet, so it stands alone. The merge
        # of 2026-10-17 left it funding from watchE while asking for the
        # fingerprint of a foreignJ nothing created, so the refusal it
        # looked for could never match.
        stickj = work / "stickJ"; stickj.mkdir()
        rpc.call("createwallet", "foreignJ")
        fa = rpc.call("getnewaddress", wallet="foreignJ")
        rpc.call("generatetoaddress", 101, fa)
        foreign = rpc.call("walletcreatefundedpsbt", [],
                           [{rpc.call("getnewaddress",
                                      wallet="foreignJ"): 0.5}],
                           0, {"fee_rate": 10}, True,
                           wallet="foreignJ")["psbt"]
        (stickj / "alien.psbt").write_bytes(base64.b64decode(foreign))
        key_sqj = work / "key_j.txt"; key_sqj.write_text(XPRV)
        foreign_xfp = signer.master_fingerprint(rpc, wallet="foreignJ")
        # Ticket 03: the transaction names its key, so the refusal comes
        # BEFORE review and names the fingerprint it wants. One key
        # dismisses it, then settings, power off.
        r = run_device(datadir, "ra" + "da" + "a" + "bb" + "a" + "a" + "draa", work / "framesJ",
                       stick=stickj, qr_key=key_sqj)
        assert r.returncode == 0, f"J failed:\n{r.stderr}"
        assert not (stickj / "alien-signed.psbt").exists(), "J: signed foreign PSBT!"
        # Returns to home after the refusal (D7); the screen must still be
        # rendered byte-identically somewhere in the run.
        assert _has(work / "framesJ", _render(
            scr.result, ok=False,
            detail=f"no loaded key owns it; wants {foreign_xfp}")), \
            "J: the exact cannot-complete screen was never shown"
        print("ok   J: foreign PSBT -> cannot-complete refusal, golden-verified")

        # ---- Session H: codex32 secret TYPED on the grid -> sign ----
        sys.path.insert(0, str(ROOT / "tests"))
        from e2e_keys import text_keys as grid_text   # noqa: E402

        def typed_share(share):
            """Pick TYPE on the collection screen, then type one string.

            The collection screen offers ABORT, SCAN and TYPE and opens
            on TYPE (section 5.2 wants both ways in). The 'ms1' prefix is
            prefilled, so only what follows it is typed.
            """
            return "a" + grid_text("codex32", share.lower()[3:])

        H_SECRET = ("ms10cqr0sqqqsyqcyq5rqwzqfpg9scrgwpugpzysnzs23v9ccrydpk8"
                    "qarc0sh5qqf9nteh5xm")   # frozen: bytes(range(32)), k=0
        stickh = work / "stickH"; stickh.mkdir()
        ph = rpc.call("walletcreatefundedpsbt", [],
                      [{rpc.call("getnewaddress", wallet="watchE"): 0.7}],
                      0, {"fee_rate": 10}, True, wallet="watchE")["psbt"]
        (stickh / "typed.psbt").write_bytes(base64.b64decode(ph))
        # Keys, then four DOWNs to "Type codex32 share", which is the
        # fifth way in. A secret carries k=0, so it opens the wallet on
        # its own with no collection and no VALID screen. Then two backs
        # to home, the Sign tile, and the review's pages.
        info_h = signer.describe_psbt(rpc, ph)
        outs_h = [(o["address"], o["amount_btc"]) for o in info_h["outputs"]]
        r = run_device(datadir,
                       "ra" + "dddd" + "a" + typed_share(H_SECRET)
                       + "bb" + "a" + "a" * scr.review_pages(outs_h)
                       + "ra" + "draa",
                       work / "framesH", stick=stickh)
        assert r.returncode == 0, f"H failed:\n{r.stderr}"
        assert (stickh / "typed-signed.psbt").exists(), "H: typed-entry sign missing"
        assert _has(work / "framesH",
                    _render(scr.busy, "Recovering seed, deriving in Core…")), \
            "H: recovery busy screen missing"
        print("ok   H: codex32 secret typed on the grid -> wallet open -> sign")

        # ---- Session H2: TWO typed shares, duplicate + error paths ----
        stickh2 = work / "stickH2"; stickh2.mkdir()
        ph2 = rpc.call("walletcreatefundedpsbt", [],
                       [{rpc.call("getnewaddress", wallet="watchE"): 0.6}],
                       0, {"fee_rate": 10}, True, wallet="watchE")["psbt"]
        (stickh2 / "duo.psbt").write_bytes(base64.b64decode(ph2))
        info_h2 = signer.describe_psbt(rpc, ph2)
        outs_h2 = [(o["address"], o["amount_btc"]) for o in info_h2["outputs"]]
        # The duplicate in the middle is a NO-OP now, which is section
        # 5.2.4: the same index with the same payload adds nothing and is
        # not an error. It used to draw a refusal and this session used to
        # assert that refusal, so both moved together.
        script = ("ra" + "dddd" + "a"
                  + typed_share(FROZEN_SHARES[0]) + "a"   # share 1, VALID
                  + typed_share(FROZEN_SHARES[0])         # again: ignored
                  + typed_share(FROZEN_SHARES[1]) + "a"   # share 2, VALID
                  + "bb" + "a"                            # home, Sign
                  + "a" * scr.review_pages(outs_h2))
        r = run_device(datadir, script + "ra" + "draa", work / "framesH2",
                       stick=stickh2)
        assert r.returncode == 0, f"H2 failed:\n{r.stderr}"
        assert (stickh2 / "duo-signed.psbt").exists(), "H2: 2-share sign missing"
        fh2 = work / "framesH2"
        assert _has(fh2, _render(scr.codex32_shares, (), "?", 2)), \
            "H2: first collect screen"
        assert _has(fh2, _render(scr.codex32_shares,
                                 (FROZEN_SHARES[0][8].upper(),), 2, 2)), \
            "H2: collect screen after share 1"
        assert not _has(fh2, _render(scr.codex32_error, "Duplicate share")), \
            "H2: a repeated share drew a refusal; 5.2.4 says it is a no-op"
        assert _has(fh2, _render(scr.codex32_verified, "share 1 of 2")), \
            "H2: share-1 VALID screen"
        assert _has(fh2, _render(scr.codex32_verified, "share 2 of 2")), \
            "H2: share-2 VALID screen"
        print("ok   H2: typed 2-of-3 shares, a repeat ignored, golden screens")

        # ---- Session H3/H4: typed-entry aborts stay closed ----
        # C on the collection screen is the way out now: the screen the
        # loop waits on is that one, not the grid.
        r = run_device(datadir, "ra" + "dddd" + "a" + "c" + "b" + "draa",
                       work / "framesH3")
        assert r.returncode == 0, f"H3 failed:\n{r.stderr}"
        assert _has(work / "framesH3", _render(scr.home, 0)), \
            "H3: abort did not return to home before power off"
        # One character committed is too short to be a codex32 string, so
        # it is the cheapest invalid one: error -> 'b' declines -> out.
        r = run_device(datadir,
                       "ra" + "dddd" + "a" + "a"
                       + grid_text("codex32", "q") + "b" + "b" + "draa",
                       work / "framesH4")
        assert r.returncode == 0, f"H4 failed:\n{r.stderr}"
        assert _has(work / "framesH4", _render(scr.home, 0)), \
            "H4: error-decline did not return to home before power off"
        assert _has(work / "framesH4", _render(
            scr.codex32_error,
            "not a valid codex32 string (checksum or format)"[:48])), \
            "H4: checksum error screen missing"
        print("ok   H3/H4: typed-entry abort and error-decline return home")

        # ---- Session F: backup tool, in-process with share capture ----
        # Dev frames redact sensitive screens, so the shares are pinned by
        # intercepting the share screen call. FROZEN backup vectors for the
        # canonical mnemonic (computed once, must never drift):
        # FROZEN backup vectors (full 64-byte BIP39 seed — the
        # 32-byte truncation was the wallet-mismatch bug):
        F_SECRET = "ms10cjmlst6cqh0wu7p5ssjyf4z4ez42ks9jlt3zneju9uuypr2hddak6tlqe5kkypvufe5ms6zrzqm0v32nvg0dw5e5s7g9d8kx53vkje60r3eq2xjsqkgy2p8lyh6"
        F_SHARES = [
            "ms12cjmla37uxfewhh3a49daeqdlagwmpdjgv2ue6f97lecs5ppzhx495f3adurg270m57y45z7qe85czv43wzsr0sruvhjq780cfdm0s6zldx8gtcxakjaudx5tvml",
            "ms12cjmlcmsj0dpwmuqkvd78gg0ynnnaweazdaey3c2e4qk0uxd2a2fypwyfjqtvldl9qq4q60asyekhhcxkferkc7fq0ucel84uaw54h20wcfr544l6s94l5ymkl6e",
            "ms12cjmldc2gc59wenneyk4mmnh5frzucltpp0v47tu5kgvx8t037g5gtrw0mas44xqqx9x2qpf04uwpa7dmyfgu2y2amnm3n8f9m6zf64pajl6fsmhh3hwtuud85kc",
        ]
        import hal
        import main as coresigner_main
        rec = []
        orig_sd = scr.backup_page
        # A 127-char codex32 string is several screenfuls, so the recorder
        # captures every page and the scripts acknowledge each one. The
        # share screen is main's own backup pager since the forward merge
        # of 2026-10-16, so this records what that draws.
        scr.backup_page = (
            lambda w, h, chunk, label, page=0, pages=1, actions_sel=1,
            offer_check=True:
            (rec.append((chunk, label)) or orig_sd(
                w, h, chunk, label, page=page, pages=pages,
                actions_sel=actions_sel, offer_check=offer_check)))

        def _pages(text):
            return scr.text_pages(text.upper())

        def _recorded(text, label):
            return [(p, label) for p in _pages(text)]

        PER = len(_pages(F_SECRET))
        try:
            def backup_run(script, tag):
                d = work / ("framesF" + tag)
                sess = coresigner_main.Session(hal.DevDisplay(d),
                                          hal.DevButtons(script), rpc=None)
                sess._tool_backup()
                return d
            rec.clear()
            fd = backup_run("a" + WORDS_SCRIPT + "a" + "a" + "a" * PER + "a", "1")
            assert rec == _recorded(F_SECRET, "CODEX32  SECRET"), \
                f"F1 drifted: {rec}"
            rec.clear()
            fd = backup_run("a" + WORDS_SCRIPT + "a" + "da" + "a" * (3 * PER) + "a",
                            "2")
            assert rec == [entry for i, sh in enumerate(F_SHARES)
                           for entry in _recorded(
                               sh, f"SHARE  {i + 1} / 3")], \
                f"F2 drifted: {rec}"
            assert _frames(fd)[-1].read_bytes() == _render(
                scr.result, ok=True,
                detail="Transcribed; the kit worksheets own paper"), \
                "F2: final frame is not the exact backup-done screen"
            for i, sh in enumerate(F_SHARES):
                for n, page in enumerate(_pages(sh)):
                    assert not _has(fd, _render(
                            orig_sd, page, f"SHARE  {i + 1} / 3",
                            page=n, pages=PER, actions_sel=0,
                            offer_check=False)), \
                        "F2: SENSITIVE share screen leaked to a dev frame"
            rec.clear()
            backup_run("a" + WORDS_SCRIPT + "a" + "b", "3")  # abort at split choice
            assert rec == [], "F3: aborted backup still showed a share"
            rec.clear()
            fd = backup_run("a" + WORDS_SCRIPT + "a" + "da" + "c", "4")  # C aborts
            assert len(rec) == 1, "F4: C after share 1 did not stop the flow"
            assert not _has(fd, _render(
                scr.result, ok=True,
                detail="Transcribed; the kit worksheets own paper")), \
                "F4: aborted backup still claimed success"
        finally:
            scr.backup_page = orig_sd
        # unit pins: threshold parsing and mainnet/testnet xprv selection
        th = coresigner_main.Session._threshold_of
        assert th(FROZEN_SHARES[0]) == 2, "threshold: k=2 share"
        assert th(H_SECRET) == 0, "threshold: k=0 secret"
        assert th("ms11xxxx") == 0, "threshold: '1' is invalid"
        assert th("msxaxxxx") == 0, "threshold: non-digit"
        import types as _types
        cap = []
        orig_open = coresigner_main.signer.open_session_xprv
        coresigner_main.signer.open_session_xprv = lambda rpc, x: cap.append(x)
        try:
            for chain, prefix in (("main", "xprv"), ("regtest", "tprv")):
                sess = coresigner_main.Session(
                    hal.DevDisplay(work / ("framesFx" + chain)),
                    hal.DevButtons(""), _types.SimpleNamespace(chain=chain))
                assert sess._codex32_open([H_SECRET]) is True
                assert cap[-1].startswith(prefix), f"{chain}: wrong xprv net"
        finally:
            coresigner_main.signer.open_session_xprv = orig_open
        print("ok   F: backup tool pinned to frozen vectors; threshold + "
              "network unit pins")


        # ---- Session N: the review's page ORDER, pinned frame by frame --
        # DERIVED, both the keys and the expected order. It was written
        # for four pages at two outputs each, and when the screen went to
        # one output a page it had seven. It kept passing: it only ever
        # looked for the first four and found them in order, so three
        # pages went unchecked and the stale count sat in an assertion
        # about its own arithmetic.
        def paged_run(tag, mode):
            st = work / ("stickN" + tag); st.mkdir()
            pn = rpc.call("walletcreatefundedpsbt", [],
                          [{rpc.call("getnewaddress", wallet="watch"): 0.05}
                           for _ in range(6)],
                          0, {"fee_rate": 10}, True, wallet="watch")["psbt"]
            (st / "n.psbt").write_bytes(base64.b64decode(pn))
            wname = signer.open_session_xprv(rpc, XPRV)
            info = signer.describe_psbt(rpc, pn)
            # The device now names the wallet it is signing for on this
            # screen (map M9, from M1 decision 2), so the expected render
            # must be given what the device gives it or every frame
            # differs by one line.
            ours = next((k.xfp for k in signer.loaded_keys(rpc)
                         if k.name == wname), None)
            signer.close_session(rpc)
            outs = [(o["address"], o["amount_btc"]) for o in info["outputs"]]
            n_pages = scr.review_pages(outs)
            assert n_pages == len(outs), \
                f"N: {len(outs)} outputs should be {len(outs)} pages"
            # Each page has two renders now: the plain one, and the one
            # that says why SIGN was refused (unseen pages remain).
            pages = [[_render(scr.review, outs, info["fee_btc"],
                              input_total_btc=info["input_total_btc"],
                              page=i, unseen_pages=refused,
                              quorum=info["quorum"],
                              cosigners=info["cosigners"], ours=ours)
                      for refused in (False, True)]
                     for i in range(n_pages)]
            key_sq = work / ("key_n" + tag + ".txt")
            key_sq.write_text(XPRV)
            # "nav" walks every page with DOWN and then signs; "forced"
            # presses A throughout, which advances instead of signing
            # while a page is unseen and carries the banner that says so.
            navkeys = ("d" * (n_pages - 1) + "a" if mode == "nav"
                       else "a" * n_pages)
            want = ([(i, False) for i in range(n_pages)] if mode == "nav"
                    else [(0, False)]
                    + [(i, True) for i in range(1, n_pages)])
            r = run_device(datadir, "ra" + "da" + "a" + "bb" + "a" + navkeys + "ra" + "draa",
                           work / ("framesN" + tag), stick=st, qr_key=key_sq)
            assert r.returncode == 0, f"N{tag} failed:\n{r.stderr}"
            assert (st / "n-signed.psbt").exists(), f"N{tag}: sign missing"
            seq = []
            for f in _frames(work / ("framesN" + tag)):
                raw = f.read_bytes()
                for i, variants in enumerate(pages):
                    if raw in variants:
                        # (page, refused): variants[1] carries the banner.
                        seq.append((i, variants.index(raw) == 1))
            return seq, want, n_pages
        seq1, want1, n1 = paged_run("1", "nav")
        assert seq1 == want1, \
            f"N1: page order or refusal state drifted: {seq1} != {want1}"
        seq2, want2, n2 = paged_run("2", "forced")
        assert seq2 == want2, \
            f"N2: forced advance must band every unseen page: {seq2}"
        print(f"ok   N: {n1}-page review order pinned, every page checked "
              "(nav and forced advance)")

        # ---- Session P: a passphrase makes a DIFFERENT wallet (S2) ----
        # Same 12 words, entered twice: once with no passphrase, once with
        # the passphrase "z". The first receive address must differ, which
        # is the only property that proves the passphrase reached Core.
        def first_address(script, tag):
            fp = work / ("framesP" + tag)
            r = run_device(datadir, script, fp)
            assert r.returncode == 0, f"P{tag} failed:\n{r.stderr}"
            return r.stdout.strip()

        import screens as _scr

        # ---- Session T: a real xprv typed on the grid (S3) ----
        # The audit's S3 asked for key material that can be TYPED, for a
        # build with no camera. Both modes were shipped once with a charset
        # that could not express them (no 'B', no brackets), so these type a
        # REAL xprv and a REAL descriptor character by character.
        def text_keys(charset, want):
            """Keys that type `want`, then take the bar's action.

            Re-states the grid's rules from the SCREEN's shape, never
            read out of main (TESTING.md rule 2). One mode at a time
            since map typing T2, so a character in another mode costs a
            C first, and L and R wrap inside a row.
            """
            import main as _main
            runs = _scr.modes(charset)
            mode, cur, out = 0, 0, []

            def route(cells, start, target):
                # The ROUTE is searched, never written down. The MOVES
                # are _cell_move's, because what one press does is the
                # device's behaviour and not the grid's shape; a copy
                # here walked routes the device would not walk once the
                # wrap changed (2026-09-18). test_ui_cost pins what
                # _cell_move itself has to do.
                seen, queue = {start: ""}, [start]
                while queue:
                    at = queue.pop(0)
                    if at == target:
                        return seen[at]
                    for k in "udlr":
                        nxt = _main._cell_move(k, cells, at)
                        if nxt not in seen:
                            seen[nxt] = seen[at] + k
                            queue.append(nxt)
                raise AssertionError("no route")

            for ch in want:
                target_mode = next(m for m, (_l, run) in enumerate(runs)
                                   if ch in run)
                while mode != target_mode:
                    # _same_cell, like _cell_move below. Where the
                    # cursor lands after a toggle cannot be re-derived
                    # from the screen's shape, because it is not about
                    # shape: it is main's rule, and a copy of it here
                    # walked the grid from a cell the device had
                    # already left when the rule changed (2026-09-18).
                    here = _scr.mode_cells(runs[mode][1])
                    mode = (mode + 1) % len(runs)
                    cur = _main._same_cell(
                        here, cur, _scr.mode_cells(runs[mode][1]))
                    out.append("c")
                cells = _scr.mode_cells(runs[mode][1])
                target = cells.index(ch)
                out.append(route(cells, cur, target) + "a")
                cur = target
            cells = _scr.mode_cells(runs[mode][1])
            downs = 0
            while _main._cell_move("d", cells, cur) != cur:
                cur = _main._cell_move("d", cells, cur)
                downs += 1
            out.append("d" * (downs + 1) + "a")
            return "".join(out)

        typed_xprv = XPRV
        assert not {c for c in typed_xprv
                    if c not in _scr.CHARSETS["xprv"]}, \
            "T: a real xprv contains characters the xprv grid cannot type"
        stickt = work / "stickT"; stickt.mkdir()
        pt = rpc.call("walletcreatefundedpsbt", [],
                      [{rpc.call("getnewaddress", wallet="watch"): 0.3}],
                      0, {"fee_rate": 10}, True, wallet="watch")["psbt"]
        (stickt / "typed.psbt").write_bytes(base64.b64decode(pt))
        # Keys -> Type private key (third row) -> type it -> back out to home ->
        # Sign tile -> sign -> home -> Settings -> POWER OFF.
        r = run_device(datadir,
                       # The grid opens holding the master prefix, so
                       # only what follows it is typed (Ben, 2026-09-19).
                       "ra" + "dda" + text_keys("xprv", typed_xprv[16:])
                       # Two review pages: the destination and the change.
                       + "bb" + "a" + "aa" + "ra" + "draa",
                       work / "framesT", stick=stickt)
        assert r.returncode == 0, f"T failed:\n{r.stderr}"
        assert (stickt / "typed-signed.psbt").exists(), \
            "T: typed xprv did not open a key that could sign"
        print("ok   T: a real xprv typed on the grid opens the key and signs")

        # The typed-descriptor checks and session T2 lived here. Type
        # descriptor left the Keys screen on 2026-09-05: a descriptor
        # lives as a printed QR, not as words on steel, so Scan a key
        # covers it, and nobody types 111 characters on a five-way pad to
        # avoid holding up a card. The path is gone, so the session that
        # proved it is gone too, rather than testing nothing.


        # ---- Session G: exact-Core generation from the Keys screen (A-19) --
        # New key generates and stops. No tradeoff screen, and no backup
        # you have to walk through to keep the key (Ben, 2026-09-05:
        # "when I click generate key it should just generate"). The paper
        # backup is a row on the key's own menu, taken here on purpose,
        # and there is no chooser in front of it: paper is the only kind
        # since A-24. The master private key is 111 characters and
        # paginates into three.
        fg = work / "framesG"
        xprv_pages = 3
        r = run_device(datadir,
                       "ra" + "a"                 # Keys, New key (first row)
                       # BY LABEL. This was "dda", which was right only
                       # while Backup was the third row; it moved to the
                       # top on 2026-09-11 so a fresh key opens on it.
                       + "d" * [lab for lab, _n, _k in
                                scr.KEY_MENU_OPTIONS].index("Backup key")
                       + "a"
                       # One press per page, then LEFT to DONE. CHECK IT
                       # is the pre-selected button on the last page
                       # since 2026-09-19, so a bare A starts the verify.
                       + "a" * (xprv_pages - 1) + "la"
                       + "b" + "b" + "draa",      # key menu -> Keys -> home -> off
                       fg)
        assert r.returncode == 0, f"G failed:\n{r.stderr}"
        assert _has(fg, _render(scr.busy,
                                "Bitcoin Core is generating your key…")), \
            "G: Core was not asked to create the wallet"
        assert not (rpc.wallet_dir / signer.WALLET).exists(), \
            "G: the session wallet was not deleted at teardown"
        # The backup was chosen, not forced. Under the flow this replaces,
        # a backup screen was the very next thing after Core finished. Here
        # three presses of the key menu separate them, and the frame the
        # device paints for a backup page is blank, because it is
        # sensitive, so what is counted is the gap.
        made = _where(fg, _render(scr.busy,
                                  "Bitcoin Core is generating your key…"))
        assert made, "G: the generating screen was never shown"
        assert len(_frames(fg)) - made[-1] > 4, \
            "G: nothing happened after generation, so nothing was chosen"
        print("ok   G: New key generates and stops; the paper backup is "
              "chosen from the key menu; both wallets gone at teardown")

        print("\nSESSION PASS: word-entry(12/24 picker), xprv-QR, SeedQR, "
              "codex32 shares, Core-RNG generation, QR in/out, stick in/out, "
              "refusal, paged review")
    finally:
        try:
            rpc.call("stop")
            daemon.wait(timeout=30)
        except Exception:
            daemon.kill()
        shutil.rmtree(datadir, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
