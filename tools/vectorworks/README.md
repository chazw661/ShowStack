# Vectorworks cable linker

`showstack_link_cables.py` runs inside Vectorworks. It finds each speaker cable's ends, works out which amp rack and fan-out it connects to, and fills the cable's fields. A worksheet then exports one row per cable to CSV for **Import from VWX** on the PA Cable Schedule.

A cable with an amp rack at one end is a main run. A cable with no rack, starting at a fan-out that a main run feeds, is an extension of that run.

## DRY_RUN

`DRY_RUN = False` at the top of the script is the default, so a run writes the fields on each cable. A field is only overwritten when a match is found, so manual entries survive. Set it to `True` to change nothing and get only the report.

## Report

Every run writes a report to `~/Desktop/showstack_link_report.txt`. `WARNING` lines show what didn't match, such as a cable with no rack or fan-out near its end.

## Field map

| CableObject field | Holds | Worksheet column |
|---|---|---|
| `CableRun_ID` | Label | Cable Label |
| `UserField_1` | Fan-out at the far end, as a ShowStack name | Fan-Out |
| `UserField_2` | Rack name | Destination |
| `UserField_3` | Total length in feet (Length + Spare + Swag) | Length (ft) |
| `Loom_ID` | The main run's label, on extensions | Extension Of |
