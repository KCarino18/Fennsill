"""Build docs/Fennsill-V1-Plan.pdf from the Dec 31 board.

Source of the wording is this file. Re-run after edits:

    python docs/build_v1_plan_pdf.py
"""

from __future__ import annotations

import os
import sys
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
HTML = HERE / "v1_plan_print.html"
OUT = HERE / "Fennsill-V1-Plan.pdf"

ITEMS: list[dict] = []


def add(section: str, verdict: str, ident: str, title: str, **fields: str | list) -> None:
    ITEMS.append(
        {
            "section": section,
            "verdict": verdict,
            "id": ident,
            "title": title,
            **fields,
        }
    )


S_WEEK = "Weekly cards"

add(
    S_WEEK,
    "pilot",
    "V1D",
    "Build the V1D",
    why=(
        "V1 is the first panel you can hand to someone who does not have this repo open. "
        "The software train is already at 0.1.27 (16 November 2026): Windows Setup, Desk, "
        "the Agent service, Factory, and the hosted MCP at https://mcp.fennsill.com/mcp. "
        "Building V1 means that path works on a PC you do not remote into."
    ),
    now=(
        "A buyer is supposed to run FennsillSetup.exe once as Admin, plug the panel in over USB, "
        "sign up, link the Device ID, paste the device key into Desk, and add the MCP URL plus "
        "an Authorization: Bearer header in Claude, ChatGPT, or Cursor. The Agent pulls the job and "
        "pushes an 800 by 480 frame. Access runs 30 days from the first MCP call after a real Agent "
        "heartbeat. You renew it. The buyer cannot."
    ),
    done=(
        "One person outside the build follows only the Quick Start, gets a page on the panel, "
        "and keeps doing that for a week without you on their machine. The release that survived "
        "that week is named 1.0. Until then, ship 0.1.x."
    ),
    steps=[
        "Freeze the buyer steps above. New product ideas go to the After the pilot section of this document.",
        "Install the GitHub release of Setup on a Windows PC that did not build FennSill. Plug in a factory-flashed panel. Create an account, link the Device ID, paste the key.",
        "Push one page from Claude and one from ChatGPT, same panel, same account header.",
        "Write the one-page operator note: how you renew or revoke a month, how you publish a signed firmware manifest, and the four checks when a push sits (Agent service running, USB connected, access window open, device key pasted).",
        "Hand the Quick Start and a panel to one outsider. Collect every failure for a week. Those failures are the only V1 bug list.",
        "Tag 1.0 only after that week.",
    ],
    note="Shopify, Wi-Fi pull, grayscale, macOS, and templates are later cards, not steps on this one.",
)

add(
    S_WEEK,
    "pilot",
    "MILE",
    "Fill out your milestones",
    why="The weekly board asked for milestones, and the Dec 31 list had a date on every row. A date is not a milestone.",
    now="Every engineering row is assigned to KC and due 31 December 2026. The on-time figure on the weekly view was 81 percent against a 90 percent goal, with the same planning cards copied and overdue.",
    done="The board has three dates, and each card sits under one of them. This PDF is the write-up.",
    steps=[
        "Close the cards in the Close these decisions section. Paste the decision sentence from each card onto the ticket, then check it off.",
        "Leave a 31 December date only on the Finish before the pilot cards.",
        "Move every After the pilot card onto a milestone named After the first pilot week. Give that milestone no December date.",
        "Treat 31 December as: decisions written down, mailbox decided, and a Windows USB proof on a clean PC. The outsider's week can fall in January if they are not lined up yet.",
    ],
    note="Clearing duplicate copies of this card does not move the pilot.",
)

add(
    S_WEEK,
    "pilot",
    "ROLES",
    "Fill out roles and responsibilities",
    why="The Dec 31 board has one assignee on every row: KC. The earlier weekly list also showed initials SO and TW on the duplicate planning cards.",
    now="One person is sequencing firmware, cloud, factory, the store, and email. Two extra initials appear only on the weekly duplicates.",
    done="You can point at one owner for the December work. If SO or TW is another person, they have one seat each and a written boundary.",
    steps=[
        "If KC is the only person building this, say so on the card and stop splitting seats. The job is the order in this PDF: close decisions, write compliance and access, prove USB, then the pilot.",
        "If SO or TW is someone else, give one of them Device and the other Buyer path.",
        "Device owns Factory, the permanent serial, the device key, firmware, the display-not-detected message, and the regression checklist.",
        "Buyer path owns the account site, the MCP header, Setup, the Agent, the Quick Start, releases, the support mailbox, and holding Shopify, Wi-Fi, and local mode until after the pilot.",
        "Either way, neither person ships 1.0 while the privacy link is still missing.",
    ],
    note="The factory master key stays offline. It is not a shared login.",
)

S_CLOSE = "Close these decisions"

add(
    S_CLOSE,
    "close",
    "MS-10",
    "Make decision on infrastructure",
    why="This milestone is the parent of the local-versus-hosted, push-versus-pull, security, and stack cards. It stays open while those sentences are still unspoken on the board.",
    now=(
        "The running design is hosted. Buyers install a Windows agent that talks USB. "
        "Their AI calls https://mcp.fennsill.com/mcp. docs/SHIPPING.md says not to ship FennsillHost.exe. "
        "fennsill-host and panel-preview are marked deprecated. Cloud storage is SQLite in the cloud process."
    ),
    done="MS-10 is checked, and the four child cards below are checked with the same sentences.",
    steps=[
        "Write this on the card: Buyers use FennSill-hosted MCP. The PC agent pulls jobs and pushes frames over USB. Wi-Fi pull is a later mode. The server is our cloud process with SQLite. One repo through 1.0.",
        "Check SM-145, SM-146, SM-147, and SM-148 with the text from their cards.",
        "Leave SM-139 (split the GitHub repos) on the After the pilot milestone.",
    ],
    note="Revisit hosting when a second operator cannot run the current process, or when a buyer you want to keep refuses an account.",
)

add(
    S_CLOSE,
    "close",
    "SM-145",
    "Decide local vs hosted (or both) and write it up",
    why="The product had a local host in the tree and a hosted server in cloud/. Shipping both makes every support reply ambiguous.",
    now="Hosted is what Setup, Desk, and Factory already tell a buyer to use. The local host app is deprecated in the tree.",
    done="The card says: V1 is hosted only. A local no-account mode is SM-053 and stays parked.",
    steps=[
        "Paste the decision: FennSill hosts MCP. The buyer runs Setup, Desk, and the Agent. The buyer does not run a server and does not open a port.",
        "Confirm the release you hand a pilot does not include FennsillHost.exe.",
        "Point SM-053 at the reopen rule on that card.",
    ],
    note="Running both modes at once is how the board grew a second copy of every delivery ticket.",
)

add(
    S_CLOSE,
    "close",
    "SM-146",
    "Decide push vs pull for content delivery",
    why="USB push and Wi-Fi pull solve different rooms. The board treats them as one argument, so neither has a finish line.",
    now=(
        "V1 delivery is USB. The Agent polls the cloud and writes 1024-byte chunks to the panel. "
        "Each chunk has a CRC-32. The panel answers ACK or NAK. The full frame is 48,000 bytes, which is 800 by 480 at 1 bit. "
        "That protocol is firmware/usb_protocol.py and firmware/fennsill/fennsill.ino."
    ),
    done="The card says: V1 is USB push via the Agent. Wi-Fi pull is FN-034 plus SM-052, after the pilot.",
    steps=[
        "Paste that sentence on SM-146.",
        "Move FN-034, FN-038, FN-151, and SM-052 to After the first pilot week.",
        "Keep the chunk, ACK, and checksum proof on FN-157. The packet format is already built.",
    ],
    note="A panel in another room, off USB, is a real product. It is the product after someone has used the USB one.",
)

add(
    S_CLOSE,
    "close",
    "SM-147",
    "Security model for hosted mode",
    why="Device keys, account auth, and what you store are the questions a privacy policy and a stolen-laptop story both ask.",
    now=(
        "The panel id identifies the board and is not a secret. The device key is the secret and only works for that id. "
        "The MCP bearer is the account secret. Cloud stores the account, the device link, and jobs. "
        "Wi-Fi passwords are written over USB into panel flash and are refused by the cloud. "
        "A buyer cannot extend their own 30 days. This is written in cloud/README.md and docs/Fennsill-Cloud-Server-Brief.md."
    ),
    done="The card quotes those four sentences, and MS-12 uses the same sentences as the engineering input to counsel.",
    steps=[
        "Paste the four sentences onto SM-147 and check it.",
        "Copy them into the MS-12 brief so the policy and the server describe one product.",
        "Keep the factory master key out of the cloud host and out of any shared password entry that also holds the MCP admin login.",
    ],
    note="Adding set_wifi to the MCP tool list breaks this card. Wi-Fi stays on the USB line.",
)

add(
    S_CLOSE,
    "close",
    "SM-148",
    "Pick the hosted stack",
    why="The card offers a build-our-own server or a fork of a bring-your-own-server project such as LaraPaper. The tree already chose.",
    now="cloud/ is the server. One process serves the account site and /mcp. The database is SQLite. SQL Server is unused. account-web/ is a spare copy of the site, and the live UI is the one inside cloud/.",
    done="The card says: keep our cloud process and SQLite through the pilot. LaraPaper is not the V1 server.",
    steps=[
        "Paste that decision and check the card.",
        "Point operators at cloud/README.md for how the container runs and how a buyer signs up.",
        "Leave a SQL Server move off the board until a backup or a second host gives you a reason.",
    ],
    note="A fork would throw away the device-key and access-window work already in cloud/store.py.",
)

add(
    S_CLOSE,
    "close",
    "MS-13",
    "MCP structure",
    why="Clients need one URL, one header, and a short tool list. Extra tools become support load and a larger security surface.",
    now=(
        "The URL buyers use is https://mcp.fennsill.com/mcp. The header is Authorization: Bearer, copied from the account site. "
        "Device ID is entered on the account site when they link a panel. It is not a field in the MCP form. "
        "The allowlist in docs/SHIPPING.md is list panels, push a page, and live update."
    ),
    done="MS-13 and SM-049 are checked with that URL, that header, and that tool list.",
    steps=[
        "Paste the URL, the header rule, and the tool list on MS-13.",
        "Check SM-049 with a pointer to the same text.",
        "When a new tool is proposed, add it to the After the pilot list first. The pilot uses the allowlist as it stands.",
    ],
    note="ChatGPT and Claude custom connectors both follow this shape. A connector that asks for the Device ID in the MCP form is the wrong form.",
)

add(
    S_CLOSE,
    "close",
    "SM-049",
    "Build an MCP connector so any authorized model can push",
    why="The card is the build item under MS-13. The connector is the hosted server, not a separate plugin per model.",
    now="cloud/main.py serves /mcp. Desk and Factory tell the buyer to use mcp.fennsill.com. Any client that can call a custom MCP server with a bearer header is in scope. Cursor is already one of those clients.",
    done="A model other than Claude can push a page with the same URL and the same header. The clean-PC test on the V1D card is the proof.",
    steps=[
        "Check SM-049 as built, and point the proof at the V1D clean-PC test.",
        "Write the buyer instructions once, in the Quick Start: URL, Authorization header, empty bearer-env field, no Device ID in the form.",
        "Leave SM-048 parked. The model sends HTML through push. It does not hand you a signed-in Claude page.",
    ],
    note="A per-vendor OAuth app is a later convenience. Custom MCP is the V1 contract.",
)

add(
    S_CLOSE,
    "close",
    "FN-030",
    "Send a READY and firmware version handshake on every USB connect",
    why="Desk has to know which board it is talking to, and which firmware, before it pushes a frame.",
    now=(
        "On connect the panel sends READY, a version, id=, and serial=. "
        "HELLO and READY? ask for that line again. The host matcher is firmware/panel_ports.py. "
        "The firmware print is in firmware/fennsill/fennsill.ino. docs/DEVICE.md describes the same line."
    ),
    done="The card is checked. A missing READY line is a failure on FN-157, not a new protocol.",
    steps=[
        "Check FN-030.",
        "Add one line to the FN-157 checklist: plug in, expect READY with a version and an FS id within a few seconds. Unplug and plug again, expect it again.",
        "If a board answers a different READY shape, treat it as the old firmware and reflash from Factory. Keep the parser on the line you ship.",
    ],
    note="Windows COM serial numbers are not the product serial. The product serial is the one Factory locked.",
)

add(
    S_CLOSE,
    "close",
    "FN-032",
    "Chunked transfer with per-chunk ACK and checksum",
    why="A full frame has to survive a noisy cable. The card is the reliability of the USB push.",
    now=(
        "The host sends magic AFC1, then 1024-byte chunks, each with a CRC-32. The panel answers ACK with the chunk index, or NAK. "
        "A show packet, magic AFS1, carries the CRC of the whole 48,000-byte frame. "
        "This is firmware/usb_protocol.py and the matching reader in the sketch."
    ),
    done="The design card is checked. FN-157 includes one bad-chunk proof: a corrupted chunk is NAKed, the retry lands, and the panel shows the frame.",
    steps=[
        "Check FN-032 as the protocol you ship.",
        "Put the bad-chunk retry on the FN-157 checklist.",
        "Leave frame size alone until FN-024 says 2-bit is worth a larger buffer.",
    ],
    note="Wi-Fi image download is a different transport. It does not replace this USB format for V1.",
)

add(
    S_CLOSE,
    "close",
    "FN-035",
    "Over-the-air firmware updates",
    why="You need a way to fix a panel that already left the bench, without asking the owner to run Factory.",
    now=(
        "If Wi-Fi is saved, boot can fetch an HTTPS manifest. The signature is an HMAC over version and sha256. "
        "The binary URL has to be https, and the download hash has to match. "
        "The panel shows an update prompt. The top button installs. The middle button skips. "
        "Serial errors are ERR bad signature and the ota url, http, begin, write, sha, and end failures. "
        "Buyers are not given a tool that publishes manifests."
    ),
    done="The mechanism card is checked. The operator note on the OPS card says how you publish a manifest, and that the panel needs saved Wi-Fi for OTA to run.",
    steps=[
        "Check FN-035 as the updater you have.",
        "Write the publish steps into the operator note: sign version plus sha256, host the binary on https, point the manifest URL, confirm the panel shows the prompt.",
        "Keep OTA off the V1 buyer Quick Start until a pilot panel has actually installed one signed build. USB reflash from Factory remains the recovery path.",
    ],
    note="A buyer-facing channel that publishes firmware would undo the operator-only rule in the cloud brief.",
)

add(
    S_CLOSE,
    "close",
    "MS-14",
    "Domain",
    why="The software, Desk, and Factory all tell buyers to open mcp.fennsill.com. A second name would split accounts.",
    now=(
        "mcp.fennsill.com resolves and sits on Cloudflare addresses. "
        "A lookup for the apex name fennsill.com returned no address record from this network on 23 November 2026. "
        "The product host name is already chosen."
    ),
    done="MS-14 is checked: the product host is https://mcp.fennsill.com. MK-127 is the registrar confirmation, not a naming workshop.",
    steps=[
        "Check MS-14 with that host name.",
        "On MK-127, confirm the registrar login is yours, auto-renew is on, and the Cloudflare zone is the one serving mcp.fennsill.com.",
        "Leave the apex without a storefront until SM-063. Point the apex at the store only when the store exists.",
    ],
    note="Print the same host in the Quick Start that Desk already shows.",
)

add(
    "After the pilot",
    "later",
    "SM-048",
    "Push a published Claude artifact to the device",
    why="The card tries to move a signed-in Claude page onto the panel, including private artifacts.",
    now="The path that exists is: the model produces HTML, push_artifact takes that HTML, Playwright renders 800 by 480 with no network, and the Agent sends the frame. There is no browser session in the cloud that is logged into Claude.",
    done="The card is parked with this sentence: V1 pushes HTML the model already sent. Private Claude artifact pages are out.",
    steps=[
        "Mark SM-048 after the pilot, with the reopen rule.",
        "Reopen it only when a buyer needs a page that cannot be expressed as the HTML their model can send to push_artifact.",
        "If you reopen it, the work is a signed-in browser on a machine the buyer controls. Store no Claude password on the FennSill server.",
    ],
    note="Rendering arbitrary signed-in web pages in the cloud is a different product and a different privacy story from SM-147.",
)

S_PILOT = "Finish before the pilot"

add(
    S_PILOT,
    "pilot",
    "MS-11",
    "Dev plan",
    why="MS-11 is the milestone that asked for this document. The board cannot stay a flat list due on one day.",
    now="The decisions, the pilot gate, and the later work are mixed on one December date, all assigned to KC.",
    done="This PDF is the dev plan. MS-11 is checked, and the board dates match the three sections.",
    steps=[
        "Read the Close, Before the pilot, and After the pilot sections once and mark anything you reject.",
        "Apply the board edits in the last section of this PDF.",
        "Check MS-11. Further planning edits land as notes on the rejected cards, not as a second empty Dev plan ticket.",
    ],
    note="The weekly milestone card MILE is the same job. Check both when the board matches this PDF.",
)

add(
    S_PILOT,
    "pilot",
    "MS-12",
    "Development compliance aspects",
    why="You are about to hand a device to someone else and store their account. The shipping checklist already stops the release on a privacy policy and an EULA.",
    now=(
        "docs/SHIPPING.md lists the facts and says counsel reviews them before a public sale. "
        "There is no policy URL in Setup or the README yet. This card is the engineering brief counsel needs, plus the links once counsel has words you can publish."
    ),
    done="Setup and the README link to a counsel-reviewed privacy policy and EULA. The policy matches what the server actually stores.",
    steps=[
        "Send counsel this inventory, labeled as engineering notes: account email and password hash; device id, label, and device key; job records for pages pushed; agent heartbeats and the access-window clock; support mail once MK-129 exists.",
        "State the exclusions in the same note. Wi-Fi passwords stay in panel flash and are refused by the cloud. Page HTML is rendered on the buyer PC. The AI vendor sees the prompt and the HTML under that vendor's terms. FennSill does not receive the buyer's AI login.",
        "Say who operates the host, where a buyer emails you, and that access is a period you turn on and off.",
        "Ask counsel for a privacy policy and an EULA you are allowed to link. Put those URLs in Setup and in the README. docs/SHIPPING.md already names those two places.",
        "Read the published policy against SM-147 once more before the pilot. If the policy promises something the server does not do, change the policy or the server before anyone signs up.",
    ],
    note="This PDF is not the policy. Publish counsel's text.",
)

add(
    S_PILOT,
    "pilot",
    "MS-15",
    "Access",
    why="A single-person project still has a bus factor. The pilot stalls if the login that can renew a buyer, or the one that can flash, is locked behind a laptop you do not have.",
    now="The board does not list the systems. From the repo and the live host, the set is at least: GitHub (KCarino18/Fennsill), the Cloudflare account in front of mcp.fennsill.com, the machine or container that runs the cloud process, the domain registrar, and the offline factory master key.",
    done="One page lists each system, who can log in, how the second factor works, and what you do if that person is unavailable. The factory master key is named on the page and stored offline, not pasted into the page.",
    steps=[
        "Make a row for GitHub, Cloudflare, the cloud host, the registrar, the mailbox from MK-129, and Factory.",
        "For each row write the login name, where the second factor lives, and the backup. A printed backup code in a known drawer is enough.",
        "Write the one action each system is for: push a release, edit DNS, renew a buyer or read a failed job, renew the domain, read support mail, flash a board.",
        "Confirm you can still sign in to each one this month. A login you have not used since the last laptop is a broken row.",
        "Leave Shopify off this page until SM-063 starts. Add it then.",
    ],
    note="Do not put the factory master key, device keys, or bearer tokens on the access page.",
)

add(
    S_PILOT,
    "pilot",
    "MS-16",
    "Decide whether to pay for business email now",
    why="The first buyer will reply to whatever address is on the Quick Start. A personal mailbox mixes that thread with everything else and disappears when you change laptops.",
    now="MK-129 is the setup card. MS-16 is the yes or no. The product host name is already on a fennsill.com subdomain. There is no support address in the Quick Start today. The Quick Start points at the GitHub releases page.",
    done="You decide yes, and you pay for one mailbox on the domain before the pilot. The address is the one printed in the Quick Start.",
    steps=[
        "Decide yes for a single mailbox. The pilot is the reason. A full suite of seats can wait.",
        "Pick the host. Google Workspace, or a mailbox at the registrar or at Cloudflare, are the usual choices. Pick the one you will actually check on your phone.",
        "Use support@ or hello@. One of those, until you have a reason to split sales and help.",
        "Hand the setup steps to MK-129.",
        "Put the address on the Quick Start and on the GitHub release that the pilot downloads.",
    ],
    note="Firmware does not wait on the mailbox. The pilot's first week does.",
)

add(
    S_PILOT,
    "pilot",
    "MK-127",
    "Buy the domain for the chosen name",
    why="The host name is already in the binaries. Losing the registration would take the account site and MCP down together.",
    now="mcp.fennsill.com answers on Cloudflare. The apex name did not return an address record from this network on 23 November 2026. The name is in use, and the bare domain is not a website yet.",
    done="You are in the registrar account, auto-renew is on, the registrant email is one you read, and the Cloudflare zone serving mcp is the zone you administer. The lock on that registrar is covered by MS-15.",
    steps=[
        "Open the registrar and confirm the domain is yours and the expiration is more than a quarter away. Turn on auto-renew.",
        "Confirm the nameservers are the Cloudflare account you control.",
        "Leave the apex without an address record until the store from SM-063 exists. A parked page is optional. A second product name is not required.",
        "Check the card once those three are true.",
    ],
    note="If the registrar login is missing, that is an MS-15 failure, and it is urgent because the subdomain is already how buyers are told to sign in.",
)

add(
    S_PILOT,
    "pilot",
    "MK-129",
    "Set up business email on the domain",
    why="MS-16 chooses to pay. This card is the mailbox existing and being watched.",
    now="No support address is wired through the product. GitHub is the help link in the current Quick Start.",
    done="Mail to the chosen address arrives, you can reply from it, and the Quick Start plus the pilot's release page show it.",
    steps=[
        "After MS-16 picks the host, add the DNS records they give you. Do that in the same Cloudflare zone that serves mcp.fennsill.com.",
        "Create the one mailbox. Sign it in on the phone you actually have with you.",
        "Send a message from another account and reply. Check the spam folder on the far side once.",
        "Replace the Quick Start help line with that address. Rebuild the Quick Start PDF the installer copies, and put the same address on the GitHub release.",
        "During the pilot week, read it daily.",
    ],
    note="Aliases and a second seat wait until a second person is on the roles card.",
)

add(
    S_PILOT,
    "pilot",
    "FN-031",
    "Timeout on the display BUSY pin and show display not detected",
    why="The UC8179 holds BUSY high while it refreshes. If the panel is missing or wedged, a waiter with no timeout hangs the USB session.",
    now=(
        "Firmware waits up to 15 seconds (BUSY_TIMEOUT_MS) and then prints ERR display not detected. "
        "The same sentence exists in firmware/usb_protocol.py. "
        "A search of the Desk and Factory C# sources does not show that sentence. The person at the PC can still see a generic failure."
    ),
    done="When the display never releases BUSY, Desk and Factory show display not detected, and the USB port is usable again for a later push.",
    steps=[
        "Reproduce it on the bench: disconnect the display ribbon, or force the timeout path, and confirm the serial line is ERR display not detected.",
        "Surface that line in Factory's log. Factory is who flashes and who will see a dead panel first.",
        "Surface the same line in Desk when a push fails for that reason, next to the existing cloud and USB status.",
        "Add the case to FN-157: ribbon unplugged or panel absent, expect the sentence within about 15 seconds, then a later good push still works.",
    ],
    note="The timeout itself is in the sketch. This card is the person seeing it.",
)

add(
    S_PILOT,
    "pilot",
    "FN-157",
    "Regression checklist to run before every firmware release",
    why="OTA and Factory will put a binary on a board a buyer already has. The checklist is what you run before that binary is the pinned one.",
    now="There is a firmware CI compile. There is no written checklist in the repo that a person runs against a real panel.",
    done="A short checklist lives next to the firmware, and the last release you flashed has the checklist filled in with pass or fail and the firmware version.",
    steps=[
        "Write the list so it fits on one screen: plug in and read READY with version and FS id; push one full 1-bit frame and watch it appear; unplug the display path and expect ERR display not detected within about 15 seconds; confirm a bad chunk is NAKed and the retry completes; confirm a reflash is still possible after those failures.",
        "Run it on the board you are about to call pinned. Record version, date, and cable.",
        "Put the filled checklist in the release notes for that firmware. A compile that passed CI is not a substitute for the panel lighting up.",
        "Run the list again after any change under firmware/fennsill/.",
    ],
    note="Wi-Fi range and 2-bit photos are not on this list. They have their own cards after the pilot.",
)

add(
    S_PILOT,
    "pilot",
    "FN-152",
    "USB tests across Windows and macOS machines, cables and ports",
    why="Panels fail in the field because of cables and ports more often than because of the protocol. The card covers two operating systems. Only Windows is a V1 installer.",
    now="Setup is FennsillSetup.exe. The host stack is Windows services, COM ports, and a bundled runtime. There is no macOS installer in the tree.",
    done="On Windows, two cables and two ports are written down, including one cable that does not carry data. macOS moves to the MAC card in After the pilot.",
    steps=[
        "On a Windows PC that did not compile the firmware, install the release. Use the cable you ship, a second data cable, and a charge-only cable.",
        "Charge-only must fail as no READY, with Desk saying the panel was not found. It must not hang.",
        "Try a rear port and a front port, or a hub and a direct port. Record which ones enumerated and which ones dropped mid-push.",
        "Unplug during a push. Plug back in. The next push works without reinstalling Setup.",
        "Write the macOS rows onto the MAC card. Check the Windows half of FN-152 now.",
    ],
    note="A green result on the dev machine is not this card.",
)

add(
    S_PILOT,
    "pilot",
    "SM-054",
    "Find the device by USB ID, free a busy port, and flash the pinned build",
    why="Every panel that ships is flashed on your bench. The card is Factory's daily path, including the failure where another program already holds the COM port.",
    now="Factory flashes the XIAO ESP32-S3 image, locks a write-once serial of the form FS-YYMM-NNNNNN, and locks the device key. Prebuilt binaries live under factory/prebuilt/. CI compiles into that folder as an Actions artifact. Busy-port detection exists in firmware/panel_ports.py.",
    done="One board that is not your everyday dev board is flashed from the pinned build. Serial and key survive a second Factory run. A port held open by another program is reported as busy, and Factory does not skip to a different board.",
    steps=[
        "Pick the exact binary you call pinned. Prefer the CI artifact for that commit over a local compile. Record the commit on the card.",
        "Flash one board. Confirm READY shows the new version, and Factory shows the device id and serial.",
        "Run Factory again. It must refuse to rewrite the serial and the device key.",
        "Open the COM port in another program. Factory should say the port is busy and stop. Close the other program and confirm a status read still works.",
        "Check the card after that log exists. Day-to-day flashing you already do counts if you write down the date and the binary.",
    ],
    note="Buyers do not run this. Recovery of a buyer's board is still you, with Factory, until SM-055.",
)

add(
    S_PILOT,
    "pilot",
    "SM-056",
    "One-click Windows and macOS setup with no firewall prompts",
    why="The buyer's first hour is Setup. Every extra dialog is a support mail.",
    now=(
        "Windows Setup is real: FennsillSetup.exe, run as Admin once, installs Desk, the Agent service, the runtime, and the Quick Start PDF, and registers an uninstall entry. "
        "The Agent is a Windows service so Desk can close. "
        "macOS setup is not in the repo. Whether a clean Windows install raises a firewall prompt is not written down."
    ),
    done="A clean Windows install shows the administrator prompt and then Desk. Any firewall prompt is either gone or written on the Quick Start as the one expected click. macOS is the MAC card.",
    steps=[
        "Install the published Setup on a Windows user account that has never run FennSill. Count the prompts.",
        "If Windows Firewall asks about the Agent or a bundled tool, decide one of two things: allow it from the installer, or show one sentence in the Quick Start. An undescribed prompt fails the card.",
        "Confirm the service is running after reboot, with the panel unplugged and with it plugged in.",
        "Uninstall from Settings, Apps, and confirm the service is gone.",
        "Leave macOS on the MAC card. Do not block December on it.",
    ],
    note="The one administrator prompt is expected. Hiding it is not the goal.",
)

add(
    S_PILOT,
    "pilot",
    "SM-142",
    "Versioning and release process for firmware and the host app",
    why="A buyer, a panel, and a cloud job have to name the same generation. The Windows apps have a GitHub release. The firmware has a sketch version and a CI artifact. Those numbers do not meet.",
    now="installer/publish_release.ps1 publishes the Windows Setup and Factory executables. The public tag called out in the README is v0.1.27 from 16 November 2026. The firmware USB version in the protocol module is 1.2.0. CI uploads prebuilt binaries as a workflow artifact.",
    done="Each pilot release has one note that lists the Setup version, the firmware READY version, and the commit both came from. 1.0 is reserved for the week after the pilot, as on the V1D card.",
    steps=[
        "Write a half page next to the publish script. The Windows version is the GitHub release. The firmware version is the READY string. They do not have to be the same number. They do have to be named together in the release note.",
        "Keep shipping 0.1.x for the apps until the pilot week is over. Bump firmware the way you already bump the READY string, and mention it in that same note.",
        "Point Factory at the binary named in the note. SM-143 is how that binary gets attached.",
        "Check this card when one release note has been published in that shape, even if the pilot has not started.",
    ],
    note="Forcing one number across USB, Windows, and the cloud is extra process. Pairing them in the note is the V1 need.",
)

add(
    S_PILOT,
    "pilot",
    "SM-143",
    "CI: build the firmware with arduino-cli and attach release binaries",
    why="The binary you flash has to be the binary CI built, or you cannot tell a buyer which sketch they have.",
    now=(
        ".github/workflows/build-firmware.yml runs on firmware pushes and on demand. "
        "It installs arduino-cli, the ESP32 core, and Seeed_GFX, and compiles firmware/fennsill for the XIAO ESP32-S3 Plus. "
        "It uploads factory/prebuilt/ as a workflow artifact. It does not attach that artifact to a GitHub Release."
    ),
    done="The release you point Factory at contains the CI-built binaries, and the release note from SM-142 names that tag.",
    steps=[
        "Run the workflow on the commit you intend to pin. Download the artifact and confirm the expected bin files are inside.",
        "Attach those files to the GitHub Release next to Setup, or copy them into the release with the publish script. Pick one place and write it on SM-142.",
        "Flash from that download, not from a local build, for the SM-054 proof.",
        "Leave the issue-template work on its own card. The board showed it with the same SM-143 badge. Split the badge when you edit the board.",
    ],
    note="A green compile that stays inside Actions is not yet a pinned build.",
)

add(
    S_PILOT,
    "pilot",
    "OPS",
    "Operator note for the pilot week",
    why="The V1D card depends on you renewing access, publishing a manifest, and explaining a stuck push without opening the repo. That note had no ticket, so it is here.",
    now="cloud/README.md and the operator CLI cover renew and revoke. OTA publish is described in docs/DEVICE.md. The four stuck-push checks are spread across Desk strings and the Quick Start.",
    done="One page you can follow when you are tired. It names the command you actually run.",
    steps=[
        "Write the renew and revoke steps the way you will run them on the host: how you identify the buyer, and what Desk should show after.",
        "Write the manifest steps from FN-035: where the binary lives, how you sign, how you know the panel saw the prompt.",
        "Write the four checks in order. Agent service running. Panel USB and a READY id. Access window open. Device key pasted and a recent heartbeat.",
        "Put the support address from MK-129 at the top, so a mail from the pilot maps to this page.",
    ],
    note="This is the thin version of SM-057. Build the guided wizard after the week shows which failures repeat.",
)

S_LATER = "After the pilot"

add(
    S_LATER,
    "later",
    "FN-024",
    "Test 2-bit grayscale and partial refresh on the UC8179",
    why="The panel controller can show more than a hard black-and-white threshold, and it can refresh a region. V1 frames are 1-bit and full-screen because that path is what you can already push.",
    now="The USB frame is 48,000 bytes, 800 by 480, one bit per pixel. The sketch draws black or white. There is no partial-window update in the buyer path.",
    done="You have side-by-side photos, at arm's length, of a 1-bit page and a 2-bit page of the same content on the UC8179, plus a note on ghosting after repeated partial refreshes. The photos decide whether SM-047 changes the frame format.",
    steps=[
        "On the bench, drive the UC8179 in 2-bit mode with a still image you already push in 1-bit. Keep USB power and the current cable. This test does not need the cloud.",
        "Photograph both. Write what you can read from a desk that you could not read before.",
        "Partial refresh: update a small region, then repeat it. Count how many partials you can do before a full refresh is required to clear ghosting.",
        "If 2-bit is not clearly better for the pages you actually send, stop and leave the 48,000-byte frame alone.",
        "If it is better, schedule the protocol change: buffer size, CRC over the new length, and a READY version bump so old hosts refuse the new frame cleanly.",
    ],
    note="Do this after the pilot week. A format change during the pilot strands the binary you just proved.",
)

add(
    S_LATER,
    "later",
    "SM-047",
    "Add dithering presets and a 2-bit grayscale output option",
    why="Once FN-024 says the panel earns 2-bit, the renderer has to produce those bytes on purpose. Dithering is how photos and charts survive e-ink.",
    now="Playwright renders an 800 by 480 page for the 1-bit push. templates/ has a few pages, including a market example. There is no dither preset and no 2-bit output.",
    done="A renderer flag produces either the current 1-bit frame or a 2-bit frame from the same HTML, and a preset name is recorded on the job so you can reproduce it.",
    steps=[
        "Wait for the FN-024 photos. Match the preset to the mode that won.",
        "Implement one dither and one plain threshold. Keep 1-bit as the default until a template opts in.",
        "Put the preset next to SM-062 so the preview and the panel use the same bytes.",
        "Ship it as a renderer change first. Templates opt in one at a time.",
    ],
    note="A gallery of presets before the panel test is artwork, not a release.",
)

add(
    S_LATER,
    "later",
    "FN-034",
    "Wi-Fi pull mode: wake, fetch the latest image, deep sleep",
    why="A panel that stays on a desk can leave the USB cable. The buyer still gets a new page.",
    now="Wi-Fi credentials can be sent over USB and stored in panel flash. The cloud refuses those secrets. OTA already uses Wi-Fi when it is configured. The panel does not yet wake, download a page, and sleep on a timer.",
    done="With credentials already stored, the panel wakes on an interval, downloads one image for its device, displays it, and goes back to deep sleep. USB push still works when the cable is attached.",
    steps=[
        "Build SM-052 first, on the hosted cloud: one image per device, fetched with the device key.",
        "Firmware: on the interval, join the saved 2.4 GHz network, fetch that image, check the hash, display, sleep. A failed fetch leaves the previous image up.",
        "Start the interval at 15 minutes or slower. E-ink does not need a one-minute poll.",
        "When the cable is present, the Agent owns the screen and the sleep loop stays quiet so the two writers do not fight.",
        "Then run FN-038 and FN-151.",
    ],
    note="V1 buyers are USB buyers. Offer this after a pilot has asked to unplug the panel.",
)

add(
    S_LATER,
    "later",
    "SM-052",
    "Device pull endpoint for Wi-Fi mode",
    why="FN-034 needs a URL that returns the latest frame for one board and for no other board.",
    now="Jobs are pushed by the Agent over USB. There is no image URL for the panel. Device keys already exist and are how the Agent authenticates.",
    done="A panel with its device key can fetch the latest rendered frame for that device only. A wrong key is refused. The body is the bytes the panel will display, plus a hash.",
    steps=[
        "Add the endpoint on the existing cloud process. Authenticate with the device key. Return a clear empty result when that device has no page yet.",
        "Store the last rendered frame beside the job so the panel does not wait on Playwright.",
        "Hosted only. A self-hosted pull is the SM-053 conversation and stays parked.",
        "Log the fetch time so you can see a panel that stopped calling. Do not log Wi-Fi credentials. The panel already has them.",
    ],
    note="The endpoint is unused until FN-034 calls it. Build them as a pair.",
)

add(
    S_LATER,
    "later",
    "FN-038",
    "Detect a 5 GHz-only network and tell the user it needs 2.4 GHz",
    why="The ESP32-S3 radio is 2.4 GHz. A phone hotspot or a modern SSID that is 5 GHz only looks like a password failure, and people retype the password.",
    now="The USB WIFI line stores SSID and passphrase. Association failure is not yet translated into a band message on the panel.",
    done="After a failed join, the panel shows that it needs a 2.4 GHz network. A following 2.4 GHz SSID joins. Desk shows the same sentence when Wi-Fi was set from the PC.",
    steps=[
        "Reproduce with a hotspot that is 5 GHz only. Confirm association fails.",
        "Show one sentence on the panel: this panel needs a 2.4 GHz network. Print the same sentence on the serial line so Desk can repeat it.",
        "Join a 2.4 GHz SSID with the same procedure and confirm the message clears.",
        "You learn the band by trying. The message follows a failed join. Say that in the Quick Start when Wi-Fi becomes a buyer feature.",
    ],
    note="This can ship with USB Wi-Fi setup, before pull mode is finished. It still waits until a buyer is asked to enter an SSID.",
)

add(
    S_LATER,
    "later",
    "FN-151",
    "Wi-Fi tests: range, reconnect after router reboot, weak signal",
    why="Pull mode that works on the bench and dies in a hallway is a return.",
    now="There is no written Wi-Fi range log. OTA and the WIFI command are the only radio use.",
    done="A one-page log: the distance where fetch still works, the behavior after the router is power-cycled, and the behavior when the fetch fails at the edge. The previous image stays up on failure.",
    steps=[
        "Run this only after FN-034 and SM-052 work on the same desk as the router.",
        "Walk the panel out. Note the last distance that completed a fetch. Note what the panel showed when the fetch failed.",
        "Reboot the router. Time how long until the next successful fetch. The panel should recover on a later wake without a USB cable.",
        "Attach the log to the firmware release that you would actually ship as Wi-Fi capable.",
    ],
    note="A single success next to the access point is FN-034's done test, not this card.",
)

add(
    S_LATER,
    "later",
    "FN-036",
    "Map keys 1 to 3 to next screen, refresh now, and status",
    why="A panel with buttons can advance a page and show who it is without a PC.",
    now="The top button installs an OTA update and the middle button skips it, and only while that prompt is showing. There is no buyer mapping for next, refresh, and status.",
    done="Outside the update prompt, three controls do next page, refresh now, and status. During the update prompt, the OTA meanings win.",
    steps=[
        "Inventory the physical buttons on the board you ship. Map only buttons that exist.",
        "Next page needs a list of pages. That list is SM-059. Until playlists exist, next can cycle the last few stored frames, or this card waits.",
        "Refresh now fetches over Wi-Fi if FN-034 exists, or asks the Agent over USB if the cable is connected.",
        "Status uses the FN-037 screen.",
        "Test the OTA prompt afterward. Top still installs. Middle still skips.",
    ],
    note="Ship this with FN-037 so the buttons agree.",
)

add(
    S_LATER,
    "later",
    "FN-037",
    "Boot self-test and status screen (battery, Wi-Fi, version)",
    why="When a panel is blank, the owner needs to see that it booted and which firmware it is.",
    now="Boot shows a splash, then waits for USB or an update prompt. READY on the serial line already carries the version and id. There is no on-panel status page.",
    done="A status screen shows the READY version and the device id. Wi-Fi shows associated, not configured, or the FN-038 failure. Power shows USB power, or a battery percent only if a sense pin is actually wired.",
    steps=[
        "Confirm the hardware. If the desk product is USB-powered and has no sense pin, the power line reads USB power. Do not invent a percentage.",
        "Draw the screen in the 1-bit frame you already have. Large type. Device id and version must be readable at arm's length.",
        "Show it from FN-036's status key, and for a few seconds at boot if that does not delay the USB READY line.",
        "READY on the cable stays the source Desk uses. The screen is for the person looking at the glass.",
    ],
    note="A battery reading without a wired sensor fails this card by lying.",
)

add(
    S_LATER,
    "later",
    "SM-060",
    "E-ink design kit: CSS tokens and components for 800 by 480 black and white",
    why="Templates drift unless type size, margin, and the few layouts you like are named.",
    now="Pages are hand-built HTML rendered at 800 by 480. There is no shared token file.",
    done="One stylesheet defines the page size, the background, the ink color, type sizes that survive 1-bit, and four components: a stat, a list, a chart, and a footer with the time. A sample page uses only those.",
    steps=[
        "Start from a page you have already pushed and liked. Pull its sizes into variables.",
        "Keep the kit black and white. Drop mid-gray lines and type smaller than what you could read on the last real panel.",
        "Render through the same Playwright path the pusher uses, then threshold to the frame, so the kit cannot depend on color the panel will drop.",
        "SM-061 templates import this file. They do not invent a second set of margins.",
    ],
    note="Build the kit when the second template starts. The first pilot page can be hand-built.",
)

add(
    S_LATER,
    "later",
    "SM-061",
    "Templates: markets, calendar, weather, homelab, daily brief",
    why="Buyers will ask for the same five pages. A template is that page with their data, rendered to the frame.",
    now="templates/ already holds a market example and a chart page. Calendar, weather, homelab, and a daily brief are not a set.",
    done="Each shipped template has a sample render on a real panel and a note of where the data comes from. You do not have to ship all five on the same day.",
    steps=[
        "After the pilot, build the one template the pilot actually asked for. That is the first done template.",
        "Markets can extend the page you already have. Weather and calendar need a source you are willing to call from the renderer. Homelab data lives on their network, and rendering already happens on their PC.",
        "A daily brief composes the others plus a short text block the model writes. Ship it after two of the pieces exist.",
        "Each template uses SM-060 and is previewed with SM-062.",
    ],
    note="Five unfinished templates help December less than one page the pilot requested.",
)

add(
    S_LATER,
    "later",
    "SM-062",
    "Template preview that shows the exact 1-bit render before pushing",
    why="HTML in a browser looks sharper than the panel. People will approve the wrong image.",
    now="The pusher renders with Playwright at 800 by 480 and then builds the 1-bit frame. The account site does not show that frame first.",
    done="The preview image is the same bytes the panel will get. Approving it is what enqueues the push.",
    steps=[
        "Render the way production renders, including the dither or threshold from SM-047 once that exists. Until then, use the current 1-bit conversion.",
        "Show that bitmap at 1:1 pixels, on white, before the push.",
        "If the template changes, throw the preview away. A cached image from yesterday is how the panel and the preview diverge.",
        "The buyer's AI can skip the preview. A person picking a template on the site should not.",
    ],
    note="A mock that is merely the same pixel size fails the card. The bytes have to match.",
)

add(
    S_LATER,
    "later",
    "SM-051",
    "Scheduled refresh",
    why="Market open and market close are the obvious timers. A person should not have to ask the model twice a day.",
    now="A push happens when an AI calls the tool, or when a person asks. There is no timer.",
    done="A device can carry a schedule. At the chosen time the page is rendered again and pushed. A missed time waits for the next chance. Missed times do not stack into five stale pushes.",
    steps=[
        "The first slice is USB, because that is the V1 hardware. The Agent runs the clock, and only while the PC is on and the panel is plugged in. Write that limit down. A closed laptop misses the slot.",
        "Use one example schedule: weekdays at the local open and close. Store the timezone on the device.",
        "Rendering uses the same template path as a manual push.",
        "The Wi-Fi slice moves the clock onto FN-034's wake interval, and only after pull mode works. The Agent clock and the panel clock must not both push.",
    ],
    note="A timer inside the panel that fetches websites on its own is a different product. Keep rendering on the PC or the cloud.",
)

add(
    S_LATER,
    "later",
    "SM-050",
    "Google Sheet as a dashboard source",
    why="A lot of the pages people want are already a sheet: prices, chores, a homelab table.",
    now="There is no sheet connector. Templates that need numbers use whatever the model typed into the HTML.",
    done="A template can read a sheet the buyer chose and render it on the schedule from SM-051. The buyer can revoke that access.",
    steps=[
        "Start with a CSV URL or a published-sheet export the buyer pastes. Render those cells into the SM-060 table. This avoids OAuth while you learn which columns matter.",
        "If that gets used, add Google OAuth on the account site. Store a refresh token for that sheet only. Show which sheet is linked, and offer a disconnect.",
        "Fetch on the schedule, not on every panel wake. The panel receives a rendered frame either way.",
        "A private sheet must be fetched with that token. Do not store the buyer's Google password.",
    ],
    note="The CSV slice can ship before OAuth. Call the card done for OAuth only when disconnect works.",
)

add(
    S_LATER,
    "later",
    "SM-059",
    "Support several devices per user with playlists",
    why="One account can already be aimed at more than one board. A playlist is the missing object: which pages, in what order, how long each stays up.",
    now="The account can link a device id and mint a key per device. Jobs target a device. There is no ordered playlist and no dwell time.",
    done="An account with two linked panels can give each one a playlist. Each entry is a template plus its data, with a dwell time. The USB Agent advances the list while the PC is on.",
    steps=[
        "Confirm a second device links and gets its own key on today's site. If a pilot owns two panels, fix that link before you build playlists.",
        "Add a playlist as an ordered list on the device. Advance it from the same Agent clock as SM-051.",
        "FN-036 next-page reads this list.",
        "Wi-Fi advance waits for FN-034. Then the panel asks for the next entry.",
    ],
    note="A playlist of one page is just a push. Build this when someone has two pages they want left alone.",
)

add(
    S_LATER,
    "later",
    "SM-053",
    "No-account local mode: desktop helper that uses the buyer's own Claude",
    why="Some buyers will refuse an account or a hosted job queue.",
    now="The shipped decision on SM-145 is hosted only. The local host executable is deprecated. Shipping this reopens that decision.",
    done="The card stays parked. It reopens only when a buyer you are willing to support refuses an account.",
    steps=[
        "Leave the card in After the pilot with the reopen rule written on it.",
        "If you reopen it, the helper runs on their PC, uses their AI credential, renders locally, and pushes USB. It does not embed a second MCP server on the public internet.",
        "Give it a separate Quick Start. The hosted steps and the local steps will be misread if they share a page.",
        "Name who supports it. A quiet local mode with no owner becomes the thing everyone is actually running.",
    ],
    note="Start this because a named buyer needs it, not because the card is old.",
)

add(
    S_LATER,
    "later",
    "SM-055",
    "Recover a device stuck in the bootloader automatically",
    why="A failed flash can leave the XIAO in the ROM bootloader. Today that is a Factory session and a person who recognizes the port.",
    now="Factory is the recovery tool. panel_ports.py already classifies ready, busy, and silent ports. Automatic reflash of every silent board is how you wipe the wrong device.",
    done="Factory offers recovery only when the USB identity matches the bootloader you expect, only one such port is present, and the operator confirms. If the board already has a FennSill serial, the confirm step names that serial.",
    steps=[
        "Write down the USB identity of this board in the bootloader, from a board you put there on purpose.",
        "When exactly one port matches, Factory may offer to flash the pinned build. Any other count, it stops and lists the ports.",
        "Confirmation is a click that shows the COM port and, if known, the serial. No timer proceeds on its own.",
        "After recovery, run the FN-157 checklist before the board goes out.",
    ],
    note="A silent unknown port is not permission to flash. A recognized port plus a person confirming is the card.",
)

add(
    S_LATER,
    "later",
    "SM-057",
    "Guided repair flow built from TROUBLESHOOTING.md",
    why="After the pilot, the same few failures will show up in mail. A wizard is those failures in order.",
    now="The Quick Start has a short troubleshooting list. The OPS card is the version you use during the pilot. A repair wizard is not what December needs.",
    done="The wizard asks the questions that matched real pilot mail, in order: cable and READY, Agent service, device key and heartbeat, access window, and display not detected. Each dead end names the one next action.",
    steps=[
        "During the pilot, tag each mail with one cause. Design the wizard from those tags.",
        "After the week, turn the causes you actually saw into the flow. Drop the ones you did not see.",
        "Reuse the Desk status strings so the wizard and the app agree.",
        "Keep Factory recovery (SM-055) as the branch for a board that never sends READY.",
    ],
    note="A wizard written before the week freezes the wrong tree.",
)

add(
    S_LATER,
    "later",
    "SM-139",
    "Create a GitHub organization and repos for firmware, host app, and templates",
    why="The card wants three repos. The release you have works as one repo, with one CI workflow and one publish script.",
    now="The code lives in KCarino18/Fennsill. Firmware, cloud, Desk, Factory, and templates are directories. CI watches firmware/fennsill.",
    done="Through 1.0 you stay in one repo. Reopen the split when two people are merging firmware and the Windows installer in each other's way, or when templates need a public repo of their own.",
    steps=[
        "Write single-repo-through-1.0 on the card and move it to After the pilot.",
        "If you later split, move firmware first, keep the compile green, and leave the Windows publish script in the repo that still tags Setup.",
        "An organization account is an MS-15 row when you create it. Transfer the repo only after the pilot release is tagged.",
    ],
    note="A new empty organization does not make the pilot more reliable.",
)

add(
    S_LATER,
    "later",
    "SM-140",
    "Move the trmnl_usb firmware into the firmware repo with a README",
    why="The product grew out of an earlier USB sketch. The card wants that history inside the current firmware tree, with docs.",
    now="The firmware you ship is firmware/fennsill. The USB protocol is documented in firmware/usb_protocol.py and docs/DEVICE.md. The buyer flash path does not use a sketch named trmnl_usb.",
    done="The old sketch is archived with a README that points at firmware/fennsill, or you record that the history can stay where it is. The shipped tree stays firmware/fennsill either way.",
    steps=[
        "Find the old tree. If it is already gone, check the card as superseded by firmware/fennsill and stop.",
        "If someone might still flash it, add a one-page README beside it: buyers get Factory and the pinned FennSill build.",
        "Put buyer troubleshooting in the Quick Start and the OPS note. A second troubleshooting file in an old folder will be the one people follow by mistake.",
    ],
    note="Do not rename firmware/fennsill during a release week.",
)

add(
    S_LATER,
    "later",
    "SM-144",
    "GitHub Project board for engineering work",
    why="The ticket asks for a project board that links back to this plan, so the cards and the write-up stay the same list.",
    now="The work lives on the board these screenshots came from. GitHub has the repo and the firmware workflow. A second board that drifts from this PDF recreates the December pile.",
    done="One GitHub Project whose columns are the three sections of this PDF, with the same ids, after the current board matches.",
    steps=[
        "Edit the current board first, using the checklist at the end of this PDF.",
        "If GitHub should become the source, create columns for decisions already closed, before the pilot, and after the pilot.",
        "Link the project from the README in one line. Point it at this PDF for the words.",
        "When you check a card, close it in one place. Two open copies of the same id is how the weekly list filled with duplicates.",
    ],
    note="Creating the GitHub project before the sort copies the mess into a second tool.",
)

add(
    S_LATER,
    "later",
    "SM-143b",
    "GitHub issue templates that match the repair log",
    why="The screenshot badged this row SM-143, the same id as firmware CI. It is a different card: what a bug report must contain so you can repair a panel.",
    now="CI is the other SM-143, and it stays in the pilot section under that id. The issue template is separate work.",
    done="A bug template asks for device id, serial, READY version, operating system, cable and port, whether READY appeared, the last ERR line, and whether Desk showed a heartbeat.",
    steps=[
        "Give this card its own id on the board so it stops sharing SM-143 with CI.",
        "Add the template when a second person files bugs, or after the pilot week, whichever comes first. Until then the support mailbox and the OPS note are enough.",
        "Use the same field names Desk already shows, so a buyer can copy them.",
        "Factory-only failures stay a separate template. Buyers should not be sent the factory form.",
    ],
    note="Five fields a person will fill beat a long form they skip.",
)

add(
    S_LATER,
    "later",
    "SM-063",
    "Choose the store platform (Shopify) and connect the domain",
    why="The card has already chosen Shopify. What is left is connecting it to the domain after a stranger has used a panel.",
    now="There is no store in the repo. The apex domain had no address record from the lookup on 23 November 2026. Buyers currently arrive through GitHub releases and mcp.fennsill.com.",
    done="A Shopify store owns the apex, or a shop subdomain, on the Cloudflare zone you already control. The product page states that V1 needs Windows and USB, and an AI that supports custom MCP.",
    steps=[
        "Start this after the pilot week. The pilot itself can be an invoice and a shipment.",
        "Create the Shopify store. Add the domain in Shopify and the DNS records in the same Cloudflare zone as mcp.fennsill.com. Leave the mcp host where it is.",
        "One product: the flashed panel. State that Setup is Windows, that V1 needs the PC on USB, and that Wi-Fi pull is later.",
        "Then do SM-065. Analytics is SM-075, after a page exists.",
    ],
    note="A checkout before the pilot sells a path you have not watched anyone else finish.",
)

add(
    S_LATER,
    "later",
    "SM-065",
    "Set up Shopify: theme, product pages, preorder or waitlist, checkout",
    why="SM-063 picks the platform and the DNS. This card is the page a person can read, and the way they pay or wait.",
    now="Nothing is themed. You do not yet have pilot photos or a counsel-reviewed policy link.",
    done="A product page shows the panel, the V1 buyer steps, the price or a waitlist, and links to the privacy policy and EULA from MS-12. Checkout is on only when you can ship another panel on a week you can name.",
    steps=[
        "Use a plain theme. The page needs the photo, the five buyer steps, and the Windows requirement.",
        "If the next panel has no ship week, use a waitlist. If it does, turn on checkout for that quantity.",
        "Put the support address from MK-129 on the page.",
        "The order confirmation points at the GitHub release named in SM-142 and at the Quick Start. The store is not a second installer.",
    ],
    note="Preorder of Wi-Fi, grayscale, or macOS waits until those cards are done.",
)

add(
    S_LATER,
    "later",
    "SM-075",
    "Analytics: GA4, Meta pixel, and Shopify analytics",
    why="Once a store page exists you will want to know whether anyone saw it.",
    now="There is no store page and no pixel.",
    done="Shopify's own analytics are on. GA4 is on if you will read it. A Meta pixel is on only if you are running ads. Each extra tool is named in the privacy policy before it is enabled.",
    steps=[
        "Ship SM-065 first. Read Shopify's analytics for a week before adding more tools.",
        "If you add GA4, add the counsel-approved sentence to the MS-12 policy in the same change.",
        "Add a Meta pixel only when an ad account exists.",
        "Leave analytics off mcp.fennsill.com. The account site is not the campaign page.",
    ],
    note="Three trackers on a waitlist is how the policy card reopens.",
)

add(
    S_LATER,
    "later",
    "MAC",
    "macOS installer and USB tests",
    why="FN-152 and SM-056 both mention macOS. There is no Mac build in the tree, and V1's installer is Windows. This card is where that work lives after the Windows halves are checked.",
    now="Setup, the Agent service, COM ports, and the publish script are Windows. A Mac buyer cannot follow the Quick Start honestly.",
    done="A Mac install sees READY, pushes one frame, and survives unplug and replug. Prompts are either gone or written down.",
    steps=[
        "Start after the Windows pilot week. The USB protocol stays. The service, the serial port names, and the installer are the work.",
        "Repeat the FN-152 cable matrix on one Mac: the cable you ship, a second data cable, a charge-only cable, and an unplug during a push.",
        "Decide how the helper stays running when the window is closed. A Windows service is not a Mac answer. Write the choice down before you build it.",
        "Ship a separate Mac Quick Start. The Windows steps about the administrator prompt and Services will be wrong there.",
    ],
    note="Checking the Windows halves of FN-152 and SM-056 does not check this card.",
)


def _steps(items: list[str]) -> str:
    lis = "".join(f"<li>{escape(str(s))}</li>" for s in items)
    return f"<ol>{lis}</ol>"


def _card(item: dict) -> str:
    verdict = item["verdict"]
    label = {"close": "Check off", "pilot": "Open", "later": "Later"}[verdict]
    note = item.get("note") or ""
    note_html = f'<p class="note">{escape(note)}</p>' if note else ""
    return f"""
<article class="card {verdict}">
  <div class="card-top">
    <p class="kicker"><span class="ident">{escape(item["id"])}</span></p>
    <span class="badge {verdict}">{label}</span>
  </div>
  <h3>{escape(item["title"])}</h3>
  <p>{escape(item["why"])}</p>
  <p class="label">Where it stands</p>
  <p>{escape(item["now"])}</p>
  <p class="label">Done when</p>
  <p>{escape(item["done"])}</p>
  <p class="label">Work</p>
  {_steps(item["steps"])}
  {note_html}
</article>
"""


def _index() -> str:
    groups = [
        ("close", "Check off"),
        ("pilot", "Open"),
        ("later", "Later"),
    ]
    parts = []
    for key, title in groups:
        rows = [i for i in ITEMS if i["verdict"] == key]
        lis = "".join(
            f'<li><span class="ident">{escape(i["id"])}</span> {escape(i["title"])}</li>'
            for i in rows
        )
        parts.append(
            f'<div class="index-col"><h3>{escape(title)} <span class="count">{len(rows)}</span></h3>'
            f'<ol class="index">{lis}</ol></div>'
        )
    return '<div class="index-grid">' + "".join(parts) + "</div>"


def _check_table() -> str:
    rows = []
    for item in ITEMS:
        if item["verdict"] != "close":
            continue
        reason = item["done"].split(". ")[0].rstrip(".")
        rows.append(
            "<tr>"
            f'<td class="id">{escape(item["id"])}</td>'
            f"<td>{escape(item['title'])}</td>"
            f"<td>{escape(reason)}</td>"
            "</tr>"
        )
    hold = (
        ("FN-031", "Display timeout", "Firmware prints the error. Desk and Factory do not show it."),
        ("SM-142", "Versioning", "The publish script exists. A release note still does not pair Setup with the READY version."),
        ("SM-143", "Firmware CI", "GitHub compiles the sketch. The binary is not attached to the release."),
        ("SM-054", "Factory flash", "Factory can flash and lock a board. The card still wants one logged flash from the pinned build."),
        ("SM-056", "Setup", "Windows Setup exists. macOS, and a clean install with no surprise firewall prompt, do not."),
    )
    hold_rows = "".join(
        f'<tr><td class="id">{escape(i)}</td><td>{escape(t)}</td><td>{escape(w)}</td></tr>'
        for i, t, w in hold
    )
    return f"""
<table class="sheet">
  <thead><tr><th>Id</th><th>Card</th><th>Why it is done</th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>
<h2 class="follow">Leave these unchecked</h2>
<p class="lede">The program is partway there. The card is done only when the missing piece exists.</p>
<table class="sheet">
  <thead><tr><th>Id</th><th>Card</th><th>What is still missing</th></tr></thead>
  <tbody>{hold_rows}</tbody>
</table>
"""


def _section(name: str, blurb: str) -> str:
    cards = "".join(_card(i) for i in ITEMS if i["section"] == name)
    return (
        f'<h2 class="section">{escape(name)}</h2>\n'
        f'<p class="blurb">{escape(blurb)}</p>\n'
        f"{cards}"
    )


COVER = """
<p class="lede">What to check off on the FennSill board, and the plan for every card that stays open. The engineering rows are assigned to KC. The public app release named in the README is v0.1.27, 16 November 2026.</p>
<ol class="path">
  <li>Run FennsillSetup.exe once and accept the administrator prompt.</li>
  <li>Plug the panel in over USB. Desk shows the Device ID.</li>
  <li>On mcp.fennsill.com, link that id, mint a device key, and paste it into Desk.</li>
  <li>Point Claude, ChatGPT, or Cursor at https://mcp.fennsill.com/mcp with the account bearer. Leave the Device ID out of that form.</li>
  <li>Ask for a page. The Agent pulls the job and the panel refreshes.</li>
</ol>
<p>That path, on a PC you do not remote into, is V1. The access window is 30 days from the first MCP call after a real Agent heartbeat. You renew it. 31 December is for the open cards in the next section, not for grayscale, Wi-Fi, macOS, or Shopify.</p>
<p>KC owns the December rows. If SO or TW are other people, the ROLES card splits Device and Buyer path. The factory master key stays offline.</p>
"""

SECTIONS = (
    (S_WEEK, "The weekly list. V1 is the pilot. Milestones and roles stay open until the board matches this document."),
    (S_CLOSE, "These are already in the firmware, the cloud, or the Windows apps. Check the card and paste the decision."),
    (S_PILOT, "Still required before anyone outside the build uses a panel. 31 December belongs to this list."),
    (S_LATER, "Real work, dated after the first pilot week. Leave the December date off these cards."),
)


def build_html() -> str:
    sections = "".join(_section(name, blurb) for name, blurb in SECTIONS)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>FennSill V1 Plan</title>
<style>
  @page {{ size: letter; margin: 0; }}
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0; padding: 0;
    color: #0a0a0a;
    background: #f7f5f1;
    font-family: "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.4;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}
  h2 {{
    font-family: "Arial Narrow", "Franklin Gothic Medium", "Segoe UI", sans-serif;
    font-size: 16pt;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    border-bottom: 2.5px solid #0a0a0a;
    padding-bottom: 6px;
    margin: 0 0 10px;
    break-after: avoid;
    page-break-after: avoid;
  }}
  h2.follow {{ margin-top: 18px; font-size: 13pt; }}
  h2.section {{
    break-before: page;
    page-break-before: always;
    margin-top: 0;
  }}
  h3 {{
    font-family: "Arial Narrow", "Franklin Gothic Medium", "Segoe UI", sans-serif;
    font-size: 13pt;
    letter-spacing: 0.01em;
    margin: 2px 0 6px;
    line-height: 1.2;
  }}
  p {{ margin: 0 0 8px; }}
  ol, ul {{ margin: 0 0 8px; padding-left: 1.2em; }}
  li {{ margin: 0 0 3px; }}
  ol.path {{ margin: 12px 0 12px; }}
  ol.path li {{ margin: 0 0 5px; }}
  section.break {{ break-before: page; page-break-before: always; }}
  header.doc-head {{
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 16px;
    align-items: end;
    border-bottom: 3px solid #0a0a0a;
    padding-bottom: 12px;
    margin-bottom: 14px;
  }}
  .brand {{
    font-family: "Arial Narrow", "Franklin Gothic Medium", "Segoe UI", sans-serif;
    font-size: 26pt;
    font-weight: 800;
    letter-spacing: 0.16em;
    line-height: 1;
    margin: 0;
  }}
  .doc-title {{
    font-family: "Arial Narrow", "Franklin Gothic Medium", "Segoe UI", sans-serif;
    font-size: 13pt;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin: 6px 0 0;
  }}
  .meta {{ text-align: right; font-size: 8.5pt; color: #333; line-height: 1.45; }}
  .lede {{ color: #222; margin-bottom: 10px; }}
  .blurb {{ color: #333; margin: 0 0 14px; }}
  .index-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 18px;
    margin-top: 4px;
  }}
  .index-col h3 {{
    font-family: "Arial Narrow", "Franklin Gothic Medium", "Segoe UI", sans-serif;
    font-size: 11pt;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    border-bottom: 1.5px solid #0a0a0a;
    padding-bottom: 4px;
    margin: 0 0 8px;
  }}
  .count {{ float: right; letter-spacing: 0; font-variant-numeric: tabular-nums; }}
  ol.index {{ list-style: none; padding: 0; margin: 0; font-size: 8.5pt; line-height: 1.35; }}
  ol.index li {{ margin: 0 0 5px; }}
  table.sheet {{
    width: 100%;
    border-collapse: collapse;
    margin: 0 0 8px;
    background: #fff;
  }}
  table.sheet th {{
    text-align: left;
    font-size: 7.5pt;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    border-bottom: 1.5px solid #0a0a0a;
    padding: 0 10px 5px 0;
    font-weight: 700;
  }}
  table.sheet td {{
    border-bottom: 1px solid #d5d5d5;
    padding: 6px 10px 6px 0;
    vertical-align: top;
    font-size: 9.5pt;
  }}
  table.sheet td.id {{
    font-family: Consolas, "Courier New", monospace;
    font-weight: 700;
    white-space: nowrap;
    width: 0.85in;
  }}
  .card {{
    margin: 0 0 14px;
    padding: 0 0 4px;
    border-bottom: 1px solid #cfcfcf;
    break-inside: avoid;
    page-break-inside: avoid;
  }}
  .card-top {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 10px;
    margin-bottom: 1px;
  }}
  .kicker {{ margin: 0; }}
  .ident {{
    font-family: Consolas, "Courier New", monospace;
    font-size: 9pt;
    font-weight: 700;
    letter-spacing: 0.02em;
  }}
  .badge {{
    border: 1px solid #0a0a0a;
    padding: 1px 6px;
    font-size: 7pt;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    white-space: nowrap;
  }}
  .badge.close {{ background: #0a0a0a; color: #fff; }}
  .badge.later {{ border-style: dashed; color: #333; }}
  .label {{
    font-size: 7.5pt;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin: 8px 0 2px;
  }}
  .note {{
    margin-top: 8px;
    font-size: 9.5pt;
    color: #333;
  }}
  .end {{
    margin-top: 18px;
    padding-top: 8px;
    border-top: 1.5px solid #0a0a0a;
    font-size: 8.5pt;
    color: #333;
    letter-spacing: 0.02em;
  }}
</style>
</head>
<body>
<header class="doc-head">
  <div>
    <p class="brand">FENNSILL</p>
    <h1 class="doc-title">Product plan</h1>
  </div>
  <div class="meta">
    <strong>23 November 2026</strong><br>
    Product plan · Revision 1<br>
    Assignee KC<br>
    Release v0.1.27
  </div>
</header>
{COVER}
<section class="break">
  <h2>Check these off</h2>
  <p class="lede">The feature is already in the firmware, the cloud, or the Windows apps. Check the card.</p>
  {_check_table()}
</section>
<section class="break">
  <h2>Contents</h2>
  {_index()}
</section>
{sections}
<p class="end">FennSill product plan, 23 November 2026. Counsel still owns the words of the privacy policy and the EULA.</p>
</body>
</html>
"""


def _browser_exe() -> Path | None:
    browsers = ROOT / "connector" / "browsers"
    preferred = browsers / "chromium-1254" / "chrome-win64" / "chrome.exe"
    if preferred.is_file():
        return preferred
    if browsers.is_dir():
        for path in browsers.rglob("chrome.exe"):
            return path
    candidates = []
    for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = os.environ.get(key)
        if not root:
            continue
        candidates.append(Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe")
        candidates.append(Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    for path in candidates:
        if path.is_file():
            return path
    return None


def build_pdf() -> Path:
    html = build_html()
    HTML.write_text(html, encoding="utf-8")
    required = (
        "MS-10", "MS-11", "MS-12", "MS-13", "MS-14", "MS-15", "MS-16",
        "FN-024", "FN-030", "FN-031", "FN-032", "FN-034", "FN-035",
        "FN-036", "FN-037", "FN-038", "FN-151", "FN-152", "FN-157",
        "SM-145", "SM-146", "SM-147", "SM-148", "SM-060", "SM-061",
        "SM-062", "SM-054", "SM-053", "SM-057", "SM-055", "SM-056",
        "SM-059", "SM-049", "SM-048", "SM-052", "SM-051", "SM-050",
        "SM-047", "SM-139", "SM-140", "SM-144", "SM-142", "SM-143",
        "SM-063", "SM-065", "SM-075", "MK-127", "MK-129",
        "V1D", "ROLES", "OPS", "MAC",
    )
    missing = [token for token in required if token not in html]
    if missing:
        raise SystemExit(f"HTML is missing ids: {missing}")

    from playwright.sync_api import sync_playwright

    exe = _browser_exe()
    browsers = ROOT / "connector" / "browsers"
    if browsers.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers)

    with sync_playwright() as p:
        launch_kwargs: dict = {"headless": True}
        if exe is not None:
            launch_kwargs["executable_path"] = str(exe)
        browser = p.chromium.launch(**launch_kwargs)
        page = browser.new_page()
        page.goto(HTML.as_uri(), wait_until="load")
        page.pdf(
            path=str(OUT),
            format="Letter",
            print_background=True,
            margin={"top": "0.55in", "right": "0.62in", "bottom": "0.62in", "left": "0.62in"},
            display_header_footer=True,
            header_template=(
                "<div style=\"width:100%; font-size:8px; font-family: Arial Narrow, Segoe UI, sans-serif; "
                "letter-spacing:0.16em; color:#111; padding: 0 0.55in;\">"
                "FENNSILL<span style=\"float:right; letter-spacing:0.12em;\">PRODUCT PLAN</span>"
                "</div>"
            ),
            footer_template=(
                "<div style=\"width:100%; font-size:8px; font-family: Segoe UI, sans-serif; "
                "color:#333; padding: 0 0.55in; display:flex; justify-content:space-between;\">"
                "<span>23 November 2026 · v0.1.27</span>"
                "<span><span class=\"pageNumber\"></span> / <span class=\"totalPages\"></span></span>"
                "</div>"
            ),
        )
        browser.close()

    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)", flush=True)
    return OUT


if __name__ == "__main__":
    build_pdf()
