#!/usr/bin/env python3
"""
Script to replace print statements with logging calls in dictator.py
"""
import re

def classify_log_level(line):
    """Determine appropriate log level based on content"""
    lower = line.lower()

    # Error/warning indicators
    if '🚨' in line or 'FATAL' in line or 'error' in lower or 'failed' in lower:
        return 'error'
    if '⚠️' in line or 'warning' in lower or 'could not' in lower:
        return 'warning'

    # Info indicators (important state changes)
    if any(word in line for word in ['✅', 'Starting', 'Stopping', 'Applied', 'Loaded', 'Saved']):
        return 'info'

    # Everything else is debug
    return 'debug'

def remove_emoji(text):
    """Remove common debug emoji from text"""
    emoji_map = {
        '🔥': '',
        '🚨': '',
        '🚀': '',
        '📝': '',
        '✅': '',
        '🎯': '',
        '🎨': '',
        '🔄': '',
        '⚠️': '',
        '📱': '',
        '🎤': '',
    }

    for emoji, replacement in emoji_map.items():
        text = text.replace(emoji, replacement)

    # Remove leading/trailing spaces from the message
    # Handle f-strings
    if 'f"' in text or "f'" in text:
        # Extract the f-string content
        match = re.search(r'f(["\'])(.*?)\1', text)
        if match:
            quote = match.group(1)
            content = match.group(2).strip()
            return f'f{quote}{content}{quote}'

    return text.strip()

def replace_print_with_log(line):
    """Replace print() with appropriate log call"""
    # Skip if already using log
    if 'log.' in line or 'logger.' in line:
        return line

    # Skip comments
    if line.strip().startswith('#'):
        return line

    # Find print statements
    if 'print(' not in line:
        return line

    # Determine log level
    level = classify_log_level(line)

    # Extract the print content
    match = re.search(r'print\((.*)\)', line, re.DOTALL)
    if not match:
        return line

    content = match.group(1)

    # Remove emoji from content
    cleaned_content = remove_emoji(content)

    # Get indentation
    indent = line[:len(line) - len(line.lstrip())]

    # Build new line with logging
    new_line = f'{indent}log.{level}({cleaned_content})\n'

    return new_line

def process_file(filepath):
    """Process the file and replace print statements"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Process each line
    new_lines = []
    for line in lines:
        new_line = replace_print_with_log(line)
        new_lines.append(new_line)

    # Write back
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    print(f"✅ Processed {filepath}")
    print(f"   Total lines: {len(lines)}")

if __name__ == '__main__':
    import glob

    # Process all Python files in src/
    src_files = glob.glob('src/**/*.py', recursive=True)
    src_files = [f for f in src_files if '__pycache__' not in f]

    for filepath in src_files:
        print(f"\n Processing {filepath}...")
        process_file(filepath)
