# ShowStack Module: Multitrack Session Builder

## Purpose

A ShowStack module that converts console channel data into ready-to-use multitrack recording sessions for Reaper and Nuendo Live. The user picks a console (already modeled in ShowStack), configures a track list (which channels to include, their order, labels, colors), and exports a DAW project file or template with everything pre-named and pre-colored.

**This is a DAW exporter that stores reusable session configurations. It is NOT a full session planner.** No setlist/marker generation, no file-naming automation, no recording-rig modeling. Those features stay out of scope until users explicitly ask.

## Why this is needed

Yamaha already integrates CL/QL/Rivage with Nuendo Live natively via Yamaha Console Extension, but:
- It's flaky in the field (widely reported as unreliable)
- It only works when the recorder is on the Dante network the console is on
- It only targets Nuendo Live — Reaper has no first-party path
- It can't pre-configure track order or filter unused channels

ShowStack already stores the channel labels, colors, and input patches. This module turns that data into the correct DAW session in one click, regardless of how audio physically reaches the recorder.

## Architecture

Standard ShowStack module conventions apply:
- Django 5.x app, lives alongside other modules
- Uses `showstack_admin_site` for any admin views
- `BaseEquipmentAdmin` and project-filtering middleware where applicable
- Project-scoped via `PROJECT_member` permissions (Owner/Editor/Viewer)
- Templates use `base_site.html` dark theme
- Static files via Whitenoise
- Use the same template save/load pattern as other ShowStack modules (Comm Config, Mic Tracker, etc.) — match the existing UX

## Data Model

### MultitrackSession

The reusable, named recording configuration. Belongs to a project, references a console.

```python
class MultitrackSession(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    console = models.ForeignKey(Device, on_delete=models.CASCADE,
                                 limit_choices_to={'category': 'console'})
    name = models.CharField(max_length=200)  # e.g. "Sat Headliner — Broadcast"
    target_daw = models.CharField(max_length=20, choices=[
        ('reaper', 'Reaper'),
        ('nuendo_live', 'Nuendo Live'),
        # ('pro_tools', 'Pro Tools'),  # deferred — see below
    ])
    feed_source = models.CharField(max_length=30, choices=[
        ('console_dante', 'Console Dante card (post-input)'),
        ('rio_direct', 'RIO / stage box direct'),
        ('custom', 'Custom mapping'),
    ], default='console_dante')
    track_order_mode = models.CharField(max_length=20, choices=[
        ('console', 'Console channel order'),
        ('dante', 'Dante stream order'),
    ], default='console')
    recorder_capacity = models.PositiveIntegerField(null=True, blank=True,
        help_text="Optional — drives over-capacity warning bar")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('project', 'name')]
```

### MultitrackTrack

Ordered list of tracks within a session. Most reference a console channel; some are manual additions.

```python
class MultitrackTrack(models.Model):
    session = models.ForeignKey(MultitrackSession, on_delete=models.CASCADE,
                                 related_name='tracks')
    track_number = models.PositiveIntegerField()  # user-orderable
    source_channel = models.ForeignKey('ConsoleChannel', null=True, blank=True,
                                        on_delete=models.SET_NULL,
                                        help_text="Null for manually-added tracks")
    label_override = models.CharField(max_length=100, blank=True)
    color_override = models.CharField(max_length=7, blank=True)  # hex
    enabled = models.BooleanField(default=True)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['track_number']
        unique_together = [('session', 'track_number')]
```

For the resolved label/color (template renders this):
- `label = label_override or source_channel.name or "(untitled)"`
- `color = color_override or source_channel.color or default`

### MultitrackTemplate

The reusable structure independent of any specific console. Apply to a console → seeds a new MultitrackSession.

```python
class MultitrackTemplate(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    target_daw = models.CharField(max_length=20)
    track_order_mode = models.CharField(max_length=20)
    feed_source = models.CharField(max_length=30)
    include_aux = models.BooleanField(default=False)
    include_matrix = models.BooleanField(default=False)
    include_groups = models.BooleanField(default=False)
    color_scheme = models.JSONField(default=dict, blank=True)
        # e.g. {"vocals": "#FF0000", "drums": "#FFA500", ...}
    naming_pattern = models.CharField(max_length=200, blank=True)
        # e.g. "{channel_name}" or "Tr{track_num:02d}_{channel_name}"
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

Match the save/load UX of existing ShowStack template systems (e.g. Comm Config). Same buttons, same placement, same modal behavior.

### Optional channel-level seed flag

On the existing `ConsoleChannel` model (or wherever channel definitions live):

```python
default_record = models.BooleanField(default=True)
default_record_color = models.CharField(max_length=7, blank=True)
```

When creating a new MultitrackSession, pre-check tracks where `default_record=True`. This is a *seed*, not the source of truth — users can always override per-session.

## CSV Parsing

The "import a CSV from the console" path is the fallback for users who haven't fully populated their console in ShowStack. It populates the channel list as a starting point; the user then picks/orders/labels.

Three console families need separate parsers:

### CL/QL series
- Source: Studio Manager / CL Editor / Console File Converter exports
- Channel name CSV is well-defined; column structure depends on export path — confirm against actual files before finalizing parser
- Color codes are an enum (Off, Red, Orange, Yellow, Green, Blue, Sky Blue, Purple, Pink, White)

### M7CL
- **Confirm a CSV export path exists before scoping this in.** Native session is `.M7C` (binary via Studio Manager). If no clean CSV, this is either drop M7CL from v1 or add `.M7C` parsing as separate work.

### Rivage PM
- Source: Console File Converter or RIVAGE PM Editor labels CSV
- Different field set from CL/QL; higher channel count (up to 144 inputs, plus Mix/Matrix/Cue)
- More color options (Rivage has expanded palette vs CL/QL)

Build a pluggable parser interface — `parse_console_csv(file, console_family) → list[ChannelData]` — so each family is a self-contained module.

## Feed Source Logic

This is the critical correctness logic. The `feed_source` field on MultitrackSession determines how track labels map to recorder channels:

- **`console_dante`** — Recording from the console's own Dante output card. Dante stream N = console channel N. Label-to-track mapping is trivial; both order modes produce the same result. This is the "easy" case.
- **`rio_direct`** — Recording from RIO/stage box Dante outputs directly. Dante stream N = RIO physical input N. The label for Dante stream N comes from whatever console channel has that RIO input patched to it. Requires the input patch (which ShowStack already stores). If `track_order_mode='dante'`, tracks are ordered by Dante stream and labeled via patch lookup. If `track_order_mode='console'`, the user is overriding the natural recorder order — produce the export with tracks in console order but warn that the Dante stream numbers won't be sequential.
- **`custom`** — User provides an explicit mapping table (Dante stream N → console channel X). Show a mapping editor in the UI.

Default to `console_dante` since it's the most common for self-contained CL/QL/Rivage rigs.

## UI Flow

Mirror existing ShowStack module patterns. Suggested flow:

1. **Module landing page** — list existing MultitrackSessions in this project, "New Session" button, "Templates" tab
2. **New Session wizard:**
   - Step 1: Pick console (dropdown of project consoles)
   - Step 2: Pick target DAW + feed source + track order mode
   - Step 3: (optional) Apply template
   - Step 4: Track configuration UI (the main editor)
3. **Track configuration UI** — single-page editor:
   - Top bar: session name, target DAW, save/export buttons
   - Capacity warning bar (only if `recorder_capacity` is set): "47 of 64 tracks" or in red "72 / 64 — 8 over capacity"
   - Bulk include/exclude toggles for Aux, Matrix, Groups (collapsible sections)
   - Drag-to-reorder track list — each row shows: enabled checkbox, track #, channel ref, label (with override), color swatch (with override), notes, delete (for manual tracks)
   - "Add manual track" button at bottom (creates a track with no `source_channel` — for click tracks, room mics not on the console, talkback returns)
4. **Export** — generates the file, presents download

## DAW Exporters

### Reaper (.RPP)
- Plain text format, well-documented
- Generate a project file with one track per enabled MultitrackTrack
- Track name = resolved label
- Track color = resolved color converted to Reaper's native color int (RGB packed)
- Track index = `track_number`
- Optionally: also offer a Reaper track template (`.RTrackTemplate`) export for users who want to merge into an existing project
- This is the simpler exporter — start here

### Nuendo Live (.nlpr)

Confirmed via diffing four real Nuendo Live 3 session files (1-track, 2-track same color, 2-track different colors, and a 76-track production session):

- **Format is plain XML**, root `<SteinbergProject>`, encoding `utf-8`. Line endings vary — the McKesson file uses CRLF, the others use bare CR (classic Mac style). Both are accepted by Nuendo Live.
- **No separate track-archive format exists** in Nuendo Live (unlike full Nuendo). `.nlpr` is the only target.
- File version observed: `Application Version` class with `value="Nuendo Live"`, `Version="Version 3.0.0"`, `Platform="WIN64"`.

**Implementation: template-injection approach.** Do NOT synthesize the file from scratch.

1. Bundle a known-good empty `.nlpr` template as a fixture in the module (`fixtures/nuendo_live_3_template.nlpr`). Charlie generates this by saving a fresh empty Nuendo Live 3 session with one default audio track named e.g. `"Audio 01"`.
2. At export time:
   - Load the template XML using `lxml` (preserves formatting; stdlib ElementTree mangles output)
   - Locate the audio track folder: `MFolderTrack` whose `MTrackList → Name` value is `"Audio"` (NOT the `"Input/Output Channels"` folder, which holds device routings — leave that alone)
   - Inside that folder's `<list name="Tracks" type="obj">`, find the single existing `MAudioTrackEvent`
   - For track 1: modify its name and Channel ID in place; add Farb if user set a color
   - For tracks 2..N: deep-copy the modified track 1, change name, Channel ID, regenerate unique IDs, set Farb if applicable
   - Append the new track elements as siblings inside the `<list>`
   - Write to disk preserving the encoding declaration

**Per-track XML structure (verified from real files):**

```xml
<obj class="MAudioTrackEvent" ID="{unique_id}">
   <float name="Start" value="0"/>
   <float name="Length" value="{project_length}"/>     <!-- copy from template -->
   <obj class="MListNode" name="Node" ID="{unique_id}">
      <string name="Name" value="{track_label}" wide="true"/>
      <member name="Domain">
         <int name="Type" value="1"/>
         <float name="Period" value="1"/>
      </member>
   </obj>
   <member name="Additional Attributes">
      <int name="Farb" value="{0..15}"/>     <!-- OMIT this line for default color -->
      <int name="Eths" value="-38323736"/>   <!-- copy from template; opaque hash -->
   </member>
   <obj class="MAudioTrack" name="Track Device" ID="{unique_id}">
      <int name="Connection Type" value="1"/>
      <string name="Device Name" value="VST Multitrack"/>
      <int name="Channel ID" value="{1-based_index}"/>
      <member name="DeviceAttributes">
         <member name="Name">
            <string name="String" value="{track_label}" wide="true"/>   <!-- must match outer Name -->
         </member>
         <!-- ... ~150 lines of Volume / Panner / SendFolder / OwnInputBus / IDString boilerplate ... -->
         <!-- Copy verbatim from template's existing track. Do not attempt to synthesize. -->
      </member>
      <int name="Flags" value="0"/>
   </obj>
   <int name="Height" value="42"/>
</obj>
```

**Color storage — fully decoded.**

Per-track color is stored as `<int name="Farb" value="N"/>` inside `<member name="Additional Attributes">`. (German for color — Steinberg is German.) Behavior:

- **Omit `Farb` entirely** → track uses Nuendo Live default (no color override).
- **Include `Farb`** with integer value 0–15 → track uses palette index N from the project's UColorSet.

The 16 default Nuendo Live palette colors (decoded from real file's UColorSet):

| Farb | Hex     | Color           |
|------|---------|-----------------|
| 0    | #E53636 | Red             |
| 1    | #E57636 | Orange          |
| 2    | #E5BA3B | Yellow          |
| 3    | #D5E84C | Yellow-green    |
| 4    | #8DE536 | Light green     |
| 5    | #51D83C | Green           |
| 6    | #35DD5F | Bright green    |
| 7    | #33D697 | Teal            |
| 8    | #30CCCC | Cyan            |
| 9    | #40AAE8 | Light blue      |
| 10   | #5D80EA | Blue            |
| 11   | #796AED | Indigo          |
| 12   | #A056EA | Purple          |
| 13   | #CF44E5 | Magenta         |
| 14   | #E536B9 | Pink            |
| 15   | #E53679 | Hot pink        |

The UColorSet is stored as 32-bit ARGB ints (e.g. `4293211702` = `0xFFE53636`). Don't generate a custom UColorSet — use the project's existing one and just reference its indices.

**Yamaha → Nuendo color mapping (initial table, tune from engineer feedback):**

| Yamaha CL/QL  | Farb | Notes              |
|---------------|------|--------------------|
| Off           | omit | no color override  |
| Red           | 0    |                    |
| Orange        | 1    |                    |
| Yellow        | 2    |                    |
| Green         | 5    |                    |
| Sky Blue      | 8    | cyan               |
| Blue          | 10   |                    |
| Purple        | 12   |                    |
| Pink          | 14   |                    |
| White         | omit | use default        |

Rivage palette is larger (20+ colors); add a separate mapping table when Rivage parser lands.

**Other per-track details that vary across tracks:**

- All `ID` attributes within `MAudioTrackEvent`, `MListNode`, `MAudioTrack` — must be unique within the document. Generate as random 32-bit ints or sequentially from a high base.
- `RuntimeID` values inside DeviceAttributes — also need uniqueness; observed sequence increments by ~7 per track in real files (tracks have multiple sub-RuntimeIDs for SendFolder, Panner, etc.). Random unique ints work.
- `Channel ID` inside MAudioTrack — observed as `1` on all tracks in the diff samples (it's not the input bus assignment; that's elsewhere). Set to `1` and don't worry about it for v1.
- `OwnInputBus → IDString → Name` (e.g. `"Audio 01"`, `"Audio 02"`) — sequential default; Nuendo Live will reassign on import if user routes differently.

**Things NOT to touch in the template:**

- `Devices` block (audio interface routings)
- `WindowLayouts`
- `MMarkerTrackEvent`, `MTempoTrackEvent`, `MSignatureTrackEvent`
- The `Input/Output Channels` MFolderTrack
- `UColorSet`, `PMarkerAttributeSettings`, transport/global state

The exporter only mutates the `Audio` MFolderTrack's track list. Everything else passes through untouched.

**Round-trip test plan:**

1. Generate a `.nlpr` with 8 tracks, varied names, 4 with colors, 4 without
2. Open in real Nuendo Live 3
3. Verify: all track names render correctly, colored tracks have correct color, default-color tracks look like a fresh project's tracks, no errors on load, can record audio onto tracks
4. Save the loaded project, diff against generated file — Nuendo will rewrite IDs and add session state, but track names and Farb values should round-trip cleanly

### Pro Tools (deferred)
- Format: tab-delimited "Import Session Data" `.txt` file or AAF
- **Do not ship without tester access.** Charlie does not have a Pro Tools subscription. Options:
  - Pro Tools Intro (free) — verify it supports session-data import on the free tier
  - 30-day trial during a focused PT sprint
  - Recruit a PT-using beta tester from network
- Mark as v2. Stub out `target_daw='pro_tools'` choice but disable in UI until testable.

## Color Mapping

Build a translation layer between systems:
- Yamaha CL/QL palette → Reaper RGB ints + Nuendo color enum
- Yamaha Rivage palette → same
- User-overridable per-track in the editor

Store the canonical mapping as a constant module (or JSON fixture). Document the mapping decisions; engineers will have opinions about which Reaper red maps to Yamaha red.

## Capacity Warning Behavior

- If `recorder_capacity` is unset → show count only ("47 tracks")
- If set and under → green/neutral count ("47 / 64")
- If set and over → red warning bar ("72 / 64 — 8 over capacity") but **do not block export**. Engineers know their rigs.

## Implementation Phases

Suggested order:

**Phase 1 — Core data model + manual session building**
- Models, migrations, admin
- Session list view, new session form
- Track configuration UI (no CSV import yet — just pull from existing ShowStack console channels)
- Reaper `.RPP` exporter

**Phase 2 — CSV import**
- CL/QL parser (highest-confidence format)
- Rivage parser
- M7CL parser only if CSV path confirmed
- Import flow that creates/updates console channels, then opens session editor

**Phase 3 — Templates**
- MultitrackTemplate model + admin
- Save-as-template from existing session
- Apply-template to new session
- Match existing ShowStack template UX patterns

**Phase 4 — Nuendo Live exporter**
- Charlie provides empty `.nlpr` template + 2-track-with-colors diff sample
- Identify where per-track color is assigned (from the diff)
- Implement template-injection exporter using `lxml`
- Color mapping table (Yamaha → Nuendo palette indices)
- Round-trip test: generate `.nlpr`, open in Nuendo Live 3, verify track names + colors render correctly

**Phase 5 — Polish**
- Default-record seed flags on console channels
- Capacity warning bar
- Drag reorder
- Color picker per track
- Bulk Aux/Matrix/Group inclusion toggles

**Deferred — Pro Tools** (v2, after tester access secured)

## Explicitly Out of Scope

The following were considered and deliberately excluded from v1. Do not build:

- Setlist / song marker timeline generation
- File naming pattern automation for recorded files
- Recording rig (recorder/interface) modeling
- Show notes / recording log per session
- Virtual soundcheck asset tracking
- Post-show delivery automation (cloud links, manifests)
- Real-time DAW control (transport, marker drop)
- Yamaha Console Extension protocol replacement
- Console families other than Yamaha (DiGiCo, A&H, Avid) — separate effort

## Differentiation / Marketing Note

Position this against the native Yamaha-Steinberg integration as:

> *"Works regardless of how audio gets into the recorder — Dante, MADI, USB, anything. Pre-configure your track set once, reuse it across consoles and shows. Reaper and Nuendo Live supported, with the patch awareness ShowStack already has built in."*

The core differentiator is: **ShowStack knows your patch and your labels. The exporter produces a correct multitrack template in seconds, for any DAW, no matter how you're capturing the audio.**

## Testing

- Unit tests for each CSV parser against fixture files (ship real exports as fixtures)
- Unit tests for the feed-source mapping logic (this is where correctness bugs hide)
- Round-trip test for Reaper: generate `.RPP`, parse it back, verify track names/colors/order match input
- Manual test on actual hardware: real CL5 + real Reaper + real RIO → verify labels land on correct tracks
- Manual test for Nuendo Live import once exporter format is settled

## Open Questions to Resolve at Implementation Time

1. Confirm M7CL CSV export path exists before scoping the M7CL parser into Phase 2
2. Confirm Pro Tools Intro free tier supports session data import (informs deferred Phase ordering)
3. Decide whether "color scheme" templates apply by name pattern (regex on channel name) or are manual-only
