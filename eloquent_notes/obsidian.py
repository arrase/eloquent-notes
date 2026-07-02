import os
from datetime import datetime

def save_note(vault_path, folder, daily_notes, text):
    expanded_vault = os.path.expanduser(vault_path)
    target_dir = os.path.join(expanded_vault, folder)
    os.makedirs(target_dir, exist_ok=True)
    
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    
    if daily_notes:
        note_path = os.path.join(target_dir, f"{date_str}.md")
        entry = f"\n\n## Dictation - {time_str}\n{text}"
        if not os.path.exists(note_path):
            content = f"---\ntags: [dictation, unprocessed]\ndate: {date_str}\n---\n# Dictations of {date_str}{entry}"
            mode = "w"
        else:
            content = entry
            mode = "a"
    else:
        timestamp = now.strftime("%Y-%m-%d-%H%M%S")
        note_path = os.path.join(target_dir, f"Dictation-{timestamp}.md")
        content = f"---\ntags: [dictation, unprocessed]\ndate: {date_str} {time_str}\n---\n# Dictation - {date_str} {time_str}\n\n{text}"
        mode = "w"
        
    with open(note_path, mode, encoding="utf-8") as f:
        f.write(content)
    return note_path
