import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy.interpolate import PchipInterpolator

# =====================================================
# NORMALIZED LIGHT CURVE VS TIME
# =====================================================
def plot_relative_flux_time(asteroid_name, time_vector, flux_vector):
    flux_vector = np.array(flux_vector)
    # Normalization
    F_ref = np.mean(flux_vector)
    flux_rel = flux_vector / F_ref
    print("Relative flux range:",np.min(flux_rel),"-",np.max(flux_rel))
    
    # Convert time for interpolation
    time_num = mdates.date2num(time_vector)
    time_smooth = np.linspace(time_num.min(),time_num.max(),300)
    
    # interpolation
    pchip = PchipInterpolator(time_num,flux_rel)
    flux_smooth = pchip(time_smooth)
    
    # Plot
    plt.figure(figsize=(10,5))
    plt.plot(mdates.num2date(time_smooth),flux_smooth,label="Interpolated relative flux",linewidth=2)
    plt.scatter(time_vector, flux_rel,label="Render points")
    
    # --- SCALA VERTICALE FISSA ---
    plt.ylim(0.8, 1.2)
    
    plt.xlabel("UTC time")
    plt.ylabel("Relative flux F/Fmean")
    plt.title(f"{asteroid_name} - Relative Flux Light Curve")
    plt.grid(True)
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()

# =====================================================
# LIGHT CURVE VS ROTATION PHASE (CONFRONTO DAMIT)
# =====================================================
def plot_lightcurves(asteroid_name, time_vector, flux_vector, damit_path):
    # ===============================
    # CONVERT TO ARRAY & NORMALIZE
    # ===============================
    flux_vector = np.array(flux_vector)
    F_ref = np.mean(flux_vector)
    flux_rel = flux_vector / F_ref
    print("Relative flux range:",np.min(flux_rel),"-",np.max(flux_rel))

    # ===============================
    # TIME -> ROTATION PHASE
    # ===============================
    t0 = time_vector[0]
    t_end = time_vector[-1]
    rotation_phase = np.array([(t-t0).total_seconds() / (t_end-t0).total_seconds() for t in time_vector])

    # ===============================
    # PCHIP INTERPOLATION
    # ===============================
    rotation_phase_smooth = np.linspace(0, 1, 300)
    pchip = PchipInterpolator(rotation_phase, flux_rel)
    flux_phase_smooth = pchip(rotation_phase_smooth)

    # ===============================
    # LOAD DAMIT
    # ===============================
    damit_data = np.loadtxt(damit_path)
    damit_phase = damit_data[:,0]
    damit_flux = damit_data[:,1]

    # ===============================
    # PLOT
    # ===============================
    plt.figure(figsize=(10,5))
    plt.plot(rotation_phase_smooth, flux_phase_smooth, label="Blender model", linewidth=2)
    plt.scatter(rotation_phase, flux_rel, label="Blender renders")
    plt.plot(damit_phase, damit_flux, "--", label="DAMIT reference", linewidth=2)
    
    plt.xlabel("Rotation phase")
    plt.ylabel("Relative flux F/Fmean")
    plt.xlim(0, 1)
    
    # --- SCALA VERTICALE FISSA ---
    plt.ylim(0.8, 1.2)
    
    plt.title(f"{asteroid_name} - Light Curve Comparison")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.show()