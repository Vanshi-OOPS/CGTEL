import type { SVGProps } from 'react';

export type IconName = 'overview' | 'desk' | 'ledger' | 'policy' | 'benchmark' | 'arrow' | 'refresh' | 'search' | 'shield' | 'activity';

const paths: Record<IconName, React.ReactNode> = {
  overview: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></>,
  desk: <><path d="M4 5.5h16v11H4z"/><path d="M8 20h8M12 16.5V20M7 9h5M7 12.5h9"/></>,
  ledger: <><path d="M7 4h13v16H7z"/><path d="M4 7v13h13M10 8h6M10 12h6M10 16h4"/></>,
  policy: <><path d="M12 3 20 6v5c0 5-3.4 8.4-8 10-4.6-1.6-8-5-8-10V6z"/><path d="m9 12 2 2 4-4"/></>,
  benchmark: <><path d="M4 19V5M4 19h17"/><path d="m7 15 4-4 3 2 6-7"/><circle cx="20" cy="6" r="1"/></>,
  arrow: <><path d="M5 12h14M13 6l6 6-6 6"/></>,
  refresh: <><path d="M20 7v5h-5M4 17v-5h5"/><path d="M5.7 9a7 7 0 0 1 11.6-2L20 12M4 12l2.7 5a7 7 0 0 0 11.6-2"/></>,
  search: <><circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 4.5 4.5"/></>,
  shield: <><path d="M12 3 20 6v5c0 5-3.4 8.4-8 10-4.6-1.6-8-5-8-10V6z"/><path d="M9 12h6"/></>,
  activity: <><path d="M3 12h4l3-7 4 14 3-7h4"/></>,
};

export function Icon({ name, size = 18, ...props }: SVGProps<SVGSVGElement> & { name: IconName; size?: number }) {
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" {...props}>{paths[name]}</svg>;
}
