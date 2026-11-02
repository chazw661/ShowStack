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
  columns.
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
  - `Titles:` cells.
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

## Flags

- **Not caught:** sent, but never caught afterwards.
- **Still listed:** caught, but the segment straight after the catch still
  lists them as a speaker. They stay on, as when a host and a keynote are
  caught and then both appear in the "Keynote Conversation".
- **No cue:** listed as a speaker in a segment that no send/catch window
  covers.
- **Speaker?:** Speaker column text that matches no person.
- **BSM only:** a name that only ever appears in a cue, usually a nickname to
  merge.
- **Crew?:** a send/catch verb after a name that is not in the crew list.
- **Times:** a Start time earlier than the one before it.

## Reading time

pdfplumber's table search is nearly all of an import. A page whose only text
is digits (an empty ruled grid, at most numbered down the side) can't yield a
row, so it is skipped. On one file, searching such a 27-column grid cost
three times as much as a full page.

## Not stored

The PDF is read in memory during the request and discarded. Only the rows and
what was read from them are saved. Railway's disk is ephemeral, and showflows
can be under NDA.
