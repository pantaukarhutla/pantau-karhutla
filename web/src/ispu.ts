// Indonesian air-quality categories (ISPU) for PM2.5.

export const ISPU_LEVELS = ["baik", "sedang", "tidak_sehat", "sangat_tidak_sehat", "berbahaya"] as const;
export type Ispu = (typeof ISPU_LEVELS)[number];

// Upper PM2.5 bound (µg/m³) of each category but the last: Permen LHK P.14/2020.
const ISPU_PM25_MAX = [15.5, 55.4, 150.4, 250.4];

export function ispuOf(pm25: number): Ispu {
  const k = ISPU_PM25_MAX.findIndex((max) => pm25 <= max);
  return ISPU_LEVELS[k < 0 ? ISPU_LEVELS.length - 1 : k];
}
