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
- A segment is a break when any of these holds:
  - a "BREAK" or "LUNCH" line and no Speaker text (Client E);
  - its name has break, lunch, networking, intermission, recess, coffee,
    refresh, reception, transition or meal in it, and its heading row names
    nobody to speak (Client A "Networking Break"; Client B "BREAK" with "DJ
    Audio Throughout"; not Client A "Back from Break" or "... & Lunch
    Transition", where presenters walk on);
  - 15 minutes or more with nobody named and no Speaker text (Client A
    "Doors").
- Editors can set any segment to break or not (the Break toggle on its
  heading in Showflow + plan). The setting is stored by the heading's line,
  is kept on Re-read and Replace, and shows as "break · set by you". Setting
  it back to the detected value removes it. Changing it makes the plan stale.

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

## Exits and re-entries

- A description says who exits: names joined by `,` `and` `&` right before
  exit / exits / exiting / leave(s) / walk(s) off / off stage ("Ola exits
  when the exam is complete", "Max and Dr. Reyes Exit", "Ned welcomes Bo
  and Zed to stage Ned exits"). The names are read as in Speaker cells: a
  full name, a first name meaning whoever was introduced last, "Dr. Surname".
- Re-enter(s) / reenter(s) / returns brings someone back on ("Max re-enters
  with Dr. Una Reyes").
- A verb followed by ":" is a stage note ("Exit: BSR"), not an exit.
- A group before the exit verb: all / everyone / panel / panelists /
  presenters / speakers exit ends everyone on stage in that part except
  hosts and anyone named as staying ("Panel Exits (Kit Stays)"). "both
  exit" ends the two non-hosts on stage, and only when exactly two are on.
- They decide off times only in parts without cues (see The plan).

## Adding people by hand

- A **Not listed** card offers "Add people from this line": the names after
  the welcome / introduce wording, split on `,` `and` `&`, with a suffix
  such as "MD" or "PhD" kept on the name before it ("Name, Name, MD, Name"),
  and a label before " - " dropped ("your MC'S - Name & Name"). The list is
  edited before confirming. Adding clears the card.
- People's **Add person** takes a name, an on line and an optional off line.
- A name already on the day (by name, an alias, or the name without a title
  or suffix) is matched, not duplicated; a Presenter is linked the same way.
- Each added appearance is user state (`flags['added']`), kept on Re-read
  and Replace by the label of its line. If that line is gone it stays, flagged
  "Line N no longer in this showflow", and is left out of the plan.

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
- **Exit?:** a part without cues has an exit line naming nobody ShowStack
  recognises ("who exits?"). Nobody comes off there.
- **Both?** (plan): "both exit" with other than two non-hosts on stage. Nobody
  comes off there.
- **Added:** a line someone was added on by hand is no longer in the showflow.

## Re-import and re-read

Every import, Replace, delete, merge, crew change and **Re-read with current
rules** (part menu) re-parses the stored rows of every part of the day from
scratch. Only what the user set is carried over:

| Kept (user) | Rebuilt every time (parser) |
|---|---|
| Merges (aliases; only a merge writes them) | The people themselves, their lines and intro line |
| A mic hint picked by hand (`mic_hint_locked`) | A hint read from a callout ("HH", "backup") |
| A Presenter chosen by hand, including "no presenter" (`flags['presenter_by'] = 'user'`) | An automatic Presenter match by name |
| A segment set to break or not by hand (`ShowflowImport.break_overrides`, by line) | Break detection |
| Appearances added by hand (`flags['added']`, by line label) | Exit and re-entry lines (`flags['exits']`, `flags['enters']`) |

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
- **A part without cues** (PR 5.2): on at a row naming them (Speaker /
  welcome) or saying they re-enter. Off at the earliest of a row saying they
  exit (by name, or a group: see Exits) and the end of the segment they came
  on in. An exit on their walk-on row, or on a row with no time of its own
  later than the walk-on, ends when the next row with a later time starts.
  Named again after an exit, or in a later segment: a new appearance (back
  on at once in the next segment: one wearing, the pack stays on). Before
  PR 5.2 they came off when the row after their last naming row started, so
  a panel named once on its title row was de-mic'd minutes into the panel.
- **Added by hand:** on at the line; off at the off line if one was given,
  else by the rule above, in any part, cued or not.
- **Hosts:** 3+ appearances, or listed in 3+ segments: one appearance from
  their first on to their last off, one pack, never de-mic'd. Counted the way
  appearances were before PR 5.2 (consecutive segments one stretch, exits
  ignored), so exits and re-entries never make someone a host.
- **Back on within the pre-mic lead** of coming off: the pack stays on (no
  de-mic, no new mic).

### A2 time
- Mic: released at on − lead, must finish by on − margin. De-mic: released at
  off.
- The A2 free soonest takes the next action; one A2's actions never overlap.
- Mics come first. A de-mic (or an idle minute) is done only when it makes no
  open mic any later past its deadline (on − margin), checked mic by mic with
  an earliest-deadline-first pass across all A2s. Comparing against the day's
  worst lateness instead let an unavoidably late run at 11:41 wave through
  de-mics that made 8:26 mics late; the per-mic check is what stops that.
- Otherwise a mic is done as soon as it is released and a pack is free. With
  no free pack it waits for one to free up, unless none can free up in time,
  and opens a new pack only when waiting longer would make a mic later. This
  is how A2s work (people are mic'd as they arrive) and never needs more packs
  than the prototype's latest-safe mics (tested on both fixtures).
- Late (ready after the walk-on) and tight (inside the margin) are flagged
  with their cause: "A2 time", or "no pack free (body limit 9)" when the mic
  waited on a set pack count while it could still have been on time. With no
  pack count set every late mic is A2 time (tested: its A2 did only mics from
  its release to its start).
- A run of A2-time mics (release-to-finish windows overlapping) gets a fix on
  its first flag: the smallest pre-mic lead that puts every mic in it on time
  with the same A2s, and "or a second A2" when that would too. Both come from
  solving the day again (lead +1 min at a time, up to 240), not an estimate.
- Nothing is retried, so an impossible day still finishes.

### Packs
- The person's own previous pack if free. Otherwise it depends on the pack
  policy (Plan settings, "Pack use"):
  - **Recycle at breaks** (the default): a pack last worn before the latest
    session start, lowest RF first ("down the line"), else a new one. Within
    a session a pack that has been worn never goes to someone else, so a
    returner always gets their own back.
  - **Fewest packs** (the behaviour before PR 2.2): the pack free longest,
    else a new one. This greedy reuse can cost a pack: on the Client E
    fixture, line 310's two walk-ons wait idle for packs to free up, which
    leaves the A2 no time to de-mic before the 9:00 wave, so it opens an
    extra pack (11 against Recycle at breaks' 10). So Fewest packs also
    solves the day with Recycle at breaks and uses that plan when it needs
    fewer body packs (or as many and fewer handhelds) with no more late,
    tight or short flags, without its mid-session and break-turnover flags.
    Fewest packs therefore never needs more packs (tested on the fixtures;
    checked on the 8 real files).
- Sessions start at each break segment's start, and at the start of a part
  that begins after every earlier part has ended. A walk-on at or after a
  session start is in that session. A pack's session is the last one it was
  worn in.
- De-mics still happen when people come off; only reuse waits for the break.
  Whether a pack's de-mic fits before the next walk-on is the A2-time model's
  call. When it doesn't, the next person gets a new pack, and the break gets
  one flag: "Break at line 196 too short to turn over 2 packs." (K: the
  number of new packs opened after it while a pack from before it was still
  waiting for its de-mic.)
- Under Recycle at breaks, at a set count: a mic first waits for a pack from
  before the break if one frees up by its deadline, then reuses the pack free
  longest mid-session, flagged at its line ("Line 141: RF 3 reused
  mid-session — body pack count (9) reached."), then waits as below.
- Body and handheld are separate pools (hint "HH" = handheld). Hosts and
  backup packs are the same under both policies.
- On Generate the day is also solved under both policies with the pack
  counts blank. The packs each needs are shown in the settings tile and form
  ("Recycle at breaks: 14 body · Fewest packs: 9 body"); only the chosen
  policy's plan is saved. Plans from before PR 2.2 count as Fewest packs.
- Hint "backup": an extra pack of their own (handheld unless set to body pack
  in People), mic'd and de-mic'd with them, shown as "<Name> backup" and
  counted in the totals.
- RF numbers: body, body backups, handheld, handheld backups, then the
  emergency spare handheld, which is never assigned and counts against the
  handheld total.
- A set body or handheld count is binding: at it, a mic waits for the next
  de-mic of that pool instead of opening a pack (it may then be tight or late,
  cause "no pack free"). It goes over the count only when no pack can free up
  before its walk-on. Backup packs count toward the pool and never wait.
- Over a set body or handheld count, the plan is still made. Each stretch of
  time with more packs of a pool in use than set gets one flag, at the line
  where it starts, giving its peak ("Line 183: need 2 more body packs than the
  9 set (11 in use from 11:35a)").

### A2 busy and spill
- Busy: the A2's action minutes inside each segment, per A2. Where segments
  overlap (a "Doors" holding a "Pre-Show"), a minute counts in the one that
  started later, so no minute is counted twice.
- One A2 can never be busier than a segment is long, so "over 100 %" is
  shown as spill instead: work the segment owes (de-mics released in it, mics
  due in it) still going after it ends. It is shown on the segment's meter
  ("+3 min into Lunch") and goes to Review when it is 5 min or more, or runs
  into a segment with a mic due.
- Segments shorter than one mic (a 1-minute video) are left out of the
  "A2 ≥ 90 %" tile and of spill: nothing fits in them.
- "Pack changes" (stat tile): times a pack goes to someone other than who wore
  it last.

### Edits (moves, pins, undo)
- Every change the A2 makes is one entry in the day plan's edit log
  (`MicPlanEdit`): Move to RF (drag a pack chart bar to a lane, tap a bar then
  a lane, or a pack chip's menu), Switch body/HH, Unpin. Each is one POST
  against the plan's version; a stale version is refused ("reload").
- Edits are keyed by appearance, not by pk: the person's name key, the label
  of the line they come on at, and how many of their earlier appearances
  start on a line with that label (`kim keynote|113|0`). The key survives
  re-solves, Re-read and Replace. An edit whose key no longer matches is kept,
  not applied, and shown in Review ("Your change to <name> at line N no
  longer matches the showflow").
- Pins (the log replayed in order) are hard: a pinned appearance wears its RF
  for its whole wearing (all appearances sharing that pack). It never waits
  on the pack count. If its RF's wearer comes off before its walk-on it waits
  for that de-mic (tight/late flags then say "RF 3 is with <name> until 8:57a
  (your change at line 316)"); otherwise it takes the RF while it is still
  worn, and Review shows a red conflict: "RF 5 on two people 9:05a–9:12a
  (<name> and <name>) — your change at line 171." A pin that reuses a pack
  mid-session under Recycle at breaks is an info card. A move onto a handheld
  lane makes them handheld ("→ RF 13, now handheld").
- Minimal change: every re-solve except Start over prefers each appearance's
  RF from the version it replaces, before any other pack rule; the other
  rules avoid RFs someone else is pinned or preferred to over the same
  stretch. Pinned and preferred RFs keep their numbers; other packs take the
  lowest free number. Appearances that could not keep their RF are listed on
  one info card ("Moved"); the "N changed" pill lists every RF change of the
  latest generate, edit or undo.
- An edit or undo re-solves with the plan's own settings and skips the
  lead-fix search (fix suggestions come back on the next Generate). Undo
  removes the last edit and re-solves preferring the RFs from just before
  it, which gives back that plan. No redo.
- Re-generate offers "keeping my changes" (the log replayed, previous RFs
  preferred: only what new data or settings force moves) and "Start over"
  (clears the log, numbers every pack afresh; confirmed inline).
- A stale plan takes no edits until it is re-generated. Viewers see pins and
  changes, no controls.

## Interactions with the plan

- A re-read changes `est_time`, and with it every on/off time, so it marks
  the day's MicPlan stale. So do an import, Replace, delete, merge, alias
  removal, crew change, Remove and a mic hint or backup type change. A plan
  settings change is shown as a banner (the plan keeps its settings snapshot).
- PR 5: once a plan has been applied to Mic Tracker, Re-generate keeps the
  applied RF numbers through the same path as "keeping my changes" (previous
  RFs as soft preferences), so labels already printed stay valid.

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
