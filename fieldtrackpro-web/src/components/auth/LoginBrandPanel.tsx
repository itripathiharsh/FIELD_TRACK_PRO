import React from 'react';
import { MapPin, Radio, FileText, Image as ImageIcon, BarChart3 } from 'lucide-react';
import phoneMockup from '../../assets/login-phone-mockup.png';
import phoneMockupWebp from '../../assets/login-phone-mockup.webp';

const FEATURES: { icon: React.ElementType; label: string }[] = [
  { icon: MapPin, label: 'GPS based visit verification' },
  { icon: Radio, label: 'Real-time field activity' },
  { icon: FileText, label: 'Digital forms & order capture' },
  { icon: ImageIcon, label: 'Attachments & proof' },
  { icon: BarChart3, label: 'Complete field visibility' },
];

export const BrandLogo: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div className={`flex items-center gap-4 lg:gap-[1.4vw] ${className}`}>
    <div className="w-[52px] h-[52px] lg:w-[3.7vw] lg:h-[3.7vw] lg:min-w-[52px] lg:min-h-[52px] rounded-[14px] bg-[#f9ae03] flex items-center justify-center shrink-0 shadow-[0_6px_18px_rgba(249,174,3,0.35)]">
      <svg
        viewBox="0 0 32 32"
        className="w-[58%] h-[58%]"
        fill="none"
        stroke="#0b2440"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M16 3.5 6 7.2v7.4c0 6.2 4.1 11 10 13.4 5.9-2.4 10-7.2 10-13.4V7.2z" />
        <path d="M16 20.5s-3.6-3.4-3.6-6.1a3.6 3.6 0 0 1 7.2 0c0 2.7-3.6 6.1-3.6 6.1z" />
        <circle cx="16" cy="14.3" r="1.2" fill="#0b2440" stroke="none" />
      </svg>
    </div>
    <div className="lg:pt-[0.7vw]">
      <div className="font-portal font-bold text-white text-[26px] lg:text-[clamp(26px,2vw,38px)] leading-none tracking-tight">
        FieldTrack Pro
      </div>
      <div className="hidden sm:block font-portal text-[10px] lg:text-[clamp(9px,0.62vw,12px)] tracking-[0.27em] text-[#9db0c6] mt-2 whitespace-nowrap">
        FIELD OPERATIONS • VISIBILITY • CONTROL
      </div>
    </div>
  </div>
);

const ROUTE =
  'M-10 882 L140 862 L248 849 L318 783 L340 775 L407 715 L452 650 L478 560 L530 520 L610 420 M868 152 L880 120 L900 42';
const PINS: Array<[number, number]> = [
  [140, 862],
  [407, 735],
  [901, 56],
];

/** Faint map streets + glowing orange route and pins (decorative). */
const RouteArt: React.FC = () => (
  <svg
    className="absolute inset-0 w-full h-full pointer-events-none"
    viewBox="0 0 1672 941"
    preserveAspectRatio="xMinYMid slice"
    aria-hidden="true"
  >
    <defs>
      <radialGradient id="ft-glow" cx="0" cy="1" r="0.6">
        <stop offset="0" stopColor="#ffa31e" stopOpacity="0.55" />
        <stop offset="0.45" stopColor="#ff8a00" stopOpacity="0.14" />
        <stop offset="1" stopColor="#ff8a00" stopOpacity="0" />
      </radialGradient>
      <filter id="ft-blur" x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="5" />
      </filter>
    </defs>
    <rect x="0" y="441" width="620" height="500" fill="url(#ft-glow)" />
    <g stroke="#7fa4cc" strokeOpacity="0.1" strokeWidth="1.2" fill="none">
      <path d="M0 120 L260 90 L520 150 L1000 60" />
      <path d="M-20 300 L180 270 L420 330 L700 250 L1000 290" />
      <path d="M0 520 L220 470 L360 560 L640 500 L1000 560" />
      <path d="M0 700 L260 640 L520 720 L800 660 L1000 700" />
      <path d="M0 860 L300 800 L560 880 L1000 820" />
      <path d="M120 0 L90 260 L170 520 L110 941" />
      <path d="M330 0 L380 300 L310 560 L400 941" />
      <path d="M560 0 L520 340 L600 600 L540 941" />
      <path d="M780 0 L840 300 L760 620 L840 941" />
      <path d="M230 0 L280 200 L200 420 L280 700 L240 941" strokeOpacity="0.06" />
      <path d="M450 0 L430 250 L500 480 L470 941" strokeOpacity="0.06" />
      <path d="M680 0 L700 200 L650 420 L720 700 L690 941" strokeOpacity="0.06" />
      <path d="M0 40 L1000 200" strokeOpacity="0.05" />
      <path d="M0 400 L1000 640" strokeOpacity="0.05" />
      <path d="M0 620 L700 380" strokeOpacity="0.05" />
    </g>
    <g className="max-lg:hidden" fill="none" strokeLinecap="round" strokeLinejoin="round">
      <path d={ROUTE} stroke="#ff9a1a" strokeOpacity="0.55" strokeWidth="6" filter="url(#ft-blur)" />
      <path d={ROUTE} stroke="#ffb02e" strokeWidth="2" />
    </g>
    <g className="max-lg:hidden" fill="#ffb02e">
      <circle cx="478" cy="560" r="5" />
      <circle cx="339" cy="775" r="3.5" />
      <circle cx="452" cy="650" r="3" />
    </g>
    {PINS.map(([x, y]) => (
      <g key={`${x}-${y}`} className="max-lg:hidden" transform={`translate(${x} ${y})`}>
        <ellipse cx="0" cy="2" rx="14" ry="5" fill="#ffa31e" opacity="0.35" />
        <path d="M0 0 C-4 -8 -14 -14 -14 -26 a14 14 0 0 1 28 0 C14 -14 4 -8 0 0z" fill="#ffb02e" />
        <circle cx="0" cy="-26" r="5.5" fill="#0b2440" />
      </g>
    ))}
  </svg>
);

export const LoginBrandPanel: React.FC = () => (
  <div
    className="relative overflow-hidden text-white lg:absolute lg:inset-0"
    style={{ background: 'linear-gradient(115deg,#07182a 0%,#0a2038 45%,#0f2d4d 100%)' }}
  >
    <RouteArt />

    {/* Mobile / tablet compact header */}
    <div className="relative lg:hidden px-6 pt-8 pb-12 md:px-10 md:pt-10 md:pb-10">
      <BrandLogo />
      <h2 className="font-portal font-bold text-[28px] md:text-[40px] leading-[1.12] mt-6 md:mt-8">
        Your Field Team.
        <br />
        <span className="text-[#ffa31e]">Always Connected.</span>
      </h2>
      <p className="hidden md:block font-portal text-lg text-[#c4d1e0] mt-4 max-w-xl">
        Visit verification, live location, field forms and order capture.
      </p>
      <ul className="hidden md:grid grid-cols-2 gap-x-6 gap-y-3 mt-8">
        {FEATURES.map(({ icon: Icon, label }) => (
          <li key={label} className="flex items-center gap-3 font-portal text-base text-[#e6edf5]">
            <span className="w-10 h-10 rounded-lg bg-[#1c2b3d] flex items-center justify-center shrink-0">
              <Icon className="w-5 h-5" aria-hidden="true" />
            </span>
            {label}
          </li>
        ))}
      </ul>
    </div>

    {/* Desktop: sized in vw so the composition tracks the 1672x941 design */}
    <div className="hidden lg:block relative h-full">
      <BrandLogo className="absolute left-[3.17vw] top-[3.17vw]" />
      <div className="absolute left-[3.45vw] top-[11.3vw] w-[30vw] z-10">
        <h2 className="font-portal font-bold text-[clamp(32px,3.02vw,60px)] leading-[1.22] tracking-[-0.01em] whitespace-nowrap">
          Your Field Team.
          <br />
          <span className="text-[#ffa31e]">Always Connected.</span>
        </h2>
        <p className="font-portal text-[clamp(16px,1.55vw,30px)] leading-[1.4] text-[#b9c6d6] mt-[1.4vw] max-w-[24vw]">
          Visit verification, live location, field forms and order capture.
        </p>
        <ul className="mt-[1.9vw] space-y-[0.76vw]">
          {FEATURES.map(({ icon: Icon, label }) => (
            <li
              key={label}
              className="flex items-center gap-[1.4vw] font-portal text-[clamp(14px,1.1vw,21px)] text-[#e6edf5]"
            >
              <span className="w-[3.1vw] h-[3.1vw] min-w-[40px] min-h-[40px] rounded-[0.7vw] bg-[#1c2b3d] flex items-center justify-center shrink-0">
                <Icon className="w-[1.35vw] h-[1.35vw] min-w-[18px] min-h-[18px]" aria-hidden="true" />
              </span>
              {label}
            </li>
          ))}
        </ul>
      </div>
      {/* Lossless WebP (~37% smaller, pixel-identical) with the original PNG as fallback. */}
      <picture>
        <source srcSet={phoneMockupWebp} type="image/webp" />
        <img
          src={phoneMockup}
          alt="FieldTrack Pro mobile app: Visit Details screen"
          className="absolute left-[30.4vw] top-[8.2%] w-[21.95vw] z-0 h-auto drop-shadow-[0_30px_40px_rgba(0,0,0,0.45)] select-none"
          draggable={false}
        />
      </picture>
    </div>
  </div>
);
