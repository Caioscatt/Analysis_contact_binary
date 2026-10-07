import subprocess
import sys
import os
import glob

# ============================================================
# INSTALLAZIONE LIBRERIE PYTHON NECESSARIE
# ============================================================
# Qui inseriamo tutte le librerie esterne usate nei tuoi codici
REQUIRED_PACKAGES = [
    "numpy",         # Per il calcolo numerico
    "astropy",       # Per la gestione del tempo e delle coordinate astronomiche (Time, ecc.)
    "matplotlib",    # Per la creazione dei plot e delle lightcurve
    "scipy",         # Per l'interpolazione (PchipInterpolator, ecc.)
    "tifffile",      # Per la gestione dei file TIFF renderizzati
    "astroquery"
]

def install_python_libraries():
    print("=" * 60)
    print(" CHECKING PYTHON LIBRARIES...")
    print("=" * 60)
    
    for package in REQUIRED_PACKAGES:
        try:
            __import__(package)
            print(f" [OK] Library '{package}' is already installed.")
        except ImportError:
            print(f" [INSTALLING] Library '{package}' not found. Installing via pip...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f" [SUCCESS] '{package}' installed successfully.")
    print("-" * 60)

# ============================================================
# CONTROLLO PRESENZA BLENDER
# ============================================================
def check_blender_presence():
    print("\n" + "=" * 60)
    print(" CHECKING BLENDER INSTALLATION...")
    print("=" * 60)
    
    common_paths = [
        r"C:\Program Files\Blender Foundation\**\blender.exe",
        r"C:\Program Files (x86)\Blender Foundation\**\blender.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Blender Foundation\**\blender.exe")
    ]
    
    found_paths = []
    for pattern in common_paths:
        matches = glob.glob(pattern, recursive=True)
        found_paths.extend(matches)
        
    if found_paths:
        blender_exe = found_paths[-1]
        print(f" [OK] Blender found at: {blender_exe}")
        return True
    else:
        print("\n" + "!" * 60)
        print(" [WARNING] Blender executable not found on your system!")
        print(" Please make sure Blender is installed or specify its path")
        print(" correctly in your configuration.json file.")
        print("!" * 60)
        return False

# ============================================================
# MAIN EXECUTION
# ============================================================
if __name__ == "__main__":
    print("STARTING ENVIRONMENT SETUP...")
    
    # 1. Installa/Verifica tutte le librerie esterne
    install_python_libraries()
    
    # 2. Controlla Blender e avvisa se manca
    check_blender_presence()
    
    print("\n" + "=" * 60)
    print(" ENVIRONMENT SETUP COMPLETED!")
    print("=" * 60)