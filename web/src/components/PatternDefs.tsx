/**
 * SVG pattern definitions used globally for hatching fills.
 * Rendered once at the top of the app.
 */
export function PatternDefs() {
  return (
    <svg
      width="0"
      height="0"
      style={{ position: 'absolute' }}
      aria-hidden="true"
    >
      <defs>
        {/* Diagonal hatch - LOG_AND_MONITOR / ochre */}
        <pattern
          id="hatch-diagonal"
          width="6"
          height="6"
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(45)"
        >
          <rect width="6" height="6" fill="var(--ochre)" />
          <line
            x1="0"
            y1="0"
            x2="0"
            y2="6"
            stroke="var(--paper)"
            strokeWidth="2"
          />
        </pattern>

        {/* Dense cross-hatch - HUMAN_REVIEW / vermilion */}
        <pattern
          id="hatch-cross"
          width="6"
          height="6"
          patternUnits="userSpaceOnUse"
        >
          <rect width="6" height="6" fill="var(--vermilion)" />
          <line
            x1="0"
            y1="0"
            x2="6"
            y2="6"
            stroke="var(--paper)"
            strokeWidth="1"
          />
          <line
            x1="6"
            y1="0"
            x2="0"
            y2="6"
            stroke="var(--paper)"
            strokeWidth="1"
          />
        </pattern>

        {/* Dotted pattern - for failure rate bar segment */}
        <pattern
          id="hatch-dots"
          width="4"
          height="4"
          patternUnits="userSpaceOnUse"
        >
          <rect width="4" height="4" fill="var(--ink)" />
          <circle cx="2" cy="2" r="0.8" fill="var(--paper)" />
        </pattern>

        {/* Diagonal hatch - ink colored (for contribution bar confidence gap) */}
        <pattern
          id="hatch-diagonal-ink"
          width="6"
          height="6"
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(45)"
        >
          <rect width="6" height="6" fill="var(--ink-soft)" />
          <line
            x1="0"
            y1="0"
            x2="0"
            y2="6"
            stroke="var(--paper)"
            strokeWidth="2"
          />
        </pattern>

        {/* Roughen filter for stamps */}
        <filter id="roughen">
          <feTurbulence
            type="turbulence"
            baseFrequency="0.04"
            numOctaves="4"
            result="noise"
          />
          <feDisplacementMap
            in="SourceGraphic"
            in2="noise"
            scale="2"
            xChannelSelector="R"
            yChannelSelector="G"
          />
        </filter>
      </defs>
    </svg>
  );
}
