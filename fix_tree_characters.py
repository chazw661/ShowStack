#!/usr/bin/env python
"""
fix_tree_characters.py
Fixes the specific tree characters for proper visual hierarchy
"""

import re

# Read the models.py file
with open('planner/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix specific tree characters:
# 1. Comm Positions (first one) should be ├─ (T-type) since it's in the middle
# 2. Amp Model Templates should be ├─ (T-type) since it's in the middle  
# 3. Amplifier Assignments should be └─ (L-type) since it's at the end

replacements = [
    # Fix first Comm Positions to T-type (middle item)
    (r'verbose_name_plural = "    └─ Comm Positions"', 
     'verbose_name_plural = "    ├─ Comm Positions"'),
    
    # Fix Amp Model Templates to T-type (middle item)
    (r'verbose_name_plural = "    └─ Amp Model Templates"',
     'verbose_name_plural = "    ├─ Amp Model Templates"'),
    
    # Fix Amplifier Assignments to L-type (last item)
    (r'verbose_name_plural = "    ├─ Amplifier Assignments"',
     'verbose_name_plural = "    └─ Amplifier Assignments"'),
]

# Apply the specific fixes
for old_text, new_text in replacements:
    if old_text in content:
        content = content.replace(old_text, new_text)
        print(f"✅ Fixed: {new_text.split('=')[1].strip()}")
    else:
        # Try with regex in case of whitespace differences
        pattern = old_text.replace('    ', r'\s*')
        content = re.sub(pattern, new_text, content)

# Save the updated file
with open('planner/models.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("\n✅ Fixed tree characters!")
print("\nNext steps:")
print("1. Run: python manage.py makemigrations")
print("2. Run: python manage.py migrate") 
print("3. Restart server: python manage.py runserver")
print("4. Clear browser cache")