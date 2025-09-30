#!/usr/bin/env python
"""
fix_tree_structure.py
Fixes the tree structure to properly group Power Distribution items
"""

import re

# Read the models.py file
with open('planner/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Define replacements with correct tree structure
replacements = [
    # Main items (no prefix)
    (r'verbose_name_plural = "[^"]*Consoles[^"]*"', 'verbose_name_plural = "Consoles"'),
    (r'verbose_name_plural = "[^"]*I/O Devices[^"]*"', 'verbose_name_plural = "I/O Devices"'),
    
    # Show Days group
    (r'verbose_name_plural = "[^"]*Show Days[^"]*"', 'verbose_name_plural = "Show Days"'),
    (r'verbose_name_plural = "[^"]*Mic Sessions[^"]*"', 'verbose_name_plural = "    ├─ Mic Sessions"'),
    (r'verbose_name_plural = "[^"]*Mic Assignments[^"]*"', 'verbose_name_plural = "    ├─ Mic Assignments"'),
    (r'verbose_name_plural = "[^"]*Mic Show Information[^"]*"', 'verbose_name_plural = "    └─ Mic Show Information"'),
    
    # Comm group
    (r'verbose_name_plural = "[^"]*Comm Belt Packs[^"]*"', 'verbose_name_plural = "Comm Belt Packs"'),
    (r'verbose_name_plural = "[^"]*Comm Locations[^"]*"', 'verbose_name_plural = "    ├─ Comm Locations"'),
    (r'verbose_name_plural = "[^"]*Comm Positions[^"]*"', 'verbose_name_plural = "    └─ Comm Positions"'),
    (r'verbose_name_plural = "[^"]*Comm Channels[^"]*"', 'verbose_name_plural = "    └─ Comm Channels"'),
    
    # System Processors (standalone)
    (r'verbose_name_plural = "[^"]*System Processors[^"]*"', 'verbose_name_plural = "System Processors"'),
    
    # PA Cable group  
    (r'verbose_name_plural = "[^"]*PA Cable Entries[^"]*"', 'verbose_name_plural = "PA Cable Entries"'),
    (r'verbose_name_plural = "[^"]*PA Fan Outs[^"]*"', 'verbose_name_plural = "    └─ PA Fan Outs"'),
    
    # PA Zones (standalone for now - could be moved)
    (r'verbose_name_plural = "[^"]*PA Zones[^"]*"', 'verbose_name_plural = "PA Zones"'),
    
    # Soundvision group
    (r'verbose_name_plural = "[^"]*Soundvision Predictions[^"]*"', 'verbose_name_plural = "Soundvision Predictions"'),
    (r'verbose_name_plural = "[^"]*Speaker Arrays[^"]*"', 'verbose_name_plural = "    ├─ Speaker Arrays"'),
    (r'verbose_name_plural = "[^"]*Speaker Cabinets[^"]*"', 'verbose_name_plural = "    └─ Speaker Cabinets"'),
    
    # Power Distribution group - ALL TOGETHER
    (r'verbose_name_plural = "[^"]*Power Distribution Plans[^"]*"', 'verbose_name_plural = "Power Distribution Plans"'),
    (r'verbose_name_plural = "[^"]*Amplifiers in Power Plan[^"]*"', 'verbose_name_plural = "    ├─ Amplifiers in Power Plan"'),
    (r'verbose_name_plural = "[^"]*Amplifier Assignments[^"]*"', 'verbose_name_plural = "    ├─ Amplifier Assignments"'),
    (r'verbose_name_plural = "[^"]*Amplifier Profiles[^"]*"', 'verbose_name_plural = "    ├─ Amplifier Profiles"'),
    (r'verbose_name_plural = "[^"]*Amp Model Templates[^"]*"', 'verbose_name_plural = "    └─ Amp Model Templates"'),
    
    # Audio Checklist (standalone)
    (r'verbose_name_plural = "[^"]*Audio Checklists[^"]*"', 'verbose_name_plural = "Audio Checklists"'),
]

# Apply all replacements
for pattern, replacement in replacements:
    content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)

# Save the updated file
with open('planner/models.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Fixed tree structure in models.py!")
print("\nNext steps:")
print("1. Update planner/admin_ordering.py with the fixed version")
print("2. Run: python manage.py makemigrations")
print("3. Run: python manage.py migrate") 
print("4. Restart server: python manage.py runserver")
print("5. Clear browser cache and check admin")