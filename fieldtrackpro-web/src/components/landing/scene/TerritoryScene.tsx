import React, { useLayoutEffect, useMemo, useRef, type MutableRefObject } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import * as THREE from 'three';
import { DashboardScreen, PhoneScreen } from '../Mockups';
import {
  CELL,
  MAP_DESKTOP,
  MAP_MOBILE,
  PINS_DESKTOP,
  PINS_MOBILE,
  ROUTES_DESKTOP,
  ROUTES_MOBILE,
  districts,
  type MapSpec,
  type Pt,
} from './data';

const ACCENT = new THREE.Color('#ff9f2e');
const INK = new THREE.Color('#ededed');

export interface TerritorySceneProps {
  /** 0..1 scroll progress through the pinned hero, read every frame (no re-render). */
  progress: MutableRefObject<number>;
  reduced: boolean;
  mobile: boolean;
  /** pauses rendering while the hero is off-screen */
  active: boolean;
  onReady?: () => void;
}

const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const clamp01 = (t: number) => Math.min(1, Math.max(0, t));

function pathFrom(points: Pt[], y = 0.03): THREE.CurvePath<THREE.Vector3> {
  const path = new THREE.CurvePath<THREE.Vector3>();
  for (let i = 0; i < points.length - 1; i++) {
    const [ax, az] = points[i];
    const [bx, bz] = points[i + 1];
    path.add(new THREE.LineCurve3(new THREE.Vector3(ax, y, az), new THREE.Vector3(bx, y, bz)));
  }
  return path;
}

/* ---------------- Map ---------------- */

const Districts: React.FC<{ spec: MapSpec }> = ({ spec }) => {
  const list = useMemo(() => districts(spec), [spec]);
  const ref = useRef<THREE.InstancedMesh>(null);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const m = new THREE.Matrix4();
    const c = new THREE.Color();
    const size = CELL - 0.34;
    list.forEach((d, i) => {
      m.compose(new THREE.Vector3(d.x, d.h / 2, d.z), new THREE.Quaternion(), new THREE.Vector3(size, d.h, size));
      mesh.setMatrixAt(i, m);
      mesh.setColorAt(i, c.set(d.zone ? '#3a2a1a' : '#202026'));
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [list]);
  return (
    <instancedMesh ref={ref} args={[undefined, undefined, list.length]}>
      <boxGeometry />
      <meshStandardMaterial roughness={0.85} metalness={0.05} />
    </instancedMesh>
  );
};

const Roads: React.FC<{ spec: MapSpec }> = ({ spec }) => {
  const geom = useMemo(() => {
    const w = (spec.cols * CELL) / 2;
    const d = (spec.rows * CELL) / 2;
    const pts: number[] = [];
    for (let c = 0; c <= spec.cols; c++) {
      const x = -w + c * CELL;
      pts.push(x, 0.002, -d, x, 0.002, d);
    }
    for (let r = 0; r <= spec.rows; r++) {
      const z = -d + r * CELL;
      pts.push(-w, 0.002, z, w, 0.002, z);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
    return g;
  }, [spec]);
  return (
    <lineSegments geometry={geom}>
      <lineBasicMaterial color="#2c2c33" transparent opacity={0.9} />
    </lineSegments>
  );
};

/* ---------------- Routes, reps, pins ---------------- */

const Route: React.FC<{ points: Pt[]; primary: boolean; reduced: boolean; index: number }> = ({ points, primary, reduced, index }) => {
  const path = useMemo(() => pathFrom(points), [points]);
  const tube = useMemo(() => new THREE.TubeGeometry(path, points.length * 24, primary ? 0.05 : 0.03, 6, false), [path, points.length, primary]);
  const rep = useRef<THREE.Group>(null);
  const total = tube.index ? tube.index.count : 0;
  const start = useRef<number | null>(null);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    if (start.current === null) start.current = t;
    // draw the route in on load, then keep it full
    const drawn = reduced ? 1 : clamp01((t - start.current - index * 0.35) / 1.8);
    tube.setDrawRange(0, Math.floor(ease(drawn) * total));
    if (rep.current) {
      const u = reduced ? 0.35 + index * 0.2 : (t * (primary ? 0.045 : 0.035) + index * 0.31) % 1;
      const p = path.getPointAt(u);
      rep.current.position.set(p.x, 0.16, p.z);
      rep.current.visible = drawn > 0.6;
    }
  });

  return (
    <group>
      <mesh geometry={tube}>
        <meshBasicMaterial color={primary ? ACCENT : INK} transparent opacity={primary ? 1 : 0.38} />
      </mesh>
      <group ref={rep}>
        <mesh>
          <sphereGeometry args={[0.13, 20, 20]} />
          <meshBasicMaterial color={primary ? ACCENT : INK} />
        </mesh>
        <mesh>
          <sphereGeometry args={[0.28, 20, 20]} />
          <meshBasicMaterial color={primary ? ACCENT : INK} transparent opacity={0.14} depthWrite={false} />
        </mesh>
      </group>
    </group>
  );
};

const Pin: React.FC<{ at: Pt; delay: number; reduced: boolean; accent: boolean }> = ({ at, delay, reduced, accent }) => {
  const group = useRef<THREE.Group>(null);
  const ring = useRef<THREE.Mesh>(null);
  const ringMat = useRef<THREE.MeshBasicMaterial>(null);
  const color = accent ? ACCENT : INK;

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    const appear = reduced ? 1 : ease(clamp01((t - 1.6 - delay) / 0.7));
    if (group.current) group.current.scale.setScalar(Math.max(0.0001, appear));
    if (ring.current && ringMat.current) {
      const cycle = reduced ? 0.5 : ((t - delay) % 2.4) / 2.4;
      ring.current.scale.setScalar(1 + cycle * 3.2);
      ringMat.current.opacity = (1 - cycle) * 0.55 * appear;
    }
  });

  return (
    <group position={[at[0], 0, at[1]]}>
      <group ref={group}>
        <mesh position={[0, 0.42, 0]}>
          <cylinderGeometry args={[0.018, 0.018, 0.84, 6]} />
          <meshBasicMaterial color={color} transparent opacity={0.75} />
        </mesh>
        <mesh position={[0, 0.9, 0]}>
          <sphereGeometry args={[0.11, 18, 18]} />
          <meshBasicMaterial color={color} />
        </mesh>
      </group>
      <mesh ref={ring} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
        <ringGeometry args={[0.16, 0.2, 48]} />
        <meshBasicMaterial ref={ringMat} color={color} transparent depthWrite={false} />
      </mesh>
    </group>
  );
};

/* ---------------- Product screens as 3D planes ---------------- */

const Screens: React.FC<{ progress: MutableRefObject<number>; mobile: boolean; reduced: boolean }> = ({ progress, mobile, reduced }) => {
  const dash = useRef<THREE.Group>(null);
  const phone = useRef<THREE.Group>(null);
  const smooth = useRef(0);

  useFrame(({ clock }, dt) => {
    const target = reduced ? 0.55 : progress.current;
    smooth.current = reduced ? target : smooth.current + (target - smooth.current) * Math.min(1, dt * 4);
    const p = smooth.current;
    // 0 → assembled above the map, 1 → separated and laid toward the map
    const sep = ease(clamp01((p - 0.15) / 0.7));
    const bob = reduced ? 0 : Math.sin(clock.getElapsedTime() * 0.8) * 0.08;
    if (dash.current) {
      dash.current.position.set(THREE.MathUtils.lerp(-0.6, -1.6, sep), THREE.MathUtils.lerp(2.5, 1.7, sep) + bob, THREE.MathUtils.lerp(-1.2, -2.6, sep));
      dash.current.rotation.set(THREE.MathUtils.lerp(-0.42, -0.5, sep), THREE.MathUtils.lerp(-0.12, 0.05, sep), 0);
    }
    if (phone.current) {
      phone.current.position.set(
        mobile ? THREE.MathUtils.lerp(0.8, 1.6, sep) : THREE.MathUtils.lerp(2.4, 3.2, sep),
        (mobile ? THREE.MathUtils.lerp(2.6, 2.3, sep) : THREE.MathUtils.lerp(2.3, 1.6, sep)) - bob,
        mobile ? THREE.MathUtils.lerp(-3.4, -2.4, sep) : THREE.MathUtils.lerp(0.2, 1.4, sep),
      );
      phone.current.rotation.set(THREE.MathUtils.lerp(-0.4, -0.3, sep), THREE.MathUtils.lerp(-0.28, -0.42, sep), 0);
    }
  });

  return (
    <>
      {!mobile && (
        <group ref={dash}>
          <Html transform distanceFactor={1.9} pointerEvents="none" zIndexRange={[5, 0]} className="ftl-3d-screen">
            <div className="ftl-3d-dash">
              <DashboardScreen />
            </div>
          </Html>
        </group>
      )}
      <group ref={phone}>
        <Html transform distanceFactor={mobile ? 2.2 : 1.9} pointerEvents="none" zIndexRange={[6, 1]} className="ftl-3d-screen">
          <div className="ftl-3d-phone">
            <PhoneScreen />
          </div>
        </Html>
      </group>
    </>
  );
};

/* ---------------- Camera rig ---------------- */

const CameraRig: React.FC<{ progress: MutableRefObject<number>; reduced: boolean; mobile: boolean }> = ({ progress, reduced, mobile }) => {
  const { camera, pointer } = useThree();
  const smooth = useRef(0);
  const look = useMemo(() => new THREE.Vector3(), []);
  const from = useMemo(() => (mobile ? new THREE.Vector3(0, 17, 15) : new THREE.Vector3(0, 13.5, 15.5)), [mobile]);
  const to = useMemo(() => (mobile ? new THREE.Vector3(3, 9, 11) : new THREE.Vector3(2.4, 8.4, 12.5)), [mobile]);

  useFrame((_, dt) => {
    const target = reduced ? 0.35 : progress.current;
    smooth.current = reduced ? target : smooth.current + (target - smooth.current) * Math.min(1, dt * 3);
    const p = ease(smooth.current);
    camera.position.lerpVectors(from, to, p);
    if (!reduced && !mobile) {
      camera.position.x += pointer.x * 0.8;
      camera.position.y += pointer.y * 0.4;
    }
    look.set(THREE.MathUtils.lerp(mobile ? 0 : 0.4, mobile ? 1.8 : 0.6, p), THREE.MathUtils.lerp(0.4, 0.9, p), THREE.MathUtils.lerp(0, -0.6, p));
    camera.lookAt(look);
  });
  return null;
};

const World: React.FC<Omit<TerritorySceneProps, 'active' | 'onReady'>> = ({ progress, reduced, mobile }) => {
  const spec = mobile ? MAP_MOBILE : MAP_DESKTOP;
  const routes = mobile ? ROUTES_MOBILE : ROUTES_DESKTOP;
  const pins = mobile ? PINS_MOBILE : PINS_DESKTOP;
  return (
    <>
      <fog attach="fog" args={['#09090b', 16, mobile ? 34 : 40]} />
      <ambientLight intensity={0.7} />
      <directionalLight position={[6, 12, 4]} intensity={1.4} color="#fff3e6" />
      <directionalLight position={[-8, 6, -6]} intensity={0.35} color="#9fb4ff" />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.001, 0]}>
        <planeGeometry args={[80, 80]} />
        <meshStandardMaterial color="#0d0d10" roughness={1} />
      </mesh>
      <Roads spec={spec} />
      <Districts spec={spec} />
      {routes.map((r, i) => (
        <Route key={i} points={r} primary={i === 0} reduced={reduced} index={i} />
      ))}
      {pins.map(([ri, vi], i) => (
        <Pin key={i} at={routes[ri][vi]} delay={i * 0.45} reduced={reduced} accent={ri === 0} />
      ))}
      <Screens progress={progress} mobile={mobile} reduced={reduced} />
      <CameraRig progress={progress} reduced={reduced} mobile={mobile} />
    </>
  );
};

/** Lazy-loaded WebGL hero. Rendered on top of the static poster, which it fades over. */
const TerritoryScene: React.FC<TerritorySceneProps> = ({ progress, reduced, mobile, active, onReady }) => (
  <Canvas
    className="ftl-canvas"
    dpr={mobile ? [1, 1.5] : [1, 2]}
    camera={{ fov: 34, near: 0.1, far: 80, position: [0, 13.5, 15.5] }}
    gl={{ antialias: !mobile, alpha: true, powerPreference: 'high-performance' }}
    frameloop={!active ? 'never' : reduced ? 'demand' : 'always'}
    onCreated={() => onReady?.()}
    aria-hidden="true"
  >
    <World progress={progress} reduced={reduced} mobile={mobile} />
  </Canvas>
);

export default TerritoryScene;
