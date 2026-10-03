import type { ReactNode } from 'react'

/**
 * Hover (and keyboard focus / tap) tooltip with rich content.
 * The trigger is focusable so it also works with a keyboard and on touch screens.
 */
export default function Tooltip({ children, content, label }: { children: ReactNode; content: ReactNode; label?: string }) {
  return (
    <span className="tip" tabIndex={0} aria-label={label}>
      <span className="tip-trigger">{children}</span>
      <span className="tip-body" role="tooltip">
        {content}
      </span>
    </span>
  )
}
