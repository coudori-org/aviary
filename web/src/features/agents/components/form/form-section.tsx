import * as React from "react";

interface FormSectionProps {
  title: string;
  description: string;
  children: React.ReactNode;
}

/**
 * Consistent header + body wrapper used by every form section so spacing
 * and typography stay in lockstep with the Slate design system.
 */
export function FormSection({ title, description, children }: FormSectionProps) {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="t-h3 fg-primary">{title}</h2>
        <p className="t-small fg-tertiary mt-1">{description}</p>
      </div>
      {children}
    </section>
  );
}
