# Seed Generation, Seed In Use, Seed At Rest: An Honest Map of Bitcoin Self-Custody

*Draft v4, 2026-09-15. For Bitcoin Butlers. The framework of this article,
one secret weighed across three phases of its life, comes from jimbocoin.
Every checkable claim carries a link; quotations from jimbocoin, Ben
Westgate, FractalEncrypt, @heavilyarmedc and @btcpavao come from public
posts and correspondence, and are reproduced in full rather than summarised
where they carry an argument against this article's own conclusions.*

---

Most Bitcoin users believe one sentence that is only half true: "my twelve
words are my wallet."

The words are one piece of a system with three distinct phases, and each
phase has its own threats, its own tools, and its own ways to fool
yourself. A seed is **generated** once, **used** every time you sign, and
**at rest** in your backups for decades. Most custody advice argues about
one phase while silently assuming the other two are fine. This article
walks all three, using what we learned building and testing signing
setups across every model below, and it names the trade-offs the industry
prefers to round off.

## Phase 1: Seed generation, or the problem nobody can audit

Every wallet begins with one gulp of randomness. Every property you will
ever have flows from those 128 or 256 bits being genuinely unpredictable.
And here is the uncomfortable fact this phase turns on: **a compromised
random number generator is undetectable from its output.** A malicious or
broken generator can emit seeds that pass every statistical test ever
devised while being predictable to whoever planted the flaw. This is not
a hypothetical class: the [Dual_EC_DRBG backdoor](https://en.wikipedia.org/wiki/Dual_EC_DRBG)
was a standardized, NIST-blessed generator with exactly this property. You
cannot audit randomness by looking at it. Firmware review helps the one
percent who read code; nobody reviews the silicon.

This stopped being theoretical. In 2026, a Coldcard entropy failure
demonstrated the exact scenario: seeds from the device's compromised RNG
path were at risk, while seeds derived from user-supplied dice rolls
remained secure (documented in the
[SeedSigner dice-generation analysis](https://kdmukai-bot.github.io/seedsigner-ai-analysis/dice/standard.html)).
One sentence from that analysis deserves to be engraved somewhere:
**"You have to trust a seed a device creates for you. You can verify a
seed you rolled yourself."**

The asymmetry that saves us: generation is unverifiable, but everything
after generation is deterministic and therefore checkable. If the entropy
comes from your own hands, the device's remaining work (checksum,
derivation, addresses) can be cross-checked against independent software
and a liar gets caught. Physical entropy converts the one untrustable step
into the one step you performed yourself.

So: dice or cards?

**Dice, examined honestly.** The instinctive worry about dice, biased
faces, turns out to be the wrong worry.
[Measured real-world dice bias](https://kdmukai-bot.github.io/seedsigner-ai-analysis/dice/standard.html)
runs around 1.4 percent, which costs a 24-word seed roughly 2.9 bits out
of 256. Negligible. The real problems are human and structural. Human: the
procedure is boring, and a bored human skips steps; twenty honest rolls
followed by eighty impatient button-mashes is not entropy, and nothing in
the procedure catches it. Structural, and this is the decisive one: **the
mapping from rolls to seed happens inside software.** A
[survey of seventeen implementations](https://kdmukai-bot.github.io/seedsigner-ai-analysis/dice/standard.html)
found five incompatible constructions: hash the digit string, remap sixes
then hash, pack bits directly, treat the rolls as one base-6 number, or
use a worksheet. Identical rolls produce different seeds on different
devices.

How far can a determined human push the mapping out of software? Arman
The Parman's guides
([site](https://armantheparman.com/dicev1/),
[worksheets](https://github.com/ArmanTheParman/PrivateKeyWithDice))
mark the exact boundary: dice to binary, binary to words, all of it by
hand on paper, except one step. The checksum is a SHA-256 hash, and his
own instructions reach for an offline computer for that single command
before returning to hand conversion. No human computes SHA-256 on paper,
so every dice-to-BIP39 construction keeps at least that one foot in
software, and most keep the whole mapping there. That boundary is a
design artifact of BIP39's hash choice, not a law:
[codex32 (BIP93)](https://github.com/bitcoin/bips/blob/master/bip-0093.mediawiki)
uses a BCH checksum built from lookup tables precisely so that checksums,
verification, splitting and recovery are all, in the spec's own words,
possible "entirely using pen and paper." The mitigation exists, verify with
disposable test rolls against a second implementation, but the dependence
never goes to zero.

**Cards, examined honestly.**
[SeedPicker Solitaire](https://github.com/jimbojw/seed-picker-solitaire)
(jimbocoin's procedure) was designed against six criteria: easy to learn,
hard to screw up, errors detectable, fast, enough entropy, resists bias.
A standard 52-card deck, riffle-shuffled seven times
([the count research says suffices](https://en.wikipedia.org/wiki/Shuffling)),
then 23 pairs drawn without replacement. Each pair maps to a seed word
through a **printed lookup table**, and a shortcut removes even the
table-reading risk: pairs of different suits always land on a valid word.
The 24th word is the checksum, so a transcription error announces itself
instead of surfacing years later as a wallet that restores empty. The
full-deck draw preserves
[slightly more than 205 bits](https://github.com/jimbojw/seed-picker-solitaire),
comfortably past the 128 bits that matter once a public key is exposed.

Why cards beat dice is now precise: **the deck maps to words on paper, in
the open, by lookup; dice map to seeds inside arithmetic you cannot
perform.** With cards, the offline device only computes the final checksum
word, and that single computation is cross-checkable. With dice, the device
performs the whole conversion, and five mutually incompatible conventions
mean even honest devices disagree. Shuffling is also a skill humans
practice for fun, which is not nothing: the procedure people enjoy is the
procedure people complete.

The bias objection to human entropy deserves its steel-man, because the
"do not roll your own randomness" advice came from somewhere real: humans
inventing "random" values from their heads are catastrophically
predictable, and humans get bored inside long procedures and start
improvising. The cards answer both, not by asking the human to be random,
but by making the physics short, pleasant, and checksummed. The human
shuffles; the deck is random.

**Ranked by how much unverifiable trust each method requires:** cards the
least (one cross-checkable computation), dice next (the whole mapping,
mitigated by test-roll verification), device RNG the most (the one step
that can never be audited). Device generation remains a defensible
convenience at small amounts; the Coldcard incident is the price sheet
for that convenience at large ones. It is also why some signing devices exclude
on-device generation from their scope entirely: a signer with no entropy
story has no entropy story to attack.

## The second axis: who compiled the code that touches your keys

Phase 1 ranked three ways of making a secret by how much unverifiable trust
each one needs. That ranking holds, and it is incomplete. It weighs the
entropy and says nothing about the binary that consumes it. A perfect
shuffle handed to a backdoored library is a perfect shuffle wasted. Two
practitioners put the missing axis plainly, and both deserve their full
length rather than a paraphrase.

**The toolchain argument.**
[@heavilyarmedc](https://x.com/heavilyarmedc/status/2099879826949620126):

> Very few people in Bitcoin seem to understand that a sophisticated attacker would not hide security flaws in an apps viewable source code.
>
> They would hide it in the prebuilt crypto binaries (AKA the thing that actually touches your private keys).
>
> These much more difficult to properly audit and its one of the many reasons why Bitcoin Core is the gold standard for the security critical functions of a Bitcoin Wallet (both generating secure keys AND signing).
>
> After "the incident" with coldcard, the overton window has shifted drastically towards entropy, but random enough entropy is only one small piece of what makes cryptography safe.
>
> Those of you that are overly focused on "entropy" and wanting to "roll the dice", are actually rolling dice on a single point of failure.
>
> Bitcoin Core is one of the very few projects that takes this seriously enough to actually pin its entire build toolchain with guix.
>
> This means that dozens of independent contributors can, on their own hardware, run the Guix build and publish their own signed hash attestation that the crypto libraries they ship are exactly what they claim to be.
>
> You simply aren't going to find this assurance in the rest of these projects, even the ones that look like they have a ton of github activity (i.e. open source review and contribution).
>
> They all rely on single points of trust, which is most often, trusting the one single party that built the crypto library isn't going to rug you with a backdoor.
>
> Bad actors will intentionally distract users from this by publishing attestations that prove nothing of substance. End users see a SHA256SUMS file and think verifying it gives them security...
>
> ...but the only thing it proves is that nobody messed with the app after it got strung together with some spooky crypto library compiled by some anonymous contributor in Ukraine.

He compressed it himself in a follow-up, and the compression is the part worth
keeping:

> TLDR
>
> In most cases, the only thing verifying a SHA256SUMS file for a piece of Bitcoin software tells you is that you are downloading the same thing the maintainer uploaded.
>
> But it tells you very little about what they actually uploaded, unless you use Bitcoin Core.

That distinction is the whole section in two sentences. A checksum answers a
transit question. Reproducibility answers a provenance question. Most people
verifying a download believe they have answered the second when they have
answered the first.

**The same argument, published six months earlier.** The thread points at Mike
Schmidt's
["The Core Issue: Beneath The Binary, Verifying Trust"](https://bitcoinmagazine.com/print/the-core-issue-beneath-the-binary-verifying-trust)
in Bitcoin Magazine, 24 March 2026, which sets out the build system from the
maintainers' side. Four things in it matter here.

**Its root is older than Bitcoin.** Schmidt traces the whole problem to Ken
Thompson's 1984 essay *Reflections on Trusting Trust*, which showed that clean
source code proves nothing if the compiler that built it was compromised.
Reproducible builds are the answer to that specific attack, and @heavilyarmedc
is describing the same attack forty years later.

**The line everyone quotes is not Schmidt's.** It belongs to Bitcoin Core
contributor Michael Ford, who signs as fanquake, and Schmidt quotes him:
"Reproducible builds are critical, because no user of our software should have
to trust that what's contained inside is what we say it is. This must always
be independently verifiable." Schmidt's own framing sits beside it: the build
process is itself an attack surface to be minimised and defended.

**Attestation is open to the public.** This is the detail that gives the
number below its weight. Schmidt is explicit that signing is not restricted to
Core developers, that the process is open to anyone, and that many
non-code-contributors regularly contribute signatures. So the sixteen are not
sixteen insiders vouching for each other. In his phrase, the official binaries
are "the intersection of dozens of independent builders' outputs."

**And the limit, which he states plainly and which this article must carry.**
Reproducible builds prove that a binary is a genuine representation of its
source code. They prove nothing about whether that source code is any good.
Schmidt puts the boundary directly: correctness "is left to processes around
thorough testing and code review." So the toolchain axis answers one question
completely and another not at all. Sixteen builders agreeing means nobody
slipped anything in between the source and your download. It does not mean the
source is free of bugs, and no attestation count will ever mean that.

Two further properties from the piece bear on the dependency test at the end
of this article. Core has been removing third-party dependencies for a decade,
OpenSSL and MiniUPnP gone, Boost and Libevent being phased out, with fully
static binaries as the goal, because every inherited dependency is code you did
not write and cannot audit. And Core has never shipped automatic updates and
its developers say it never will, on the reasoning that an auto-update channel
is a single group able to push code to every node. A new binary reaches you
only when you choose to fetch and verify it.

Schmidt does not count builders. That is the one number this article supplies
below.

**The record, checked rather than repeated.** The reproducibility claim is
testable, which is the point of it, so we tested it. Bitcoin Core 31.1
carries Guix attestations from sixteen independent builders, each having run
the pinned toolchain on their own hardware and published a signed hash:
`0xb10c`, `Emzy`, `Sjors`, `achow101`, `benthecarman`, `fanquake`,
`guggero`, `hebasto`, `m3dwards`, `marcofleon`, `pinheadmz`, `sedited`,
`sipsorcery`, `svanstaa`, `theStack`, `willcl-ark`. Counted directly in the
[guix.sigs repository](https://github.com/bitcoin-core/guix.sigs/tree/main/31.1)
on 2026-09-15, where each name is a directory holding that builder's
attestation. Sixteen parties who do not need to trust each other arrived at
identical binaries. No signing device in this article can make that claim,
and most cannot make any claim about their toolchain at all.

**The same record, and a wider conclusion.**
[@btcpavao](https://x.com/btcpavao/status/2099891574779875630) names the same
sixteen and pushes past the build question into a second one:

> Strongly agree.
>
> When I verified Bitcoin Core 31.1 myself, I didn't stop at checking the SHA256 hash.
>
> I imported public PGP keys and verified signatures. More importantly, Bitcoin Core uses reproducible Guix builds: independent builders can build the same release on their own machines and attest that they arrived at the same binaries.
>
> Bitcoin Core 31.1 has Guix attestations from 16 independent builders:
>
> 0xb10c — github.com/0xb10c
> Emzy — github.com/Emzy
> Sjors — github.com/Sjors
> achow101 — github.com/achow101
> benthecarman — github.com/benthecarman
> fanquake — github.com/fanquake
> guggero — github.com/guggero
> hebasto — github.com/hebasto
> m3dwards — github.com/m3dwards
> marcofleon — github.com/marcofleon
> pinheadmz — github.com/pinheadmz
> sedited — github.com/sedited
> sipsorcery — github.com/sipsorcery
> svanstaa — github.com/svanstaa
> theStack — github.com/theStack
> willcl-ark — github.com/willcl-ark
>
> That is a radically different trust model from simply checking a checksum published by the same party that gave you the binary.
>
> And frankly, it seems crazy to me that so much of the current discussion has shifted toward worrying about whether users need to generate their own randomness.
>
> We routinely trust general-purpose computers and modern operating systems to generate cryptographically strong passwords, passphrases and keys.
>
> Password managers do this every day.
>
> Anyone who has looked at how a modern OS seeds and maintains its CSPRNG knows that it continuously incorporates entropy from system and hardware events and exposes secure randomness once properly initialized.
>
> On a clean, freshly installed general-purpose OS, I am far more comfortable relying on a mature OS CSPRNG and well-reviewed cryptographic software than inventing my own entropy ceremony with dice.
>
> The bigger question for me is why we keep introducing specialized Bitcoin hardware in the first place.
>
> A device whose explicit purpose is securing Bitcoin creates targetedness. Manufacturers, payment processors, fulfillment companies, shipping providers and other third parties may now have economically valuable information about you: you probably own Bitcoin.
>
> If that data leaks, it can enable targeted phishing, social engineering, fake firmware or support messages, seed extraction attempts, SIM attacks, extortion or physical coercion — without anyone breaking the cryptography inside the device.
>
> The same trade-off exists with the current mantra of multi-vendor hardware-wallet multisig.
>
> Multisig can reduce key-compromise and correlated-device risk.
>
> But on the targetedness axis, every additional hardware-wallet vendor can add another manufacturer, customer database, supply chain, shipping provider, email system and specialized dependency to your threat model.
>
> If you wanted to create the biggest possible operational headache for yourself and your future heirs, one way would be to buy one device from every hardware-wallet vendor you can find.
>
> And there is certainly no shortage of them.
>
> You'd accumulate a huge specialized attack surface while repeatedly signaling to companies and their third-party providers that you are someone who takes Bitcoin custody seriously enough to buy dedicated signing devices.
>
> To me, that is completely backwards.
>
> Once you see the targetedness problem, you can't unsee it.
>
> My preference remains:
>
> Generic hardware.
> Linux.
> Bitcoin Core.
>
> Minimize specialized dependencies.
> Minimize targetedness.
> Minimize attack surface.

**Where this lands against Phase 1, honestly.** Take the strongest form of
the disagreement first. Both posts say the entropy argument is the wrong
thing to obsess over, and one of them would rather trust a mature operating
system's CSPRNG on a clean install than run a dice ceremony. Phase 1 said
device generation carries the most unverifiable trust. Both claims are
correct, because they are claims about different things.

Phase 1's asymmetry survives intact: a CSPRNG's output cannot be verified,
and an OS CSPRNG is no exception, however well seeded. What the posts
establish is that the same asymmetry applies one layer down, to the code
performing the derivation and the signing. A shuffle you watched is worth
less if the library turning it into a key was compiled by a party you
cannot identify. So the honest statement is that self-custody has two
unverifiable-trust axes, not one:

- **Entropy provenance.** Did you witness the randomness? Cards the least
  trust, dice next, device RNG the most. Unchanged from Phase 1.
- **Toolchain provenance.** Can independent parties prove the binary
  matches the source? Bitcoin Core, alone in this article, answers yes
  sixteen times over. Nearly everything else answers with a checksum
  published by the same party that shipped the binary, which proves only
  that the file did not change in transit.

The dice critique cuts hardest exactly where Phase 1 already conceded. Five
incompatible dice-to-seed constructions are a toolchain problem wearing an
entropy costume: the rolls are yours, the arithmetic is not, and you cannot
check the arithmetic. The card procedure is the one method that answers both
axes at once, because the mapping is a printed lookup table and the only
computation left is a single cross-checkable checksum.

These two axes are independent, so nothing forces a choice between them.
Card entropy feeding Bitcoin Core satisfies both, and this article already
reached that conclusion from the other direction when it noted that
card-generated seeds would close Yeti Cold's one open gap.

**Targetedness, the axis this article had not priced.** The second half of
@btcpavao's post is a harder challenge, and it lands. A dedicated signing
device is a purchase that tells a manufacturer, a payment processor, a
fulfilment house and a courier that you probably own Bitcoin. The
cryptography inside the device is irrelevant to that leak. Multi-vendor
multisig, which this article calls the ceiling for large holdings,
multiplies the leak by the number of vendors: more customer databases, more
shipping records, more support inboxes, each one a place your name sits next
to the fact that you take custody seriously enough to buy hardware for it.

This is a real cost and the article had not named it. It is also a cost with
a known shape rather than an argument-ender. Generic hardware does not
escape correlation, it relocates it: the laptop was still bought somewhere,
and the coins were still acquired somewhere, and for most holders the
exchange that sold them their Bitcoin already holds the strongest version of
this information. Cash purchase, second-hand generic hardware and delivery
to somewhere other than home each cut the leak, and none of them require
choosing between Core and a signing device. The trade is real in both
directions: a signer with no radios and a screen you verify against buys you
something a general-purpose laptop cannot, and it buys it at the price of
being a Bitcoin-shaped purchase.

So targetedness joins the list of trusts to name rather than the list of
reasons to stop. The weighing below now carries it as its own line.


## Phase 2: Seed in use, or who signs and on what

Signing is where the seed touches a computer. Three questions decide
everything: whose wallet code runs, on what hardware, and what does the
device remember afterward.

**Whose code.** Hardware wallets run their vendor's implementation.
SeedSigner-class DIY devices run a small open reimplementation chosen for
auditability. A third model runs the reference implementation itself,
Bitcoin Core, wallet-only and offline, on the argument that Core's wallet
logic is the most reviewed in existence. [Yeti Cold](https://yeticold.com/), JW Weatherman's protocol
([source](https://github.com/JWWeatherman/yeticold)), makes the same bet
at system scale: nearly everything it does is Core, on the argument that
you depend on Core anyway, so depend on only that.

State the counter-argument fairly, because it is strong, and it rests on
one epistemic premise jimbocoin states better than anyone: "The only time
you know for sure your seed hasn't leaked is before it has been entered
into any device. At any other time you can't be sure." No audit disproves
a leak you cannot see, so his answer is structural: multi-vendor multisig
where no single vendor ever sees a quorum of your seed material, because
it is vanishingly unlikely that two independent vendors carry an
exfiltration bug at the same time, exploitable by the same parties.
Ideally you even reproduce the coordination (the coordinator: the online
watch-only wallet app, such as Sparrow, that builds transactions for your
signer to approve) on two independent stacks and confirm both derive
identical addresses before funding. Core is
simultaneously the most reviewed codebase in Bitcoin and its most valuable
infiltration target. Which risk is larger, one infiltration of the
best-reviewed honeypot or a coordinated simultaneous infiltration of
several smaller vendors, is genuinely unresolved; whichever side of that
bet a setup takes, it is a bet, and it deserves to be held with open
eyes.

**On what hardware, and the question you asked us straight: the wiped
laptop.** The standard air-gap recipe says factory-reset an old laptop and
never connect it. Honesty requires saying what that does not achieve. A
wipe replaces the software; it does not remove the WiFi and Bluetooth
hardware, and every off-switch you can reach from the keyboard is a
software claim about that hardware. The OS toggle, rfkill, even the BIOS
setting are all promises made by code you cannot see, on radios that are
still physically powered. For most threat models the promise is probably
kept. "Probably kept" is not an air gap.

The honest ladder, weakest to strongest:

1. Software disable (settings, rfkill, BIOS): a claim, not a fact.
2. Driver removal or an OS that never ships the drivers: a stronger claim,
   still software.
3. **Open the laptop and pull the radio card.** In most laptops WiFi and
   Bluetooth live on one small M.2 or mini-PCIe card with two antenna
   leads. Ten minutes with a screwdriver converts "promised off" into
   "physically absent." If you keep a laptop signer, this is the step that
   makes the word air-gap true.
4. Hardware manufactured without radios: a Pi Zero v1.3 or a no-wireless
   Compute Module instead of a Zero 2 W with its radio on the die.
   "Cannot transmit" outranks every promise on the list.

Yeti, to its credit, is honest about its own gap: keys cross to the
networked machine on USB sticks because Core has no offline QR signing,
and the protocol accepts that as a measured compromise. USB is a wider
channel than photons through a camera, and a stick is writable both ways.
Reasonable people accept it; nobody should accept it unknowingly.

**What the device remembers.** A hardware wallet keeps your key inside it,
guarded by a PIN and a secure element, from setup until loss. A stateless
signer (SeedSigner-class) holds nothing: you bring the seed each session,
sign, power off, and the device forgets. Statelessness means a seized
device is just electronics. Its price must be stated with the same
honesty, and jimbocoin's premise above sets it: the seed is exposed in the
room at every use, and every entry into a device is another moment after
which "it has never leaked" can no longer be known for certain. The
stateless answer (the same audited device each time, nothing persisted,
a reproducible binary) is a real answer, not a complete one. Pick
deliberately: state guarded by silicon, or no state and disciplined
handling.

One asymmetry to complete the picture: a malicious signer can leak key
material through its signature nonces while producing normal-looking
transactions. Some hardware wallets counter with
[anti-exfil protocols](https://blog.blockstream.com/anti-exfil-stopping-key-exfiltration/)
where the coordinator contributes randomness. A Core-based signer cannot
run those protocols, because Core generates its own nonces and offers no
hook; its answer is that the signing binary is Core's reproducible,
hash-verified build. Anti-exfil
defends against a compromised build, transparency defends against a
compromised vendor, and neither defends against both.

**Who you still depend on after the sale.** The 2026 Coldcard incident
surfaced a fourth question that the first three hide: after you buy a
signer, what still requires its maker? The property [Shinobi named](https://x.com/brian_trollz/status/2090155610994065573)
as the real loss was not a feature but a freedom: a device
that never required the vendor's app to generate keys, to sign, or to
update firmware, and never sent an xpub to a vendor server during setup.
Most reputable hardware wallets fail at least one of those tests, and a
setup performed on an online computer with the vendor's companion app
typically discloses your extended public keys, and therefore your entire
balance history, to that vendor. The systems that pass all four tests
today are the DIY and Core-based classes, which buy the freedom with
labor; the assessment each person must make is how much vendor
dependency they accept, and whether they could keep operating, and
eventually replace, every component of their setup if its maker vanished
or turned. Tony of The Bitcoin Way [framed the goal precisely](https://x.com/v4btc/status/2090159244981211599): design the
setup so that no manufacturer, application, server, firmware ecosystem,
or single device becomes a dependency you cannot escape.

A second honest note from the same debate: open source is an inspection
property, not by itself a security property. Source availability lets
you verify software you compile and run; on a hardware device it cannot
prove that what runs is what you loaded (that requires attestation, which
open DIY devices lack), it cannot open the chip's own black-box
firmware, and "many eyes" is a hope, not a threat model. Secure-element
vendors make this argument in defense of their closed layers, and the
argument is sound as far as it goes; what it purchases in physical-attack
resistance it pays for in vendor dependency and unauditable code, which
is the same trade this whole section describes, taken from the other
end. Neither side of it is free. And one principle survived the incident
intact on all sides: risk isolation and attack-surface minimization,
keys on a dedicated, single-purpose, offline device, remain correct even
when one implementation of them fails. A flawed signer does not argue
for keys on a networked general-purpose computer; it argues for signers
whose failures you can survive.

## Phase 3: Seed at rest, or the two backups

Now the phase where most coins are actually lost, and the distinction the
whole article hangs on.

**Your words back up a secret. A descriptor backs up a wallet.**
[BIP39](https://github.com/bitcoin/bips/blob/master/bip-0039.mediawiki)
words encode entropy and nothing else: no derivation path, no script type,
no birth date. Recovery from words alone is a guessing game played against shifting
conventions (the standard derivation path has moved three times:
[BIP44](https://github.com/bitcoin/bips/blob/master/bip-0044.mediawiki),
[BIP84](https://github.com/bitcoin/bips/blob/master/bip-0084.mediawiki),
[BIP86](https://github.com/bitcoin/bips/blob/master/bip-0086.mediawiki)),
which is why Core developer Gregory Maxwell
[opposed the standard from the start](https://github.com/bitcoin/bips/pull/17)
("The lack of versioning is a serious design flaw... On this basis alone
I would recommend against use") and why Bitcoin Core
[never implemented it](https://github.com/bitcoin/bitcoin/issues/17748). Underneath both formats sits the same machinery:
[BIP32](https://github.com/bitcoin/bips/blob/master/bip-0032.mediawiki)
hierarchical deterministic wallets, one master key deriving every address.
The words are one human-friendly door to that master key. Core's native
object, the
[descriptor](https://github.com/bitcoin/bitcoin/blob/master/doc/descriptors.md),
is the complete recipe around it: key, path, script type, checksum, one
line of text. Electrum
[rejected BIP39 for the same reason](https://electrum.readthedocs.io/en/latest/seedphrase.html)
and built version numbers into its own seed format. The wider ecosystem
shipped BIP39 anyway because words stamp into steel and elegance does
not.

The gap closes for the cost of one sheet of paper. Words on steel hold
the secret; a printed public descriptor beside your documents holds the
map. The descriptor cannot spend; its only effect is turning recovery
from archaeology into a lookup, so the tradeoff runs one way: a page of
non-spending paper against a guessing game decades from now.
With multisig the rule sharpens, with one exception worth knowing
(FractalEncrypt's point): in a 2-of-2, the two seeds alone can both
reconstruct the wallet and spend, and with only four script policies in
existence, brute-checking them is trivial, so the descriptor backup is
optional there. Anything above 2-of-2 flips it to mandatory: a 2-of-3
can spend with two seeds but cannot rebuild the wallet without the third
cosigner's public key, and only the descriptor carries it.

**What Core's own backup doc is telling you.**
[managing-wallets.md](https://github.com/bitcoin/bitcoin/blob/master/doc/managing-wallets.md)
describes wallet-file backups (keys plus labels, history, and the
descriptor set, richer than words and heavier: a file, on media, in one
program's format) and is refreshingly blunt about encryption: it protects
the file at rest, a keylogger defeats it, and "if the passphrase is lost,
all the coins in the wallet will also be lost forever." Encryption narrows
an attack; it does not remove one.

**Backup privacy, from the person who built the standard.** Ben Westgate,
author of [codex32 (BIP93)](https://github.com/bitcoin/bips/blob/master/bip-0093.mediawiki): encryption and secret-splitting are the tools for backup
privacy, so a single compromised hiding place reveals nothing; multisig
addresses different threats; and these are not either-or decisions. Want
one stolen backup to disclose nothing? Split the seed codex32-style,
k-of-n, checksums verifiable by hand on paper (that hand-verifiability is
[designed into the standard](https://github.com/bitcoin/bips/blob/master/bip-0093.mediawiki)).
codex32 also holds a property unique among backup formats, and the
epistemic premise from Phase 2 explains its worth: because its checksums
are hand-computable, a holder can verify a backup's integrity for
decades without ever re-entering the secret into hardware. That is the one
health check that costs no new exposure. Two boundaries complete the
picture. It encodes BIP32 master seeds, not BIP39 words, and Bitcoin
Core does not export seeds, so it applies to seeds born outside Core.
And jimbocoin's counter-position deserves its full strength: he
explicitly and generally discourages seed splitting, granting only rare
operational exceptions (his example: an exchange running a thousand
single-sig altcoins that needs a procedure employees can follow). His
reasoning is protocol-shaped: Bitcoin transactions natively support
M-of-N multisig, Taproot hides the structure on-chain, and reinventing
protocol functionality outside the protocol is where he draws the line;
secret-splitting earns its keep only for what the protocol cannot
express, such as metadata.

Laid side by side, the disagreement resolves into a taxonomy: there are
three different things a holder can split. **Split the spending
authority** (multisig: native, on-chain, the protocol enforces it).
**Split the seed** (codex32: off-chain mathematics, hand-verifiable, and
the option one side of this debate discourages on principle). Or **split
the key that encrypts a backup**: keep N identical copies of a
symmetrically encrypted payload, each stored beside one Shamir share of
the encryption key. That third design is where the two positions quietly
converge. Westgate's warning about hand-rolled 2-of-2s (an encrypted
backup here, its password there) is answered by it, because k-of-n
shares of the key turn the fragile pair into real redundancy, and both
he and jimbocoin endorse exactly this construction for encrypted
payloads and metadata. The remaining dispute is narrower than it first
appears: not whether splitting is legitimate, but whether the seed
itself is ever the right thing to split. Want theft of a whole
signer to be insufficient to spend? Multisig. Want both properties? Use
both. And the companion warning from the same thread: pairing an encrypted
backup with a separately-stored password hand-builds a fragile 2-of-2; if
you want 2-of-2, the protocol sells the real thing.

**Media and transcription.** Paper burns and fades; steel survives the
house fire; optical discs shrug at EMP and magnets; the archival industry
keeps tape in salt mines. Redundancy across media types is nearly free.
Yeti's transcription discipline (keys written in NATO phonetic alphabet
with periodic checksums) addresses the quietest failure of all,
because the failure that actually takes coins is one backup, in one place,
in one format, that quietly stopped being readable, and handwriting
ambiguity is part of that failure.

## Putting it together: five systems, and what each one costs

This section ranks nothing and recommends nothing. Each system below is
listed with what it answers, what it still trusts, and what it costs to
run. The axes are the ones this article has established: entropy
provenance, toolchain provenance, targetedness, loss modes, and effort. A
holder with ten thousand dollars and a holder with a family inheritance are
solving different problems, and no single answer serves both.

**Bitcoin Core on an online desktop, single-sig with encryption.** The keys
live full-time on an online, general-purpose machine. The doc's own
keylogger caveat applies, and the wallet passphrase adds a loss mode faster
than it removes a theft mode. Core's bridge for pairing with hardware
wallets, HWI,
[entered minimal maintenance in August 2026](https://github.com/bitcoin-core/HWI/issues/850)
by its maintainer's announcement, pending a third-party successor. To be
plain about the scope of that: running Core, running your own node and
verifying your own chain are all sound on this machine. Holding spending
keys on it is the part that carries the online attack surface.

**Hardware wallet plus card-generated seed.** An earlier draft called this
the lowest total unverifiable trust available at ordinary effort. The
toolchain axis makes that claim false, and it is worth saying why rather
than quietly deleting it. A signing device's firmware is the single point
of trust @heavilyarmedc describes: one party compiled the code that
touches your keys, and no independent builder can prove what shipped. So
this system lowers entropy trust and leaves toolchain trust at its maximum.
What it does answer is narrower and still real: card entropy closes the RNG
hole with only the checksum computed on the offline device, the keys never
sit on a general-purpose networked machine, signing is confirmed on a
second screen the host cannot paint, and steel words plus a printed
descriptor cover both halves of the backup. Its largest practical advantage
is effort, and effort decides what people actually complete. Its remaining trusts
are the vendor's firmware and supply chain, its remaining loss modes are the
human ones, and its remaining leak is targetedness: the purchase itself
tells several companies that you probably own Bitcoin. The BIP39 passphrase sits on a knife edge here: it
defends the steel if the steel is found, and it is the component most
often lost forever, so it trades a theft mode for a loss mode; written
and stored as seriously as the seed itself, with a small decoy balance on
the no-passphrase wallet, the trade tilts one way, and held only in a
skull it tilts the other.

**Bitcoin Core on an airgapped, clean machine.** This is the strongest form
of the Core case and the article's earlier draft never weighed it, which was
an omission. Radios removed rather than switched off, a freshly installed
system, PSBTs crossing on removable media, and the watch-only wallet living
on a separate online machine. Measured on the axes above it is the leading
system on three of them. Toolchain provenance: sixteen independent builders
can prove the binaries, and no signing device in this article can match
that. Targetedness: nothing about the purchase says Bitcoin. Vendor trust:
there is no firmware author and no supply chain to trust, so the entire
category of vendor risk disappears.

What it still carries is genuine. A general-purpose operating system is a
much larger body of code than a signer's firmware, so the airgap is doing
heavy work, and the airgap is a procedure rather than a physical fact.
Removable media is the crossing point, and USB is a worse crossing than a
QR code or an SD card. Address verification happens on the same machine
that composed the transaction, so a compromised host has one screen to lie
on rather than two. The seed-to-Core path also needs specifying: Core does
not read BIP39 words, and importing witnessed entropy as a descriptor
wallet is possible but the exact procedure is the open work, so treat that
step as unfinished rather than solved.

And the cost that decides it for most people is not a security property. It
requires installing Linux and working in a command line. Stating the
security case plainly does not change how many people will do that, and a
fraction will.

**Yeti Cold.** Core-only 3-of-7 multisig across cheap laptops and
geography: survives four lost keys, requires three compromised locations
to steal, trusts Core and nothing else, which is the one toolchain here
that sixteen independent builders can prove. Its honest costs: USB crossings
instead of QR, radios handled by procedure rather than by absence (pull
the cards), an on-chain fingerprint from the unusual quorum, and hours of
setup. And one charge this article's own first section requires us to
file: Yeti generates its seeds with Core's random number generator.
Jimbocoin's assessment is exactly right: arguably the best available
software generator, and epistemologically the same risk as letting a
Coldcard or any other manufacturer perform your seed genesis, because no
RNG's output can be verified. "If you're determined to trust a
counterparty, Core is the best counterparty to trust" is both Yeti's best
defense and its honest indictment, and card-generated seeds would close
the gap in Yeti just as they close it everywhere else. For deep cold
storage by someone who accepts the Core bet with that caveat attached, it
remains a serious, published, criticizable protocol, which is more than
most vendors offer.

**Multi-vendor multisig, no vendor a quorum.** The strongest answer to
"what if the implementation itself is the flaw": if no vendor ever sees
enough of your seed material to spend, no single vendor bug, however
invisible, can drain you. Judge it by the same six criteria the card
procedure was designed against: easy to learn, hard to screw up, errors
detectable, fast, enough entropy, resists bias. The cards pass because
they were engineered to pass. Multi-vendor multisig, today, fails the
first two for most people, and its own advocates concede the bind: making
it simpler means making the vendors more alike, and their unlikeness is
the security. For large holdings with a professional or a patient
operator, it is the ceiling. Sold to an average person as a starting
point, it mostly manufactures stuck funds. And it carries the highest
targetedness cost of the five, because every vendor added to the quorum adds
a customer database, a shipping record and a support inbox holding your name
next to the fact that you buy signing hardware.

## The through-line

This article names trades rather than picking one. What survives all three
phases is a set of questions, and the value is in asking all of them about
your own setup instead of arguing one of them loudly.

**Entropy provenance.** Did you witness the randomness, or did something
generate it for you? No generator's output can be audited, so this is
settled at the moment of creation or never.

**Toolchain provenance.** Can parties who do not trust each other prove the
binary matches the source? Sixteen can, for Bitcoin Core 31.1. A checksum
published by the party that shipped the file answers a smaller question. Keep
the boundary in view: this asks whether the binary matches the source, never
whether the source is correct.

**Where the secret rests, and what it restores.** Words back up a secret and
a descriptor backs up a wallet, so a backup holding only one of the two is
incomplete whatever it is stamped into.

**The dependency test.** If any single maker, app or server in your setup
disappeared tomorrow, could you still generate, sign, update and recover?
Every "no" is a trust you carry, whether or not you knew its name.

**The targetedness test**, which @btcpavao's post forces: for every trust
you keep, count who learned you own Bitcoin in order to grant it.

**Effort, counted honestly.** A procedure nobody completes protects nothing.
The strongest system on the axes above asks for a Linux install and a
command line, and stating its case plainly does not change how many people
will do that. A smaller number will, and they get a better answer. Whoever
designs custody advice has to hold both facts at once.

None of these questions remove trust. They locate it, and name it, which is
the difference between a threat model and a preference.

The words were never your wallet. They were one third of one phase of it.
Now you have the map.

---

*Helping people weigh the models above is literally our job.*
