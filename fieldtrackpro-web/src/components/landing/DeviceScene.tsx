import React, { useEffect, useRef } from 'react';
import { CheckCircle2, IndianRupee, RefreshCw } from 'lucide-react';
import { DesktopScreen, PhoneScreen } from './Mockups';

/**
 * Hero 3D scene: a desktop monitor and a phone built with CSS 3D transforms.
 * The stage follows the pointer and flattens as the page scrolls. Motion is written
 * to CSS variables in a rAF loop, never through React state. With reduced motion the
 * scene renders at a fixed angle and no listeners are attached.
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
      // Ease toward the pointer target for a smooth, weighty feel.
      cx += (tx - cx) * 0.08;
      cy += (ty - cy) * 0.08;
      const scrollP = Math.min(1, window.scrollY / Math.max(1, window.innerHeight));
      el.style.setProperty('--rx', cy.toFixed(3));
      el.style.setProperty('--ry', cx.toFixed(3));
      el.style.setProperty('--sp', scrollP.toFixed(3));
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
    <div
      ref={sceneRef}
      className="ftl-scene"
      role="img"
      aria-label="FieldTrack Pro on a desktop dashboard and on an Android phone"
    >
      <div className="ftl-stage">
        <div className="ftl-desktop">
          <div className="ftl-desktop-bezel">
            <DesktopScreen />
            <span className="ftl-glare" />
          </div>
          <div className="ftl-desktop-neck" />
          <div className="ftl-desktop-base" />
        </div>

        <div className="ftl-phone">
          <div className="ftl-phone-body">
            <PhoneScreen />
            <span className="ftl-glare" />
          </div>
        </div>

        <div className="ftl-chip ftl-chip--1">
          <CheckCircle2 aria-hidden="true" />
          <div>
            <b>Check-in verified</b>
            <span>Inside geofence · 12 m</span>
          </div>
        </div>
        <div className="ftl-chip ftl-chip--2">
          <IndianRupee aria-hidden="true" />
          <div>
            <b>₹ 48,200 collected</b>
            <span>UPI · receipt attached</span>
          </div>
        </div>
        <div className="ftl-chip ftl-chip--3">
          <RefreshCw aria-hidden="true" />
          <div>
            <b>Synced to Tally</b>
            <span>Voucher matched</span>
          </div>
        </div>
      </div>
      <div className="ftl-floor" aria-hidden="true" />
    </div>
  );
};

export default DeviceScene;
