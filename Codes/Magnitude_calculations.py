import numpy as np
import tifffile


def compute_flux(image_path, ls_correction=1.0):

    # ==============================
    # READ IMAGE
    # ==============================

    img = tifffile.imread(image_path)

    # grayscale if RGB
    if img.ndim == 3:
        img = img.mean(axis=2)

    img = img.astype(float)


    # ==============================
    # CHECK BLACK BACKGROUND
    # ==============================

    if np.any(img == 0) is False:
        raise RuntimeError(
            "ERROR: background is not completely black"
        )


    # ==============================
    # TOTAL ASTEROID FLUX
    # ==============================

    flux = np.sum(img)

    if flux <= 0:
        raise RuntimeError(
            "ERROR: zero flux detected"
        )


    # ==============================
    # INSTRUMENTAL MAGNITUDE
    # ==============================

    mag_inst = -2.5*np.log10(flux)


    return flux, mag_inst