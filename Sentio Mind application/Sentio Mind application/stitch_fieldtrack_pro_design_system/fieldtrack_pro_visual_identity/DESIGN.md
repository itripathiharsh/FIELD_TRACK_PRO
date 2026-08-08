---
name: FieldTrack Pro Visual Identity
colors:
  surface: '#fbf8fb'
  surface-dim: '#dbd9dc'
  surface-bright: '#fbf8fb'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f5f3f6'
  surface-container: '#f0edf0'
  surface-container-high: '#eae7ea'
  surface-container-highest: '#e4e2e5'
  on-surface: '#1b1b1e'
  on-surface-variant: '#45464d'
  inverse-surface: '#303033'
  inverse-on-surface: '#f2f0f3'
  outline: '#75777e'
  outline-variant: '#c5c6ce'
  surface-tint: '#525e7d'
  primary: '#000a24'
  on-primary: '#ffffff'
  primary-container: '#14213d'
  on-primary-container: '#7c89aa'
  inverse-primary: '#b9c6ea'
  secondary: '#855300'
  on-secondary: '#ffffff'
  secondary-container: '#ffa515'
  on-secondary-container: '#684000'
  tertiary: '#130900'
  on-tertiary: '#ffffff'
  tertiary-container: '#321d00'
  on-tertiary-container: '#a58359'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d9e2ff'
  primary-fixed-dim: '#b9c6ea'
  on-primary-fixed: '#0d1b36'
  on-primary-fixed-variant: '#3a4664'
  secondary-fixed: '#ffddb8'
  secondary-fixed-dim: '#ffb95f'
  on-secondary-fixed: '#2a1700'
  on-secondary-fixed-variant: '#653e00'
  tertiary-fixed: '#ffddb6'
  tertiary-fixed-dim: '#e7c092'
  on-tertiary-fixed: '#2a1800'
  on-tertiary-fixed-variant: '#5c421e'
  background: '#fbf8fb'
  on-background: '#1b1b1e'
  surface-variant: '#e4e2e5'
typography:
  headline-lg:
    fontFamily: League Spartan
    fontSize: 32px
    fontWeight: '700'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: League Spartan
    fontSize: 24px
    fontWeight: '700'
    lineHeight: '1.2'
  headline-md:
    fontFamily: League Spartan
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.3'
  headline-sm:
    fontFamily: League Spartan
    fontSize: 20px
    fontWeight: '600'
    lineHeight: '1.3'
  body-lg:
    fontFamily: Libre Baskerville
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.6'
  body-md:
    fontFamily: Libre Baskerville
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
  label-md:
    fontFamily: League Spartan
    fontSize: 14px
    fontWeight: '600'
    lineHeight: '1'
    letterSpacing: 0.05em
  button:
    fontFamily: League Spartan
    fontSize: 16px
    fontWeight: '700'
    lineHeight: '1'
  nav-link:
    fontFamily: League Spartan
    fontSize: 15px
    fontWeight: '500'
    lineHeight: '1'
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  base: 8px
  gutter: 24px
  margin: 32px
  container-max: 1440px
---

## Brand & Style
This design system adopts a **Corporate Modern** aesthetic with **Minimalist** efficiency, specifically tailored for field management and industrial logistics. The brand personality is authoritative, precise, and dependable. 

The visual narrative relies on high-contrast color blocking to separate navigation from content, using deep navy surfaces to anchor the experience. Interaction is driven by high-visibility accents, ensuring that critical path actions and status indicators are unmistakable in high-pressure environments. The style avoids unnecessary decoration, focusing instead on structural integrity and legibility.

## Colors
The palette is architectural and functional. 

- **Primary (#14213D):** This navy is the structural foundation. Use it for the sidebar, top navigation bars, large header sections, and primary surface containers.
- **Accent (#FCA311):** Use this yellow/gold exclusively for high-priority interaction points: Primary CTAs, active selection states, progress bars, and focus rings. 
- **Neutrals:** Use #000000 for primary body text on light backgrounds. #E5E5E5 serves as the background for the main content area to provide a subtle distinction from white cards. #FFFFFF is reserved for card surfaces and secondary button backgrounds.

## Typography
The typographic system utilizes a "Workhorse and Scholar" pairing. 

- **League Spartan** provides the industrial, geometric strength required for headers, navigation, buttons, and data labels. Its bold weights should be used for all UI scaffolding.
- **Libre Baskerville** is used for secondary text, descriptions, and supporting narrative content. This serif choice adds a layer of traditional authority and improves long-form readability.

All UI labels and buttons must use uppercase Spartan to maintain a disciplined, "pro" feel.

## Layout & Spacing
This design system follows a rigid **Fixed Grid** model to ensure stability in data-dense views.

- **Grid:** 12-column system for desktop with 24px gutters.
- **Margins:** 32px safe-area margins for desktop; 16px for mobile.
- **Rhythm:** All vertical spacing must be a multiple of 8px. Use 16px for tight groupings and 32px-48px for section separation.
- **Sidebar:** Fixed width of 280px, utilizing the Primary Navy color for its entire height.

## Elevation & Depth
Depth is created through **Tonal Layering** and **Low-contrast Outlines** rather than heavy shadows.

- **Base Layer:** #E5E5E5 (Light Gray) background.
- **Surface Layer:** #FFFFFF (White) cards with a 1px border of #D1D1D1. No shadows on static cards.
- **Interaction Layer:** Use a subtle, tight shadow (0px 4px 12px rgba(0,0,0,0.08)) only for hovered elements or modals to indicate temporary elevation.
- **Sidebar:** Flat Primary Navy, using #FCA311 as a left-border "indicator" for active navigation states.

## Shapes
The shape language is "Soft" yet disciplined. Standard UI components like buttons and input fields use a 0.25rem (4px) radius. Larger containers and cards use a 0.5rem (8px) radius. This minimal rounding maintains the professional, industrial feel while preventing the UI from feeling sharp or aggressive.

## Components
- **Buttons:** Primary buttons use #FCA311 background with #000000 text for maximum contrast. Secondary buttons use a #14213D outline with no fill. All buttons use League Spartan Bold in Uppercase.
- **Chips/Badges:** Status badges use a light tint of the status color with a 1px solid border of the same color. 
- **Input Fields:** 1px border (#D1D1D1) that turns Primary Navy on focus. Labels sit above the field in League Spartan (Small/Bold/Uppercase).
- **Cards:** White backgrounds, 8px corner radius, 1px light gray border. Headers within cards should have a subtle bottom divider.
- **Data Tables:** Headers in Primary Navy with White text (League Spartan). Rows alternate with a very light gray (#F9F9F9) for zebra striping to maintain legibility in large data sets.
- **Sidebar Links:** White text on Navy background. Active state: #FCA311 text or a 4px left-border highlight in #FCA311.