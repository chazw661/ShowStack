# Mic Plan: showflow parsing rules

How `planner/mic_plan/extract.py` and `parser.py` read a run-of-show PDF. The
rules came from a prototype tested on a real corporate showflow. That file and
the prototype stay out of the repo: showflows can be under NDA. Every name
below is a placeholder, and the test fixture
(`planner/tests/showflow_fixture.py`) uses made-up names too.

## Columns

- Columns are found by their header text, never by position. Two layouts
  have been seen:
  - 14 columns: blank/line, Start, End, Duration, Description, Speaker Name,
    Enter/Exit or Location, Video Preset, Background/Screen Notes, DSM's,
    Audio, Lighting, BSM, Notes.
  - 9 columns: LINE #, Start, End, Duration, Description, Speaker Name, Video
    Preset, DSM's, BSM.
  A third, upper-case layout adds LINE #, SCENE #, PROPS and STAGE LOCATION
  columns. A fourth heads the line column "a"; a fifth uses LINE # with
  "Enter Exit" and "DSMs" and has no send/catch cues at all.
- A header row names Start and Description, plus End, Speaker Name or BSM.
  If no row on any page does, the import fails with a clear message. Mic
  Plan does not guess.
- Header matching ignores case and also tries the text with its spaces
  removed, because a narrow column wraps its header mid-word ("DURATIO N").
  The speaker column can be headed SPEAKER, Speaker or Speaker Name.
- Legend rows above the header ("SESSION SEGMENT", "VOG", colour keys) are
  ignored.
- If the column the header marks for line numbers is empty, the line numbers
  are found in whichever unmapped column holds them (one file heads it "a").
- The header is usually on page 1 only, and later pages continue the same
  table. The column mapping carries over while the column count matches.
- A missing BSM or Speaker column is a warning, not an error.

## Times

- The Start column also holds video run times. `0:05:13` (hour 0) and the
  timecode `00:04:08:00` (four fields) are not clock times.
- A bare `8:46:00` or `10:18:00` has no AM/PM. It is read as whichever of the
  two times lies closest *after* the previous clock time, within 120 minutes.
- An explicit AM/PM time beats earlier guesses. If `10:45:00` was read as
  10:45a and the next segment says `10:41 AM`, the guess is dropped.
- Rows without a clock time are interpolated by row index between the clock
  times around them, and shown with ≈.
- If one explicit time sits ahead of the rest (a stray "9:33 AM" on a VOG
  line before the 9:00 segment), that stray time is dropped and flagged. The
  correct times after it are kept.
- A segment is a row with a clock Start and a clock End. Duration is used in
  whatever form the file uses for segments:
  - Where segments carry `H:MM:SS`, only rows with that form count, so a
    `0:24` beside a slide count isn't taken for a segment.
  - Otherwise `H:MM` rows count.
  - If the Duration column is blank throughout, Start and End alone are
    enough.
- A segment ends at its End time, or failing that at the next segment's
  start.

## People

- Names come from three places:
  - "please welcome …" lines. Names are split on `,` `&` `and`, and if the
    line has an ellipsis only the part after the last one counts
    ("please welcome… Acme President & CEO… Alex Host").
  - `Titles:` cells, and `TITLE:` / `N-UP TITLE:` cells (any N, any case).
    Their names may sit on the next line of the cell.
  - The Speaker column.
- A welcome line often lists "Title, Company, Name" ("welcome to the stage,
  Vice President, Acme Consulting, Alex Host"), so a welcome-line name only
  counts if a Speaker or Titles cell carries it too.
- Speaker cells are cleaned of stage directions first:
  - "Enter: BSL Exit: BSR"
  - "{CLICKER 1}"
  - parentheticals such as "(SL)", "(MC)" or "(Partner)"
  - bare stage codes
- Speaker and Titles cells run names together with no separator ("Dana Able
  Chris Baker"). Known names are matched first. What's left becomes a name if
  it is:
  - two or three words standing alone between separators (`,` `&` `and` `+`
    `;` `/`), such as "Tess St. Clair" or "Rory vandeberg" (a lower-case
    particle is allowed), or
  - a run of capitalised pairs.
- Anything else is flagged as unmatched speaker text, such as "Customer Panel
  Group 1-5". Text that is plainly not a person, like "DJ Audio Throughout"
  or "No audio", is dropped without a flag.
- After "Name -" comes an affiliation ("Alex Host - Acme AI Robin Cole -
  Initech"). It is skipped, and a trailing capitalised pair in it is the next
  person.
- A first name on its own doesn't match in the middle of a name, so "Tess
  St. Clair" is never read as Clair Dunn.
- An all-caps name ("ROBIN COLE" in a VOG line) is shown in title case.
- A first name counts as a person while it is unique among the people found.
  Merges on the review page add aliases ("KK" → Kim Keynote).
- A job title after `Name,` or `Name -` is dropped ("Alex Host, President &
  CEO").
- A title before a name stays part of it: "Dr. Ann Lee" (written with a full
  stop whether or not the file has one). "Ann Lee" without it is the same
  person. In a run-together cell a title starts the next name ("Kit Ames Dr.
  Lou Penn Dr. Sol Tate").
- A title and a surname alone ("Dr. Lee") never make a person. It is whoever
  was last introduced with that surname, or left over and flagged.

## Short names

- A first name alone in a Speaker cell ("Ned, Ola, Vic") is the person most
  recently introduced in full with that first name. An introduction is a
  `TITLE:` row, a welcome line, or an earlier Speaker cell with the full name;
  rows are read in order. Not any roster match: when "Vic Stone" is
  introduced on line 304 and "Vic Dahl" on line 316, "Vic" on line 305 is Vic
  Stone and on line 317 Vic Dahl.
- With no introduction yet, a first name only one person on the day has is
  that person.
- If the latest introduction names two people with that first name ("Vic
  Stone & Vic Dahl"), or nobody was introduced and two people share it, the
  line is flagged "which Vic?" and nobody is guessed.
- Each person keeps the line that first introduced them; the review page
  shows it as "intro'd line N".
- First names in BSM cues still need to be unique on the day (a merge sets
  an alias otherwise).
- "Pickle" means a clicker, not a mic, and is never a person.
- Mic hints only come from explicit callouts: HH or handheld gives HH, and
  "backup mic" gives backup. The hint goes to the people named in the same
  cell. If the cell names nobody ("no clicker, handheld"), it goes to that
  row's speakers. Anything else is left for the A2 to decide.

## Send / catch

- A cue is `<crew> (to) send(s) / catch(es) <names>`. Crew names come from
  the import: detected on a first import, after that copied from the
  project's last import, and editable on the review page. A verb after a
  capitalised word that is neither a crew name nor a person raises a flag.
- A BSM cell that opens with the verb ("Send Alex") is a cue with no crew
  name.
- A name list stops at BSM chatter that follows it ("Sends Kim Needs
  Clicker"): verbs and nouns such as needs, grab, clicker and mic are never
  part of a name.
- Matching runs over every BSM cell joined into one word stream. Cues that
  spill into the next row or onto the next page still read ("Lee Catches
  Dana," / "Chris, and Robin Rio Sends Alex").
- A cue belongs to the row its verb is on.
- The name list ends at the first word that is not joined by a comma, "and"
  or "&". So "Sam sends Dana, Chris, Robin and Morgan Robin and Dana have
  pickles" sends four people and stops at Morgan.
- When a cue happens:
  - A row with its own clock time always uses that time.
  - A send happens at the start of the next segment, if that segment begins
    within 4 rows. Otherwise it uses the row's own interpolated time, since
    the cue is mid-segment ("Alex Enters").
  - A catch happens at the start of the next segment. After the last
    segment, it happens at that segment's end.
  - When the same row both sends and catches someone, the catch is the send
    plus the row's Duration, or 5 minutes if it has none.

## Segment names

- A segment's name is its first description that is not a VOG line, a
  "ROLL RECORDS" / "END RECORDS" cue, a "STAGE SET" note or a walk-in loop;
  one file puts the VOG line on the row with the segment's times.
- A segment with a "BREAK" or "LUNCH" line and no Speaker text is a break.

## Description intros

- A description that brings people on (welcome / join / introduce / bring
  up / invite wording) is checked: the "First Last" items after that wording,
  and any known full name there, should be in a Speaker cell within three
  rows either side. One upper-case export lists the Speaker two rows before
  the VOG welcome, so the check looks back as well as ahead.
- Items with a job title or an organisation word ("… Consulting", "Product
  Management", a game or talk title) are not people.
- If someone is missing, the line is flagged "description names people not
  in the Speaker column — check who goes on". They are not made into people.

## Flags

- **Not caught:** sent, but never caught afterwards.
- **Still listed:** caught, but the segment straight after the catch still
  lists them as a speaker. They stay on, as when a host and a keynote are
  caught and then both appear in the "Keynote Conversation".
- **No cue:** listed as a speaker in a segment that no send/catch window
  covers. Not raised when the part has no cues, or when cues cover fewer than
  half of the people listed (one stray cue in a file without cues).
- **Which?:** a first name that more than one person on the day could be.
- **Not listed:** a description brings on people no nearby Speaker cell
  names.
- **Speaker?:** Speaker column text that matches no person.
- **BSM only:** a name that only ever appears in a cue, usually a nickname to
  merge.
- **Crew?:** a send/catch verb after a name that is not in the crew list.
- **Times:** a Start time earlier than the one before it.
- **Gone:** someone no part of the day mentions any more, kept because of a
  merge, Presenter link or mic hint the user set. Shown in People with a
  Remove button.

## Re-import and re-read

Every import, Replace, delete, merge, crew change and **Re-read with current
rules** (part menu) re-parses the stored rows of every part of the day from
scratch. Only what the user set is carried over:

| Kept (user) | Rebuilt every time (parser) |
|---|---|
| Merges (aliases; only a merge writes them) | The people themselves, their lines and intro line |
| A mic hint picked by hand (`mic_hint_locked`) | A hint read from a callout ("HH", "backup") |
| A Presenter chosen by hand, including "no presenter" (`flags['presenter_by'] = 'user'`) | An automatic Presenter match by name |

The parser is only told about merges (each alias and the name it points to).
A hand-set hint or Presenter link stays with the person by name after the
parse. People an older parse made are not fed back to it: they would count as merged spellings and
override later rules (Client E: a first-name person from the #160 parser took
an earlier line from the recency rule). A user alias still wins over the
parser. Someone with no lines after a re-parse is deleted, unless they carry
user state; then they stay, flagged **Gone**.

Re-read also recomputes each stored row's times and segments (est_time,
segment start/end) and the part's span. Presenter links that existed before
this rule (PR 1.2) were all treated as automatic on the first rebuild.

## The plan

`planner/mic_plan/solver.py` (pure Python, no Django; `planning.py` feeds it
from the database and saves the day's `MicPlan`). Times are minutes.

### Appearances
- **A part with cues** (cues cover at least half the people it lists): on at
  the send, off at the catch.
  - Caught, but a segment starting before the catch still lists them: kept on
    to the end of that segment ("still listed").
  - Never caught: on through the segment they were sent into, and through any
    segments straight after it that still list them.
  - Listed in a segment no cue window covers: on for that segment. As in the
    parser's "No cue" rule, "listed in a segment" means named by the
    segment's heading row (its Speaker cell), not by a welcome line just
    before it.
- **A part without cues:** on at the first row naming them; off when the row
  after their last naming row starts, at most the end of that segment (the
  end of the segment when that row has no later time). Rows in the same or the
  next segment are one appearance; a segment without them splits it.
- **Hosts:** 3+ appearances, or listed in 3+ segments: one appearance from
  their first on to their last off, one pack, never de-mic'd.
- **Back on within the pre-mic lead** of coming off: the pack stays on (no
  de-mic, no new mic).

### A2 time
- Mic: released at on − lead, must finish by on − margin. De-mic: released at
  off.
- The A2 free soonest takes the next action; one A2's actions never overlap.
- A de-mic is done first when doing it now still lets every open mic make its
  deadline (earliest-deadline-first check across all A2s, against the lateness
  that is already unavoidable).
- Otherwise a mic is done as soon as it is released and a pack is free. With
  no free pack it waits for one to free up, unless none can free up in time,
  and opens a new pack only when waiting longer would make a mic later. This
  is how A2s work (people are mic'd as they arrive) and never needs more packs
  than the prototype's latest-safe mics (tested on both fixtures).
- Late (ready after the walk-on) and tight (inside the margin) are flagged;
  nothing is retried, so an impossible day still finishes.

### Packs
- The person's own previous pack if free, else the pack free longest, else a
  new one. Body and handheld are separate pools (hint "HH" = handheld).
- Hint "backup": an extra pack of their own (handheld unless set to body pack
  in People), mic'd and de-mic'd with them, shown as "<Name> backup" and
  counted in the totals.
- RF numbers: body, body backups, handheld, handheld backups, then the
  emergency spare handheld, which is never assigned and counts against the
  handheld total.
- Over a set body or handheld count, the plan is still made and each pack
  over is flagged at its line ("need 1 more body pack than the 8 set").
- A2 busy: action minutes inside each segment, per A2. More than the segment
  is long is flagged "A2 overload"; 90 % and over is counted in the stat tile.

## Interactions with the plan

- A re-read changes `est_time`, and with it every on/off time, so it marks
  the day's MicPlan stale. So do an import, Replace, delete, merge, alias
  removal, crew change, Remove and a mic hint or backup type change. A plan
  settings change is shown as a banner (the plan keeps its settings snapshot).
- PR 5: once a plan has been applied to Mic Tracker, Re-generate must treat
  the current RF numbers as soft pins, so labels already printed stay valid.

## Reading time

Up to 60 pages. On Railway a 19-page file read in 0.77 s.

pdfplumber's table search is nearly all of an import. A page whose only text
is digits (an empty ruled grid, at most numbered down the side) can't yield a
row, so it is skipped. On one file, searching such a 27-column grid cost
three times as much as a full page.

## Not stored

The PDF is read in memory during the request and discarded. Only the rows and
what was read from them are saved. Railway's disk is ephemeral, and showflows
can be under NDA.
