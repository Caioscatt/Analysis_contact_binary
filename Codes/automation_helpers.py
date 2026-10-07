import os
import glob
import csv
import time
import json
import sys
import shutil
import subprocess
from datetime import datetime, timedelta
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from Rot_matrix import euler_to_Rbc
from Astro_tools import compute_W, utc_to_julian
from Magnitude_calculations import compute_flux

# =====================================================================
# GESTIONE DEI PERCORSI (Separazione tra Script e Root del Progetto)
# =====================================================================
script_dir = os.path.dirname(os.path.abspath(__file__))        # Cartella Codes
project_root = os.path.dirname(script_dir)                    # Cartella principale ANALYSIS_CONTACT_Binary

PARAM_MAP = {
    "secondary_radius": "secondary_radius",
    "radius": "secondary_radius",
    "sun_ra": "sun_ra",
    "sun_dec": "sun_dec",
    "earth_ra": "earth_ra",
    "earth_dec": "earth_dec"
}

def normalize_param_name(name):
    """Maps JSON parameter synonyms to internal keys."""
    n = str(name).lower().strip()
    return PARAM_MAP.get(n, n)

def fmt_num(val, dec=4):
    """Formats a number for Italian Excel (comma as decimal separator)."""
    try:
        s = f"{float(val):.{dec}f}"
        return s.replace('.', ',')
    except (ValueError, TypeError):
        return str(val)

def write_csv_with_retry(filepath, rows, headers=None, delimiter=';'):
    """Writes rows to a CSV handling potential locks by Excel."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    file_exists = os.path.exists(filepath) and os.path.getsize(filepath) > 0
    
    for attempt in range(5):
        try:
            mode = "a" if file_exists else "w"
            with open(filepath, mode, newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=delimiter)
                if not file_exists and headers:
                    writer.writerow(headers)
                for r in rows:
                    writer.writerow(r)
                f.flush()
                os.fsync(f.fileno())
            return True
        except PermissionError:
            print(f"[WARNING]: File locked ({filepath}). Attempt {attempt+1}/5, waiting...")
            time.sleep(1)
    print(f"[CRITICAL ERROR]: Unable to write to {filepath}. Please close Excel!")
    return False

def find_blender_executable(blender_path_cfg):
    """Searches for the Blender executable if not explicitly specified."""
    if blender_path_cfg and os.path.exists(blender_path_cfg):
        return blender_path_cfg
    common_paths = [
        r"C:\Program Files\Blender Foundation\**\blender.exe",
        r"C:\Program Files (x86)\Blender Foundation\**\blender.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Blender Foundation\**\blender.exe")
    ]
    found_paths = []
    for pattern in common_paths:
        found_paths.extend(glob.glob(pattern, recursive=True))
        
    if found_paths:
        return found_paths[-1]
    raise FileNotFoundError("Unable to find Blender automatically. Please specify 'blender_path' in the configuration file.")

def build_single_analysis_process(config, base_secondary_radius, base_sun_ra, base_sun_dec, base_earth_ra=0.0, base_earth_dec=0.0):
    """Builds runs by applying the correct override from sweep parameters for binary systems."""
    sweep_cfg = config.get("sweep_config", {})
    
    default_run_base = {
        "secondary_radius": float(base_secondary_radius),
        "sun_ra": float(base_sun_ra),
        "sun_dec": float(base_sun_dec),
        "earth_ra": float(base_earth_ra),
        "earth_dec": float(base_earth_dec)
    }

    if sweep_cfg and sweep_cfg.get("enabled", False):
        p1 = sweep_cfg.get("param1", {})
        
        def get_vals(p_dict, default_val):
            start_val = p_dict.get("start")
            start = float(start_val) if start_val is not None else float(default_val)
            step_val = p_dict.get("step")
            step = float(step_val) if step_val is not None else 1.0
            count_val = p_dict.get("count")
            count = int(count_val) if count_val is not None else 3
            return [start + i * step for i in range(count)]

        p1_name = normalize_param_name(p1.get("name", "secondary_radius"))
        p1_vals = get_vals(p1, default_run_base.get(p1_name, 5.0))

        runs = []
        for v1 in p1_vals:
            run = default_run_base.copy()
            run[p1_name] = v1
            runs.append(run)
        return {
            "name": f"CUSTOM 1D ({p1_name.upper()})",
            "runs": runs, "is_2d": False, "p1_name": p1_name, "p2_name": None
        }

    runs = [default_run_base.copy()]
    return {"name": "SINGLE BASELINE RUN", "runs": runs, "is_2d": False, "p1_name": "single", "p2_name": None}

def generate_simulation_rows(start_date, finish_date, timestep, W0, P_hours, 
                            earth_ra, earth_dec, s_ra, s_dec, spin_ra, spin_dec):
    """Generates time table rows using Astro_tools (UTC/JD and compute_W) and Rot_matrix."""
    rows = []
    curr_t = start_date
    
    JD0 = 2451545.0
    period_days = P_hours / 24.0
    rotation_rate = 360.0 / period_days

    while curr_t <= finish_date:
        jd_curr = utc_to_julian(curr_t)
        W_curr = compute_W(jd_curr, W0, rotation_rate, JD0) % 360.0
        Rbc_obj = euler_to_Rbc(spin_ra, spin_dec, W_curr)
        qx, qy, qz, qw = Rbc_obj.as_quat()

        rows.append({
            "date": curr_t.strftime("%Y-%m-%d_%H-%M-%S"),
            "W": W_curr,
            "earth_ra": earth_ra, 
            "earth_dec": earth_dec,
            "sun_ra": s_ra, 
            "sun_dec": s_dec, 
            "sun_distance": 1.0,
            "qw": float(qw),
            "qx": float(qx),
            "qy": float(qy),
            "qz": float(qz)
        })
        curr_t += timedelta(minutes=timestep)
        
    return rows

def run_blender_binary_pipeline(blender_path, proj_root, scr_dir, asteroid_name, secondary_radius, camera_orthoscale, spin_ra, spin_dec):
    """Esegue la generazione del contatto binario e configura la scena tramite Setup_blender."""
    cache_dir = os.path.join(proj_root, "cache")
    blend_file = os.path.join(cache_dir, "object.blend")
    
    binary_script = os.path.join(scr_dir, "Script_contact.py")
    setup_script = os.path.join(scr_dir, "Setup_blender.py")
    render_script = os.path.join(scr_dir, "Rendering2.py")
    asteroid_rel_file = os.path.join("Shapes", f"{asteroid_name}.obj")

    subprocess.run([blender_path, "-b", "-P", binary_script, "--", asteroid_name, proj_root, str(secondary_radius)], check=True)
    subprocess.run([blender_path, "-b", "-P", setup_script, "--", asteroid_name, asteroid_rel_file, str(camera_orthoscale), proj_root], check=True)
    subprocess.run([blender_path, "-b", blend_file, "-P", render_script, "--", asteroid_name, str(spin_ra), str(spin_dec), proj_root], check=True)

def run_blender_ellipsoid_pipeline(blender_path, proj_root, scr_dir, camera_orthoscale, spin_ra, spin_dec):
    """Esegue Setup_blender direttamente passando ellipsoid.obj, sovrascrivendo la scena pulitamente."""
    cache_dir = os.path.join(proj_root, "cache")
    blend_file = os.path.join(cache_dir, "object.blend")
    
    setup_script = os.path.join(scr_dir, "Setup_blender.py")
    render_script = os.path.join(scr_dir, "Rendering2.py")
    
    ellipsoid_name = "ellipsoid"
    ellipsoid_rel_file = os.path.join("Shapes", f"{ellipsoid_name}.obj")

    subprocess.run([blender_path, "-b", "-P", setup_script, "--", ellipsoid_name, ellipsoid_rel_file, str(camera_orthoscale), proj_root], check=True)
    subprocess.run([blender_path, "-b", blend_file, "-P", render_script, "--", ellipsoid_name, str(spin_ra), str(spin_dec), proj_root], check=True)

def get_uncratered_sphere_flux(blender_path, proj_root, scr_dir, asteroid_name, camera_orthoscale, 
                                spin_ra, spin_dec, render_folder, simulation_rows, compute_flux_fn):
    """Generates the reference render for R = 0 (single base sphere) and calculates base flux."""
    print(f"\n[BASELINE R=0]: Running pure sphere render for F_base calculation...")
    
    run_blender_binary_pipeline(
        blender_path=blender_path,
        proj_root=proj_root,
        scr_dir=scr_dir,
        asteroid_name=asteroid_name,
        secondary_radius=0.0,
        camera_orthoscale=camera_orthoscale,
        spin_ra=spin_ra,
        spin_dec=spin_dec
    )
    
    f_base_list = []
    for row in simulation_rows:
        image_path = os.path.join(render_folder, f"{asteroid_name}_{row['date']}.tiff")
        if os.path.exists(image_path):
            res = compute_flux_fn(image_path)
            flux = res[0] if isinstance(res, (tuple, list)) else res
            f_base_list.append(flux)
            
    if not f_base_list:
        raise FileNotFoundError(f"[CRITICAL ERROR]: Unable to find baseline renders in {render_folder}")

    f_base = float(np.mean(f_base_list))
    print(f"[BASELINE SUCCESS]: Base Pure Sphere Flux/Magnitude = {f_base:.4f}\n")
    return f_base

def compute_lightcurve_metrics(simulation_rows, render_folder, asteroid_name, compute_flux_fn, P_hours, base_flux):
    """Normalizes the lightcurve and computes metrics."""
    if base_flux is None:
        raise ValueError("[PHYSICAL ERROR]: A valid base_flux is required for normalization.")

    f_vector, t_vector = [], []
    for row in simulation_rows:
        image_path = os.path.join(render_folder, f"{asteroid_name}_{row['date']}.tiff")
        res = compute_flux_fn(image_path)
        flux = res[0] if isinstance(res, (tuple, list)) else res
        f_vector.append(flux)
        t_vector.append(datetime.strptime(row["date"], "%Y-%m-%d_%H-%M-%S"))

    raw_arr = np.array(f_vector, dtype=float)

    if np.all(raw_arr > 0) and np.mean(raw_arr) > 1.0:
        rel_flux = raw_arr / float(base_flux)
    else:
        rel_flux = 10.0 ** (-0.4 * (raw_arr - float(base_flux)))

    min_rel_flux = float(np.min(rel_flux))
    max_rel_flux = float(np.max(rel_flux))
    
    dev_from_base = np.abs(rel_flux - 1.0)
    extreme_idx = int(np.argmax(dev_from_base))
    max_abs_dev_percent = float(dev_from_base[extreme_idx]) * 100.0
    
    peak_to_peak = max_rel_flux - min_rel_flux
    amplitude_percent = peak_to_peak * 100.0

    t_seconds = np.array([(t - t_vector[0]).total_seconds() for t in t_vector])
    period_seconds = P_hours * 3600.0
    rotation_phase = (t_seconds / period_seconds) % 1.0
    if len(rotation_phase) > 1 and rotation_phase[-1] == 0.0 and t_seconds[-1] > 0:
        rotation_phase[-1] = 1.0

    return {
        "min_rel_flux": min_rel_flux, 
        "max_rel_flux": max_rel_flux,
        "peak_to_peak": peak_to_peak, 
        "amplitude_percent": amplitude_percent,
        "max_abs_dev_percent": max_abs_dev_percent, 
        "extreme_idx": extreme_idx,
        "t_seconds": t_seconds, 
        "rotation_phase": rotation_phase, 
        "rel_flux": rel_flux,
        "raw_flux": raw_arr,
        "base_flux": base_flux
    }

def plot_single_lightcurve(rotation_phase, rel_flux, extreme_idx, max_abs_dev_percent, min_rel_flux, max_rel_flux, title, output_base_path):
    """Generates and saves the plot for a single lightcurve."""
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(rotation_phase, rel_flux, color='navy', linewidth=2.0, label="Relative Flux (F/F_sphere)")
    ax.plot(rotation_phase[extreme_idx], rel_flux[extreme_idx], 'ro', markersize=6, label=f"Max Dev ({rel_flux[extreme_idx]:.4f}, |Δ|={max_abs_dev_percent:.2f}%)")
    ax.axhline(1.0, color='gray', linestyle=':', alpha=0.7, label="Pure Sphere Baseline (1.0)")
    ax.set_title(title)
    ax.set_xlabel("Rotation phase")
    ax.set_ylabel("Relative flux F / F_sphere")
    ax.set_xlim(0, 1)
    ax.set_ylim(min(min_rel_flux - 0.02, 0.95), max(max_rel_flux + 0.02, 1.02))
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.legend(loc='upper right')
    fig.tight_layout()  

    os.makedirs(os.path.dirname(output_base_path), exist_ok=True)
    fig.savefig(f"{output_base_path}.pdf", format="pdf")
    fig.savefig(f"{output_base_path}.svg", format="svg")
    plt.close(fig)

def plot_combined_lightcurves(curves_data, title, output_base_path):
    """Generates a cumulative plot with multiple phase-overlapped lightcurves."""
    if not curves_data:
        return
    
    fig, ax = plt.subplots(figsize=(11, 6))
    colors = plt.cm.tab10(np.linspace(0, 1, max(10, len(curves_data))))
    all_flux_values = []
    
    for idx, item in enumerate(curves_data):
        phase, flux = item["rotation_phase"], item["rel_flux"]
        all_flux_values.extend(flux)
        ax.plot(phase, flux, linewidth=1.8, label=item["label"], color=colors[idx % len(colors)])
        
    ax.axhline(1.0, color='black', linestyle='--', alpha=0.8, label="Pure Sphere Baseline (1.0)")
    ax.set_title(title, fontsize=12, fontweight='bold', pad=12)
    ax.set_xlabel("Rotation phase", fontsize=10)
    ax.set_ylabel("Relative Flux (F / F_sphere)", fontsize=10)
    ax.set_xlim(0, 1)
    if all_flux_values:
        ax.set_ylim(min(np.min(all_flux_values) - 0.02, 0.95), max(np.max(all_flux_values) + 0.02, 1.02))
        
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1.0), fontsize=9, borderaxespad=0.)
    fig.tight_layout()  
    
    os.makedirs(os.path.dirname(output_base_path), exist_ok=True)
    fig.savefig(f"{output_base_path}.pdf", format="pdf", bbox_inches='tight')
    fig.savefig(f"{output_base_path}.svg", format="svg", bbox_inches='tight')
    plt.close(fig)

def plot_param_trend_analysis(x_vals, y_vals, param_name, title, output_base_path):
    """Performs trend analysis for the sweep parameter uniting points directly (no polynomial fit)."""
    if len(x_vals) < 2:
        return

    x_arr = np.array(x_vals, dtype=float)
    y_arr = np.array(y_vals, dtype=float)

    sort_idx = np.argsort(x_arr)
    x_arr, y_arr = x_arr[sort_idx], y_arr[sort_idx]

    fig, ax = plt.subplots(figsize=(11, 6.5))
    ax.plot(x_arr, y_arr, marker='o', color='crimson', markersize=6, linewidth=2.0, label='Simulation Trend')

    ax.set_title(title, fontsize=12, fontweight='bold', pad=12)
    ax.set_xlabel("Secondary Radius R (km)", fontsize=10, labelpad=8)
    ax.set_ylabel("Peak-to-Peak Lightcurve Amplitude (%)", fontsize=10)
    
    ax.tick_params(axis='x', which='major', pad=6)
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1.0), fontsize=8.5, framealpha=0.9)
    fig.tight_layout(rect=[0, 0, 0.78, 1])  

    os.makedirs(os.path.dirname(output_base_path), exist_ok=True)
    fig.savefig(f"{output_base_path}.pdf", format="pdf", bbox_inches='tight')
    fig.savefig(f"{output_base_path}.svg", format="svg", bbox_inches='tight')
    plt.close(fig)

def plot_max_radius_trends_comparison(all_runs_data, output_base_path):
    """Crea un unico grafico riassuntivo nella cartella principale con le 6 curve (con info Sole e Terra in legenda)."""
    if not all_runs_data:
        return

    flat_data = []
    if isinstance(all_runs_data[0], list):
        for run_list in all_runs_data:
            flat_data.extend(run_list)
    else:
        flat_data = all_runs_data

    runs_dict = {}
    for item in flat_data:
        run_key = item.get("run_name", "Run")
        if run_key not in runs_dict:
            runs_dict[run_key] = []
        runs_dict[run_key].append(item)

    fig, ax = plt.subplots(figsize=(11, 6.5))
    colors = ['crimson', 'navy', 'forestgreen', 'darkorange', 'purple', 'deeppink']
    
    for idx, (run_name, items) in enumerate(runs_dict.items()):
        radii = [c.get("secondary_radius", 0.0) for c in items]
        amps = [c.get("amplitude_percent", 0.0) for c in items]

        if not radii:
            continue

        sample_item = items[0]
        sun_ra = sample_item.get("sun_ra", 0.0)
        sun_dec = sample_item.get("sun_dec", 0.0)
        earth_ra = sample_item.get("earth_ra", 0.0)
        earth_dec = sample_item.get("earth_dec", 0.0)

        sorted_pairs = sorted(zip(radii, amps))
        radii_sorted, amps_sorted = zip(*sorted_pairs)
        color_to_use = colors[idx % len(colors)]

        label_text = f"Sun: RA={sun_ra}°, Dec={sun_dec}° | Earth: RA={earth_ra}°, Dec={earth_dec}°"

        ax.plot(
            radii_sorted, amps_sorted, 
            marker='o', markersize=6, linewidth=2.0, 
            color=color_to_use, label=label_text
        )

    ax.set_title("Comparison of 6 Runs Trend: Amplitude vs Secondary Radius", fontsize=12, fontweight='bold', pad=12)
    ax.set_xlabel("Secondary Radius (km)", fontsize=10, labelpad=8)
    ax.set_ylabel("Peak-to-Peak Lightcurve Amplitude (%)", fontsize=10)

    ax.xaxis.set_major_locator(plt.MaxNLocator(nbins=10))
    ax.tick_params(axis='x', which='major', pad=6)
    ax.grid(True, linestyle='--', alpha=0.6)
    
    ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1.0), fontsize=8.0, framealpha=0.9)
    fig.tight_layout(rect=[0, 0, 0.72, 1])  

    os.makedirs(os.path.dirname(output_base_path), exist_ok=True)
    fig.savefig(f"{output_base_path}.pdf", format="pdf", bbox_inches='tight')
    fig.savefig(f"{output_base_path}.svg", format="svg", bbox_inches='tight')
    fig.savefig(f"{output_base_path}.png", format="png", dpi=300, bbox_inches='tight')
    plt.close(fig)

# =====================================================================
# CONFIGURAZIONE DELLE 6 GEOMETRIE
# =====================================================================
CUSTOM_GEOMETRY_TABLE = [
    {"sun_ra": 0.0, "sun_dec": 0.0, "earth_ra": 0.0, "earth_dec": 0.0},
    {"sun_ra": 0.0, "sun_dec": 30.0, "earth_ra": 0.0, "earth_dec": 30.0},
    {"sun_ra": 0.0, "sun_dec": 60.0, "earth_ra": 0.0, "earth_dec": 60.0},
    {"sun_ra": 30.0, "sun_dec": 0.0, "earth_ra": 0.0, "earth_dec": 0.0},
    {"sun_ra": 30.0, "sun_dec": 30.0, "earth_ra": 0.0, "earth_dec": 30.0},
    {"sun_ra": 30.0, "sun_dec": 60.0, "earth_ra": 0.0, "earth_dec": 60.0}
]

start_total = time.perf_counter()

try:
    config_path = os.path.join(project_root, "configuration.json")
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found in root: {project_root}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    asteroid_name = str(config["asteroid_name"])
    blender_path = find_blender_executable(config.get("blender_path", "").strip())
    starting_date = datetime.strptime(config["starting_date"], "%Y-%m-%d %H:%M:%S")
    finish_date = datetime.strptime(config["finish_date"], "%Y-%m-%d %H:%M:%S")
    timestep = int(config["timestep_minutes"])

    spin_ra, spin_dec = float(config["spin_ra"]), float(config["spin_dec"])
    W0, camera_orthoscale = float(config["W0"]), float(config["camera_orthoscale"])
    P_hours = float(config.get("P_hours", 3.0))

    bin_params = config.get("binary_parameters", config.get("crater_parameters", {}))
    base_secondary_radius = float(bin_params.get("secondary_radius", bin_params.get("radius_single", 5.0)))

    render_folder = os.path.join(project_root, "renders", asteroid_name)
    ellipsoid_render_folder = os.path.join(project_root, "renders", "ellipsoid")
    cache_dir = os.path.join(project_root, "cache")
    shapes_dir = os.path.join(project_root, "Shapes")
    base_analysis_dir = os.path.join(project_root, "analysis")
    csv_path = os.path.join(cache_dir, "simulation.csv")

    for folder in [render_folder, ellipsoid_render_folder, cache_dir, shapes_dir, base_analysis_dir]:
        os.makedirs(folder, exist_ok=True)

    print(f"\n============================================================\n >>> BINARY & ELLIPSOID MULTI-GEOMETRY START: {asteroid_name} ({len(CUSTOM_GEOMETRY_TABLE)} Configs)\n============================================================")

    all_runs_global_data = []

    for geo_idx, geo in enumerate(CUSTOM_GEOMETRY_TABLE, start=1):
        earth_ra = float(geo["earth_ra"])
        earth_dec = float(geo["earth_dec"])
        sun_ra = float(geo["sun_ra"])
        sun_dec = float(geo["sun_dec"])

        print(f"\n------------------------------------------------------------")
        print(f" >>> [Geometry {geo_idx}/6] SunRA={sun_ra}°, Dec={sun_dec}° | EarthRA={earth_ra}°, Dec={earth_dec}°")
        print(f"------------------------------------------------------------")

        geo_tag = f"SunRA{sun_ra:.1f}_Dec{sun_dec:.1f}_EarthRA{earth_ra:.1f}_Dec{earth_dec:.1f}".replace(".", "_")
        run_label_name = f"Run {geo_idx} (SunRA {sun_ra}°, Dec {sun_dec}°)"
        
        analysis_dir = os.path.join(base_analysis_dir, f"{asteroid_name}_{geo_tag}")
        os.makedirs(analysis_dir, exist_ok=True)

        analysis_csv_path = os.path.join(analysis_dir, "binary_analysis.csv")
        csv_headers = [
            "process_name", "secondary_radius", "sun_ra", "sun_dec", "earth_ra", "earth_dec",
            "min_rel_flux", "max_rel_flux", "peak_to_peak", "amplitude_percent", "max_abs_dev_percent"
        ]
        with open(analysis_csv_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f, delimiter=';').writerow(csv_headers)

        process = build_single_analysis_process(
            config, base_secondary_radius, sun_ra, sun_dec, earth_ra, earth_dec
        )

        proc_name = process["name"]
        runs = process["runs"]
        p1_name = process["p1_name"]

        clean_proc_name = proc_name.replace(' ', '_').replace('x', 'X').replace('(', '').replace(')', '')
        proc_folder = os.path.join(analysis_dir, clean_proc_name)
        proc_curves_data = []
        
        baseline_cache = {}
        simulation_rows = generate_simulation_rows(
            starting_date, finish_date, timestep, W0, P_hours,
            earth_ra, earth_dec, sun_ra, sun_dec, spin_ra, spin_dec
        )
        sim_fieldnames = ["date", "W", "earth_ra", "earth_dec", "sun_ra", "sun_dec", "sun_distance", "qw", "qx", "qy", "qz"]

        # 1. BASELINE (Sfera singola di riferimento R=0)
        illum_key = (sun_ra, sun_dec, earth_ra, earth_dec)
        if illum_key not in baseline_cache:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=sim_fieldnames, delimiter=',')
                writer.writeheader()
                writer.writerows(simulation_rows[:1])

            base_flux = get_uncratered_sphere_flux(
                blender_path=blender_path,
                proj_root=project_root,
                scr_dir=script_dir,
                asteroid_name=asteroid_name,
                camera_orthoscale=camera_orthoscale,
                spin_ra=spin_ra,
                spin_dec=spin_dec,
                render_folder=render_folder,
                simulation_rows=simulation_rows[:1],
                compute_flux_fn=compute_flux
            )
            baseline_cache[illum_key] = base_flux
        else:
            base_flux = baseline_cache[illum_key]

        # ---------------------------------------------------------------------
        # 2. SIMULAZIONE ELLISSOIDE (Eseguita per ogni geometria tramite Setup_blender)
        # ---------------------------------------------------------------------
        print("   -> Running Ellipsoid Simulation (ellipsoid.obj via Setup_blender)...")
        if os.path.exists(ellipsoid_render_folder):
            for f_item in os.listdir(ellipsoid_render_folder):
                if f_item.endswith(".tiff"):
                    try:
                        os.remove(os.path.join(ellipsoid_render_folder, f_item))
                    except OSError:
                        pass

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=sim_fieldnames, delimiter=',')
            writer.writeheader()
            writer.writerows(simulation_rows)

        run_blender_ellipsoid_pipeline(blender_path, project_root, script_dir, camera_orthoscale, spin_ra, spin_dec)
        
        ellipsoid_stats = compute_lightcurve_metrics(
            simulation_rows=simulation_rows,
            render_folder=ellipsoid_render_folder,
            asteroid_name="ellipsoid",
            compute_flux_fn=compute_flux,
            P_hours=P_hours,
            base_flux=base_flux
        )

        # Salvataggio foto (render raw) dell'ellissoide nella cartella di run
        ellipsoid_images_dir = os.path.join(proc_folder, "images")
        os.makedirs(ellipsoid_images_dir, exist_ok=True)
        raw_renders_ellipsoid_target = os.path.join(ellipsoid_images_dir, "raw_renders_ellipsoid")
        os.makedirs(raw_renders_ellipsoid_target, exist_ok=True)
        for f_item in os.listdir(ellipsoid_render_folder):
            if f_item.endswith((".tiff", ".png", ".jpg")):
                src_path = os.path.join(ellipsoid_render_folder, f_item)
                dst_path = os.path.join(raw_renders_ellipsoid_target, f_item)
                if not os.path.exists(dst_path):
                    shutil.copy(src_path, dst_path)

        # Salvataggio dei dati dell'ellissoide nei file CSV di analisi
        ellipsoid_row = [
            "ELLIPSOID", fmt_num(0.0, 2), 
            fmt_num(sun_ra, 2), fmt_num(sun_dec, 2), fmt_num(earth_ra, 2), fmt_num(earth_dec, 2),
            fmt_num(ellipsoid_stats["min_rel_flux"], 4), fmt_num(ellipsoid_stats["max_rel_flux"], 4),
            fmt_num(ellipsoid_stats["peak_to_peak"], 4), fmt_num(ellipsoid_stats["amplitude_percent"], 4), fmt_num(ellipsoid_stats["max_abs_dev_percent"], 4)
        ]
        write_csv_with_retry(analysis_csv_path, [ellipsoid_row])
        specific_csv_name = f"{clean_proc_name.lower()}_analysis.csv"
        tables_dir_path = os.path.join(proc_folder, "tables")
        os.makedirs(tables_dir_path, exist_ok=True)
        write_csv_with_retry(os.path.join(tables_dir_path, specific_csv_name), [ellipsoid_row], headers=csv_headers)

        # ---------------------------------------------------------------------
        # 3. CICLO RUN BINARIE
        # ---------------------------------------------------------------------
        for run_idx, run in enumerate(runs, 1):
            secondary_radius = run.get("secondary_radius", base_secondary_radius)

            print(f"   [Run {run_idx}/{len(runs)}] Secondary Radius={secondary_radius} km")

            run_target_dir = proc_folder
            images_dir = os.path.join(run_target_dir, "images")
            tables_dir = os.path.join(run_target_dir, "tables")
            os.makedirs(images_dir, exist_ok=True)
            os.makedirs(tables_dir, exist_ok=True)

            if os.path.exists(render_folder):
                for f_item in os.listdir(render_folder):
                    if f_item.endswith(".tiff"):
                        try:
                            os.remove(os.path.join(render_folder, f_item))
                        except OSError:
                            pass

            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=sim_fieldnames, delimiter=',')
                writer.writeheader()
                writer.writerows(simulation_rows)

            run_blender_binary_pipeline(
                blender_path, project_root, script_dir, asteroid_name, 
                secondary_radius, camera_orthoscale, spin_ra, spin_dec
            )

            stats = compute_lightcurve_metrics(
                simulation_rows=simulation_rows,
                render_folder=render_folder,
                asteroid_name=asteroid_name,
                compute_flux_fn=compute_flux,
                P_hours=P_hours,
                base_flux=base_flux
            )
            
            raw_renders_target = os.path.join(images_dir, f"raw_renders_SecRad_{secondary_radius}")
            os.makedirs(raw_renders_target, exist_ok=True)
            for f_item in os.listdir(render_folder):
                if f_item.endswith((".tiff", ".png", ".jpg")):
                    src_path = os.path.join(render_folder, f_item)
                    dst_path = os.path.join(raw_renders_target, f_item)
                    if not os.path.exists(dst_path):
                        shutil.copy(src_path, dst_path)

            run_data_dict = {
                "run_name": run_label_name,
                "secondary_radius": secondary_radius,
                "sun_ra": sun_ra, "sun_dec": sun_dec,
                "earth_ra": earth_ra, "earth_dec": earth_dec,
                "amplitude_percent": stats["amplitude_percent"],
                "t_seconds": stats["t_seconds"], "rotation_phase": stats["rotation_phase"],
                "rel_flux": stats["rel_flux"]
            }
            proc_curves_data.append(run_data_dict)
            all_runs_global_data.append(run_data_dict)

            formatted_row = [
                proc_name, fmt_num(secondary_radius, 2), 
                fmt_num(sun_ra, 2), fmt_num(sun_dec, 2), fmt_num(earth_ra, 2), fmt_num(earth_dec, 2),
                fmt_num(stats["min_rel_flux"], 4), fmt_num(stats["max_rel_flux"], 4),
                fmt_num(stats["peak_to_peak"], 4), fmt_num(stats["amplitude_percent"], 4), fmt_num(stats["max_abs_dev_percent"], 4)
            ]

            write_csv_with_retry(analysis_csv_path, [formatted_row])
            specific_csv_name = f"{clean_proc_name.lower()}_analysis.csv"
            write_csv_with_retry(os.path.join(tables_dir, specific_csv_name), [formatted_row], headers=csv_headers)

            filename_base = f"{asteroid_name}_SecRad{secondary_radius}_SunRA{sun_ra}_SunDec{sun_dec}"
            plot_title = f"Lightcurve - {asteroid_name}\n(Secondary R={secondary_radius}km, SunRA={sun_ra}°, SunDec={sun_dec}°)"
            plot_single_lightcurve(
                stats["rotation_phase"], stats["rel_flux"], stats["extreme_idx"],
                stats["max_abs_dev_percent"], stats["min_rel_flux"], stats["max_rel_flux"],
                plot_title, os.path.join(images_dir, filename_base)
            )

            # GRAFICO CONFRONTO: BINARIO VS ELLISSOIDE
            fig, ax = plt.subplots(figsize=(9, 5))
            ax.plot(stats["rotation_phase"], stats["rel_flux"], label=f"Binary (R={secondary_radius} km, Amp: {stats['amplitude_percent']:.2f}%)", color='crimson', lw=2)
            ax.plot(ellipsoid_stats["rotation_phase"], ellipsoid_stats["rel_flux"], label=f"Ellipsoid (Amp: {ellipsoid_stats['amplitude_percent']:.2f}%)", color='navy', lw=2, linestyle='--')
            
            ax.set_title(f"Comparison: Contact Binary vs Ellipsoid\nGeometry: Sun [RA:{sun_ra}°, Dec:{sun_dec}°] | Earth [RA:{earth_ra}°, Dec:{earth_dec}°]", fontsize=10, fontweight='bold')
            ax.set_xlabel("Rotation phase", fontsize=9)
            ax.set_ylabel("Relative flux F / F_sphere", fontsize=9)
            ax.grid(True, linestyle='--', alpha=0.6)
            ax.legend(loc='best', fontsize=8.5)
            fig.tight_layout()  

            comp_plot_path = os.path.join(images_dir, f"{asteroid_name}_SecRad{secondary_radius}_vs_ellipsoid")
            fig.savefig(f"{comp_plot_path}.pdf", format="pdf", bbox_inches='tight')
            fig.savefig(f"{comp_plot_path}.png", format="png", dpi=300, bbox_inches='tight')
            plt.close(fig)

        plot_items = [{"rotation_phase": sc["rotation_phase"], "rel_flux": sc["rel_flux"], "label": f"Sec. Rad = {sc['secondary_radius']} km"} for sc in proc_curves_data]
        title = f"Combined Lightcurves - {proc_name} ({asteroid_name})"
        plot_combined_lightcurves(plot_items, title, os.path.join(proc_folder, "images", f"{asteroid_name}_{clean_proc_name}_combined"))

        if p1_name != "single":
            x_vals = [sc["secondary_radius"] for sc in proc_curves_data]
            amp_vals = [sc["amplitude_percent"] for sc in proc_curves_data]
            t_title = f"Amplitude Trend vs Secondary Radius ({asteroid_name})"
            plot_param_trend_analysis(x_vals, amp_vals, p1_name, t_title, os.path.join(proc_folder, "images", f"{asteroid_name}_secondary_radius_trend"))

    summary_plot_path = os.path.join(base_analysis_dir, f"{asteroid_name}_binary_trends_comparison")
    plot_max_radius_trends_comparison(all_runs_global_data, summary_plot_path)
    print(f"\n [INFO] Grafico riassuntivo globale con le 6 curve generato in: {base_analysis_dir}")

    end_total = time.perf_counter()
    print(f"\n============================================================\n ALL ANALYSES COMPLETED IN: {end_total - start_total:.2f} s\n============================================================")

except Exception as e:
    print(f"\n[CRITICAL ERROR]: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)