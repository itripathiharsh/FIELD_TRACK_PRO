/*
 * Shared demo geometry for the hero territory map. Both the static poster (SVG) and the
 * WebGL scene are drawn from these numbers, so the fallback matches the live scene.
 * Everything here is invented: no real outlets, reps or amounts.
 */

export const CELL = 1.5;

export interface MapSpec {
  cols: number;
  rows: number;
}

export const MAP_DESKTOP: MapSpec = { cols: 16, rows: 10 };
export const MAP_MOBILE: MapSpec = { cols: 10, rows: 8 };

/** Deterministic PRNG (mulberry32) so the map is identical on every load. */
function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a += 0x6d2b79f5;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export interface District {
  /** cell centre in world units (x, z) */
  x: number;
  z: number;
  /** extrusion height */
  h: number;
  /** part of the highlighted demo territory */
  zone: boolean;
}

export function districts({ cols, rows }: MapSpec): District[] {
  const r = rng(7);
  const out: District[] = [];
  const x0 = -(cols * CELL) / 2 + CELL / 2;
  const z0 = -(rows * CELL) / 2 + CELL / 2;
  for (let c = 0; c < cols; c++) {
    for (let w = 0; w < rows; w++) {
      const v = r();
      if (v < 0.12) continue; // open ground / parks
      const x = x0 + c * CELL;
      const z = z0 + w * CELL;
      // the demo territory: a cluster right of centre
      const zone = Math.hypot(x - 2.6, z + 0.6) < 4.2;
      out.push({ x, z, h: 0.08 + Math.pow(r(), 2.2) * (zone ? 0.9 : 0.55), zone });
    }
  }
  return out;
}

/** Road coordinates sit on cell boundaries. Route points are [x, z]. */
export type Pt = [number, number];

export const ROUTES_DESKTOP: Pt[][] = [
  // primary route (accent)
  [
    [-10.5, 6],
    [-10.5, 3],
    [-4.5, 3],
    [-4.5, 0],
    [1.5, 0],
    [1.5, -3],
    [7.5, -3],
    [7.5, -6],
  ],
  [
    [-12, -4.5],
    [-6, -4.5],
    [-6, -1.5],
    [0, -1.5],
    [0, 4.5],
    [6, 4.5],
    [6, 1.5],
    [12, 1.5],
  ],
  [
    [10.5, 7.5],
    [10.5, 3],
    [4.5, 3],
    [4.5, -1.5],
    [9, -1.5],
    [9, -7.5],
  ],
];

export const ROUTES_MOBILE: Pt[][] = [
  [
    [-6, 4.5],
    [-6, 1.5],
    [-1.5, 1.5],
    [-1.5, -1.5],
    [3, -1.5],
    [3, -4.5],
    [6, -4.5],
  ],
  [
    [6, 6],
    [6, 3],
    [1.5, 3],
    [1.5, 0],
    [-4.5, 0],
    [-4.5, -6],
  ],
];

/** Check-in pins as [routeIndex, vertexIndex]. */
export const PINS_DESKTOP: [number, number][] = [
  [0, 2],
  [0, 4],
  [0, 6],
  [1, 3],
  [1, 5],
  [2, 2],
  [2, 4],
];
export const PINS_MOBILE: [number, number][] = [
  [0, 2],
  [0, 4],
  [1, 2],
  [1, 4],
];
