import os
import glob

def find_blender():
    print("Cerco Blender sul computer...")
    
    # Percorsi comuni in cui Blender viene installato su Windows
    common_paths = [
        r"C:\Program Files\Blender Foundation\**\blender.exe",
        r"C:\Program Files (x86)\Blender Foundation\**\blender.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Blender Foundation\**\blender.exe")
    ]
    
    found_paths = []
    for pattern in common_paths:
        # glob.glob cerca usando i caratteri jolly (**) per trovare qualsiasi versione
        matches = glob.glob(pattern, recursive=True)
        found_paths.extend(matches)
        
    if found_paths:
        print("\nTrovato! Ecco i percorsi di Blender disponibili:")
        for i, path in enumerate(found_paths):
            # Sostituisce i backslash singoli con i doppi backslash per il JSON
            json_ready_path = path.replace("\\", "\\\\")
            print(f"\n{i+1}. Percorso standard:")
            print(path)
            print(f"   Copia questo nel JSON (con le doppie barre):")
            print(f'   "blender_path": "{json_ready_path}"')
    else:
        print("\nNessun Blender trovato nei percorsi standard.")
        print("Se l'hai installato in un percorso personalizzato, dovrai cercarlo manualmente.")

if __name__ == "__main__":
    find_blender()