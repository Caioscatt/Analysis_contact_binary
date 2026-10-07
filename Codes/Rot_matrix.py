"""
Astronomical Coordinate and Orientation Transformations
"""

import numpy as np
from numpy import pi
from scipy.spatial.transform import Rotation


# Fundamental single-axis rotation
Rx = lambda theta: Rotation.from_euler('X', -theta)
Ry = lambda theta: Rotation.from_euler('Y', -theta)
Rz = lambda theta: Rotation.from_euler('Z', -theta)

# Mean obliquity of the ecliptic J2000
Rce = Rx(23.4392911 * pi / 180)  # ICRF to Ecliptic
Rec = Rce.inv()                  # Ecliptic to ICRF

# Normalize vectors to unit vectors
unit_vector = lambda v: v / np.linalg.norm(v, axis=-1, keepdims=True)


def euler_to_Rbc(alpha, delta, W, units='deg'):
    """
    Convert IAU orientation angles to a Body-to-ICRF orientation object

    Uses the standard IAU convention where the body orientation relative to 
    ICRF is defined by Right Ascension (alpha), Declination (delta) of the 
    north pole, and Prime Meridian location (W) using a 'ZXZ' Euler sequence

    Parameters
    ----------
    alpha : Right Ascension of the body's north pole
    delta : Declination of the body's north pole
    W : Location of the prime meridian
    units : Units of input angles, default 'deg'

    Returns
    -------
    Body-to-ICRF orientation object
    """
    assert units == 'deg', 'Only degrees are supported.'
    euler_angles = np.array([90. + alpha, 90. - delta, W]).T
    return Rotation.from_euler('ZXZ', euler_angles, degrees=True)


def Rbc_to_euler(Rbc, units='deg'):
    """
    Extract IAU orientation angles (alpha, delta, W) from Body-to-ICRF orientation object

    Parameters
    ----------
    Rbc : Body-to-ICRF orientation object
    units : Units of output angles, default 'deg'

    Returns
    -------
    alpha : Right Ascension of the body's north pole in [0, 360) degrees
    delta : Declination of the body's north pole in [-90, 90] degrees
    W : Prime Meridian location angle in [0, 360) degrees
    """
    assert units == 'deg', 'Only degrees are supported.'
    # Deconstruct orientation back into ZXZ Euler sequence
    t1, t2, t3 = Rbc.as_euler('ZXZ', degrees=True).T
    
    alpha = (t1 - 90.) % 360.
    delta = 90. - t2
    W = t3 % 360.
    
    return alpha, delta, W


def ecliptic_to_Rbc(lon, lat, phi, units='deg'):
    """
    Convert Ecliptic orientation parameters into a Body-to-ICRF orientation object

    Parameters
    ----------
    lon : Ecliptic longitude of the pole direction
    lat : Ecliptic latitude of the pole direction
    phi : Body rotation angle
    units : Units of input angles, default 'deg'

    Returns
    -------
    Body-to-ICRF orientation object
    """
    assert units == 'deg', 'Only degrees are supported.'
    # Body-to-Ecliptic orientation via ZYZ sequence
    Rbe = Rotation.from_euler('ZYZ', np.array([lon, 90. - lat, phi]).T, degrees=True)
    
    # Chain rotations
    return Rec * Rbe


def Rbc_to_ecliptic(Rbc, units='deg'):
    """
    Convert Body-to-ICRF orientation object into Ecliptic spherical parameters

    Parameters
    ----------
    Rbc : Body-to-ICRF orientation object
    units : Units of output angles, default 'deg'

    Returns
    -------
    lon : Ecliptic longitude in [0, 360) degrees
    lat : Ecliptic latitude in [-90, 90] degrees
    phi : Body spin angle in [0, 360) degrees
    """
    assert units == 'deg', 'Only degrees are supported.'
    # Transform Body-to-ICRF frame into Body-to-Ecliptic frame
    Rbe = Rce * Rbc
    
    # Extract Euler angles and reconstruct Ecliptic polar coordinates
    t1, t2, t3 = Rbe.as_euler('ZXZ', degrees=True).T
    lon = (t1 - 90.) % 360.
    lat = 90. - t2
    phi = t3 % 360.
    
    return lon, lat, phi


def ecliptic_to_euler(lon, lat, phi, eps=23.4392911):
    """
    Convert Ecliptic orientation parameters to Equatorial IAU angles (alpha, delta, W)

    Parameters
    ----------
    lon : Ecliptic longitude
    lat : Ecliptic latitude
    phi : Rotation angle
    eps : Obliquity of the ecliptic in degrees

    Returns
    -------
    alpha : Right Ascension (RA) in degrees [0, 360)
    delta : Declination (Dec) in degrees [-90, 90]
    W : Prime Meridian location in degrees [0, 360)
    """
    # 1. Define transformation from Ecliptic to ICRF
    Rec = Rotation.from_euler('X', eps, degrees=True)
    
    # 2. Define transformation Body-to-Ecliptic
    Rbe = Rotation.from_euler('ZYZ', np.array([lon, 90. - lat, phi]).T, degrees=True)
    
    # 3. Combine rotations
    Rbc = Rec * Rbe
    
    # 4. Extract standard IAU equatorial parameters (RA, Dec, W)
    t1, t2, t3 = Rbc.as_euler('ZXZ', degrees=True).T
    alpha = (t1 - 90.) % 360.
    delta = 90. - t2
    W = t3 % 360.
    
    return alpha, delta, W


def angular_distance(u, v, units='rad'):
    """
    Calculate the angular separation between 3D vectors
    with numerically stable arctan2

    Parameters
    ----------
    u : First vector
    v : Second vector
    units : Desired return units, default 'rad'

    Returns
    -------
    Angular separation between vectors in radians or degrees.
    """
    # Normalize input vectors to unit magnitude
    u = u / np.linalg.norm(u)
    v = v / np.linalg.norm(v)
    
    # Calculate sine (via cross product norm) and cosine (via dot product)
    s = np.linalg.norm(np.cross(u, v))
    c = np.dot(u, v)
    
    # Compute angle via arctan2(sin, cos)
    if 'deg' in units.lower():
        return np.arctan2(s, c) * 180. / pi
    return np.arctan2(s, c)


def rotation_distance(A, B, units='rad'):
    """
    Calculate the orientation error between
    orientation matrix A and orientation matrix B

    Parameters
    ----------
    A : First 3x3 orientation matrix
    B : Second 3x3 orientation matrix
    units : Desired return units, default 'rad'

    Returns
    -------
    Orientation error between A and B.
    """
    # Compute relative rotation: R_rel = A^(-1) * B
    R = Rotation.from_matrix(A).inv() * Rotation.from_matrix(B)
    
    # Extract rotation angle magnitude
    if 'deg' in units.lower():
        return R.magnitude() * 180. / pi
    return R.magnitude()
 