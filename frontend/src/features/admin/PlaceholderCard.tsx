/**
 * Placeholder card used by the admin shell's section pages while their
 * dedicated implementations land in follow-up issues. Each card surfaces
 * the title + a one-line description + a link to the GitHub issue.
 */
import type { ReactNode } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface PlaceholderCardProps {
  title: string;
  description: string;
  issueNumber: number;
  children?: ReactNode;
}

const REPO = "ganjasan/fastsaas";

export function PlaceholderCard({
  title,
  description,
  issueNumber,
  children,
}: PlaceholderCardProps): ReactNode {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </header>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Coming soon</CardTitle>
          <CardDescription>
            This surface lands in{" "}
            <a
              href={`https://github.com/${REPO}/issues/${issueNumber}`}
              target="_blank"
              rel="noreferrer"
              className="text-primary underline-offset-4 hover:underline"
            >
              issue #{issueNumber}
            </a>
            . The sidebar nav + auth gate are wired today; the page content fills in when that issue
            ships.
          </CardDescription>
        </CardHeader>
        {children ? <CardContent>{children}</CardContent> : null}
      </Card>
    </div>
  );
}
