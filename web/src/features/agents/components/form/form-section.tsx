import * as React from "react";

interface FormSectionProps {
  title: string;
  description: string;
  children: React.ReactNode;
}

/**
 * FormSection — consistent header + body wrapper used by every form
 * section so spacing and typography stay in lockstep.
 */
export function FormSection({ title, description, children }: FormSectionProps) {
  return (
    <section className="space-y-5">
      <div>
        <h2 className="type-button text-fg-primary">{title}</h2>
        <p className="type-caption text-fg-muted mt-1">{description}</p>
      </div>
      {children}
    </section>
  );
}
