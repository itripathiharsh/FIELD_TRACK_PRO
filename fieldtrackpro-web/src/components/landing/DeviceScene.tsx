import React, { useEffect, useRef } from 'react';
import { BarChart3, ClipboardList, MapPin, Users } from 'lucide-react';
import { DashboardScreen } from './Mockups';

/** Pie chart with real depth: the same conic-gradient disc stacked in Z. */
const Pie3D: React.FC = () => (
  <div className="ftl-pie" aria-hidden="true">
    {Array.from({ length: 12 }, (_, i) => (
      <span key={i} className={i === 11 ? 'is-top' : ''} style={{ '--z': `${i * 2}px` } as React.CSSProperties} />
    ))}
    {Array.from({ length: 12 }, (_, i) => (
      <span
        key={`s${i}`}
        className={`ftl-pie-slice${i === 11 ? ' is-top' : ''}`}
        style={{ '--z': `${i * 2 + 10}px` } as React.CSSProperties}
      />
    ))}
  </div>
);

/**
 * Hero 3D scene: a laptop showing the admin dashboard on a glowing pedestal, with glossy
 * floating tiles and a 3D pie chart. Pointer and scroll parallax are written to CSS
 * variables in a rAF loop. With reduced motion nothing moves and no listeners attach.
 */
const DeviceScene: React.FC<{ reduced: boolean }> = ({ reduced }) => {
  const sceneRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = sceneRef.current;
    if (!el || reduced) return;
    let tx = 0;
    let ty = 0;
    let cx = 0;
    let cy = 0;
    let frame = 0;
    const finePointer = window.matchMedia?.('(pointer: fine)').matches ?? true;

    const tick = () => {
      cx += (tx - cx) * 0.07;
      cy += (ty - cy) * 0.07;
      const sp = Math.min(1, window.scrollY / Math.max(1, window.innerHeight));
      el.style.setProperty('--rx', cy.toFixed(3));
      el.style.setProperty('--ry', cx.toFixed(3));
      el.style.setProperty('--sp', sp.toFixed(3));
      frame = Math.abs(tx - cx) > 0.001 || Math.abs(ty - cy) > 0.001 ? requestAnimationFrame(tick) : 0;
    };
    const kick = () => {
      if (!frame) frame = requestAnimationFrame(tick);
    };
    const onMove = (e: PointerEvent) => {
      if (!finePointer) return;
      tx = (e.clientX / window.innerWidth) * 2 - 1;
      ty = (e.clientY / window.innerHeight) * 2 - 1;
      kick();
    };
    const onLeave = () => {
      tx = 0;
      ty = 0;
      kick();
    };
    kick();
    window.addEventListener('pointermove', onMove, { passive: true });
    document.addEventListener('pointerleave', onLeave);
    window.addEventListener('scroll', kick, { passive: true });
    return () => {
      window.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerleave', onLeave);
      window.removeEventListener('scroll', kick);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [reduced]);

  return (
    <div ref={sceneRef} className="ftl-scene" role="img" aria-label="FieldTrack Pro admin dashboard on a laptop">
      <div className="ftl-stage">
        <div className="ftl-pedestal" aria-hidden="true">
          <span className="ftl-pedestal-top" />
          <span className="ftl-pedestal-rim" />
        </div>

        <div className="ftl-laptop">
          <div className="ftl-lid">
            <div className="ftl-lid-bezel">
              <DashboardScreen />
              <span className="ftl-glare" />
            </div>
          </div>
          <div className="ftl-deck" aria-hidden="true">
            <span className="ftl-keys" />
            <span className="ftl-pad" />
          </div>
        </div>

        <div className="ftl-tile ftl-tile--team" aria-hidden="true">
          <Users />
        </div>
        <div className="ftl-tile ftl-tile--chart" aria-hidden="true">
          <BarChart3 />
        </div>
        <div className="ftl-tile ftl-tile--pin" aria-hidden="true">
          <MapPin />
        </div>
        <div className="ftl-tile ftl-tile--clip" aria-hidden="true">
          <ClipboardList />
        </div>
        <Pie3D />
      </div>
    </div>
  );
};

export default DeviceScene;
