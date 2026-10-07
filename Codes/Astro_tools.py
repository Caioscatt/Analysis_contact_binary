import math
from astropy.time import Time

def utc_to_julian(dt):
    t = Time(dt, scale='utc')
    return t.jd

def compute_W(jd, w0, rotation_rate, JD0):
    return w0 + rotation_rate * (jd - JD0)

def get_geometry(jpl_id, time_obj):
    from astroquery.jplhorizons import Horizons
    # ==========================
    # EARTH OBSERVER
    # ==========================
    earth = Horizons(id=jpl_id, location="500", epochs=time_obj.jd)
    ephE = earth.ephemerides()
    earth_ra = float(ephE["RA"][0])
    earth_dec = float(ephE["DEC"][0])
    earth_ra = (earth_ra + 180.0) % 360.0
    earth_dec = -earth_dec
    
    r = float(ephE["r"][0])
    delta = float(ephE["delta"][0])
    alpha = float(ephE["alpha"][0])
    
    # ==========================
    # SUN OBSERVER
    # ==========================
    sun = Horizons(id=jpl_id, location="@10", epochs=time_obj.jd)
    ephS = sun.ephemerides()
    sun_ra = float(ephS["RA"][0])
    sun_dec = float(ephS["DEC"][0])
    sun_ra = (sun_ra + 180.0) % 360.0
    sun_dec = -sun_dec
    
    return (earth_ra, earth_dec, sun_ra, sun_dec, r, delta, alpha)


def ecliptic_to_ra_dec(lambda_deg, beta_deg, phi0_ecliptic, JD0):
    """
    Conversione rigorosa del polo e ricalcolo di phi0 (W0) 
    dal sistema eclittico a quello equatoriale.
    """
    T = (JD0 - 2451545.0) / 36525.0
    epsilon_deg = (23.43929111 - 0.013004167 * T - 1.64e-7 * T**2 + 5.04e-7 * T**3)
    
    lam = math.radians(lambda_deg)
    beta = math.radians(beta_deg)
    eps = math.radians(epsilon_deg)

    # 1. Conversione delle coordinate del polo (Lambda, Beta) -> (RA, Dec)
    sin_dec = (
        math.sin(beta) * math.cos(eps)
        + math.cos(beta) * math.sin(eps) * math.sin(lam)
    )
    dec = math.asin(max(-1.0, min(1.0, sin_dec)))

    y = math.sin(lam) * math.cos(eps) - math.tan(beta) * math.sin(eps)
    x = math.cos(lam)
    ra = math.atan2(y, x)

    ra_deg = math.degrees(ra) % 360
    dec_deg = math.degrees(dec)

    # 2. Correzione di phi0 (W0) basata sulla trasformazione dei piani di riferimento
    # Angolo del nodo ascendente e rotazione differenziale dei meridiani
    cos_eps = math.cos(eps)
    sin_eps = math.sin(eps)
    
    # Componenti dei vettori di rotazione
    num = sin_eps * math.cos(lam)
    den = cos_eps * math.cos(beta) - sin_eps * math.sin(beta) * math.sin(lam)
    
    delta_phi = math.degrees(math.atan2(num, den))
    phi0_equatorial = (phi0_ecliptic + delta_phi) % 360

    return ra_deg, dec_deg, phi0_equatorial