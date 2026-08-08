---
name: FieldTrack Pro
colors:
  surface: '#FFFFFF'
  surface-dim: '#d8dadf'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3f9'
  surface-container: '#eceef3'
  surface-container-high: '#e6e8ed'
  surface-container-highest: '#e1e2e8'
  on-surface: '#191c20'
  on-surface-variant: '#3d4943'
  inverse-surface: '#2e3135'
  inverse-on-surface: '#eff0f6'
  outline: '#6d7a73'
  outline-variant: '#bccac1'
  surface-tint: '#006c4e'
  primary: '#00694c'
  on-primary: '#ffffff'
  primary-container: '#008560'
  on-primary-container: '#f5fff7'
  inverse-primary: '#68dbae'
  secondary: '#0060a8'
  on-secondary: '#ffffff'
  secondary-container: '#5da9fe'
  on-secondary-container: '#003d6d'
  tertiary: '#7d5400'
  on-tertiary: '#ffffff'
  tertiary-container: '#9d6a00'
  on-tertiary-container: '#fffbff'
  error: '#E24B4A'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#86f8c9'
  primary-fixed-dim: '#68dbae'
  on-primary-fixed: '#002115'
  on-primary-fixed-variant: '#00513a'
  secondary-fixed: '#d2e4ff'
  secondary-fixed-dim: '#a1c9ff'
  on-secondary-fixed: '#001c38'
  on-secondary-fixed-variant: '#004880'
  tertiary-fixed: '#ffddb0'
  tertiary-fixed-dim: '#fcbb4f'
  on-tertiary-fixed: '#281800'
  on-tertiary-fixed-variant: '#614000'
  background: '#F7F8F9'
  on-background: '#191c20'
  surface-variant: '#e1e2e8'
  primary-tint: '#EAF7F1'
  secondary-tint: '#EAF3FC'
  warning-tint: '#FFF6E5'
  error-tint: '#FDECEC'
  border-subtle: '#EDEFF2'
  text-muted: '#8A919C'
typography:
  display:
    fontFamily: Inter
    fontSize: 36px
    fontWeight: '700'
    lineHeight: '1.2'
  h1:
    fontFamily: Inter
    fontSize: 30px
    fontWeight: '700'
    lineHeight: '1.25'
  h2:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.3'
  h3:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: '1.35'
  body:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.5'
  body-emphasis:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: '1.5'
  caption:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.4'
  micro:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: '1.3'
    letterSpacing: 0.02em
  h1-mobile:
    fontFamily: Roboto
    fontSize: 28px
    fontWeight: '700'
    lineHeight: '1.25'
  h2-mobile:
    fontFamily: Roboto
    fontSize: 22px
    fontWeight: '600'
    lineHeight: '1.3'
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  space-1: 4px
  space-2: 8px
  space-3: 12px
  space-4: 16px
  space-6: 24px
  space-8: 32px
  space-12: 48px
---

## Brand & Style

The design system is built on a foundation of **"explainable over enforced"** design, prioritizing trust and professional clarity. It serves as a reliable infrastructure for field operations, moving away from clinical or accusatory aesthetics toward a helpful, non-judgmental partnership between the tool and the user.

The visual style is **Corporate / Modern**, leaning heavily into systematic reliability. It utilizes a balanced mix of platform-native patterns (Material 3 and shadcn) to ensure the interface feels "boring but dependable"—a feature that reduces cognitive load in high-stakes field environments. The UI avoids excessive decoration, focusing instead on high legibility, functional elevation, and clear semantic mapping of status and data.

## Colors

The palette is driven by semantic honesty. **Primary Teal** is the core brand and action color, representing success and movement. **Secondary Blue** handles informational accents and navigation. A critical distinction is made for the **Warning/Flagged Amber**; this color is used for review states to avoid the "accusatory" nature of red, which is reserved strictly for **Error Red** (critical failures or destructive actions).

The color system uses a "tint-and-text" model for status indicators. Light surface tints (e.g., `#EAF7F1`) are paired with high-contrast text or icons of the parent hue to ensure maximum readability and accessibility. The neutral scale is optimized for information density, using soft grays for borders and secondary meta-data to maintain a calm visual hierarchy.

## Typography

Typography follows a platform-native approach: **Inter** for Web/Dashboard and **Roboto** for Android. The scale is built on a geometric progression with a strict 12px (or 12sp) floor to ensure legibility in varied field lighting conditions.

- **Headlines:** Use higher weights (600-700) to anchor page sections and titles.
- **Body Text:** Standardized at 16px to ensure a comfortable reading rhythm for technical documentation.
- **Micro Typography:** Used for table headers (often uppercased) and status badges.
- **Android Adaptation:** When rendering on mobile, font sizes are adjusted to the `sp` equivalents defined in the variables to respect system-level scaling settings.

## Layout & Spacing

This design system employs a **fluid grid** model with platform-specific adjustments. The underlying rhythm is based on a **4px base unit**.

- **Web Dashboard:** Utilizes a 12-column grid for the main content area (max-width 1280px) with a fixed 240px sidebar. Gutter spacing is typically set at `space-6` (24px).
- **Mobile (Android):** Shifts to a single-column linear layout with `space-4` (16px) standard horizontal margins.
- **Touch Targets:** A strict minimum of 48dp (48px) is enforced for all interactive elements on mobile to ensure usability for workers in the field.
- **Rhythm:** `space-2` is the standard for internal element padding (like inputs), while `space-4` serves as the default for container padding.

## Elevation & Depth

Elevation is used functionally to communicate the "interactive weight" of an object rather than for aesthetic flair. The system uses a range of 0–4dp (or equivalent shadows).

- **Flat (Elevation 0):** Used for the primary canvas and standard list items that do not require individual focus.
- **Resting Cards (Elevation 1):** Provides a subtle lift for visit cards and employee rows to distinguish them from the background.
- **Interactive Focus (Elevation 2):** Applied during hover states or for dropdown menus to indicate active engagement.
- **Overlays (Elevation 3 & 4):** Reserved for modals, dialogs, and high-priority "Toasts" or "Snackbars" that require immediate user attention.
- **Shadow Quality:** Shadows are low-opacity and neutral-tinted, ensuring they don't muddy the clean, professional appearance of the interface.

## Shapes

The shape language varies based on the component's role in the hierarchy, generally following a "Rounded" (8px base) philosophy.

- **Inputs & Small Buttons:** Use an 8px radius (`radius-md`) for a professional, modern look.
- **Cards & Modals:** Use a 12px radius (`radius-lg`) to provide a softer, more approachable container for complex data.
- **Badges & FABs:** Use a "Full" (9999px) pill shape. This distinguishes status indicators and primary action buttons (like "Start Visit") from structural UI elements.
- **Borders:** Containers use a 1px solid border in `neutral-100` as the primary separator, ensuring a clean, lightweight layout.

## Components

### Buttons
Primary buttons use the Brand Teal (`primary-500`) with white text and 8px corners. Secondary buttons use the Blue (`secondary-500`) or a ghost variant with the Teal tint for hover states. All mobile buttons must meet the 48px touch target height.

### Status Badges (Chips)
Badges are pill-shaped (full radius). They follow strict semantic mapping:
- **Success/Completed:** Teal tint background with dark teal text.
- **In-Progress:** Blue tint background with dark blue text.
- **Flagged:** Amber tint background with dark amber text.
- **Missed/Inactive:** Dark gray (`neutral-500`) tint with neutral-900 text.

### Input Fields
Inputs use an 8px radius and a 1px `neutral-300` border. Upon focus, the border increases to 2px and changes to the `secondary-500` Blue. Labels should always be visible (no floating labels) to ensure clarity.

### Cards
Cards are the primary container for field data. They feature a 12px radius, a 1px `neutral-100` border, and Level 1 elevation. Internal padding is standardized to `space-4` (16px).

### Lists
Flat list rows should be separated by 1px `neutral-100` dividers. On hover, the row background shifts to `neutral-50`.

### Iconography
- **Web:** Lucide icons with a 2px stroke.
- **Android:** Material Symbols (Rounded) with a 1.5px stroke.
- **Usage:** Icons are always paired with labels for critical actions to ensure the "explainable" design mandate is met.