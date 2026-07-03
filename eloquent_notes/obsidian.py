import os
from datetime import datetime

def save_note(vault_path, folder, daily_notes, text, template_standalone, template_daily_new, template_daily_append):
    expanded_vault = os.path.expanduser(vault_path)
    target_dir = os.path.join(expanded_vault, folder)
    os.makedirs(target_dir, exist_ok=True)
    
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    
    if daily_notes:
        note_path = os.path.join(target_dir, f"{date_str}.md")
        if not os.path.exists(note_path):
            content = template_daily_new.format(date=date_str, time=time_str, text=text)
            mode = "w"
        else:
            content = template_daily_append.format(date=date_str, time=time_str, text=text)
            mode = "a"
    else:
        timestamp = now.strftime("%Y-%m-%d-%H%M%S")
        note_path = os.path.join(target_dir, f"Dictation-{timestamp}.md")
        content = template_standalone.format(date=date_str, time=time_str, text=text)
        mode = "w"
        
    with open(note_path, mode, encoding="utf-8") as f:
        f.write(content)
    return note_path
