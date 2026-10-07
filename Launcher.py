import os
import sys
import time
import csv
import shutil
import json
import subprocess
import traceback
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt

base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(base_dir, "Codes"))

from Magnitude_calculations import compute_flux
from automation_helpers import (
    fmt_num, write_csv_with_retry, find_blender_executable,
    build_single_analysis_process, generate_simulation_rows,
    get_uncratered_sphere_flux, compute_lightcurve_metrics, plot_single_lightcurve,
    plot_combined_lightcurves, plot_param_trend_analysis
)

# =====================================================================
# FUNZIONI DI BLENDER (BINARIO & ELLISSOIDE)
# =====================================================================
def run_blender_binary_pipeline(blender_path, base_dir, asteroid_name, secondary_radius, camera_orthoscale, spin_ra, spin_dec):
    """Esegue la sequenza di script Blender per il sistema binario a contatto."""
    cache_dir = os.path.join(base_dir, "cache")
    blend_file = os.path.join(cache_dir, "object.blend")
    binary_script = os.path.join(base_dir, "Codes", "Script_binary.py")
    setup_script = os.path.join(base_dir, "Codes", "Setup_blender.py")
    render_script = os.path.join(base_dir, "Codes", "Rendering2.py")
    asteroid_rel_file = os.path.join("Shapes", f"{asteroid_name}.obj")

    subprocess.run([blender_path, "-b", "-P", binary_script, "--", asteroid_name, base_dir, str(secondary_radius)], check=True)
    subprocess.run([blender_path, "-b", "-P", setup_script, "--", asteroid_name, asteroid_rel_file, str(camera_orthoscale), base_dir], check=True)
    subprocess.run([blender_path, "-b", blend_file, "-P", render_script, "--", asteroid_name, str(spin_ra), str(spin_dec), base_dir], check=True)

def run_blender_ellipsoid_pipeline(blender_path, base_dir, camera_orthoscale, spin_ra, spin_dec):
    """Esegue Setup_blender direttamente passando ellipsoid.obj, sovrascrivendo la scena pulitamente."""
    cache_dir = os.path.join(base_dir, "cache")
    blend_file = os.path.join(cache_dir, "object.blend")
    setup_script = os.path.join(base_dir, "Codes", "Setup_blender.py")
    render_script = os.path.join(base_dir, "Codes", "Rendering2.py")
    
    ellipsoid_name = "ellipsoid"
    ellipsoid_rel_file = os.path.join("Shapes", f"{ellipsoid_name}.obj")

    subprocess.run([blender_path, "-b", "-P", setup_script, "--", ellipsoid_name, ellipsoid_rel_file, str(camera_orthoscale), base_dir], check=True)
    subprocess.run([blender_path, "-b", blend_file, "-P", render_script, "--", ellipsoid_name, str(spin_ra), str(spin_dec), base_dir], check=True)

# =====================================================================
# GRAFICO RIASSUNTIVO GLOBALE PER I CORPI BINARI
# =====================================================================
def plot_max_radius_trends_comparison(all_runs_data, output_base_path):
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

        sorted_pairs = sorted(zip(radii, amps))
        radii_sorted, amps_sorted = zip(*sorted_pairs)

        color_to_use = colors[idx % len(colors)]

        ax.plot(
            radii_sorted, 
            amps_sorted, 
            marker='o', 
            markersize=6, 
            linewidth=2.0, 
            color=color_to_use, 
            label=run_name
        )

    ax.set_title("Comparison of 6 Runs Trend: Amplitude vs Secondary Radius", fontsize=12, fontweight='bold', pad=12)
    ax.set_xlabel("Secondary Radius (km)", fontsize=10, labelpad=8)
    ax.set_ylabel("Peak-to-Peak Lightcurve Amplitude (%)", fontsize=10)

    ax.tick_params(axis='x', which='major', pad=6)
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1.0), fontsize=8.5, framealpha=0.9)
    ax.tight_layout(rect=[0, 0, 0.78, 1])

    os.makedirs(os.path.dirname(output_base_path), exist_ok=True)
    fig.savefig(f"{output_base_path}.pdf", format="pdf", bbox_inches='tight')
    fig.savefig(f"{output_base_path}.svg", format="svg", bbox_inches='tight')
    fig.savefig(f"{output_base_path}.png", format="png", dpi=300, bbox_inches='tight')
    plt.close(fig)

# =====================================================================
# TABLE OF 6 CUSTOM GEOMETRIC CONFIGURATIONS
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
    config_path = os.path.join(base_dir, "configuration.json")
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found in: {base_dir}")

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
    base_secondary_radius = float(bin_params.get("secondary_radius", bin_params.get("radius_single", 10.0)))
    base_lat = 0.0  

    render_folder = os.path.join(base_dir, "renders", asteroid_name)
    ellipsoid_render_folder = os.path.join(base_dir, "renders", "ellipsoid")
    cache_dir = os.path.join(base_dir, "cache")
    shapes_dir = os.path.join(base_dir, "Shapes")
    base_analysis_dir = os.path.join(base_dir, "analysis")
    csv_path = os.path.join(cache_dir, "simulation.csv")

    for folder in [render_folder, ellipsoid_render_folder, cache_dir, shapes_dir, base_analysis_dir]:
        os.makedirs(folder, exist_ok=True)

    print(f"\n============================================================\n >>> BINARY & ELLIPSOID MULTI-GEOMETRY START ({len(CUSTOM_GEOMETRY_TABLE)} Configurations)\n============================================================")

    sample_geo = CUSTOM_GEOMETRY_TABLE[0]
    sample_process = build_single_analysis_process(
        config, base_lat, base_secondary_radius, 
        sample_geo["sun_ra"], sample_geo["sun_dec"], 
        sample_geo["earth_ra"], sample_geo["earth_dec"]
    )
    total_runs_all = len(sample_process["runs"]) * len(CUSTOM_GEOMETRY_TABLE)
    est_total_seconds = total_runs_all * 75
    est_hours = est_total_seconds // 3600
    est_minutes = (est_total_seconds % 3600) // 60
    
    time_str = f"about {int(est_hours)} hours and {int(est_minutes)} minutes" if est_hours > 0 else f"about {int(est_minutes)} minutes"
    print(f" [TIME ESTIMATE] {total_runs_all} total simulations expected -> Estimated time: {time_str}")
    print(f"============================================================")

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
            config, base_lat, base_secondary_radius, sun_ra, sun_dec, earth_ra, earth_dec
        )

        proc_name = process["name"]
        runs = process["runs"]
        p1_name = process["p1_name"]

        clean_proc_name = proc_name.replace(' ', '_').replace('x', 'X').replace('(', '').replace(')', '')
        proc_folder = os.path.join(analysis_dir, clean_proc_name)
        proc_curves_data = []
        
        # =====================================================================
        # 1. SIMULAZIONE ELLISSOIDE (Eseguita per ogni geometria corrente)
        # =====================================================================
        print("   -> Running Ellipsoid Simulation (ellipsoid.obj via Setup_blender)...")
        simulation_rows = generate_simulation_rows(
            starting_date, finish_date, timestep, W0, P_hours,
            earth_ra, earth_dec, sun_ra, sun_dec, spin_ra, spin_dec
        )
        sim_fieldnames = ["date", "W", "earth_ra", "earth_dec", "sun_ra", "sun_dec", "sun_distance", "qw", "qx", "qy", "qz"]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=sim_fieldnames, delimiter=',')
            writer.writeheader()
            writer.writerows(simulation_rows[:1])

        base_flux = get_uncratered_sphere_flux(
            blender_path=blender_path,
            base_dir=base_dir,
            asteroid_name=asteroid_name,
            camera_orthoscale=camera_orthoscale,
            spin_ra=spin_ra,
            spin_dec=spin_dec,
            render_folder=render_folder,
            simulation_rows=simulation_rows[:1],
            compute_flux_fn=compute_flux
        )

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=sim_fieldnames, delimiter=',')
            writer.writeheader()
            writer.writerows(simulation_rows)

        if os.path.exists(ellipsoid_render_folder):
            for f_item in os.listdir(ellipsoid_render_folder):
                if f_item.endswith(".tiff"):
                    try:
                        os.remove(os.path.join(ellipsoid_render_folder, f_item))
                    except OSError:
                        pass

        # CHIAMATA BLENDER CORRETTA PER L'ELLISSOIDE
        run_blender_ellipsoid_pipeline(blender_path, base_dir, camera_orthoscale, spin_ra, spin_dec)
        
        ellipsoid_stats = compute_lightcurve_metrics(
            simulation_rows=simulation_rows,
            render_folder=ellipsoid_render_folder,
            asteroid_name="ellipsoid",
            compute_flux_fn=compute_flux,
            P_hours=P_hours,
            base_flux=base_flux
        )

        # =====================================================================
        # 2. CICLO RUN BINARIE
        # =====================================================================
        for run_idx, run in enumerate(runs, 1):
            secondary_radius = run.get("secondary_radius", run.get("crater_radius", base_secondary_radius))

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

            run_blender_binary_pipeline(blender_path, base_dir, asteroid_name, secondary_radius, camera_orthoscale, spin_ra, spin_dec)

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

            # GRAFICO SOVRAPPOSTO: BINARIO VS ELLISSOIDE
            fig, ax = plt.subplots(figsize=(9, 5))
            ax.plot(stats["rotation_phase"], stats["rel_flux"], label=f"Binary (Sec. R={secondary_radius} km, Amp: {stats['amplitude_percent']:.2f}%)", color='crimson', lw=2)
            ax.plot(ellipsoid_stats["rotation_phase"], ellipsoid_stats["rel_flux"], label=f"Ellipsoid (ellipsoid.obj, Amp: {ellipsoid_stats['amplitude_percent']:.2f}%)", color='navy', lw=2, linestyle='--')
            
            ax.set_title(f"Comparison: Contact Binary vs Ellipsoid\nGeometry: Sun [RA:{sun_ra}°, Dec:{sun_dec}°] | Earth [RA:{earth_ra}°, Dec:{earth_dec}°]", fontsize=10, fontweight='bold')
            ax.set_xlabel("Rotation Phase", fontsize=9)
            ax.set_ylabel("Relative Flux / Mag", fontsize=9)
            ax.grid(True, linestyle='--', alpha=0.6)
            ax.legend(loc='best', fontsize=8.5)
            ax.tight_layout()

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
            plot_param_trend_analysis(x_vals, amp_vals, "secondary_radius", t_title, os.path.join(proc_folder, "images", f"{asteroid_name}_secondary_radius_trend"))

    summary_plot_path = os.path.join(base_analysis_dir, f"{asteroid_name}_binary_trends_comparison")
    plot_max_radius_trends_comparison(all_runs_global_data, summary_plot_path)
    print(f"\n [INFO] Grafico riassuntivo globale generato in: {base_analysis_dir}")

    end_total = time.perf_counter()
    print(f"\n============================================================\n ALL 6 ANALYSES COMPLETED IN: {end_total - start_total:.2f} s\n============================================================")

except Exception as e:
    print(f"\n[CRITICAL ERROR]: {e}")
    traceback.print_exc()
    sys.exit(1)