// Small spherical helpers: distance, bearing and 8-point compass names.

const R_KM = 6371;
const rad = (d: number) => (d * Math.PI) / 180;

/** Great-circle distance in km. */
export function distanceKm(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const a = Math.sin(rad(lat2 - lat1) / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(rad(lon2 - lon1) / 2) ** 2;
  return 2 * R_KM * Math.asin(Math.sqrt(a));
}

/** Initial bearing from point 1 to point 2, degrees clockwise from north (0-360). */
export function bearingDeg(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const y = Math.sin(rad(lon2 - lon1)) * Math.cos(rad(lat2));
  const x = Math.cos(rad(lat1)) * Math.sin(rad(lat2)) - Math.sin(rad(lat1)) * Math.cos(rad(lat2)) * Math.cos(rad(lon2 - lon1));
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

/** 0 = north, 1 = north-east, ... 7 = north-west. */
export const compassIndex = (bearing: number) => Math.round((((bearing % 360) + 360) % 360) / 45) % 8;
