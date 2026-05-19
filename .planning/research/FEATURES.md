# Feature Research

**Domain:** Signal flow diagrammer for live audio production (ShowStack v2.2)
**Researched:** 2026-05-19
**Confidence:** HIGH (industry practice, existing model fields verified); MEDIUM (formal notation standards)

---

## 1. What Engineers Actually Draw: Concrete Diagram Examples

Research across ProSoundWeb, AES technical documents, and live-audio production resources identifies five recurring diagram types that A1 engineers produce per show. These are not educational exercises — they are working documents handed to the venue PM, shared with advance crew, and pulled up on a laptop at FOH during load-in. Engineers currently rebuild all five from scratch in Visio or Lucidchart on every gig because no tool knows their gear list.

### Example A: Full System Block Diagram (most common)
Every corporate event and tour produces this document. Typical content:
- Stage rack / I/O device with a split from its outputs: one path to FOH console, one path to monitor world
- FOH console → system processor (DSP) → amplifier rack → L/R main arrays + delay hangs + fills
- Monitor console (or aux sends from FOH) → IEM transmitter packs → performer receivers
- Broadcast / record feed: matrix output from FOH console (or dedicated split) → broadcast desk or recording interface
- Intercom backbone: Arcadia main station or RTS base → beltpacks annotated by position (A1, A2, SM, LD, VD)
- Redundant paths drawn as dashed lines or parallel connectors (backup console on standby, MADI redundancy loop, Dante primary/secondary network)

### Example B: Dante Network Diagram
Engineers managing Dante-networked systems (Yamaha consoles + RIO/RUIO stage boxes + FOH processing) produce a separate topology diagram:
- Each Dante device as a labeled box annotated with Dante channel count
- Network switch(es) as the center hub node
- Dante connections in a visually distinct style (different line weight, color, or dash pattern) from analog
- Primary and secondary (redundant) Dante network shown as two separate switch paths
- IP addresses annotated directly on each node — this is where ShowStack's IP Address Management module intersects

### Example C: Intercom Architecture Diagram
Clear-Com or RTS system topology:
- Arcadia main station → FreeSpeak II base stations (with antenna positions annotated)
- Partyline assignments labeled on connections
- Beltpack grid: each position (A1/A2/SM/LD/VD/STAGE) with channel-key assignments called out
- 4W IFB feed from console into broadcast chain
- This is a direct visualization of what ShowStack's COMM Config module already stores

### Example D: Amp Rack and PA Zone Schematic
Less commonly drawn as a standalone signal-flow diagram but frequently requested by venue PMs and system techs:
- Amplifier outputs → NL4/NL8 cable runs → speaker array destinations (e.g., "KIVA II L," "KS28 Sub L," "KARA Fill R")
- Zone labels matching PA cable schedule
- Draws on PACableSchedule and SpeakerArray data already stored in ShowStack

### Example E: Broadcast / Multiformat Output Map
Used on broadcast shows and hybrid corporate events:
- Console matrix outputs labeled with program name and signal format (AES, analog, Dante AoIP)
- Record split path to multitrack interface labeled with session name
- Feeds from the console to broadcast truck or production mix
- Network segments labeled for broadcast IT team

**Key insight:** Engineers draw all five types per show and report they rebuild them from scratch because no tool knows their gear list. ShowStack already holds the underlying data for Examples A through D.

---

## 2. Industry Notation Conventions

### Signal Direction
Left-to-right flow is the universal convention (mirrors text reading). Sources (mics, instruments) on the left; destinations (speakers, record, broadcast) on the right. Arrows on connectors show direction; bidirectional connections (intercom 2W partyline) use double-headed arrows.

### Symbol Shapes
AVIXA publishes a free "Audio Video and Control Architectural Drawing Symbols" standard (derived from the former InfoComm 2M-2010) that defines floor-plan symbols. For signal-flow block diagrams, practical conventions from working engineers are:

| Shape | Equipment Type |
|-------|---------------|
| Rectangle / rounded rectangle | General-purpose device, processor, console, amp |
| Trapezoid / triangle | Amplifier (electronics convention, inconsistently applied in audio) |
| Circle or speaker icon | Loudspeaker / speaker array |
| Microphone icon | Mic source (rarely used in block diagrams; label usually sufficient) |
| Diamond / split-arrow | Signal splitter |
| Labeled box | I/O device, stage box, patch panel |

In practice, professional live audio engineers use labeled rectangular boxes for almost everything. The label (e.g., "Yamaha Rivage PM10," "L'Acoustics LA12X," "Clear-Com Arcadia") carries more semantic weight than a stylized shape. Generic labeled boxes are universally understood; exotic pictographic icons create ambiguity for crew reading the diagram under show conditions.

**Implication for v2.2:** ShowStack's decision to use smart labeled shapes rather than pictographic icons is correct. Shape type (Console vs. Device vs. SpeakerArray vs. CommBeltPack) plus label is the right combination. Custom rack-unit SVG faceplates are a visual polish item for v2.3+, not a v2.2 requirement.

### Line Styles by Signal Type
No single published standard mandates line styles for all signal types in live-audio block diagrams. AVIXA's standard covers floor-plan symbols, not signal-flow block diagram connector styles. De facto conventions observed across professional production documentation and educational resources:

| Signal Type | Common Visual Convention | Notes |
|-------------|--------------------------|-------|
| Analog audio (XLR/TRS) | Solid thin line | Baseline default |
| AES/EBU digital (AES3) | Solid line, same or heavier weight | Often just labeled "AES" rather than visually distinguished |
| Dante (AoIP / Ethernet) | Dashed line OR distinct color (blue or gold in many templates) | Network paradigm — visually distinct from point-to-point analog is critical |
| MADI | Solid line, distinct from Dante | Typically labeled "MADI" explicitly; coax BNC or fiber |
| Intercom (2W/4W partyline) | Dotted line or colored line | Separate signal domain from audio |
| Redundant / backup path | Dashed or lighter-weight line | Must be visually distinguishable from primary paths |
| Control / network (non-audio) | Dotted or separate layer | Often placed on a separate visual layer if layers are supported |

**Color-coding:** No universal color standard exists for live audio signal-flow diagrams. AVIXA recommends including a legend rather than assuming universal color meaning. Engineers establish per-project conventions. The key requirement is that grayscale-printed versions of the diagram remain legible (diagrams go into printed show files), so color must not be the only differentiator — line style is also required.

**Confidence: MEDIUM.** The conventions above are real and widely practiced, but they are not formally standardized for live-audio block diagrams the way IEC 60617 is for electrical schematics. The v2.2 locked choices (line-style variants: analog / AES / Dante / MADI / intercom) are correctly aligned with de facto industry practice.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features an A1 engineer expects from any diagrammer. Missing these makes the tool feel broken compared to Visio or Lucidchart, which are the current alternatives.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Undo / redo (unlimited depth) | Universal in every diagrammer; losing work to a mis-click is unacceptable | MEDIUM | JointJS core CommandManager plugin handles this; wire before any graph mutations |
| Multi-select (rubber-band + Shift+click) | Engineers move groups of devices (an entire stage rack, an amp world) as a unit | MEDIUM | JointJS core Selection component |
| Copy / paste nodes | Duplicate a device shape with its type and ShowStack record link | MEDIUM | JointJS core Clipboard plugin — verify what's in core vs JointJS+ paid tier; may require manual implementation |
| Delete selected via keyboard (Delete / Backspace) | Universal keyboard shortcut; missing it makes the tool feel unusable | LOW | JointJS paper keyboard event binding |
| Snap-to-grid | Keeps diagrams tidy without manual alignment effort; professional appearance | LOW | JointJS paper `gridSize` option |
| Zoom in / out / zoom-to-fit | Diagrams with 20+ nodes exceed viewport; zoom-to-fit required when reopening a saved diagram | LOW | JointJS paper scale + fitToContent() methods |
| Named diagram list (many per project) | Engineers maintain separate diagrams per signal domain (audio vs Dante vs intercom) and per show day | LOW | Already in v2.2 scope as SignalFlowDiagram model list page |
| Connector line-style selection (Analog / AES / Dante / MADI / Intercom) | Signal type is a first-class concept; a Dante connection and an analog XLR must look different | MEDIUM | In v2.2 locked scope; implement as link property mapped to SVG stroke-dasharray + stroke-color |
| Node label propagates from ShowStack record on rename | Engineers rename gear in ShowStack; the diagram must not go stale | MEDIUM | In v2.2 locked scope via content_type / object_id pattern |
| PNG export | Diagrams go in show files, get emailed to venues, embedded in production decks | LOW | JointJS paper toDataURL() + white background; in v2.2 scope |
| JSON autosave | Browser crash or closed tab must not lose diagram state | LOW | Debounced POST on graph change event; in v2.2 scope |
| Soft-fail render if linked ShowStack record deleted | Console was removed from project after diagram was drawn — shape must degrade, not crash | LOW | In v2.2 scope; render "[deleted]" placeholder label with visual indicator |
| Port-to-port connector snapping | Connectors must snap to defined connection points on shapes, not float on the shape boundary | MEDIUM | JointJS magnet attribute on port SVG elements; required for signal-flow model to be meaningful |
| Midpoint waypoints (vertex drag on connectors) | Engineers need to manually route connectors around overlapping nodes | LOW | JointJS core supports link.vertices() and vertex drag via VertexHandle tool |

### Differentiators (Competitive Advantage)

Features that make ShowStack's diagrammer superior to Visio / Lucidchart for this specific use case. This is where ShowStack wins.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Circuit-label autocomplete from signal_name fields | No other diagrammer knows the engineer's patch; ShowStack-exclusive | MEDIUM | In v2.2 scope; pull from DeviceInput.signal_name, DeviceOutput.signal_name scoped to current project |
| Smart shapes linked to live ShowStack records | Rename gear in ShowStack → diagram updates; click shape → jump to record | HIGH | In v2.2 scope; content_type / object_id pattern already proven in DeviceOutput model |
| Signal-type connector vocabulary matching the domain | Dante, MADI, AES, intercom are first-class connector types — not manual style workarounds | MEDIUM | In v2.2 scope |
| COMM Config visualization (v2.3) | CommBeltPack positions and intercom partyline assignments drawn from live COMM Config data | HIGH | Deferred; requires reading CommConfigPartyline and CommConfigPortAssignment records |
| PA Cable Schedule cross-reference (v2.3) | PACableSchedule zone and destination fields match the amp → speaker path on the diagram | MEDIUM | Deferred; read-only annotation layer from existing PA data |
| IP address annotation on nodes (v2.3) | Show each device's IP from ShowStack IP management as a secondary label | LOW | Data already in Console.primary_ip_address and Device.primary_ip_address |
| PDF export (v2.3) | Diagrams go into printed show files and technical riders; PDF is the format venues and PMs request | MEDIUM | Deferred per PROJECT.md; ReportLab already used for other module PDF exports |
| Bidirectional connector type for intercom | 2W partyline is inherently bidirectional; double-headed arrow is the correct notation | LOW | Implement as connector property: direction = source-to-target / target-to-source / bidirectional |
| Group / ungroup shapes by location (v2.3) | Engineers logically group gear by physical location (stage rack, FOH rack, amp world) | MEDIUM | JointJS supports parent-child grouping via embed; UI wrapper needed |

### Anti-Features (Do NOT Build)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Auto-layout that reorders nodes by hierarchy or connectivity | Looks smart; both Lucidchart and Visio offer it | Signal-flow diagrams encode spatial meaning — stage is physically stage-left, FOH is audience-center-right, monitor world is stage-right. An auto-layout algorithm sorts by connectivity hierarchy and will destroy the engineer's mental model, making the diagram physically wrong. This is the most-cited frustration engineers have with general-purpose diagrammers when used for AV work. | Provide snap-to-grid and alignment guides; let engineers place nodes manually |
| Flowchart or swimlane templates as default | Business diagrammers default to these; looks similar to what engineers want | Swimlanes impose vertical/horizontal lane constraints that conflict with signal-flow left-to-right topology. Swimlanes also carry "process step" semantics that are wrong for a signal chain. | Blank canvas only; optional location-grouping bands in v2.3+ |
| Real-time multi-user collaborative editing | Advertised by every SaaS diagrammer | ShowStack is a single-engineer per project tool. Multi-user introduces merge conflicts on a shared JSON blob with no resolution strategy. The autosave model (last write wins) is correct for a solo A1. | Viewer role sees the diagram read-only; editor role edits. Role-based access is sufficient. |
| Pictographic rack-unit SVG faceplates per equipment model | Looks polished; some AV tools offer this | Custom SVG faceplates per equipment model is a maintenance burden (Yamaha PM10 vs PM7 vs CL5 each needs its own SVG) and adds no operational value — the label is what matters. | Smart labeled shapes with equipment-type color accents; defer custom SVGs to v2.3+ |
| Obstacle-aware auto-routing | Expected in premium diagrammers like draw.io | Already locked out of v2.2 scope per PROJECT.md decision. JointJS core orthogonal routing has no obstacle avoidance; hand-rolling it is significant engineering complexity. | Basic orthogonal routing; engineers drag waypoints manually to reroute around overlapping nodes |
| Version history and diagram snapshots | Engineers might want to track evolution across show days | Adds schema complexity (versioned JSON blobs); no beta feedback supporting this yet | Last-write autosave is correct for v2.2; snapshots deferred to v2.3+ |
| SVG export | Power-user request; keeps diagram editable in Illustrator | Means engineers maintain two copies: one in ShowStack, one in Illustrator. Defeats ShowStack as source of truth. | PNG for embedding; eventual PDF for printed show files |
| Export to Visio .vsdx | Power-user request | Reverse-engineering the OOXML Visio format is significant work with no payoff — the whole point is engineers stop using Visio | PNG + PDF is sufficient for show documentation sharing |

---

## 3. Canvas Interaction Features: Must-Have vs. Nice-to-Have

### MUST-HAVE for v2.2 (missing = unusable tool)

- **Undo / redo:** Engineers make placement and connection mistakes constantly. A diagram tool without undo loses user trust immediately. JointJS CommandManager is available.
- **Multi-select + rubber-band:** Moving a sub-system's devices as a block is fundamental; individual drag-one-at-a-time is too slow.
- **Keyboard delete (Delete / Backspace):** Expected universally; missing it makes the tool feel broken.
- **Zoom in / out / zoom-to-fit:** A full corporate-show diagram has 20–40 nodes across multiple signal domains. Zoom-to-fit is a one-click requirement when reopening a saved diagram.
- **Snap-to-grid:** Without it, engineers spend significant time manually aligning nodes and diagrams look unprofessional. This is table stakes in any technical diagrammer.
- **Port-to-port connector snapping:** Connectors must originate from and terminate at defined connection points on shapes. Floating connectors that connect to arbitrary positions on a shape boundary break the signal-flow model and look wrong to engineers who think in terms of "output of console to input of DSP."
- **Midpoint waypoints (vertex drag):** Engineers need to reroute connectors around nodes. JointJS core supports link.vertices() and vertex drag via VertexHandle. This must ship.

### NICE-TO-HAVE for v2.2 (add if implementation time permits; defer to v2.3 if not)

- **Copy / paste nodes:** Genuinely useful (duplicate a device shape to represent a redundant unit) but can be worked around by dragging a new shape. Prioritize if JointJS Clipboard is in core; defer if it requires JointJS+.
- **Alignment guides (smart snap lines):** Professional feel; speeds up diagram cleanup. JointJS+ Snaplines is the clean path. If building manually, medium effort. Defer unless easy.
- **Right-click context menu:** UX shortcut for delete / connect / properties. Toolbar buttons are sufficient for v2.2.
- **Find in diagram:** Useful on diagrams with 40+ nodes. Low demand on initial release. Defer.
- **Minimap / navigator panel:** Useful for very large diagrams. Not needed at beta scale. Defer.

---

## 4. Connector Behaviors Engineers Expect

### Port-to-port snapping
Connectors originate from and terminate at defined named ports on shapes. Engineers think "output of the console → input of the DSP" — this is port-to-port semantics, not arbitrary-boundary connection. JointJS `magnet` attribute on port SVG elements enables this. Each smart shape must define input and output ports. Unlabeled port positions are acceptable in v2.2; named port labels (e.g., "Dante Out 1") are v2.3+.

### Midpoint waypoints
Engineers need to drag connector segments to route around overlapping shapes. JointJS core supports `link.vertices()` and vertex drag via the `VertexHandle` element tool. This ships in v2.2 as a mandatory feature.

### Connector label placement
Labels on connectors float near the connector midpoint with a white background knockout so the label is readable over grid lines and other connectors. "Near-port" label placement (useful for pin numbers) is a v2.3+ feature. Midpoint floating labels are the dominant pattern in professional signal-flow documentation.

### Bidirectional connectors
Intercom connections (2W partyline) are bidirectional — signal flows both ways. The convention is a double-headed arrow. Implement as a connector property: `direction = 'source-to-target' | 'target-to-source' | 'bidirectional'`. Source-to-target single arrow is the default for all audio signal connectors.

### Multiple connectors between the same two nodes
An engineer may draw both a primary Dante path and an analog backup path between the same stage box and console — two parallel connectors with different line styles. JointJS supports multiple links between the same source/target pair. In v2.2, parallel connectors will visually overlap, which engineers can work around by offsetting waypoints manually. Auto-offset for parallel links is a v2.3 polish item.

### Connector style as a first-class property
Line style and stroke color are the primary semantic carriers for signal type. Each connector must surface a style picker with the five types: Analog, AES/EBU, Dante, MADI, Intercom. This drives both the visual representation and the semantic type label available for future PA Cable Schedule cross-referencing.

---

## 5. Export Behaviors

### PNG export — MUST ship in v2.2
PNG is the correct format for including diagrams in show files, emailing to venues, and embedding in Google Slides or keynote production decks. JointJS `paper.toDataURL()` produces this. White background is required — transparent PNG looks broken when inserted into Word documents and printed show files. In v2.2 locked scope.

### PDF export — defer to v2.3
PDF is the format production managers and venues explicitly request for technical riders and advance documentation. Engineers who assemble show documentation as a PDF packet need the signal-flow diagram embeddable without rasterization. ShowStack already uses ReportLab for other module exports — the pattern is proven. Implementation is medium complexity. Deferred per PROJECT.md decision.

### Print scaling / multi-page — defer to v2.3+
Large corporate show diagrams printed on 11×17 are common. Multi-page layout for very large diagrams is low-priority. Not needed at beta scale.

### SVG export — anti-feature (do not build)
SVG keeps the diagram editable in Illustrator, which creates a secondary copy outside ShowStack. Defeats the source-of-truth model.

---

## 6. Cross-Module Interactions

### Mic Tracker / ConsoleInput — active in v2.2 (circuit-label autocomplete)
`ConsoleInput.source_hardware` and `DeviceInput.signal_name` are the fields that feed connector label autocomplete. When an engineer clicks a connector and starts typing a circuit name, the autocomplete dropdown suggests existing signal names scoped to the current project. This is the primary v2.2 competitive differentiation over Visio/Lucidchart and should be tested end-to-end with realistic project data.

### IP Address Management — additive annotation in v2.3
`Console.primary_ip_address`, `Console.secondary_ip_address`, `Device.primary_ip_address`, and `Device.secondary_ip_address` are already stored per device. In v2.2 the diagram node inherits the record label only. In v2.3, a secondary annotation on the node showing the IP address makes the diagrammer directly useful for Dante network diagrams (Example B above) without any additional data entry.

### COMM Config — visualization layer in v2.3
`CommConfig`, `CommConfigPartyline`, `CommConfigRole`, `CommConfigPortAssignment`, and `CommBeltPack` records store exactly what an intercom architecture diagram needs: device positions, partyline assignments, port-to-beltpack assignments. In v2.2, a CommBeltPack smart shape links to a CommBeltPack record, providing the position label via the `position` FK. In v2.3, a "generate intercom diagram from COMM Config" feature would be a meaningful differentiator — no tool outside ShowStack has this data.

### PA Cable Schedule — cross-reference in v2.3
`PACableSchedule` stores zone label (via `PAZone` FK), destination (e.g., "KIVA II - L"), cable type, and length. These are the same connections that appear in the amp → speaker path of a signal-flow diagram. In v2.2 this is fully independent — the engineer draws the PA path manually. In v2.3, a read-only overlay could annotate diagram connectors between amplifier and speaker-array nodes with the cable type and length from PACableSchedule.

### Multitrack Session Builder — no direct interaction in v2.2 or v2.3
Multitrack sessions link to ConsoleInput channels (individual channel level). Signal-flow diagrams link to Console and Device nodes at the equipment level. No cross-module interaction is needed.

---

## Feature Dependencies

```
Snap-to-grid
    └──enables──> Tidy placement for all other canvas operations

Port-to-port snapping
    └──requires──> Named port definitions on each smart shape SVG
    └──required by──> Circuit-label autocomplete (connector must know its endpoint records)

Connector line-style variants (Analog / AES / Dante / MADI / Intercom)
    └──required by──> Connector direction property (bidirectional only meaningful on Intercom type)
    └──enables──> PA Cable Schedule cross-reference (v2.3) (cable type inferred from connector type)

ShowStack record linking (content_type / object_id on node)
    └──required by──> Label propagation on record rename
    └──required by──> Soft-fail render on record delete
    └──required by──> Circuit-label autocomplete (scope autocomplete to project)
    └──enables──> COMM Config auto-generate (v2.3)
    └──enables──> IP address annotation on node (v2.3)

Circuit-label autocomplete
    └──requires──> Connector line-style variants (filter by signal domain)
    └──requires──> ShowStack record linking (project-scope the signal_name query)

Undo / redo
    └──requires──> CommandManager wired before first graph mutation on canvas init
    └──required by──> Every destructive operation (delete, move, connect)

PNG export
    └──requires──> JointJS paper rendered to DOM with white background
    └──enables──> PDF export path (v2.3) (SVG-to-PDF via ReportLab uses same raster or SVG intermediate)

PDF export (v2.3)
    └──requires──> PNG export working and validated
    └──defers until──> v2.3 per PROJECT.md

COMM Config auto-generate diagram (v2.3)
    └──requires──> CommBeltPack smart shape (v2.2) ← unblocks this path
    └──requires──> CommConfigPartyline and CommConfigPortAssignment readable in diagram view context

PA Cable Schedule visualization (v2.3)
    └──requires──> SpeakerArray + Device / Amplifier smart shapes (v2.2) ← unblocks this path
    └──requires──> Connector line-style variants (v2.2) ← unblocks cable-type inference
```

---

## MVP Definition

### v2.2 Launch With (locked scope — ship all of these)

- [x] Drag-and-drop canvas (JointJS core) — without a canvas there is no feature
- [x] Smart shapes: Console / Device / SpeakerArray / CommBeltPack / Generic — covers all major node types from the existing data model
- [x] ShowStack record linking with label propagation and soft-fail render — core differentiator
- [x] Orthogonal connectors with five line-style variants (Analog / AES / Dante / MADI / Intercom) — core differentiator
- [x] Circuit-label autocomplete from DeviceInput.signal_name / DeviceOutput.signal_name — core differentiator
- [x] Undo / redo — table stakes; no diagrammer survives without this
- [x] Multi-select + rubber-band — table stakes for moving equipment groups
- [x] Keyboard delete — table stakes
- [x] Snap-to-grid — table stakes for professional-looking output
- [x] Port-to-port connector snapping — required for signal-flow model to be meaningful
- [x] Midpoint waypoints (vertex drag) on connectors — required to route around overlapping nodes
- [x] Zoom in / out / zoom-to-fit — required for any diagram of real show complexity
- [x] Bidirectional connector direction property — required for intercom partyline notation
- [x] JSON autosave — no data loss on tab close
- [x] PNG export with white background — required for show-file sharing
- [x] Many diagrams per project (list page + name + delete) — required for separate per-domain diagrams

### Add After v2.2 Validation (v2.3)

- [ ] PDF export — trigger: engineers report they cannot embed PNG in their printed show documentation workflow
- [ ] Group / ungroup nodes by location — trigger: beta testers managing large diagrams request this
- [ ] IP address annotation as secondary node label — trigger: engineers using Dante diagram type request this; low implementation cost, high value
- [ ] COMM Config auto-generate intercom diagram — trigger: COMM Config module is stable and FSII port swap fix is shipped
- [ ] PA Cable Schedule visualization overlay — trigger: beta testers using both modules report manual duplication
- [ ] Alignment guides (smart snap lines) — trigger: feedback that grid alone is insufficient for alignment
- [ ] Mobile viewer at /m/ — trigger: engineers reference diagrams from stage tablets
- [ ] Copy / paste nodes — trigger: if JointJS Clipboard is not in core, defer until v2.3

### Future Consideration (v2.4+)

- [ ] Obstacle-aware auto-routing — only worth building if JointJS+ commercial license is acquired
- [ ] Version history / diagram snapshots — needed if engineers iterate diagrams across multiple show days in the same project
- [ ] Custom rack-unit SVG faceplates per equipment model — visual polish only; not operationally necessary
- [ ] Real-time multi-user view — needed only if ShowStack expands to multi-engineer per project

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Undo / redo | HIGH | MEDIUM | P1 |
| Port-to-port connector snapping | HIGH | MEDIUM | P1 |
| Multi-select + rubber-band | HIGH | LOW | P1 |
| Connector line-style variants | HIGH | MEDIUM | P1 |
| Circuit-label autocomplete | HIGH | MEDIUM | P1 |
| ShowStack record linking | HIGH | HIGH | P1 |
| Snap-to-grid | HIGH | LOW | P1 |
| Zoom to fit | HIGH | LOW | P1 |
| PNG export | HIGH | LOW | P1 |
| JSON autosave | HIGH | LOW | P1 |
| Midpoint waypoints | HIGH | LOW | P1 |
| Bidirectional connector direction | MEDIUM | LOW | P1 |
| Copy / paste nodes | MEDIUM | MEDIUM | P1 (if in core) / P2 (if JointJS+ only) |
| PDF export | HIGH | MEDIUM | P2 (v2.3) |
| IP address node annotation | HIGH | LOW | P2 (v2.3) |
| Group / ungroup | MEDIUM | MEDIUM | P2 (v2.3) |
| COMM Config auto-generate | HIGH | HIGH | P2 (v2.3) |
| PA Cable Schedule overlay | HIGH | MEDIUM | P2 (v2.3) |
| Alignment guides | MEDIUM | MEDIUM | P2 (v2.3) |
| Mobile viewer | MEDIUM | MEDIUM | P2 (v2.3) |
| Version history | LOW | HIGH | P3 (v2.4+) |
| Custom SVG faceplates | LOW | HIGH | P3 (v2.4+) |
| Obstacle-aware auto-routing | MEDIUM | HIGH | P3 (v2.4+) |

**Priority key:** P1 = must have for v2.2 launch; P2 = add after v2.2 validation (v2.3); P3 = future consideration (v2.4+)

---

## Competitor Feature Analysis

| Feature | Lucidchart | Visio (desktop) | X-DRAW (XTEN-AV) | ShowStack v2.2 |
|---------|-----------|-----------------|------------------|----------------|
| AV-specific shape library | Partial (generic + user imports) | Partial (stencil packs) | YES (manufacturer catalogs) | YES (smart shapes from ShowStack equipment types) |
| Live data link to project equipment records | NO | NO | NO | YES (core differentiator) |
| Circuit label autocomplete from patch data | NO | NO | NO | YES (core differentiator) |
| Signal-type connector vocabulary | Manual custom styles | Manual custom styles | YES | YES |
| Auto-layout that reorders nodes | YES (problematic for AV) | YES (problematic for AV) | LIMITED | NO (intentionally not built) |
| PNG export | YES | YES | YES | YES (v2.2) |
| PDF export | YES | YES | YES | v2.3 |
| Multi-user collaboration | YES | Limited | NO | Viewer role read-only |
| Cost | ~$10–15/user/month | ~$15/user/month (365) | Subscription | Included in ShowStack |
| Show-file integration | NO | NO | NO | YES (same project context as console CSV, COMM config, IP plan) |

**Lucidchart pain points specifically cited by AV engineers (ProSoundWeb community, Duke DDMC case study):**
- General-purpose shape library requires creating custom shapes per equipment type — significant per-show setup time
- Auto-layout reorders nodes by hierarchy when applied, destroying the manually-arranged signal-flow topology; engineers report learning to never touch this button after one experience
- No signal-type awareness — a Dante connection and an analog XLR look identical unless the engineer manually styles every individual connector
- No concept of "show project" — diagrams are free-floating documents, not scoped to a production with a gear list

---

## Sources

- AVIXA Audio Video and Control Architectural Drawing Symbols standard: https://www.avixa.org/standards/audio-video-and-control-architectural-drawing-symbols
- AVIXA AV System Documentation overview: https://xchange.avixa.org/posts/av-system-documentation-a-comprehensive-overview
- AVIXA Published Standards list: https://www.avixa.org/standards/current-standards
- ProSoundWeb: Developing System Diagrams as a Useful Road Map: https://www.prosoundweb.com/church-sound-developing-system-diagrams-as-a-useful-road-map/
- ProSoundWeb: Tool to draw audio signal path? (community thread): https://forums.prosoundweb.com/index.php?topic=170268.0
- ProSoundWeb: So You Want To Be A Corporate Events Audio Engineer (Part 4): https://www.prosoundweb.com/putting-it-all-together-so-you-want-to-be-a-corporate-events-audio-engineer-part-4/
- ProSoundWeb: Mastering Signal Flow: https://www.prosoundweb.com/mastering-signal-flow-here-it-comes-there-it-goes/
- Live Sound Explained: The PA System Signal Flow Diagram (essentialdecibels.com): http://essentialdecibels.com/blog/articles/live-sound-explained-3-the-pa-system/
- Signal Flow in Live Sound (mixingmusiclive.com): https://www.mixingmusiclive.com/blog/core-principles-signal-flow
- Audio For Broadcast: Traditional Signal Flow (thebroadcastbridge.com): https://www.thebroadcastbridge.com/content/entry/20193/audio-for-broadcast-traditional-signal-flow
- IEM Signal Flow discussion (Gearspace): https://gearspace.com/board/live-sound/949721-iem-signal-flow.html
- SoundGirls: The Important Art of Documentation in Theatre Sound Design: https://soundgirls.org/the-important-art-of-documentation-in-theatre-sound-design/
- Quick AV Signal Flow with Lucidchart (Duke DDMC): https://sites.duke.edu/ddmc/2019/04/08/quick-av-signal-flow-with-lucidchart/
- Top 5 Free Signal Flow Diagram Software for Audio Designers (XTEN-AV): https://xtenav.com/signal-flow-diagram-software/
- JointJS core vs JointJS+ feature comparison: https://www.jointjs.com/comparison
- JointJS Undo / Redo documentation: https://docs.jointjs.com/learn/features/undo-redo/
- JointJS Features overview: https://docs.jointjs.com/learn/features/
- How Signal Flow Diagrams Integrate with Rack and Wiring Diagrams: https://avsyncstudio.wordpress.com/2026/02/27/how-signal-flow-diagrams-integrate-with-rack-and-wiring-diagrams/
- Signal Flow Diagrams Explained (avsyncstudio.wordpress.com): https://avsyncstudio.wordpress.com/2025/04/30/signal-flow-diagrams-explained-a-beginners-guide-with-software-examples/
- Patchify — Professional Cable Diagram and Signal Flow Tool: https://patchify.app/
- ShowStack planner/models.py — DeviceInput.signal_name, DeviceOutput.signal_name, Console, Device, SpeakerArray, CommBeltPack fields verified directly from codebase

---

*Feature research for: ShowStack v2.2 Signal Flow Diagrammer*
*Researched: 2026-05-19*
