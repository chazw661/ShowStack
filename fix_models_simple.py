from planner.models import *

# Fix the main parent items with clean prefixes
Console._meta.verbose_name_plural = "A01 🎛️ Consoles"
Device._meta.verbose_name_plural = "A02 🔌 I/O Devices"
ShowDay._meta.verbose_name_plural = "B01 📅 Show Days"
MicSession._meta.verbose_name_plural = "B02   ├─ Mic Sessions"
MicAssignment._meta.verbose_name_plural = "B03   ├─ Mic Assignments"
MicShowInfo._meta.verbose_name_plural = "B04   └─ Mic Show Information"
CommBeltPack._meta.verbose_name_plural = "C01 📡 Comm Belt Packs"
CommChannel._meta.verbose_name_plural = "C02   └─ Comm Channels"
CommPosition._meta.verbose_name_plural = "C03   └─ Comm Positions"
AmplifierAssignment._meta.verbose_name_plural = "D01 ⚡ Amplifier Assignments"
AmplifierProfile._meta.verbose_name_plural = "D02   └─ Amplifier Profiles"
AmpModel._meta.verbose_name_plural = "D03   └─ Amp Model Templates"
SystemProcessor._meta.verbose_name_plural = "E01 ⚙️ System Processors"
PACableSchedule._meta.verbose_name_plural = "F01 🔌 PA Cable Entries"
PAZone._meta.verbose_name_plural = "F02   └─ PA Zones"
SoundvisionPrediction._meta.verbose_name_plural = "G01 🎵 Soundvision Predictions"
SpeakerArray._meta.verbose_name_plural = "G02   └─ Speaker Arrays"
SpeakerCabinet._meta.verbose_name_plural = "G03   └─ Speaker Cabinets"
PowerDistributionPlan._meta.verbose_name_plural = "H01 ⚡ Power Distribution Plans"
AudioChecklist._meta.verbose_name_plural = "I01 ✅ Audio Checklist"

print("Fixed in memory! Restart your server to see changes.")
exit()