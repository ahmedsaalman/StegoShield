"""Built-in sample messages for the Evaluation Lab, from a one-line note to a long dossier.

Fictional, original text. Sizes grow roughly 3x per step so users can see detectability rise with
message length in the same image. Longer texts are built by repeating numbered sections, so every
byte is still readable text.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SampleText:
    """One built-in message."""

    id: str
    title: str
    description: str
    text: str

    @property
    def size_bytes(self) -> int:
        return len(self.text.encode("utf-8"))


_NOTE = "Meet at the north gate at 9 tonight. Bring the blue folder. Burn this note."

_CHAT = """[21:02] A: Are we still on for tomorrow?
[21:03] B: Yes. Usual place, but use the side entrance - the front is being watched.
[21:03] A: Who is watching?
[21:04] B: Two cars since Monday. Same plates. I wrote them down.
[21:05] A: Send the plates through the usual channel, not here.
[21:06] B: Understood. 10:30, side entrance, come alone.
[21:06] A: See you then. Delete this thread."""

_EMAIL = """Subject: Quarterly figures - do not forward

Hi Sara,

As promised, here is the short version before tomorrow's meeting. The numbers in the shared
folder are not the real ones; finance asked us to keep the draft private until the audit closes.

Revenue for the quarter came in at 4.2 million, about 11 % below the forecast we gave the board.
Most of the gap is the delayed contract in the northern region, which legal now expects to sign
in the first week of next month. Costs are on plan, with one exception: the data-centre move ran
two weeks long and added roughly 180,000 in overtime and equipment rental.

Two things I need from you:
1. Do not mention the northern contract by name in the slides. Call it "a regional renewal".
2. Keep the overtime figure out of the summary page; it is in the appendix with an explanation.

If anyone asks where the numbers came from, point them to me. I will send the full workbook
once the audit team has signed off. Thanks for keeping this quiet.

Best,
Daniel"""

_LETTER_PARAGRAPHS = (
    "Dear Mira, I am writing this by hand first and copying it out, because I do not trust the "
    "usual post any more. Letters arrive opened and resealed, and twice now a page has gone missing. "
    "So this one travels inside a photograph of the harbour, which nobody will look at twice.",
    "The work at the archive is going better than I hoped. The ledgers from 1962 to 1971 are all "
    "there, bound in the order the clerks left them, and they confirm what your father suspected: "
    "the land transfers were recorded twice, once under the real buyer and once under a shell name.",
    "I have photographed every page that matters, about four hundred in all, and kept the "
    "originals exactly where I found them. If anyone checks the reading-room log they will see a "
    "student studying shipping records, which is not entirely untrue.",
    "Please do not reply to this address. When you are ready to meet, leave the blue scarf on the "
    "railing outside your window and I will come the following Thursday at noon, to the café by "
    "the fish market. Bring nothing written down. We can talk while we walk.",
    "Take care of yourself, and of the boy. Whatever happens with the ledgers, the truth is safe "
    "now in more than one place. With love, as always, your friend from the old street.",
)

_REPORT_SECTION = """Section {n}. Field observations, week {n}

Site visits: three warehouses on the east quay were checked between 06:00 and 09:00. Loading
activity was normal at two of them. At the third, a refrigerated truck without company markings
arrived at 07:40 and left at 08:15; the driver did not sign the gate log. Registration noted.

Interviews: two dock workers agreed to speak informally. Both described night shifts that are
not on the published roster and payments made in cash. Neither would give a name on record.
Their accounts match each other on dates and times, which suggests they are not rehearsed.

Documents: copies of four delivery notes were obtained. Quantities on the notes do not match the
customs declarations filed the same day; the difference is between 12 and 19 %, always in the
same direction. Originals remain with the source. Copies are stored offline.

Assessment: the pattern is consistent with goods being under-declared at entry. Confidence is
moderate. Next step is to compare a full month of declarations against the port's weighbridge
records, which should be obtainable through the existing contact in the harbour office.

"""

_LETTER_PAGES = 3
_REPORT_TARGET_BYTES = 12_000
_DOSSIER_TARGET_BYTES = 40_000


def _paged_letter(pages: int) -> str:
    body = "\n\n".join(_LETTER_PARAGRAPHS)
    return "\n\n".join(f"- page {page} of {pages} -\n\n{body}" for page in range(1, pages + 1))


def _numbered_sections(target_bytes: int) -> str:
    sections, total, number = [], 0, 1
    while total < target_bytes:
        section = _REPORT_SECTION.format(n=number)
        sections.append(section)
        total += len(section.encode("utf-8"))
        number += 1
    return "".join(sections).rstrip() + "\n"


SAMPLE_TEXTS: tuple[SampleText, ...] = (
    SampleText("note", "One-line note", "The smallest realistic message.", _NOTE),
    SampleText("chat", "Chat excerpt", "A short private conversation.", _CHAT),
    SampleText("email", "Confidential email", "A typical one-page email.", _EMAIL),
    SampleText("letter", "Three-page letter", "A personal letter over several pages.", _paged_letter(_LETTER_PAGES)),
    SampleText("report", "Field report", "A multi-section document.", _numbered_sections(_REPORT_TARGET_BYTES)),
    SampleText(
        "dossier",
        "Long dossier",
        "A long document; fills a large share of a 512 px image.",
        _numbered_sections(_DOSSIER_TARGET_BYTES),
    ),
)


def find_sample_text(text_id: str) -> SampleText | None:
    """The sample text with this id, or None."""
    return next((sample for sample in SAMPLE_TEXTS if sample.id == text_id), None)
